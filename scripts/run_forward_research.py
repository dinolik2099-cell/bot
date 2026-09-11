"""Start/status the independent public-market Shadow Research runtime."""
from __future__ import annotations
import argparse,hashlib
from pathlib import Path
from quantbot.forward_research.core import AppendOnlyStore,identity,utc_now
from quantbot.forward_research.runtime import ForwardRuntime
def main():
 p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--status',action='store_true');args=p.parse_args();config=Path(args.config).read_bytes();runtime=ForwardRuntime()
 if args.status:print(runtime.health());return 0
 print('FORWARD_RESEARCH_ONLY=True');print('ORDER_PLACEMENT_ALLOWED=False');print('OOS_ALLOWED=False');print('PUBLIC_COLLECTOR_NOT_STARTED_BY_CLI_WITHOUT_SERVICE_AUTHORITY');return 2
if __name__=='__main__':raise SystemExit(main())
