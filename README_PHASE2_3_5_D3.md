# QuantBot Phase 2.3.5-D-3 OOS 深度分析 V1.0

## 目的
对 Phase 2.3.5-D-2 已完成的 72 个 Model×Symbol 冻结参数 OOS 结果做纯分析：单元排名、模型级汇总、币种级汇总、TRAIN→VALIDATION→OOS 稳定性诊断，以及收益曲线相关性诊断。

## 严格边界
- 只读取 D-1 freeze manifest、D-2 OOS validation report、D-2 OOS equity curves。
- 不读取市场原始数据，不重新运行策略。
- 不重新选择参数，不修改 D-1 冻结参数。
- A/B/C/D 分类门槛在脚本中预先固定，属于 OOS 后诊断分类，不是事后调参规则。
- 相关性只为后续组合研究提供诊断，不直接淘汰参数。

## 固定分类
- A_STRONG：Return>0、PF>=1.10、DD<=25%、Trades>=30、Calmar-like>=0.75。
- B_RETAIN：Return>0、PF>=1、DD<=35%、Trades>=20、Calmar-like>=0.40。
- C_OBSERVE：Return>0 且 PF>=1，但未达到 A/B；仅观察。
- D_RETIRE：其余结果，作为研究池淘汰候选；不删除历史结果。

## 运行
```bash
cd /www/wwwroot/QuantBot
source venv/bin/activate
python scripts/test_phase2_3_5_d3_oos_analysis.py
python scripts/run_phase2_3_5_d3_oos_analysis.py
```

## 输出
- `data/reports/phase2_3_5_d3_oos_analysis.json`
- `data/reports/phase2_3_5_d3_summary.md`

D-3 完成后再进入组合研究；不得用 D-3 结果回头修改 D-1。
