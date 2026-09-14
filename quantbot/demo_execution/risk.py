from __future__ import annotations
from decimal import Decimal,ROUND_DOWN
from datetime import datetime,timezone
from .core import FailClosedError

def normalize_quantity(notional,price,filters):
 quantity=Decimal(str(notional))/Decimal(str(price));step=Decimal(str(filters['stepSize']));minimum=Decimal(str(filters['minQty']));min_notional=Decimal(str(filters['minNotional']))
 quantity=(quantity/step).to_integral_value(rounding=ROUND_DOWN)*step
 if quantity<minimum or quantity*Decimal(str(price))<min_notional:raise FailClosedError('demo_quantity_filter_rejected')
 return format(quantity,'f')
def check_risk(policy,signal,*,open_orders,gross_exposure,strategy_exposure,daily_pnl,now=None):
 risk=policy['risk'];now=now or datetime.now(timezone.utc);created=datetime.fromisoformat(signal['created_at'].replace('Z','+00:00'))
 if (now-created).total_seconds()>policy['max_signal_age_seconds']:raise FailClosedError('demo_signal_stale')
 if open_orders>=risk['max_open_orders'] or gross_exposure+policy['order_notional']>risk['max_total_gross_exposure'] or strategy_exposure+policy['order_notional']>risk['max_strategy_exposure'] or policy['order_notional']>risk['max_order_notional'] or daily_pnl<=-risk['max_daily_loss']:raise FailClosedError('demo_risk_limit')
 return True
