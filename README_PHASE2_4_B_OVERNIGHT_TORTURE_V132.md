# Phase 2.4-B Overnight Torture V1.3.2

## 本版目的
修复 V1.3.1 暴露的压力测试计算问题后，再进入下一轮最坏情况压力测试。

### V1.3.1 根因
V1.3.1 在循环中使用已被上一场景修改过的 `P.FEE_RATE` / `P.SLIPPAGE_BPS` 作为下一场景基准，导致压力参数递归放大。
例如：
- 基准：0.04% / 2 bps
- 手续费×2 后基准变成 0.08%
- 滑点×3 后继续从 6 bps 计算
- 后续手续费×3+滑点×10 会进一步递归放大

这会制造远超声明场景的成本，并最终出现负资金。

V1.3.2 固定保存基准：
- 手续费：0.04%
- 滑点：2 bps
每个场景均直接从该固定基准计算。

## 账户安全
共享资金引擎新增：
- 资金 <= 0：立即进入破产状态
- 破产后停止新开仓
- 资金不允许以负数继续复利
- 记录原始最低资金、最低资金、破产状态、风险限制拒绝、最大连续亏损

## Monte Carlo / Bootstrap
交易 Bootstrap、7日 Block Bootstrap、多方向同步冲击仍属于路径压力近似。
它们不应被描述成“重新执行完整共享资金 K 线引擎”。
本版重点先保证共享资金正式回测与成本压力场景本身可信。

## 运行前
先运行：
```bash
source venv/bin/activate
python scripts/test_phase2_4_b_overnight_torture_v132.py
```

通过后再运行，例如：
```bash
python scripts/run_phase2_4_b_overnight_torture_v132.py --hours 8 --workers 24 --mc-per-round 2000
```

输出：
- `data/reports/phase2_4_b_overnight_torture_v132.jsonl`
- `data/reports/phase2_4_b_overnight_torture_summary_v132.md`

## 研究纪律
- 只使用 D-1 冻结参数 + TRAIN/VALIDATION
- 不读取 D-2/D-3/OOS
- 不按最好收益选模
- 本阶段优先看本金生存、最大回撤、连续亏损、风险限制和压力成本
