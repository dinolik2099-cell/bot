from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.risk import RiskSnapshot,evaluate_circuit_breaker,emergency_stop_from_breaker
def main():
 s=RiskSnapshot(96,100,100,100);stop=emergency_stop_from_breaker(evaluate_circuit_breaker(s),s)
 assert stop.active and stop.reason=="max_daily_loss" and stop.equity==96
 print("EMERGENCY_STOP_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
