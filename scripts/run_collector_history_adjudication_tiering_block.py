"""Run bridged-history validation followed by adjudication and dynamic tiering."""
from __future__ import annotations
import argparse, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/governance/permanence/certification/collector_history_adjudication_tiering"

def main():
    p=argparse.ArgumentParser(); p.add_argument("--strict",action="store_true"); a=p.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
    commands=[[sys.executable,"scripts/run_collector_historical_bridge_certification_block.py","--strict"],[sys.executable,"scripts/adjudicate_collector_history_and_build_tiers.py"]]
    if a.strict: commands[-1].append("--strict")
    steps=[]
    for cmd in commands:
        result=subprocess.run(cmd,cwd=ROOT); steps.append({"command":cmd,"return_code":result.returncode,"passed":result.returncode==0})
        if result.returncode!=0: break
    passed=all(x["passed"] for x in steps) and len(steps)==len(commands)
    summary={"block_name":"Collector History Adjudication and Tiering Block","block_version":"1.0.0","generated_at":datetime.now(timezone.utc).isoformat(),"steps":steps,"all_steps_passed":passed,"historical_append_executed":False,"purchase_recommendation_authorized":False,"uip_delivery_authorized":False,"status":"PASS_HISTORY_ADJUDICATION_TIERING_CANDIDATE_ONLY" if passed else "REVIEW_REQUIRED"}
    (OUT/"collector_history_adjudication_tiering_block_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8"); print(json.dumps(summary,indent=2)); return 0 if passed else 1
if __name__=="__main__": raise SystemExit(main())
