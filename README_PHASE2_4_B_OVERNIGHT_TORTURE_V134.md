# QuantBot Phase 2.4-B Overnight Torture V1.3.4

## 本版目的

V1.3.4 不改变 V1.3.3 的核心压力测试逻辑，只增加**短测/长测双模式**，避免部署后第一次运行就误启动数小时压力测试。

## 默认行为：短测

直接执行：

```bash
python scripts/run_phase2_4_b_overnight_torture_v134.py
```

默认：
- `--mode quick`
- 最多约 5 分钟
- 最多 1 轮
- 组合：`MODEL_4_X6`
- 窗口：TRAIN + VALIDATION
- 场景：基准 + 手续费×3+滑点×10
- 不执行 Monte Carlo / Block Bootstrap / 多方向同步冲击

短测用于确认：数据加载、共享资金回测、成本压力、模型级连续亏损审计、报告输出等主链路正常。

## 完整压力测试

必须显式指定：

```bash
python scripts/run_phase2_4_b_overnight_torture_v134.py \
  --mode full \
  --hours 8 \
  --workers 24 \
  --mc-per-round 2000
```

完整模式保持 4 个组合、5 个成本场景、TRAIN/VALIDATION，并在 VALIDATION 执行尾部模拟。

## 重要说明

当前脚本的数据预加载按 6 个交易对并行，`--workers 24` 是并行池上限；共享资金回测主循环仍按场景顺序执行，因此 24 并不等于 24 个共享资金回测同时运行。

## V1.3.3/V1.3.4 已修复

- 成本场景使用固定基准手续费/滑点，不递归放大。
- 资金 <= 0 时立即进入破产停止路径。
- Bootstrap “最差”分位方向正确。
- 模型×交易对连续亏损单独审计。
- 模型级最大连续亏损 >=21 判定为不合格；16-20 为严重关注。
- OOS/D-2/D-3 不读取。
