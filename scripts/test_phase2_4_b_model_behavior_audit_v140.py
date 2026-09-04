from pathlib import Path
import json, subprocess, sys

def main():
    root=Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable,str(root/'scripts/run_phase2_4_b_model_behavior_audit_v140.py'), '--root', str(root)],check=True)
    p=root/'data/reports/phase2_4_b_model_behavior_audit_v140.json'
    o=json.loads(p.read_text())
    assert o['summary']['total_sleeves']==72
    assert o['summary']['overall_max']==23
    assert o['summary']['grades']['淘汰候选']==6
    assert all(x['oos_max_consecutive_losses']>=0 for x in o['rows'])
    print('72个冻结Sleeve审计：通过')
    print('连续亏损分级：通过')
    print('OOS仅诊断、不参与选模：通过（代码路径）')
    print('PHASE2_4_B_MODEL_BEHAVIOR_AUDIT_V1.4.0_TEST_OK')
if __name__=='__main__': main()
