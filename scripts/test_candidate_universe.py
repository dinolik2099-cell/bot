"""Synthetic/metadata-only candidate-universe contract tests; no research data."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.candidate_universe import build_candidate_universe,candidate_universe_hash
from quantbot.research.model_registry import register_existing_models
from quantbot.strategies.model_pool import register_model_pool
def main():
 register_existing_models();register_model_pool()
 universe=build_candidate_universe();again=build_candidate_universe()
 assert 30 <= len(universe) <= 50
 assert candidate_universe_hash(universe)==candidate_universe_hash(again)
 assert len({x.model_id for x in universe})==len(universe)
 assert all(x.family and x.long_short_capable and x.timeframe=="1h" for x in universe)
 assert all(x.lifecycle_status not in {"retired","deferred"} and x.warmup_bars >= 1 for x in universe)
 assert all(len(x.parameter_grid_hash)==64 and len(x.implementation_hash)==64 for x in universe)
 print("CANDIDATE_UNIVERSE_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
