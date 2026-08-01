"""Run the consolidated Collector data-foundation completion block."""
from __future__ import annotations
import argparse, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/governance/permanence/certification/collector_data_foundation_completion'

def run(cmd):
 p=subprocess.run(cmd,cwd=ROOT); return {'command':cmd,'return_code':p.returncode,'passed':p.returncode==0}

def main():
 p=argparse.ArgumentParser(); p.add_argument('--strict',action='store_true'); a=p.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
 py=sys.executable
 steps=[]
 steps.append(run([py,'scripts/run_collector_official_release_date_completion_block.py','--strict']))
 steps.append(run([py,'scripts/build_collector_mtgjson_sealed_crosswalk.py']+(['--strict'] if a.strict else [])))
 steps.append(run([py,'scripts/build_collector_ebay_search_contracts.py','--strict']))
 steps.append(run([py,'scripts/audit_collector_source_completeness.py']+(['--strict'] if a.strict else [])))
 summary_path=ROOT/'data/governance/permanence/certification/collector_source_completeness/collector_source_completeness_summary.json'
 source_summary=json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.is_file() else {}
 result={'block_name':'Collector Data Foundation Completion Block','block_version':'1.0.0','generated_at':datetime.now(timezone.utc).isoformat(),'steps':steps,
         'all_steps_passed':all(x['passed'] for x in steps),'source_layer_certified':bool(source_summary.get('source_layer_certified',False)),
         'source_layer_blockers':source_summary.get('source_layer_blockers',''),'ebay_contracts_ready':steps[2]['passed'],
         'ebay_live_collection_executed':False,'forecasting_resume_authorized':False,'purchase_recommendation_authorized':False,'uip_delivery_authorized':False}
 result['status']='PASS_DATA_FOUNDATION_SOURCE_LAYER' if result['all_steps_passed'] and result['source_layer_certified'] else 'REVIEW_REQUIRED'
 (OUT/'collector_data_foundation_completion_summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8'); print(json.dumps(result,indent=2))
 return 1 if a.strict and result['status']!='PASS_DATA_FOUNDATION_SOURCE_LAYER' else 0
if __name__=='__main__': raise SystemExit(main())
