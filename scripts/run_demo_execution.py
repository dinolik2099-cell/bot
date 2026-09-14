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
 parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--data-root',required=True);parser.add_argument('--forward-root',required=True);parser.add_argument('--diagnostics',action='store_true');parser.add_argument('--dry-run',action='store_true');parser.add_argument('--execute-demo-orders',action='store_true');parser.add_argument('--serve',action='store_true');parser.add_argument('--poll-seconds',type=int,default=15);parser.add_argument('--reconcile-seconds',type=int,default=60)
 args=parser.parse_args();config=validate_config(load_json(args.config));credentials=load_credentials();adapter=BinanceDemoAdapter(config['endpoint'],credentials['api_key'],credentials['api_secret']);runtime=DemoRuntime(config,args.data_root,args.forward_root,adapter,git_commit(Path.cwd()))
 if args.diagnostics:print(json.dumps(runtime.diagnostics(),sort_keys=True,default=str));return 0
 if args.dry_run==args.execute_demo_orders:raise SystemExit('select exactly one of --dry-run or --execute-demo-orders')
 if args.execute_demo_orders and not credentials['loaded']:raise SystemExit('demo credentials required')
 engine=DemoExecutionEngine(runtime.ledger,runtime.persistence,adapter,config,Path(args.data_root).name)
 try:runtime.startup_reconcile()
 except Exception:runtime.fail_closed=True;engine.disable('startup_reconciliation_failed')
 if not args.serve:
  result=runtime.consume_once(engine,args.dry_run);print(json.dumps({'environment':'DEMO','live_allowed':False,'dry_run':args.dry_run,**result},sort_keys=True));return 0
 result=runtime.serve(engine,dry_run=args.dry_run,poll_seconds=args.poll_seconds,reconcile_seconds=args.reconcile_seconds)
 print(json.dumps({'environment':'DEMO','live_allowed':False,'dry_run':args.dry_run,**result},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
