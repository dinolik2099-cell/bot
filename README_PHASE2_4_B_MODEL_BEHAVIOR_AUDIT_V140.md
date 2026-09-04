# QuantBot Phase 2.4-B V1.4.0

模型行为/连续亏损审计。

用途：对 D1 冻结的 72 个 Model × Symbol 做行为审计，不重新参数搜索，不修改冻结参数，不使用 OOS 选模。

输入：
- data/reports/phase2_3_5_d1_freeze_manifest.json
- data/reports/phase2_3_5_d2_oos_validation.json

运行：
```bash
python scripts/test_phase2_4_b_model_behavior_audit_v140.py
python scripts/run_phase2_4_b_model_behavior_audit_v140.py
```

连续亏损判定：
- <=10 合格
- 11-15 警戒
- 16-20 严重警戒
- >=21 淘汰候选

注意：本版本的“淘汰候选”是行为审查结果，不自动修改 D1 freeze manifest，也不自动删除模型。
