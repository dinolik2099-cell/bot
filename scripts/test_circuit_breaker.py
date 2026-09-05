from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.risk import RiskSnapshot,evaluate_circuit_breaker
def main():
 assert evaluate_circuit_breaker(RiskSnapshot(100,100,100,100)).allowed
 assert evaluate_circuit_breaker(RiskSnapshot(96,100,100,100)).reason=="max_daily_loss"
 assert evaluate_circuit_breaker(RiskSnapshot(100,100,100,100,5)).reason=="max_consecutive_losses"
 print("CIRCUIT_BREAKER_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
