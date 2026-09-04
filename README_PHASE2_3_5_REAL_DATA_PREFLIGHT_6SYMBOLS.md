# Phase 2.3.5-B：六币种 × 36 模型真实数据预检

本阶段在 ModelPool V1.1 与单币种真实数据预检通过后，对完整目标宇宙做逐币种独立预检。

## 目标

- BTCUSDT / ETHUSDT / BNBUSDT / SOLUSDT / XRPUSDT / DOGEUSDT
- 每个币种 36 个模型，共 **216 个组合**
- 默认 TRAIN 每个币种前 1500 根真实 1H K线用于执行链预检
- `--rows 0` 可改为整个窗口，但会明显增加运行时间
- SOL/XRP 的历史缺口不补K线，并在缺口前后做局部执行链检查

## 检查项目

1. OHLCV 字段、时间排序、重复时间
2. NaN / Inf / 非法价格 / 负成交量
3. 策略输出长度、索引和字段
4. 非零信号的止损/止盈有限性
5. 未来数据敏感性检查
6. Strategy Adapter 的严格 pre-T 历史约束
7. Backtest Engine 的 T OPEN 执行链
8. 基准手续费 0.04% + 滑点 2bps
9. SOL/XRP 历史缺口政策

## 研究边界

- 不做参数搜索
- 不做模型选择
- 不改变 Phase 2.3 已冻结参数
- 不使用 OOS 做筛选
- 本阶段收益率、回撤、PF 仅用于发现执行/接口异常，**不是正式研究结论**

## 为什么逐币种独立进程

每个币种使用独立 Python 进程，避免模型注册表和其他全局状态在连续多币种运行时互相污染。这样也更容易定位单一币种问题。

## 运行

```bash
cd /www/wwwroot/QuantBot
bash scripts/run_phase2_3_5_real_data_preflight_6symbols.sh
```

可选参数：

```bash
bash scripts/run_phase2_3_5_real_data_preflight_6symbols.sh --rows 1500 --gap-probe-rows 120
```

最终报告：

`data/reports/phase2_3_5_real_data_preflight_6symbols.json`

成功标志：

`PHASE2_3_5_REAL_DATA_PREFLIGHT_6SYMBOLS_OK`
