"""Run safe monthly history and historical bridge certification."""
from __future__ import annotations
import argparse, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_historical_bridge_certification"


def main():
    p=argparse.ArgumentParser(description="Run Collector historical bridge certification block")
    p.add_argument("--strict",action="store_true")
    a=p.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
    commands=[
        [sys.executable,"scripts/run_collector_safe_monthly_history_block.py","--strict"],
        [sys.executable,"scripts/build_collector_historical_bridge_certification.py"] + (["--strict"] if a.strict else []),
    ]
    steps=[]
    for cmd in commands:
        r=subprocess.run(cmd,cwd=ROOT)
        steps.append({"command":cmd,"return_code":r.returncode,"passed":r.returncode==0})
        if r.returncode!=0: break
    summary={
        "block_name":"Collector Historical Bridge Certification Block",
        "block_version":"1.0.0",
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "steps":steps,
        "all_steps_passed":all(x["passed"] for x in steps) and len(steps)==len(commands),
        "historical_append_executed":False,
        "historical_append_authorized":False,
        "forecasting_resume_authorized":False,
        "purchase_recommendation_authorized":False,
    }
    summary["status"]="PASS_HISTORICAL_BRIDGE_CANDIDATE_ONLY" if summary["all_steps_passed"] else "REVIEW_REQUIRED"
    (OUT/"collector_historical_bridge_block_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))
    return 0 if summary["all_steps_passed"] else 1

if __name__=="__main__": raise SystemExit(main())
