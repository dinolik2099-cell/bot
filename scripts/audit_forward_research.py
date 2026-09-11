from __future__ import annotations
import argparse,json
from collections import Counter
from pathlib import Path
from quantbot.forward_research.core import ForwardResearchError,identity

def audit_forward_evidence(root,days):
 root=Path(root);files=sorted(root.rglob('*.jsonl'));counts=Counter();chains=Counter();records=0
 for path in files:
  parts=path.relative_to(root).parts;kind=parts[0]
  # Persistence partitions use kind/YYYY-MM-DD/kind.jsonl.  Ignore older
  # generic append-only fixtures rather than treating them as a data source.
  if len(parts)>=3 and parts[1].count('-')==2 and parts[1] < '1970-01-01':continue
  for raw in path.open(encoding='utf-8'):
   row=json.loads(raw);counts[f'{kind}_records']+=1;records+=1
   if row.get('schema_version')=='quantbot-forward-record-v1':
    if row.get('source')!='binance_public' or not row.get('git_commit') or not row.get('config_identity') or not row.get('universe_identity'):raise ForwardResearchError('forward_evidence_provenance_invalid')
    if row.get('oos_allowed') is True or row.get('oos_authorization') not in (None,'NOT_AUTHORIZED'):raise ForwardResearchError('forward_evidence_oos_violation')
    chains[(row['git_commit'],row['config_identity'],row['universe_identity'])]+=1
 if len(chains)>1:raise ForwardResearchError('forward_evidence_provenance_chain_drift')
 out={'schema_version':'quantbot-forward-research-audit-v2','days':days,'files':len(files),'records':records,**dict(sorted(counts.items())),'provenance_chains':len(chains),'forward_evidence_only':True,'model_ranking_updated':False,'frozen_selection_modified':False,'oos_read':False}
 out['audit_identity']=identity(out);return out
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--days',type=int,choices=(7,14,21,30),required=True);args=p.parse_args();print(json.dumps(audit_forward_evidence(args.root,args.days),sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
