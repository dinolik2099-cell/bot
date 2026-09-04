"""Guard against reintroducing the retired independent backtest path."""

import importlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

legacy_engine = importlib.import_module("quantbot.backtest.engine")


for fn in (legacy_engine.backtest, legacy_engine.metrics):
    try:
        fn()
    except RuntimeError as exc:
        assert "retired" in str(exc)
    else:
        raise AssertionError("retired legacy backtest API must reject execution")

print("LEGACY_ENGINE_RETIREMENT_TEST_OK")
