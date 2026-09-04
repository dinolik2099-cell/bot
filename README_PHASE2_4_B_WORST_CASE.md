# Phase 2.4-B 最坏情况压力测试 V1.0

## 目的

本阶段不追求最好收益，而是回答：

> 在成本恶化、滑点恶化、交易顺序不利等情况下，QuantBot 是否仍能生存。

## 测试

- 3 个 Phase 2.4-A 固定组合
- TRAIN / VALIDATION
- 10 个手续费/滑点压力场景，共 60 次真实共享资金回测
- VALIDATION 交易序列蒙特卡洛随机重排
- 默认 20,000 次模拟，可通过 `--mc` 调整
- OOS、D-2、D-3 完全不读取
- 不修改 D-1 冻结参数
- 不用压力结果反向调参

## 中文结果

报告和终端输出均使用中文指标名称：收益、最大回撤、盈利因子、交易次数、最终资金、最差1%、最差0.1%等。

## 运行

```bash
python scripts/test_phase2_4_b_worst_case_stress.py
python scripts/run_phase2_4_b_worst_case_stress.py --workers 6 --mc 20000
```

注意：蒙特卡洛属于路径风险分析，不是新的策略参数优化，也不授权 OOS。
