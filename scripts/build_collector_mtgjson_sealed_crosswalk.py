"""Build an exact-TCGplayer-ID MTGJSON sealed-product crosswalk from preserved JSON sources."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
AUTH=ROOT/'data/governance/permanence/certification/collector_official_release_date_authority/collector_official_release_date_authority.csv'
OUT=ROOT/'data/governance/permanence/certification/collector_mtgjson_sealed_crosswalk'
SEARCH_ROOTS=[ROOT/'data/raw/mtgjson',ROOT/'data_vault/raw/mtg/collector_booster']

def norm(v):
 s=str(v).strip(); return s[:-2] if s.endswith('.0') else s

def walk(obj,path=''):
 if isinstance(obj,dict):
  yield obj,path
  for k,v in obj.items(): yield from walk(v,f'{path}.{k}' if path else k)
 elif isinstance(obj,list):
  for i,v in enumerate(obj): yield from walk(v,f'{path}[{i}]')

def find_tcg_ids(d):
 vals=[]
 for k,v in d.items():
  lk=str(k).lower().replace('_','')
  if 'tcgplayer' in lk and ('productid' in lk or lk.endswith('id')):
   if isinstance(v,(str,int,float)): vals.append(norm(v))
   elif isinstance(v,list): vals.extend(norm(x) for x in v if isinstance(x,(str,int,float)))
 return {x for x in vals if x and x.lower()!='nan'}

def first(d,*keys):
 for k in keys:
  if k in d and d[k] not in (None,'',[],{}): return d[k]
 return ''

def main():
 p=argparse.ArgumentParser(); p.add_argument('--authority',type=Path,default=AUTH); p.add_argument('--output-dir',type=Path,default=OUT); p.add_argument('--strict',action='store_true'); a=p.parse_args()
 out=a.output_dir.resolve(); out.mkdir(parents=True,exist_ok=True)
 auth=pd.read_csv(a.authority,dtype=str,encoding='utf-8-sig').fillna(''); auth['tcgplayer_product_id']=auth['tcgplayer_product_id'].map(norm)
 wanted=set(auth['tcgplayer_product_id']); matches={x:[] for x in wanted}; files=0; errors=[]
 for root in SEARCH_ROOTS:
  if not root.exists(): continue
  for fp in root.rglob('*.json'):
   files+=1
   try:
    raw=fp.read_bytes(); obj=json.loads(raw.decode('utf-8-sig'))
    for d,path in walk(obj):
     ids=find_tcg_ids(d)&wanted
     if not ids: continue
     row={'source_path':str(fp.relative_to(ROOT)).replace('\\','/'),'source_sha256':hashlib.sha256(raw).hexdigest(),'json_path':path,
          'mtgjson_uuid':str(first(d,'uuid','id')),'mtgjson_name':str(first(d,'name','productName')),
          'category':str(first(d,'category','productType','type')),'subtype':str(first(d,'subtype','subType')),
          'release_date_mtgjson':str(first(d,'releaseDate','release_date')),'product_size':str(first(d,'productSize','product_size')),
          'contents_json':json.dumps(first(d,'contents','sealedProductContents','packContents'),ensure_ascii=False,sort_keys=True) if first(d,'contents','sealedProductContents','packContents')!='' else ''}
     for pid in ids: matches[pid].append(row)
   except Exception as e: errors.append({'source_path':str(fp),'error':f'{type(e).__name__}: {e}'})
 rows=[]
 for _,r in auth.iterrows():
  pid=r['tcgplayer_product_id']; candidates=matches.get(pid,[])
  exact=len(candidates)==1; c=candidates[0] if exact else {}
  rows.append({'tcgplayer_product_id':pid,'box_name':r.get('box_name',''),'candidate_count':len(candidates),**c,
               'configuration_match_status':'EXACT_TCGPLAYER_ID_MATCH' if exact else 'NO_EXACT_MATCH' if not candidates else 'MULTIPLE_EXACT_ID_CANDIDATES',
               'structural_verification_status':'MTGJSON_STRUCTURE_VERIFIED' if exact else 'REVIEW_REQUIRED'})
 frame=pd.DataFrame(rows); unresolved=frame[frame['structural_verification_status']!='MTGJSON_STRUCTURE_VERIFIED']
 frame.to_csv(out/'collector_mtgjson_sealed_crosswalk.csv',index=False); unresolved.to_csv(out/'collector_mtgjson_sealed_crosswalk_review.csv',index=False); pd.DataFrame(errors).to_csv(out/'collector_mtgjson_source_errors.csv',index=False)
 summary={'block_name':'Collector MTGJSON Sealed Crosswalk','block_version':'1.0.0','generated_at':datetime.now(timezone.utc).isoformat(),'governed_products':len(frame),'source_json_files_scanned':files,'exact_id_matches':int((frame.structural_verification_status=='MTGJSON_STRUCTURE_VERIFIED').sum()),'review_required':len(unresolved),'source_errors':len(errors),'status':'PASS_MTGJSON_SEALED_CROSSWALK' if len(unresolved)==0 else 'REVIEW_REQUIRED'}
 (out/'collector_mtgjson_sealed_crosswalk_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8'); print(json.dumps(summary,indent=2)); return 1 if a.strict and len(unresolved) else 0
if __name__=='__main__': raise SystemExit(main())
