# QuantBot Phase 2.3.5-D-1

## 目的
对 C 阶段锁定的 12 个模型进行完整参数 Grid 研究。TRAIN 扫描全部登记参数组合，每个 Model×Symbol 取 TRAIN Top-5 进入 Validation；按 Validation `total_return - max_drawdown` 选择参数。记录参数边界最优和邻域稳定性作为诊断。Validation Return > 0 且 PF >= 1.0 才进入 FROZEN，否则 HOLD。

**D-1 完全不读取 OOS。** OOS 只允许在后续冻结后进入独立 OOS 阶段。

## 研究规模
12 模型，6 币种，786 个参数组合总量：TRAIN 4716 次；Validation 360 次；合计 5076 次。

## 运行
```bash
cd /www/wwwroot/QuantBot
source venv/bin/activate
python scripts/test_phase2_3_5_d1_parameter_research.py
python scripts/run_phase2_3_5_d1_parameter_research.py --workers 6
```

## 输出
- `data/reports/phase2_3_5_d1_parameter_research.json`
- `data/reports/phase2_3_5_d1_freeze_manifest.json`
- `data/reports/phase2_3_5_d1_summary.md`

## 成本与风险
fee 0.04%，slippage 2 bps，initial equity 10,000U，risk 1%，max position 1，max positions 1。沿用 C 阶段 Fast Backtest Path，其数值等价性由既有测试保障。

## 禁止事项
- 不读取 OOS
- 不扩大参数 Grid
- 不根据 OOS 改参数
- 不按收益单一指标选参数
- 不把边界最优自动视为更优或自动扩大搜索范围
