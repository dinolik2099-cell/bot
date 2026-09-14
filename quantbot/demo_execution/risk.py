from __future__ import annotations
from decimal import Decimal,ROUND_DOWN
from datetime import datetime,timezone
from .core import FailClosedError,DemoRiskRejected

def normalize_quantity(notional,price,filters):
 quantity=Decimal(str(notional))/Decimal(str(price));step=Decimal(str(filters['stepSize']));minimum=Decimal(str(filters['minQty']));min_notional=Decimal(str(filters['minNotional']))
 quantity=(quantity/step).to_integral_value(rounding=ROUND_DOWN)*step
 if quantity<minimum or quantity*Decimal(str(price))<min_notional:raise FailClosedError('demo_quantity_filter_rejected')
 return format(quantity,'f')
def check_risk(policy,signal,*,open_orders,gross_exposure,strategy_exposure,daily_pnl,now=None):
 risk=policy['risk'];now=now or datetime.now(timezone.utc);created=datetime.fromisoformat(signal['created_at'].replace('Z','+00:00'))
 if (now-created).total_seconds()>policy['max_signal_age_seconds']:raise DemoRiskRejected('stale_signal')
 if open_orders>=risk['max_open_orders']:raise DemoRiskRejected('max_open_orders')
 if gross_exposure+policy['order_notional']>risk['max_total_gross_exposure']:raise DemoRiskRejected('gross_exposure')
 if strategy_exposure+policy['order_notional']>risk['max_strategy_exposure']:raise DemoRiskRejected('strategy_exposure')
 if policy['order_notional']>risk['max_order_notional']:raise DemoRiskRejected('max_order_notional')
 if daily_pnl<=-risk['max_daily_loss']:raise DemoRiskRejected('daily_loss')
 return True
def is_stale(policy,signal,now=None):
 now=now or datetime.now(timezone.utc);created=datetime.fromisoformat(signal['created_at'].replace('Z','+00:00'))
 return (now-created).total_seconds()>policy['max_signal_age_seconds']
