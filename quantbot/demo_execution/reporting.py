from __future__ import annotations
from collections import defaultdict
from .core import identity
def daily_report(rows,starting_equity,ending_equity):
 pnl=ending_equity-starting_equity;by_model=defaultdict(float);by_symbol=defaultdict(float)
 for row in rows:by_model[row.get('model_id','')]+=float(row.get('realized_pnl',0));by_symbol[row.get('symbol','')]+=float(row.get('realized_pnl',0))
 report={'schema_version':'quantbot-demo-daily-report-v1','starting_equity':starting_equity,'ending_equity':ending_equity,'net_pnl':pnl,'realized_pnl':sum(float(r.get('realized_pnl',0)) for r in rows),'unrealized_pnl':sum(float(r.get('unrealized_pnl',0)) for r in rows),'fees':sum(float(r.get('fee',0)) for r in rows),'signals':len(rows),'orders_submitted':sum(r.get('order_state') in {'SUBMITTED','ACKNOWLEDGED','PARTIALLY_FILLED','FILLED'} for r in rows),'orders_filled':sum(r.get('order_state')=='FILLED' for r in rows),'per_model_pnl':dict(by_model),'per_symbol_pnl':dict(by_symbol)};report['report_identity']=identity(report);return report
