from __future__ import annotations
from dataclasses import dataclass,asdict
from enum import Enum
from .core import identity

class OrderState(str,Enum):
 DISCOVERED='DISCOVERED';VALIDATED='VALIDATED';INTENT_CREATED='INTENT_CREATED';SUBMITTING='SUBMITTING';SUBMITTED='SUBMITTED';ACKNOWLEDGED='ACKNOWLEDGED';PARTIALLY_FILLED='PARTIALLY_FILLED';FILLED='FILLED';CANCELED='CANCELED';EXPIRED='EXPIRED';REJECTED='REJECTED';REJECTED_POLICY='REJECTED_POLICY';FAILED_SAFE='FAILED_SAFE';RECONCILING='RECONCILING';SKIPPED='SKIPPED'

TERMINAL={OrderState.FILLED,OrderState.CANCELED,OrderState.EXPIRED,OrderState.REJECTED,OrderState.REJECTED_POLICY,OrderState.FAILED_SAFE,OrderState.SKIPPED}
@dataclass(frozen=True)
class ExecutionIntent:
 signal_identity:str;symbol:str;side:str;model_id:str;declaration_identity:str;signal_timestamp:str;client_order_id:str;intent_identity:str;notional:float;action:str
 @classmethod
 def from_signal(cls,signal,notional,action='OPEN',version='demo-execution-v1'):
  sid=signal['signal_identity'];role={'signal_identity':sid,'role':action,'version':version};intent=identity(role);client='QB'+intent[:30].upper()
  return cls(sid,signal['symbol'],str(signal['direction']).upper(),signal.get('model_id',''),signal.get('declaration_identity',''),signal['signal_timestamp'],client,intent,float(notional),action)
 def row(self):return asdict(self)
