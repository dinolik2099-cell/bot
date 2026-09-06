"""Read-only N8 loader wiring preflight; it never calls a market-data source."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.formal_runner import load_n7_context
from quantbot.research.canonical_data_adapter import load_n8_data_context
def main():
 ap=argparse.ArgumentParser(description='Validate N8 canonical non-OOS loader wiring without data access.')
 ap.add_argument('--plan',default=str(ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json'));ap.add_argument('--freeze',default=str(ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json'));ap.add_argument('--boundary-lock',default=str(ROOT/'data/reports/research_boundary_lock.json'))
 args=ap.parse_args();lock=json.loads(Path(args.boundary_lock).read_text(encoding='utf-8'));n7=load_n7_context(args.plan,args.freeze,lock);n8=load_n8_data_context(n7,args.boundary_lock);plan=n7.plan
 print('N8_PREFLIGHT_OK')
 for key,value in sorted({'research_freeze_identity':plan['research_freeze_identity'],'research_plan_identity':plan['research_plan_identity'],'dataset_id':n8.dataset.dataset_id,'market':n8.dataset.market,'interval':n8.dataset.interval,'symbols':','.join(plan['symbols']),'train_boundary':plan['boundary']['train_boundary'],'validation_boundary':plan['boundary']['validation_boundary'],'engine_identity':n7.freeze['protocol_scope']['engine_identity'],'cost_model_identity':n7.freeze['protocol_scope']['cost_model_identity'],'oos_status':plan['oos_status'],'oos_authorization':plan['oos_authorization'],'market_data_reads':0}.items()):print(f'{key}={value}')
if __name__=='__main__':main()
