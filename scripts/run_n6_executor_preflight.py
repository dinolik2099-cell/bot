"""N6 non-OOS preflight only.

This command intentionally validates the committed freeze chain and exits.  It
does not create a data loader, backtest engine, evaluator, or research result.
Formal execution requires a separate, explicitly authorized future entrypoint.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from quantbot.research.plan_executor import preflight_summary

def main():
    ap=argparse.ArgumentParser(description='Validate N3/N5 for future non-OOS execution; performs no research.')
    ap.add_argument('--plan',default=str(ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json'))
    ap.add_argument('--freeze',default=str(ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json'))
    ap.add_argument('--boundary-lock',default=str(ROOT/'data/reports/research_boundary_lock.json'))
    args=ap.parse_args()
    boundary_lock=json.loads(Path(args.boundary_lock).read_text(encoding='utf-8'))
    summary=preflight_summary(args.plan,args.freeze,boundary_lock)
    print('N6_PREFLIGHT_OK')
    for key in sorted(summary): print(f'{key}={summary[key]}')

if __name__=='__main__': main()
