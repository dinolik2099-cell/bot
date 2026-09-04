# QuantBot Phase 2.3.5 真实数据预检 V1.0

用途：在正式启动 36 个模型的大规模参数研究前，先验证模型池与 QuantBot 现有真实数据、因果检查、Strategy Adapter、Backtest Engine 的完整链路。

默认预检：
- 数据集：`UM_1H_6DC48D541517`
- 品种：`BTCUSDT`
- 窗口：`TRAIN`
- 代表性 K 线：4000 根
- 模型：36 个
- 不进行参数搜索
- 不使用 OOS

执行：

```bash
cd /www/wwwroot/QuantBot
./venv/bin/python scripts/test_phase2_3_5_real_data_preflight.py
```

通过标志：

```text
PHASE2_3_5_REAL_DATA_PREFLIGHT_OK
```

说明：4000 根 K 线是接口/执行链路预检，不代表正式研究结果。正式研究仍必须严格执行 TRAIN → VALIDATION → 冻结 → OOS。
