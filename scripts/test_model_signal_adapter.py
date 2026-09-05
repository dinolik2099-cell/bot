from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.model_registry import register_existing_models
from quantbot.research.model_registry import ModelSpec,register_model
from quantbot.signals import generate_model_intents
def main():
 register_existing_models()
 idx=pd.date_range("2025-01-01",periods=100,freq="h",tz="UTC");c=100+np.arange(100)*.2
 f=pd.DataFrame({"open":c,"high":c+.5,"low":c-.5,"close":c,"volume":1000},index=idx)
 intents=generate_model_intents("BTCUSDT","trend_breakout",f,{"lookback":20,"stop_atr":2.,"reward_r":3.})
 assert all(x.model_family=="趋势" for x in intents)
 assert all(x.risk_intent=="requires_risk_approval" for x in intents)
 def retired(df): return df.assign(signal=0,stop=np.nan,target=np.nan)
 register_model(ModelSpec("retired_test","测试","synthetic","test",("close",),{},("test",),status="retired",family="测试"),retired)
 try: generate_model_intents("BTCUSDT","retired_test",f,{})
 except PermissionError: pass
 else: raise AssertionError("retired model emitted a signal")
 print("MODEL_SIGNAL_ADAPTER_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
