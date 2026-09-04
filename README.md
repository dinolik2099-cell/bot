# QuantBot V1

面向 Binance 的研究型量化交易系统 V1。

目标：在 1×、资金安全优先的前提下，研究多模型组合能否提高 200 天资本增长概率；最终再进入模拟盘和 API 实盘。

> V1 默认只做历史回测，不包含真实下单功能。任何 Binance API 交易模块都必须在回测和模拟盘通过后再启用。

## 设计原则

1. 不把 90,000U / 200 天作为强制拟合目标。
2. 安全约束优先于收益：最大回撤、单笔风险、组合风险、连续亏损、数据异常都可以否决交易。
3. 多模型不是简单叠加，而是由市场状态/模型评分/组合风险决定是否启用。
4. 严格避免未来函数：信号只使用已完成 K 线；默认下一根 K 线开盘成交。
5. 回测包含手续费、滑点和仓位限制。
6. 参数研究必须区分 train / validation / out-of-sample，并支持 walk-forward。

## 环境

已针对 Python 3.11 设计。

推荐依赖：

```bash
python -m pip install -r requirements.txt
```

## 第一步：下载研究数据

V1 默认先研究 Binance Spot USDT 交易对，使用官方 public data archive。宽覆盖阶段优先 1h 数据；进入候选策略精测阶段再增加 15m 数据。

```bash
python scripts/download_binance.py --symbols BTCUSDT ETHUSDT SOLUSDT BNBUSDT XRPUSDT DOGEUSDT --interval 1h --start 2021-01 --end 2026-08
```

如果服务器到 `data.binance.vision` 网络较慢，可以把数据下载到服务器后直接放入 `data/raw/`，脚本支持重复运行并跳过已存在文件。

## 第二步：使用当前 Boundary-aware 研究入口

`scripts/run_research.py` 已退役，因为它会绕过 Boundary Lock 和当前 Canonical Backtest Engine 研究链路。

当前研究必须使用各阶段明确的 Boundary-aware 脚本，并保持 TRAIN / VALIDATION / OOS 隔离纪律；不要直接运行已退役的 `scripts/run_research.py`。

## 当前 V1 候选模型

- `trend_breakout`：趋势过滤 + 唐奇安/结构突破
- `trend_pullback`：趋势 + 回调恢复
- `volatility_breakout`：波动率压缩后的扩张突破
- `mean_reversion`：仅作为低相关候选，不预设它最终保留

模型只是 Alpha 候选。最终系统还需要：

- regime / 市场状态层
- portfolio / 组合层
- risk / 风险层
- execution / 执行层

## 回测输出

每个候选组合会输出：

- final_equity
- total_return
- max_drawdown
- profit_factor
- win_rate
- avg_trade
- trades
- max_consecutive_losses
- 200d target hit rate
- 240d target hit rate
- cost sensitivity

## 重要

第一轮结果只能用于研究，不能直接用于实盘。下一阶段必须加入：

- 更细的 15m/5m 执行回测
- bid/ask / spread 模型
- 真实手续费档位
- funding（如果最终选择 USDⓈ-M Futures）
- walk-forward
- Monte Carlo
- 压力测试
- paper trading
- API 权限隔离、IP 白名单、Kill Switch
