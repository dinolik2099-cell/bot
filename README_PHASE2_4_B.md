# Phase 2.4-B 共享资金 Portfolio 回测 V1.0.2

本阶段把 Phase 2.4-A 的 Validation portfolio recipes 放入一个真正共享的资金账户，测试多币种同时持仓、仓位、总风险和方向风险约束。

## 研究纪律

- 只读取 D-1 冻结参数、Phase 2.4-A recipe 报告和 TRAIN/VALIDATION 数据。
- 不读取 D-2/D-3/OOS 结果。
- 不修改 D-1 冻结参数。
- 本阶段比较 TOP8、DIVERSIFIED_8、DIVERSIFIED_12 三个既有 recipe。
- 结果用于组合层选择；组合冻结后才允许进行下一次 OOS。

## 固定风险政策

- 初始资金：10,000 USDT
- 单笔风险：1%
- 组合总风险上限：4%
- 同方向风险上限：3%
- 最大同时持仓：4
- 单仓最大名义占比：25%
- 总资金使用上限：80%
- 同一币同时最多 1 个 Sleeve
- Fee：0.04%
- Slippage：2 bps
- Funding：0

## 执行规则

- 信号来自完成的 T-1 K 线。
- T 开盘执行。
- 入场 K 线不触发新仓 SL/TP。
- 后续 K 线若同时触发 SL 和 TP，SL 优先。
- 不补造缺失 K 线。
- Gap 后第一根实际 K 线不可交易。
- 数据结束时按最后实际收盘价平仓。

## 运行

```bash
python scripts/test_phase2_4_b_shared_capital_backtest.py
python scripts/run_phase2_4_b_shared_capital_backtest.py --workers 6
```


## V1.0.2 修复记录

- 修复 Boundary / IntegrationDataset 的 `gaps=None` 情况。
- 修复单个 gap 记录为 `None` 时的遍历错误。
- 统一将 Gap 后第一根实际 K 线规范化为 `set[pd.Timestamp]`，支持零 gap、单 gap、多 gap。
- 支持 `gaps` 直接存在于对象、`metadata.gaps`、dict boundary，以及按 symbol 映射的 gap 结构。
- 补充同方向风险上限、最大同时持仓、metadata/symbol-map gap 的测试。
- 研究范围与 2.4-B 原有合同不变：只做 TRAIN / VALIDATION，不读取 OOS / D-2 / D-3。
