"""Synthetic-only tests for the non-executable Signal contract."""
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.signals import normalize_strategy_output


def main() -> None:
    index = pd.date_range("2025-01-01", periods=4, freq="h", tz="UTC")
    frame = pd.DataFrame({"close": [100.0, 101.0, 102.0, 103.0]}, index=index)
    output = pd.DataFrame({
        "signal": [1, -1, 0, 1],
        "stop": [98.0, 103.0, float("nan"), 100.0],
        "target": [104.0, 98.0, float("nan"), 107.0],
    }, index=index)
    intents = normalize_strategy_output(
        symbol="BTCUSDT", model="example", model_family="trend",
        frame=frame, strategy_output=output, metadata={"synthetic": True},
    )
    assert len(intents) == 2
    assert intents[0].side == "buy" and intents[0].timestamp == index[1]
    assert intents[1].side == "sell" and intents[1].timestamp == index[2]
    assert all(x.risk_intent == "requires_risk_approval" for x in intents)
    assert all(x.metadata["synthetic"] is True for x in intents)
    assert all(x.timestamp > pd.Timestamp(x.metadata["source_row_timestamp"]) for x in intents)
    print("SIGNAL_CONTRACTS_SYNTHETIC_TEST_OK")


if __name__ == "__main__":
    main()
