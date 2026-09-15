from __future__ import annotations
import argparse,json
from pathlib import Path
from quantbot.unattended.config import load
from quantbot.unattended.supervisor import UnattendedSupervisor
def main():
 p=argparse.ArgumentParser();p.add_argument("--config",default="config/unattended_supervisor.json");p.add_argument("--root",default=".");p.add_argument("--once",action="store_true");p.add_argument("--shadow",action="store_true");p.add_argument("--json",action="store_true");args=p.parse_args()
 if not args.once:raise SystemExit("unattended_supervisor_requires_once")
 result=UnattendedSupervisor(Path(args.root),load(args.config)).run_once(shadow=True if not args.shadow else True)
 print(json.dumps(result,sort_keys=True,default=str) if args.json else result["overall"]);return 0
if __name__=="__main__":raise SystemExit(main())
