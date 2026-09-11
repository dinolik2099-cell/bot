"""Start/status the independent public-market Shadow Research runtime."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from quantbot.forward_research.core import identity
from quantbot.forward_research.runtime import ForwardRuntime
from quantbot.forward_research.checkpoint import load_checkpoint
from quantbot.forward_research.config import validate_config
from quantbot.forward_research.frozen_declarations import load_n5_plan,load_forward_declaration_manifest
def main():
 p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--status',action='store_true');p.add_argument('--diagnostics',action='store_true');p.add_argument('--checkpoint');p.add_argument('--preflight',action='store_true');p.add_argument('--plan');p.add_argument('--declarations');args=p.parse_args();config=validate_config(args.config);runtime=ForwardRuntime()
 if args.preflight:
  if not args.plan or not args.declarations:p.error('--preflight requires --plan and --declarations')
  plan=load_n5_plan(args.plan);manifest=load_forward_declaration_manifest(args.declarations,plan)
  print(json.dumps({'FORWARD_PREFLIGHT_OK':True,'config_identity':config['config_identity'],'research_freeze_identity':plan['research_freeze_identity'],'research_plan_identity':plan['research_plan_identity'],'declaration_manifest_identity':manifest['manifest_identity'],'declarations':len(manifest['declarations']),'oos_allowed':False,'orders_allowed':False},sort_keys=True));return 0
 if args.status or args.diagnostics:
  health=load_checkpoint(args.checkpoint)['runtime'] if args.checkpoint and Path(args.checkpoint).exists() else runtime.health()
  print(json.dumps(health,sort_keys=True));return 0
 print('FORWARD_RESEARCH_ONLY=True');print('ORDER_PLACEMENT_ALLOWED=False');print('OOS_ALLOWED=False');print('PUBLIC_COLLECTOR_NOT_STARTED_BY_CLI_WITHOUT_SERVICE_AUTHORITY');return 2
if __name__=='__main__':raise SystemExit(main())
