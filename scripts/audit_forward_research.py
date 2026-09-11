from __future__ import annotations
import argparse,json
from collections import Counter
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--days',type=int,choices=(7,14,21,30),required=True);args=p.parse_args();root=Path(args.root);files=list(root.rglob('*.jsonl'));counts=Counter()
 for path in files:
  kind=path.relative_to(root).parts[0];counts[f'{kind}_records']+=sum(1 for _ in path.open(encoding='utf-8'))
 out={'schema_version':'quantbot-forward-research-audit-v1','days':args.days,'files':len(files),**dict(sorted(counts.items())),'forward_evidence_only':True,'model_ranking_updated':False,'frozen_selection_modified':False,'oos_read':False};print(json.dumps(out,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
