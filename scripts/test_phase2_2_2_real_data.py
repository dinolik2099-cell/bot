from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.research.runner import (
    build_research_dataset,
    load_research_frames,
    split_frames,
)
from quantbot.research.evaluation import (
    evaluate_strategy,
    evaluation_to_dict,
)
from quantbot.strategies.models import trend_pullback
from quantbot.backtest.engine_v2 import BacktestEngine


LOCK = ROOT / "data/reports/research_boundary_lock.json"
RAW_ROOT = ROOT / "data/raw"
PARQUET_ROOT = ROOT / "data/parquet"


def engine_factory():
    return BacktestEngine(
        initial_equity=10000.0,
        max_position_fraction=1.0,
        max_risk_fraction=0.01,
        max_positions=1,
    )


def main():
    dataset = build_research_dataset(LOCK)

    frames, sources = load_research_frames(
        dataset,
        RAW_ROOT,
        PARQUET_ROOT,
        ["BTCUSDT"],
    )

    train = split_frames(
        dataset,
        frames,
        "TRAIN",
    )["BTCUSDT"]

    print("=" * 72)
    print("PHASE 2.2.2 REAL DATA MINIMAL CLOSED-LOOP")
    print("=" * 72)

    print("dataset_id:", dataset.boundary.dataset_id)
    print("symbol:", "BTCUSDT")
    print("window:", "TRAIN")
    print("source:", sources["BTCUSDT"])
    print("rows:", len(train))
    print("first:", train.index[0].isoformat())
    print("last:", train.index[-1].isoformat())

    result = evaluate_strategy(
        symbol="BTCUSDT",
        window="TRAIN",
        frame=train,
        strategy=trend_pullback,
        engine=engine_factory(),
        params={
            "ema_fast": 20,
            "ema_slow": 80,
            "stop_atr": 2.0,
            "reward_r": 3.0,
        },
        risk_fraction=0.01,
        position_fraction=1.0,
        tag="phase2.2.2_minimal",
    )

    payload = evaluation_to_dict(result)

    print()
    print("===== BACKTEST RESULT =====")
    print("initial_equity:", payload["initial_equity"])
    print("final_equity:", payload["final_equity"])
    print("halted:", payload["halted"])
    print("rejected_signals:", payload["rejected_signals"])
    print("skipped_gap_bars:", payload["skipped_gap_bars"])
    print("gap_bars_seen:", payload["gap_bars_seen"])
    print("trades:", len(payload["trades"]))

    print()
    print("===== METRICS =====")
    for key, value in payload["metrics"].items():
        print(f"{key}: {value}")

    assert payload["symbol"] == "BTCUSDT"
    assert payload["window"] == "TRAIN"
    assert payload["rows"] > 0
    assert payload["initial_equity"] == 10000.0
    assert payload["final_equity"] > 0
    assert payload["skipped_gap_bars"] >= 0
    assert payload["gap_bars_seen"] >= 0

    for trade in payload["trades"]:
        assert trade["symbol"] == "BTCUSDT"
        assert trade["entry_time"] is not None
        assert trade["side"] in ("buy", "sell")
        assert trade["qty"] > 0

    print()
    print("=" * 72)
    print("PHASE2_2_2_REAL_DATA_MINIMAL_CLOSED_LOOP_OK")
    print("=" * 72)


if __name__ == "__main__":
    main()
