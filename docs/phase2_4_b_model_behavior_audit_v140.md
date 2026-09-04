# Phase 2.4-B V1.4.0 模型行为/连续亏损审计

## 审计原则
- 本审计不重新回测。
- 不修改冻结参数。
- OOS 只作为独立诊断展示，不参与选模。
- 评价对象是 72 个冻结 Model × Symbol。
- 连续亏损：≤10 合格；11–15 警戒；16–20 严重警戒；≥21 淘汰候选。

## 总体：72 个冻结 Sleeve

- TRAIN 最大连续亏损：23
- VALIDATION 最大连续亏损：22
- OOS 最大连续亏损：21
- 三阶段最大值：23

- 等级分布：{'淘汰候选': 6, '严重警戒': 32, '警戒': 32, '合格': 2}

## 按模型

| 模型 | Sleeve | TRAIN最大 | VALID最大 | OOS最大 | 总最大 | 判定 |
|---|---:|---:|---:|---:|---:|---|
| bollinger_breakout | 6 | 19 | 16 | 14 | 19 | **严重警戒** |
| donchian_breakout | 6 | 18 | 19 | 12 | 19 | **严重警戒** |
| ema_slope | 6 | 18 | 16 | 13 | 18 | **严重警戒** |
| higher_high_lower_low | 6 | 21 | 12 | 14 | 21 | **淘汰候选** |
| macd_trend | 6 | 18 | 17 | 19 | 19 | **严重警戒** |
| price_ema_momentum | 6 | 19 | 17 | 16 | 19 | **严重警戒** |
| roc_momentum | 6 | 21 | 22 | 21 | 22 | **淘汰候选** |
| rsi_momentum | 6 | 17 | 16 | 17 | 17 | **严重警戒** |
| trend_breakout | 6 | 18 | 17 | 19 | 19 | **严重警戒** |
| volatility_regime_trend | 6 | 18 | 22 | 17 | 22 | **淘汰候选** |
| volume_breakout | 6 | 21 | 18 | 15 | 21 | **淘汰候选** |
| volume_trend | 6 | 23 | 14 | 12 | 23 | **淘汰候选** |

## 最严重的 Model × Symbol 样本

| 模型 | 交易对 | TRAIN | VALIDATION | OOS | 最大值 | 判定 |
|---|---|---:|---:|---:|---:|---|
| volume_trend | DOGEUSDT | 23 | 10 | 12 | 23 | **淘汰候选** |
| roc_momentum | ETHUSDT | 21 | 22 | 18 | 22 | **淘汰候选** |
| volatility_regime_trend | BTCUSDT | 14 | 22 | 9 | 22 | **淘汰候选** |
| higher_high_lower_low | SOLUSDT | 21 | 12 | 9 | 21 | **淘汰候选** |
| roc_momentum | BNBUSDT | 21 | 15 | 21 | 21 | **淘汰候选** |
| volume_breakout | DOGEUSDT | 21 | 8 | 15 | 21 | **淘汰候选** |
| bollinger_breakout | SOLUSDT | 19 | 13 | 9 | 19 | **严重警戒** |
| donchian_breakout | ETHUSDT | 17 | 19 | 9 | 19 | **严重警戒** |
| macd_trend | BNBUSDT | 18 | 17 | 19 | 19 | **严重警戒** |
| price_ema_momentum | BNBUSDT | 19 | 13 | 12 | 19 | **严重警戒** |
| price_ema_momentum | ETHUSDT | 19 | 17 | 16 | 19 | **严重警戒** |
| trend_breakout | SOLUSDT | 18 | 17 | 19 | 19 | **严重警戒** |
| volume_breakout | XRPUSDT | 19 | 13 | 10 | 19 | **严重警戒** |
| bollinger_breakout | BNBUSDT | 18 | 11 | 13 | 18 | **严重警戒** |
| bollinger_breakout | DOGEUSDT | 18 | 15 | 12 | 18 | **严重警戒** |
| donchian_breakout | SOLUSDT | 18 | 17 | 7 | 18 | **严重警戒** |
| ema_slope | ETHUSDT | 18 | 16 | 11 | 18 | **严重警戒** |
| macd_trend | ETHUSDT | 18 | 14 | 9 | 18 | **严重警戒** |
| trend_breakout | DOGEUSDT | 16 | 13 | 18 | 18 | **严重警戒** |
| volatility_regime_trend | ETHUSDT | 12 | 18 | 13 | 18 | **严重警戒** |
