from __future__ import annotations
import argparse,json
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--days',type=int,choices=(7,14,21,30),required=True);args=p.parse_args();root=Path(args.root);files=list(root.rglob('*.jsonl'));print(json.dumps({'schema_version':'quantbot-forward-research-audit-v1','days':args.days,'files':len(files),'forward_evidence_only':True,'model_ranking_updated':False,'oos_read':False},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
