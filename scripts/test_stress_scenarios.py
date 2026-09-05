from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.backtest.stress import standard_scenarios
def main():
    x=standard_scenarios(); assert [s.name for s in x]==["baseline","elevated_cost","latency_liquidity"]
    assert x[1].cost_model.slippage_bps > x[0].cost_model.slippage_bps and x[2].latency_bars == 1
    print("STRESS_SCENARIOS_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
