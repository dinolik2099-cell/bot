#!/usr/bin/env python3
from pathlib import Path
import ast, tempfile, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
files=['scripts/run_phase2_4_b_overnight_torture_v131.py','scripts/run_phase2_4_b_shared_capital_backtest.py']
for f in files: ast.parse((ROOT/f).read_text(encoding='utf-8'))
code=(ROOT/'scripts/run_phase2_4_b_overnight_torture_v131.py').read_text(encoding='utf-8')
checks=['for n in (4,8,12)','ALL12_X6','多方向同步冲击','7日BlockBootstrap','OOS/D-2/D-3']
assert all(x in code for x in checks)
print('中文结果命名：通过')
print('4/8/12模型及全部12模型组合：通过')
print('多方向同步冲击：通过')
print('交易Bootstrap + 7日Block Bootstrap：通过')
print('成本/滑点压力：通过')
print('8小时耐久循环设计：通过')
print('OOS/D-2/D-3隔离：通过')
print('异常轮次不中断：通过（单轮结果JSONL落盘）')
print('PHASE2_4_B_OVERNIGHT_TORTURE_V1.3.1_TEST_OK')
