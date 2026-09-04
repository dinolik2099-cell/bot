# QuantBot Phase 2.4-A V1.0.3 冻结Sleeve组合研究 V1.0

## 目的
在不读取OOS、不修改D-1冻结参数的前提下，使用冻结的72个Model×Symbol sleeves重新评估TRAIN与VALIDATION，建立Validation-only相关性诊断和预声明组合候选。

## 严格边界
- 输入：`data/reports/phase2_3_5_d1_freeze_manifest.json`、`data/reports/research_boundary_lock.json`、TRAIN/VALIDATION市场数据。
- 不读取D-2 OOS报告、不读取D-3 OOS分析、不读取OOS市场数据。
- 不修改D-1冻结参数。
- Validation只用于组合候选研究；OOS保留给后续冻结后的组合验证。
- 当前组合曲线是独立策略sleeve归一化等权组合，不等于共享资金的真实多仓执行。

## 预声明Validation候选门槛
- Return > 0
- PF >= 1.0
- Max DD <= 35%
- Trades >= 20

组合候选使用：Validation `Return - DD` 排序，并对多元组合使用绝对相关性 <= 0.70、单币最多2个sleeve、单模型最多2个sleeve。

## 运行
```bash
cd /www/wwwroot/QuantBot
source venv/bin/activate
python scripts/test_phase2_4_a_frozen_sleeve_research.py
python scripts/run_phase2_4_a_frozen_sleeve_research.py --workers 6
```

## 输出
- `data/reports/phase2_4_a_frozen_sleeve_research.json`
- `data/reports/phase2_4_a_sleeve_equity_curves.jsonl`
- `data/reports/phase2_4_a_summary.md`

## 下一阶段
Phase 2.4-B：把冻结的组合候选接入真正的共享资金/多仓 Portfolio + Risk Engine，处理同时持仓、总风险、单币暴露、相关资产暴露和资金分配；组合冻结后再进入OOS组合验证。
