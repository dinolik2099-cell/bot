"""Explicit isolated Binance Demo execution CLI; it never starts Forward."""
from __future__ import annotations
import argparse,json,subprocess
from pathlib import Path
from quantbot.demo_execution.config import load_json,validate_config,load_credentials
from quantbot.demo_execution.binance_demo_adapter import BinanceDemoAdapter
from quantbot.demo_execution.runtime import DemoRuntime
from quantbot.demo_execution.execution_engine import DemoExecutionEngine
from quantbot.demo_execution.signal_reader import ForwardSignalReader

def git_commit(root):return subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--data-root',required=True);parser.add_argument('--forward-root',required=True);parser.add_argument('--diagnostics',action='store_true');parser.add_argument('--dry-run',action='store_true');parser.add_argument('--execute-demo-orders',action='store_true')
 args=parser.parse_args();config=validate_config(load_json(args.config));credentials=load_credentials();adapter=BinanceDemoAdapter(config['endpoint'],credentials['api_key'],credentials['api_secret']);runtime=DemoRuntime(config,args.data_root,args.forward_root,adapter,git_commit(Path.cwd()))
 if args.diagnostics:print(json.dumps(runtime.diagnostics(),sort_keys=True,default=str));return 0
 if not args.dry_run and not args.execute_demo_orders:raise SystemExit('demo mode required: use --dry-run or --execute-demo-orders')
 if args.execute_demo_orders and not credentials['loaded']:raise SystemExit('demo credentials required')
 engine=DemoExecutionEngine(runtime.ledger,runtime.persistence,adapter,config,Path(args.data_root).name);cursor=(runtime.persistence.read_checkpoint() or {}).get('last_signal_cursor');processed=0
 for marker,signal in ForwardSignalReader(args.forward_root).discover(cursor,runtime.epoch_start):
  # Real execution needs fresh exchange price/filter metadata.  Dry-run still
  # creates only safe intent evidence unless an operator supplies that context.
  if args.dry_run:runtime.persistence.append('runtime',signal['created_at'][:10],{'signal_identity':signal['signal_identity'],'cursor':marker,'dry_run_intent_only':True});cursor=marker;processed+=1;continue
  raise SystemExit('demo order execution requires reviewed market metadata integration')
 runtime.checkpoint(cursor);print(json.dumps({'environment':'DEMO','live_allowed':False,'processed':processed,'dry_run':args.dry_run,'fail_closed':runtime.fail_closed},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
