"""Diagnose MTGJSON sealed crosswalk evidence without promoting any match."""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
AUTH=ROOT/'data/governance/permanence/certification/collector_official_release_date_authority/collector_official_release_date_authority.csv'
OUT=ROOT/'data/governance/permanence/certification/collector_mtgjson_sealed_crosswalk'
ROOTS=[ROOT/'data/raw/mtgjson',ROOT/'data_vault/raw/mtg/collector_booster']

def norm_id(v):
 s=str(v).strip(); return s[:-2] if s.endswith('.0') else s

def norm_name(v):
 s=str(v).lower().replace('&',' and ')
 s=re.sub(r'\b(display|box)\b','display',s)
 s=re.sub(r'\buniverse[s]? beyond\b','',s)
 s=re.sub(r'[^a-z0-9]+',' ',s)
 return ' '.join(s.split())

def decode(raw):
 for enc in ('utf-8-sig','utf-16','utf-16-le','utf-16-be'):
  try: return raw.decode(enc),enc
  except UnicodeDecodeError: pass
 raise UnicodeDecodeError('supported-decoders',raw,0,1,'unable to decode')

def walk(obj,path=''):
 if isinstance(obj,dict):
  yield obj,path
  for k,v in obj.items(): yield from walk(v,f'{path}.{k}' if path else str(k))
 elif isinstance(obj,list):
  for i,v in enumerate(obj): yield from walk(v,f'{path}[{i}]')

def ids_from(obj):
 found=set()
 def rec(x):
  if isinstance(x,dict):
   for k,v in x.items():
    lk=str(k).lower().replace('_','')
    if 'tcgplayer' in lk and ('productid' in lk or lk.endswith('id')):
     if isinstance(v,(str,int,float)): found.add(norm_id(v))
     elif isinstance(v,list): found.update(norm_id(z) for z in v if isinstance(z,(str,int,float)))
    rec(v)
  elif isinstance(x,list):
   for z in x: rec(z)
 rec(obj); return {x for x in found if x and x.lower()!='nan'}

def first(d,*keys):
 for k in keys:
  if k in d and d[k] not in (None,'',[],{}): return d[k]
 return ''

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 auth=pd.read_csv(AUTH,dtype=str,encoding='utf-8-sig').fillna('')
 auth['tcgplayer_product_id']=auth['tcgplayer_product_id'].map(norm_id)
 wanted=set(auth.tcgplayer_product_id)
 governed_names={norm_name(r.box_name):r.tcgplayer_product_id for r in auth.itertuples()}
 exact=[]; names=[]; errors=[]; files=0
 for root in ROOTS:
  if not root.exists(): continue
  for fp in root.rglob('*.json'):
   files+=1
   raw=fp.read_bytes()
   try:
    text,enc=decode(raw); obj=json.loads(text)
    for d,path in walk(obj):
     if not isinstance(d,dict): continue
     name=str(first(d,'name','productName')).strip()
     structural=bool(name and any(k in d for k in ('uuid','contents','sealedProductContents','identifiers','category','productSize')))
     if not structural: continue
     base={'source_path':str(fp.relative_to(ROOT)).replace('\\','/'),'source_sha256':hashlib.sha256(raw).hexdigest(),'encoding':enc,'json_path':path,
           'mtgjson_uuid':str(first(d,'uuid','id')),'mtgjson_name':name,'normalized_name':norm_name(name),
           'category':str(first(d,'category','productType','type')),'subtype':str(first(d,'subtype','subType')),
           'release_date_mtgjson':str(first(d,'releaseDate','release_date')),'product_size':str(first(d,'productSize','product_size'))}
     for pid in ids_from(d)&wanted: exact.append({'tcgplayer_product_id':pid,**base})
     if base['normalized_name'] in governed_names: names.append({'tcgplayer_product_id':governed_names[base['normalized_name']],**base})
   except Exception as e:
    errors.append({'source_path':str(fp.relative_to(ROOT)).replace('\\','/'),'source_sha256':hashlib.sha256(raw).hexdigest(),'error':f'{type(e).__name__}: {e}'})
 exact_df=pd.DataFrame(exact).drop_duplicates() if exact else pd.DataFrame(columns=['tcgplayer_product_id'])
 name_df=pd.DataFrame(names).drop_duplicates() if names else pd.DataFrame(columns=['tcgplayer_product_id'])
 exact_df.to_csv(OUT/'collector_mtgjson_exact_id_candidate_evidence.csv',index=False)
 name_df.to_csv(OUT/'collector_mtgjson_exact_name_candidate_evidence.csv',index=False)
 pd.DataFrame(errors).to_csv(OUT/'collector_mtgjson_decode_errors_diagnostic.csv',index=False)
 summary={'files_scanned':files,'exact_id_candidate_rows':len(exact_df),'exact_id_products':exact_df.tcgplayer_product_id.nunique() if len(exact_df) else 0,
          'exact_name_candidate_rows':len(name_df),'exact_name_products':name_df.tcgplayer_product_id.nunique() if len(name_df) else 0,'decode_or_parse_errors':len(errors),
          'promotion_executed':False,'status':'PASS_DIAGNOSTIC_ONLY'}
 (OUT/'collector_mtgjson_crosswalk_diagnostic_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(summary,indent=2))
 return 0
if __name__=='__main__': raise SystemExit(main())
