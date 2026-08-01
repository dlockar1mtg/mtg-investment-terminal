"""Build fail-closed eBay supplemental search contracts for governed Collector displays."""
from __future__ import annotations
import argparse, json, re
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
AUTH=ROOT/'data/governance/permanence/certification/collector_official_release_date_authority/collector_official_release_date_authority.csv'
OUT=ROOT/'data/governance/permanence/certification/collector_ebay_supply_contracts'
EXCLUDES=['pack','packs','case','master case','empty','opened','open box','damaged','repack','single card','commander deck','bundle','sample booster','draft booster','set booster','play booster','japanese','german','french','italian','spanish','portuguese','korean','chinese']

def clean_name(name):
 return re.sub(r'\s+',' ',str(name).replace(' Display','').strip())

def main():
 p=argparse.ArgumentParser(); p.add_argument('--authority',type=Path,default=AUTH); p.add_argument('--output-dir',type=Path,default=OUT); p.add_argument('--strict',action='store_true'); a=p.parse_args()
 out=a.output_dir.resolve(); out.mkdir(parents=True,exist_ok=True)
 auth=pd.read_csv(a.authority,dtype=str,encoding='utf-8-sig').fillna('')
 rows=[]
 for _,r in auth.iterrows():
  name=r.get('box_name',''); base=clean_name(name)
  rows.append({'tcgplayer_product_id':r.get('tcgplayer_product_id',''),'governed_box_name':name,'marketplace_id':'EBAY_US','currency':'USD',
               'search_query':f'"{base}" sealed English','required_positive_terms':'collector booster|box','required_configuration_terms':'box|display','required_condition_terms':'sealed|new',
               'excluded_terms':'|'.join(EXCLUDES),'full_pagination_required':True,'item_detail_enrichment_required':True,'seller_pseudonymization_required':True,
               'quantity_threshold_handling':'PRESERVE_EXACT_ESTIMATE_AND_LOWER_BOUND_SEPARATELY','ambiguous_listing_action':'QUARANTINE',
               'tcgplayer_price_precedence':True,'ebay_role':'SUPPLEMENTAL_MARKETPLACE_SUPPLY_ONLY','contract_status':'READY_FOR_CAPABILITY_TEST'})
 frame=pd.DataFrame(rows); frame.to_csv(out/'collector_ebay_search_contracts.csv',index=False)
 policy={'contract_name':'Collector eBay Supplemental Supply Contract','version':'1.0.0','generated_at':datetime.now(timezone.utc).isoformat(),
         'source_precedence':['TCGCSV_TCGPLAYER_PRICE_PRIMARY','EBAY_SUPPLEMENTAL_SUPPLY'],
         'permitted_metrics':['ebay_active_listing_count','ebay_unique_seller_count','ebay_listed_quantity_lower_bound','ebay_listed_quantity_estimate','ebay_asking_price_distribution','ebay_listing_age','ebay_estimated_sold_quantity_proxy'],
         'prohibited_overrides':['tcg_market_price','tcg_low_price','tcg_mid_price','tcg_high_price','tcg_direct_low_price'],
         'buyer_count_status':'NOT_AVAILABLE_WITH_CURRENT_ACCESS','official_print_run_status':'NOT_PUBLICLY_DISCLOSED','raw_payload_vaulting_required':True,'fail_closed':True}
 (out/'collector_ebay_supply_contract_policy.json').write_text(json.dumps(policy,indent=2)+'\n',encoding='utf-8')
 summary={'block_name':'Collector eBay Search Contract Foundation','block_version':'1.0.0','governed_products':len(frame),'contracts_created':len(frame),'credential_test_executed':False,'listing_collection_executed':False,'status':'PASS_EBAY_CONTRACTS_READY_FOR_CAPABILITY_TEST'}
 (out/'collector_ebay_search_contract_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8'); print(json.dumps(summary,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
