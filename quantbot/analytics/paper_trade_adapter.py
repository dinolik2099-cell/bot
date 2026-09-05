"""Convert explicit completed-paper inputs into immutable TradeRecord audit data."""
from __future__ import annotations
from quantbot.execution import PaperOrderRequest
from .trade_records import TradeRecord

def record_paper_trade(order: PaperOrderRequest, *, entry_time: str, exit_time: str, exit_price: float, exit_reason: str, gross_pnl: float, net_pnl: float, fees: float, slippage_cost: float, holding_seconds: float, r_multiple: float | None, provenance: dict | None = None) -> TradeRecord:
    return TradeRecord(order.symbol, order.source_tag.split(":",1)[0], order.model_family, entry_time, exit_time, order.side, order.expected_execution_price, order.stop, order.take_profit, exit_price, exit_reason, gross_pnl, net_pnl, fees, slippage_cost, order.quantity, holding_seconds, r_multiple, metadata={"paper_only": True, **(provenance or {})})
