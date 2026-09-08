"""Zero-real-data wiring tests for the formal TRAIN/VALIDATION runner."""
from pathlib import Path
import json
import sys
import inspect

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import quantbot.research.canonical_data_adapter as n8mod

from quantbot.research.formal_runner import (
    N7ExecutionError,
    load_n7_context,
    make_n7_canonical_evaluator,
    make_n7_window_loader,
)
from quantbot.research.canonical_data_adapter import (
    N8DataError,
    _make_n8_window_loader_for_test,
    load_n8_data_context,
)
from quantbot.backtest.costs import CostModel
from quantbot.backtest.engine_v2 import BacktestEngine

PLAN = ROOT / "docs/handoff/FROZEN_RESEARCH_PLAN_N5.json"
FREEZE = ROOT / "docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json"
LOCK_PATH = ROOT / "data/reports/research_boundary_lock.json"


def expected_frame(n8, symbol, window):
    w = next(x for x in n8.dataset.windows if x.name == window)
    index = pd.date_range(
        w.start,
        w.end,
        freq=n8.dataset.interval,
        tz="UTC",
    )
    index = index[
        [
            not n8mod.timestamp_in_non_tradable_gap(
                n8.dataset, symbol, ts
            )
            for ts in index
        ]
    ]
    frame = pd.DataFrame(
        {
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 1.0,
        },
        index=index,
    )
    return frame


def main():
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    n7 = load_n7_context(PLAN, FREEZE, lock)
    n8 = load_n8_data_context(n7, LOCK_PATH)

    task = sorted(
        n7.plan["tasks"], key=lambda x: x["task_identity"]
    )[0]

    source_calls = []
    raw_reader_calls = []

    original_raw = n8mod.load_boundary_aware_symbol_window

    def forbidden_raw(*args, **kwargs):
        raw_reader_calls.append((args, kwargs))
        raise AssertionError("REAL_RAW_READER_CALLED")

    n8mod.load_boundary_aware_symbol_window = forbidden_raw

    try:
        def synthetic_source(
            *,
            symbol,
            market,
            interval,
            window,
            start,
            end,
            dataset_id,
        ):
            assert window in {"TRAIN", "VALIDATION"}
            assert symbol == task["symbol"]
            assert market == n8.dataset.market
            assert interval == n8.dataset.interval
            assert dataset_id == n8.dataset.dataset_id

            locked = next(
                item for item in n8.dataset.windows
                if item.name == window
            )
            assert start == locked.start
            assert end == locked.end

            source_calls.append(window)
            return expected_frame(n8, symbol, window), "canonical_raw"

        n8_loader = _make_n8_window_loader_for_test(
            n8, synthetic_source
        )
        guarded = make_n7_window_loader(n7, n8_loader)

        train = guarded(
            window="TRAIN",
            symbol=task["symbol"],
            task=task,
        )
        validation = guarded(
            window="VALIDATION",
            symbol=task["symbol"],
            task=task,
        )

        assert not train.empty
        assert not validation.empty
        assert source_calls == ["TRAIN", "VALIDATION"]

        before = len(source_calls)
        try:
            guarded(
                window="OOS",
                symbol=task["symbol"],
                task=task,
            )
        except (N7ExecutionError, N8DataError):
            pass
        else:
            raise AssertionError("OOS_WIRING_ACCEPTED")
        assert len(source_calls) == before

        try:
            guarded(
                window="TRAIN",
                symbol="NOT_FROZEN",
                task=task,
            )
        except (N7ExecutionError, N8DataError):
            pass
        else:
            raise AssertionError("NONFROZEN_SYMBOL_ACCEPTED")
        assert len(source_calls) == before

        class FakeStrategy:
            pass

        def strategy_resolver(model_id):
            return FakeStrategy()

        class FakeEngine:
            pass

        evaluator = make_n7_canonical_evaluator(
            n7,
            n8_loader,
            strategy_resolver,
            lambda: FakeEngine(),
        )

        before = len(source_calls)
        try:
            evaluator(
                "TRAIN",
                next(
                    e for e in n7.entries
                    if e.model_id == task["model_id"]
                ),
                task,
                {},
            )
        except Exception as exc:
            assert "canonical_engine_or_cost_model_required" in str(exc)
        else:
            raise AssertionError("NONCANONICAL_ENGINE_ACCEPTED")

        # Engine rejection must occur before market-data source access.
        assert len(source_calls) == before

        canonical = BacktestEngine(
            initial_equity=10_000.0,
            cost_model=CostModel(),
        )
        assert isinstance(canonical, BacktestEngine)
        assert isinstance(canonical.cost_model, CostModel)

        assert raw_reader_calls == []

        # Public formal task API must not expose any injection surface for
        # evaluator/data/model wiring.
        import importlib.util

        runner_path = ROOT / "scripts/run_formal_train_validation.py"
        runner_spec = importlib.util.spec_from_file_location(
            "formal_runner_public_surface",
            runner_path,
        )
        runner_mod = importlib.util.module_from_spec(runner_spec)
        runner_spec.loader.exec_module(runner_mod)

        public_params = inspect.signature(
            runner_mod.execute_one_task
        ).parameters

        forbidden_public_params = {
            "evaluator",
            "entries",
            "frame_loader",
            "window_loader",
            "raw_root",
            "strategy_resolver",
            "engine_factory",
        }

        exposed = forbidden_public_params.intersection(public_params)
        assert not exposed, sorted(exposed)

        print("PUBLIC_EVALUATOR_INJECTION_BLOCKED=PASS")
        print("PUBLIC_DATA_LOADER_INJECTION_BLOCKED=PASS")
        print("N8_EXACT_TRAIN_BOUNDARY=PASS")
        print("N8_EXACT_VALIDATION_BOUNDARY=PASS")
        print("N7_OOS_REJECTED_BEFORE_SOURCE=PASS")
        print("NONFROZEN_SYMBOL_REJECTED=PASS")
        print("NONCANONICAL_ENGINE_REJECTED_BEFORE_SOURCE=PASS")
        print("CANONICAL_ENGINE_COST_TYPES=PASS")
        print("REAL_RAW_READER_CALLS=0")
        print("FORMAL_RUNNER_WIRING_TEST_OK")

    finally:
        n8mod.load_boundary_aware_symbol_window = original_raw


if __name__ == "__main__":
    main()
