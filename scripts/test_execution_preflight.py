from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.execution import RuntimeConfig,preflight
from quantbot.research.provenance import RunProvenance
from quantbot.risk import RiskSnapshot
def main():
 s=RiskSnapshot(100,100,100,100)
 assert preflight(RuntimeConfig(),RunProvenance("synthetic","v1","VALIDATION"),s).allowed
 assert not preflight(RuntimeConfig(),RunProvenance("synthetic","v1","OOS"),s).allowed
 assert preflight(RuntimeConfig(),RunProvenance("synthetic","v1","VALIDATION"),RiskSnapshot(96,100,100,100)).reason=="max_daily_loss"
 print("EXECUTION_PREFLIGHT_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
