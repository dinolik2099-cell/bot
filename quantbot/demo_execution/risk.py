from __future__ import annotations
from decimal import Decimal,InvalidOperation,ROUND_DOWN
from datetime import datetime,timezone
from .core import FailClosedError,DemoRiskRejected

def normalize_quantity(notional,price,filters):
 # Do not increase quantity/notional to satisfy a venue minimum.  Invalid
 # metadata is unsafe; a valid filter that cannot accommodate the frozen
 # request is a normal per-signal policy rejection.
 try:
  requested_notional=Decimal(str(notional));market_price=Decimal(str(price));step=Decimal(str(filters['stepSize']));minimum=Decimal(str(filters['minQty']));min_notional=Decimal(str(filters['minNotional']))
 except (KeyError,InvalidOperation,TypeError,ValueError) as exc:raise FailClosedError('demo_symbol_filters_invalid') from exc
 if requested_notional<=0 or market_price<=0 or step<=0 or minimum<=0 or min_notional<=0:raise FailClosedError('demo_symbol_filters_invalid')
 quantity=requested_notional/market_price
 quantity=(quantity/step).to_integral_value(rounding=ROUND_DOWN)*step
 if quantity<minimum or quantity*market_price<min_notional:raise DemoRiskRejected('quantity_filter_unexecutable')
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
