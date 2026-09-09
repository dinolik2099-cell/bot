#!/usr/bin/env python3
"""Replay frozen N11 survivors to canonical TRAIN/VALIDATION series diagnostics."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quantbot.research.artifact_store import read_verified_json, canonical_json
from quantbot.research.canonical_data_adapter import make_n8_canonical_window_loader
from quantbot.research.non_oos_series import (
    Candidate,
    retained_candidates,
    replay_candidate, replay_candidate_group,
    metrics_match,
    series_metadata,
    build_diagnostic_artifact,
    validate_diagnostic_artifact,
)
from scripts.run_formal_train_validation import (
    RAW_ROOT, PLAN, load_formal_context, make_strategy_resolver, engine_factory,
)

N11 = ROOT / "data/reports/formal_runs/N11_FORMAL_TRAIN_VALIDATION_RESULT.json"
DEFAULT_ROOT = ROOT / "data/reports/non_oos_series_n12"
_G = {}


def _thread_limits():
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[key] = "1"


def _init_worker():
    _thread_limits()
    n7, n8 = load_formal_context()
    expected = [row["model_id"] for row in n7.plan["models"]]
    _G["n7"] = n7
    _G["loader"] = make_n8_canonical_window_loader(n8, RAW_ROOT)
    _G["resolver"] = make_strategy_resolver(expected)


def _candidate_from_dict(row):
    return Candidate(**row)


def _candidate_dict(c):
    return {
        "candidate_identity": c.candidate_identity,
        "validation_result_identity": c.validation_result_identity,
        "selected_train_result_identity": c.selected_train_result_identity,
        "task_identity": c.task_identity,
        "model_id": c.model_id,
        "family": c.family,
        "symbol": c.symbol,
        "params": c.params,
        "train_metrics": c.train_metrics,
        "validation_metrics": c.validation_metrics,
    }


def _work_group(rows):
    candidates = [_candidate_from_dict(row) for row in rows]
    return replay_candidate_group(
        candidates, n7=_G["n7"], window_loader=_G["loader"],
        strategy_resolver=_G["resolver"], engine_factory=engine_factory,
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _pairwise_corr(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.corr(min_periods=2)


def _summary_from_values(values: np.ndarray):
    values = values[np.isfinite(values)]
    if not len(values):
        return {"finite_pairs": 0, "mean": None, "median": None, "p90": None, "ge_0_90": 0, "ge_0_98": 0}
    return {
        "finite_pairs": int(len(values)),
        "mean": float(np.mean(values)), "median": float(np.median(values)),
        "p90": float(np.quantile(values, 0.90)),
        "ge_0_90": int(np.sum(values >= 0.90)), "ge_0_98": int(np.sum(values >= 0.98)),
    }


def _group_summaries(candidates, corr: pd.DataFrame):
    ids = [c.candidate_identity for c in candidates]
    by_id = {c.candidate_identity: c for c in candidates}
    families = sorted({c.family for c in candidates})
    symbols = sorted({c.symbol for c in candidates})
    out = {"family_internal": {}, "symbol_internal": {}, "relation_types": {}}
    for family in families:
        members = [x for x in ids if by_id[x].family == family]
        sub = corr.loc[members, members].to_numpy()
        vals = sub[np.triu_indices(len(members), 1)] if len(members) > 1 else np.array([])
        out["family_internal"][family] = {"candidates": len(members), **_summary_from_values(vals)}
    for symbol in symbols:
        members = [x for x in ids if by_id[x].symbol == symbol]
        sub = corr.loc[members, members].to_numpy()
        vals = sub[np.triu_indices(len(members), 1)] if len(members) > 1 else np.array([])
        out["symbol_internal"][symbol] = {"candidates": len(members), **_summary_from_values(vals)}

    buckets = {
        "same_model_same_symbol_different_params": [],
        "same_model_cross_symbol": [],
        "same_family_different_model": [],
        "cross_family": [],
    }
    for i, a in enumerate(ids):
        ca = by_id[a]
        for b in ids[i + 1:]:
            cb = by_id[b]; v = corr.at[a, b]
            if not np.isfinite(v): continue
            if ca.model_id == cb.model_id and ca.symbol == cb.symbol:
                buckets["same_model_same_symbol_different_params"].append(v)
            elif ca.model_id == cb.model_id and ca.symbol != cb.symbol:
                buckets["same_model_cross_symbol"].append(v)
            elif ca.family == cb.family and ca.model_id != cb.model_id:
                buckets["same_family_different_model"].append(v)
            elif ca.family != cb.family:
                buckets["cross_family"].append(v)
    for key, values in buckets.items():
        out["relation_types"][key] = _summary_from_values(np.asarray(values, dtype=float))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=max(1, min(12, (os.cpu_count() or 2) // 2)))
    ap.add_argument("--limit", type=int, default=None, help="Smoke only; omitted means all retained candidates.")
    ap.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    args = ap.parse_args()
    if args.workers < 1 or args.workers > 16: raise SystemExit("workers must be 1..16")

    package = read_verified_json(N11)
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    candidates = retained_candidates(package, plan)
    if len(candidates) != 724:
        raise RuntimeError(f"retained_candidate_count_mismatch:{len(candidates)}")
    selected = candidates[:args.limit] if args.limit is not None else candidates
    output = args.output_root.resolve(); series_dir = output / "series"
    output.mkdir(parents=True, exist_ok=True); series_dir.mkdir(parents=True, exist_ok=True)

    results = {}; failures = []
    grouped = {}
    for c in selected:
        grouped.setdefault(c.task_identity, []).append(_candidate_dict(c))
    groups = [grouped[key] for key in sorted(grouped)]
    if args.workers == 1:
        _init_worker()
        for group in groups:
            try:
                results.update(_work_group(group))
            except Exception as exc:
                failures.append({"task_identity": group[0]["task_identity"], "error_type": type(exc).__name__, "error_message": str(exc)})
    else:
        import multiprocessing
        ctx = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=args.workers, mp_context=ctx, initializer=_init_worker) as pool:
            future_map = {pool.submit(_work_group, group): group[0]["task_identity"] for group in groups}
            for future in as_completed(future_map):
                task_id = future_map[future]
                try:
                    results.update(future.result())
                except Exception as exc:
                    failures.append({"task_identity": task_id, "error_type": type(exc).__name__, "error_message": str(exc)})
    if failures:
        (output / "FAILURES.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
        raise RuntimeError(f"replay_failures:{len(failures)}")

    replay_mismatches = []; manifest_rows = []; validation_series = {}
    by_id = {c.candidate_identity: c for c in selected}
    for cid in sorted(results):
        c = by_id[cid]; both = results[cid]
        for window, expected in (("TRAIN", c.train_metrics), ("VALIDATION", c.validation_metrics)):
            if not metrics_match(both[window]["metrics"], expected):
                replay_mismatches.append({"candidate_identity": cid, "window": window, "actual": both[window]["metrics"], "expected": expected})
        npz_path = series_dir / f"{cid}.npz"
        np.savez_compressed(
            npz_path,
            train_timestamps_ns=both["TRAIN"]["timestamps_ns"], train_equity=both["TRAIN"]["equity"], train_returns=both["TRAIN"]["returns"],
            validation_timestamps_ns=both["VALIDATION"]["timestamps_ns"], validation_equity=both["VALIDATION"]["equity"], validation_returns=both["VALIDATION"]["returns"],
        )
        train_meta = series_metadata(c, both["TRAIN"], package); val_meta = series_metadata(c, both["VALIDATION"], package)
        manifest_rows.append({"candidate": _candidate_dict(c), "train": train_meta, "validation": val_meta, "series_file": npz_path.name, "series_file_sha256": _sha256(npz_path)})
        idx = pd.to_datetime(both["VALIDATION"]["timestamps_ns"], utc=True)
        validation_series[cid] = pd.Series(both["VALIDATION"]["returns"], index=idx).iloc[1:]

    validation_frame = pd.concat(validation_series, axis=1, join="outer").sort_index()
    corr = _pairwise_corr(validation_frame)
    corr_path = output / "VALIDATION_CORRELATION.npz"
    np.savez_compressed(corr_path, candidate_ids=np.asarray(corr.index, dtype="U64"), correlation=corr.to_numpy(dtype=np.float64))
    group_summaries = _group_summaries(selected, corr)
    diagnostic = build_diagnostic_artifact(
        package=package, candidates=selected, validation_corr=corr.to_numpy(), group_summaries=group_summaries,
        replay_matches=(2 * len(selected) - len(replay_mismatches)), replay_mismatches=replay_mismatches,
    )
    validate_diagnostic_artifact(diagnostic)
    diagnostic["correlation_file"] = corr_path.name
    diagnostic["correlation_file_sha256"] = _sha256(corr_path)
    # Re-seal after adding file provenance.
    from quantbot.research.artifact_store import seal
    diagnostic = seal({k: v for k, v in diagnostic.items() if k != "artifact_identity"})
    validate_diagnostic_artifact(diagnostic)
    (output / "N12_NON_OOS_HOMOGENEITY.json").write_text(canonical_json(diagnostic) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "quantbot-non-oos-series-manifest-n12-v1",
        "input_n11_artifact_identity": package["artifact_identity"],
        "candidate_count": len(selected), "series_count": 2 * len(selected),
        "rows": manifest_rows, "oos_status": "SEALED", "oos_authorization": "NOT_AUTHORIZED",
    }
    manifest = seal(manifest)
    (output / "N12_NON_OOS_SERIES_MANIFEST.json").write_text(canonical_json(manifest) + "\n", encoding="utf-8")
    print("NON_OOS_SERIES_COMPLETE")
    print(f"candidates={len(selected)} series={2*len(selected)} replay_mismatches={len(replay_mismatches)}")
    print(f"manifest_identity={manifest['artifact_identity']}")
    print(f"diagnostic_identity={diagnostic['artifact_identity']}")
    print(f"oos={diagnostic['oos_status']}/{diagnostic['oos_authorization']}")


if __name__ == "__main__":
    main()
