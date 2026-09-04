# QuantBot Phase 2.3.5-D-2

## 目的
对 Phase 2.3.5-D-1 已冻结的 72 个 Model×Symbol 参数配置执行一次 OOS 样本外验证。D-2 不重新搜索参数、不改变冻结参数、不根据 OOS 结果回调 D-1。

## 研究边界
只读取 `OOS` 窗口。当前 Boundary Lock 的有效 OOS 为 2026-01-01 00:00 UTC → 2026-07-31 23:00 UTC。OOS 不参与任何参数选择。

## 输入
- `data/reports/research_boundary_lock.json`
- `data/reports/phase2_3_5_d1_freeze_manifest.json`
- 当前 canonical UM 1H 数据

Freeze manifest 必须：
- phase = `2.3.5-D-1`
- dataset_id 与 Boundary Lock 一致
- 完整覆盖 12×6 = 72 个 Model×Symbol
- 每条记录 status=`FROZEN`
- `oos_authorized=true`

## OOS执行
- 使用 D-1 冻结参数原样执行
- fee = 0.04%
- slippage = 2 bps
- initial equity = 10,000U
- risk = 1%
- max position = 1
- max positions = 1
- 使用 canonical `BacktestEngine` + 已验证的 strategy adapter
- 不进行新的参数搜索

## 缺口纪律
不合成 K 线。若未来 OOS 数据包含配置缺口，禁止在缺口后的第一根实际 K 线使用缺口前信息直接开新仓；缺口信息同时写入结果。当前已锁定数据的 SOL/XRP 缺口位于 2022 年，不在当前 OOS 窗口。

## 输出
- `data/reports/phase2_3_5_d2_oos_validation.json`
- `data/reports/phase2_3_5_d2_oos_equity_curves.jsonl`
- `data/reports/phase2_3_5_d2_oos_trades.jsonl`
- `data/reports/phase2_3_5_d2_summary.md`

资金曲线和交易明细单独保存，为后续模型相关性与失败交易研究提供输入。

## 验收
成功标记：`PHASE2_3_5_D2_OOS_VALIDATION_OK`

D-2 的 PASS 只表示 72 个冻结配置均完成 OOS 计算且无执行错误，不表示策略性能通过。性能评价由后续研究规则决定，不能用 OOS 结果回改 D-1。
