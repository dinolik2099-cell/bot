# Phase 2.4-B V1.3 夜间多模型/多方向最坏情况压力测试

目的：在不读取 OOS/D-2/D-3、且不修改 D-1 冻结参数的前提下，扩大模型数量并持续压力测试共享资金组合。

固定组合：
- MODEL_4_X6：固定前4个冻结模型 × 6币种
- MODEL_8_X6：固定前8个冻结模型 × 6币种
- MODEL_12_X6：12个冻结模型 × 6币种
- ALL12_X6：全部12个冻结模型 × 6币种

每轮：TRAIN/VALIDATION × 5成本场景，并在 VALIDATION 上进行交易 Bootstrap、7日 Block Bootstrap、多方向同步冲击。

启动：
```bash
source venv/bin/activate
python scripts/test_phase2_4_b_overnight_torture_v13.py
python scripts/run_phase2_4_b_overnight_torture_v13.py --hours 8 --workers 24 --mc-per-round 2000
```

输出：
- `data/reports/phase2_4_b_overnight_torture_v13.jsonl`
- `data/reports/phase2_4_b_overnight_torture_summary_v13.md`

注意：24 workers 用于夜间压力任务规模；底层6币种数据准备仍最多6个并行 worker。不要把“多模型组合结果”当成最终选模结果；本阶段只做压力与生存边界观察。


## V1.3.1 修复
- 修复 Block Bootstrap 中 `df.eq.resample(...)` 将 `eq` 解析为 DataFrame 方法的问题。
- 正确使用 `df["eq"].resample(...)`。
