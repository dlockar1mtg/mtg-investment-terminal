"""Run the non-destructive Collector historical source inventory block."""
from __future__ import annotations
import argparse, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/governance/permanence/certification/collector_historical_source_inventory"
def main():
    p=argparse.ArgumentParser(); p.add_argument("--strict",action="store_true"); a=p.parse_args()
    cmd=[sys.executable,"scripts/audit_collector_historical_sources.py"]+(["--strict"] if a.strict else [])
    r=subprocess.run(cmd,cwd=ROOT)
    payload={"block_name":"Collector Historical Source Inventory Block","block_version":"1.0.0","generated_at":datetime.now(timezone.utc).isoformat(),"steps":[{"command":cmd,"return_code":r.returncode,"passed":r.returncode==0}],"all_steps_passed":r.returncode==0,"historical_reconstruction_executed":False,"historical_append_authorized":False,"forecasting_resume_authorized":False,"purchase_recommendation_authorized":False,"status":"PASS_HISTORICAL_SOURCE_INVENTORY" if r.returncode==0 else "REVIEW_REQUIRED"}
    OUT.mkdir(parents=True,exist_ok=True); (OUT/"collector_historical_source_inventory_block_summary.json").write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8"); print(json.dumps(payload,indent=2)); return r.returncode
if __name__=="__main__": raise SystemExit(main())
