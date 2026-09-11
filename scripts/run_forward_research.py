"""Start/status the independent public-market Shadow Research runtime."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from quantbot.forward_research.core import AppendOnlyStore,identity,utc_now
from quantbot.forward_research.runtime import ForwardRuntime
from quantbot.forward_research.checkpoint import load_checkpoint
def main():
 p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--status',action='store_true');p.add_argument('--diagnostics',action='store_true');p.add_argument('--checkpoint');args=p.parse_args();config=Path(args.config).read_bytes();runtime=ForwardRuntime()
 if args.status or args.diagnostics:
  health=load_checkpoint(args.checkpoint)['runtime'] if args.checkpoint and Path(args.checkpoint).exists() else runtime.health()
  print(json.dumps(health,sort_keys=True));return 0
 print('FORWARD_RESEARCH_ONLY=True');print('ORDER_PLACEMENT_ALLOWED=False');print('OOS_ALLOWED=False');print('PUBLIC_COLLECTOR_NOT_STARTED_BY_CLI_WITHOUT_SERVICE_AUTHORITY');return 2
if __name__=='__main__':raise SystemExit(main())
