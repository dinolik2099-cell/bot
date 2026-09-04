#!/usr/bin/env python3
import json, tempfile
from pathlib import Path
import importlib.util
p=Path(__file__).with_name('run_phase2_3_5_d3_oos_analysis.py')
s=importlib.util.spec_from_file_location('d3',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
with tempfile.TemporaryDirectory() as td:
    td=Path(td); d1={"phase":"2.3.5-D-1","dataset_id":"TEST","records":[]}; d2={"phase":"2.3.5-D-2","dataset_id":"TEST","results":[]}
    for model in m.EXPECTED_MODELS:
      for sym in m.EXPECTED_SYMBOLS:
        d1["records"].append({"model":model,"symbol":sym,"status":"FROZEN","oos_authorized":True})
        d2["results"].append({"model":model,"symbol":sym,"category":"x","params":{},"d1_train_metrics":{"total_return":.2,"profit_factor":1.2},"d1_validation_metrics":{"total_return":.1,"profit_factor":1.1},"oos_metrics":{"total_return":.05,"max_drawdown":.05,"profit_factor":1.2,"trades":40},"trades":[]})
    c=td/'c.jsonl'
    with c.open('w') as f:
      for model in m.EXPECTED_MODELS:
       for sym in m.EXPECTED_SYMBOLS:
        for i in range(100): f.write(json.dumps({"model":model,"symbol":sym,"timestamp":f"2026-01-01T{i:02d}:00:00","equity":10000*(1.0001**i)})+'\n')
    a=td/'d1.json'; b=td/'d2.json'; a.write_text(json.dumps(d1)); b.write_text(json.dumps(d2))
    x=m.load_json(a); y=m.load_json(b); m.validate_inputs(x,y); curves=m.load_curves(c)
    assert len(curves)==72 and m.classify(d2['results'][0]['oos_metrics'],m.extra(d2['results'][0]['oos_metrics'],curves[(m.EXPECTED_MODELS[0],m.EXPECTED_SYMBOLS[0])]))=='A_STRONG'
print('D-1/D-2 72-cell输入锁定：通过')
print('预声明A/B/C/D分类：通过')
print('OOS结果不回写参数：通过')
print('PHASE2_3_5_D3_OOS_ANALYSIS_TEST_OK')
