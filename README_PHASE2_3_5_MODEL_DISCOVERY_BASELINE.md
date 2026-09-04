# QuantBot Phase 2.3.5-C 模型池真实数据基线筛选 V1.0

## 目的

对当前 36 个候选模型在锁定真实数据集上进行**默认参数基线筛选**，判断哪些模型值得进入下一阶段参数研究。

本阶段不是最终交易模型选择，也不是 OOS 验证。

## 研究边界

- 数据集：`UM_1H_6DC48D541517`
- 市场：Binance USDT-M
- 周期：1H
- 币种：BTCUSDT、ETHUSDT、BNBUSDT、SOLUSDT、XRPUSDT、DOGEUSDT
- 使用窗口：TRAIN + VALIDATION
- **OOS：本阶段完全不读取、不计算、不参与任何筛选**
- 成本：手续费 0.04%，滑点 2 bps，funding=0
- 单笔风险上限：1%
- 最大持仓：1

## 参数规则

本阶段只使用每个策略函数的**代码默认参数**。

Registry 中的参数网格不会在本阶段搜索。参数搜索留到后续阶段，并继续执行：

`TRAIN → 参数研究 → VALIDATION → 冻结 → OOS`

## 筛选门槛

进入下一阶段的候选必须同时满足：

1. VALIDATION 正收益币种 ≥ 3/6
2. VALIDATION PF ≥ 1 的币种 ≥ 3/6
3. TRAIN 与 VALIDATION 均为正收益的币种 ≥ 2/6
4. VALIDATION 中位 PF ≥ 1.0
5. 最多进入下一阶段 12 个模型

这些条件只是**研究资源控制门槛**，不是最终交易模型认证标准。

## 执行方式

六币种分别独立运行单币种研究进程，然后合并结果。这样可以避免连续运行多个大 DataFrame 时产生资源累积，也便于定位单币种问题。

单币种脚本每次只加载一个币种的数据，并完成该币种 36 个模型 × TRAIN/VALIDATION 共 72 个评估。

## 运行

```bash
cd /www/wwwroot/QuantBot
bash scripts/run_phase2_3_5_model_discovery_baseline_6symbols.sh
```

最终报告：

```text
data/reports/phase2_3_5_model_discovery_baseline.json
```

分币种报告：

```text
data/reports/phase2_3_5_model_discovery_6symbols_parts/
```

成功标志：

```text
PHASE2_3_5_MODEL_DISCOVERY_BASELINE_6SYMBOLS_OK
```

## 快速回测路径

本阶段使用经过数值等价性测试的单币种快速执行路径，避免正式 BacktestEngine 在每根 K 线反复创建 `history.copy()` 带来的大量开销。

发布前已将快速路径与正式 `BacktestEngine` 对关键结果逐项进行数值等价检查，包括：

- final equity
- total return
- max drawdown
- trades
- win rate
- profit factor
- rejected signals

快速路径没有改变交易规则、手续费、滑点、仓位、止损止盈或执行时序。

## 后续研究

本阶段得到的 shortlist 只是下一阶段的研究候选，不代表已经可以实盘。

后续仍必须严格执行：

`TRAIN → 参数研究 → VALIDATION → 冻结 → OOS`

尤其是 **OOS 不得参与模型或参数选择**。
