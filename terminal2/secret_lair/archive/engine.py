from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
import json
import shutil
import numpy as np
import pandas as pd
from terminal2.config import ROOT_DIR,TCGCSV_ARCHIVE_BASE_URL,TCGCSV_ARCHIVE_START_DATE
from terminal2.sources.tcgcsv_archive import download_archive,extract_archive,parse_prices_file,get_first,as_float,month_starts
from terminal2.secret_lair.master_database.config import PRODUCT_MAP_PATH
from terminal2.secret_lair.pricing import PRICE_PATH,PRICE_COLUMNS,load_price_observations
from terminal2.secret_lair.registry import REGISTRY_PATH,load_secret_lair_registry
from terminal2.secret_lair.datetime_utils import date_string_series,to_utc_naive_series
from terminal2.secret_lair.archive.contracts import ARCHIVE_CONTRACTS
ROOT=Path(ROOT_DIR)/'data'/'terminal2'/'secret_lair_archive'
RAW_PATH=ROOT/'raw_prices.csv';LOG_PATH=ROOT/'download_log.csv';BACKUP_ROOT=ROOT/'backups'
@dataclass(frozen=True)
class ArchiveBuildResult: datasets:dict[str,pd.DataFrame]; raw_prices:pd.DataFrame; import_candidates:pd.DataFrame; apply_ready:bool

def _empty(cols):return pd.DataFrame(columns=list(cols))
def _read(path,cols=()):
 if not Path(path).exists():return _empty(cols)
 try:f=pd.read_csv(path)
 except pd.errors.EmptyDataError:return _empty(cols)
 for c in cols:
  if c not in f:f[c]=pd.NA
 return f


def _contract_empty(name):return _empty(ARCHIVE_CONTRACTS[name].required_columns)
def _conform(name,frame):
 required=ARCHIVE_CONTRACTS[name].required_columns
 if frame is None or (frame.empty and len(frame.columns)==0):return _contract_empty(name)
 f=frame.copy()
 for c in required:
  if c not in f:f[c]=pd.NA
 return f

def _choose(rows):
 if not rows:return None
 for row in rows:
  subtype=str(get_first(row,['subTypeName','sub_type_name']) or '').lower()
  if subtype in ('','normal'):return row
 return rows[0]

def ingest_snapshot(snapshot_date,product_map,force_download=False,force_extract=False):
 audit={'snapshot_date':snapshot_date,'status':'started','download_status':'','extract_status':'','files_checked':0,'rows_found':0,'message':''}
 try:
  _,audit['download_status']=download_archive(snapshot_date,force=force_download)
  root,audit['extract_status']=extract_archive(snapshot_date,force=force_extract)
  rows=[]
  for (category,group),mapped in product_map.groupby(['tcgcsv_category_id','tcgcsv_group_id']):
   path=root/str(category)/str(group)/'prices'
   if not path.exists():continue
   audit['files_checked']+=1
   payload=parse_prices_file(path); by={}
   for r in payload:
    pid=str(get_first(r,['productId','product_id','productID']))
    if pid and pid!='None':by.setdefault(pid,[]).append(r)
   for _,m in mapped.iterrows():
    pid=str(m['tcgplayer_product_id']); chosen=_choose(by.get(pid,[]))
    if not chosen:continue
    market=as_float(get_first(chosen,['marketPrice','market_price'])) or as_float(get_first(chosen,['midPrice','mid_price'])) or as_float(get_first(chosen,['lowPrice','low_price']))
    low=as_float(get_first(chosen,['lowPrice','low_price']))
    if not market or market<=0:continue
    rows.append({'observation_date':snapshot_date,'secret_lair_id':m['secret_lair_id'],'source_name':'tcgcsv_archive','market_price':round(float(market),2),'low_price':round(float(low),2) if low else np.nan,'tcgplayer_product_id':pid,'tcgcsv_group_id':str(group),'tcgcsv_category_id':str(category),'source_record_id':pid,'price_data_quality':90,'raw_payload':json.dumps(chosen,default=str)})
  audit['rows_found']=len(rows);audit['status']='success'
  return pd.DataFrame(rows),audit
 except Exception as e:
  audit['status']='failed';audit['message']=str(e);return pd.DataFrame(),audit

def _monthly(raw):
 if raw.empty:return _empty(('price_month','secret_lair_id','source_name','market_price','low_price','observation_count','latest_observation_date'))
 f=raw.copy();f['_date']=to_utc_naive_series(f['observation_date']);f['price_month']=f['_date'].dt.to_period('M').astype(str)
 return f.sort_values('_date').groupby(['price_month','secret_lair_id','source_name'],as_index=False).agg(market_price=('market_price','last'),low_price=('low_price','last'),observation_count=('market_price','count'),latest_observation_date=('observation_date','last'))

def _coverage(raw,pmap):
 base=pmap[['secret_lair_id','product_name']].drop_duplicates('secret_lair_id')
 if raw.empty:
  for c,v in [('observation_count',0),('month_count',0),('first_observation_date',''),('latest_observation_date',''),('history_span_days',0),('coverage_tier','None')]:base[c]=v
  return base
 f=raw.copy();f['_date']=to_utc_naive_series(f['observation_date']);f['_month']=f['_date'].dt.to_period('M').astype(str)
 c=f.groupby('secret_lair_id').agg(observation_count=('market_price','count'),month_count=('_month','nunique'),first_observation_date=('_date','min'),latest_observation_date=('_date','max')).reset_index();c['history_span_days']=(c['latest_observation_date']-c['first_observation_date']).dt.days;c['first_observation_date']=date_string_series(c['first_observation_date']);c['latest_observation_date']=date_string_series(c['latest_observation_date']);c['coverage_tier']=np.select([c['month_count'].ge(18),c['month_count'].ge(6),c['month_count'].ge(2)],['Deep History','Historical Ready','Emerging History'],default='Current Only')
 return base.merge(c,on='secret_lair_id',how='left').fillna({'observation_count':0,'month_count':0,'history_span_days':0,'coverage_tier':'None'})

def _gaps(monthly,pmap):
 rows=[]
 for sid,g in monthly.groupby('secret_lair_id'):
  months=pd.PeriodIndex(g['price_month'],freq='M'); expected=pd.period_range(months.min(),months.max(),freq='M'); name=pmap.loc[pmap['secret_lair_id'].eq(sid),'product_name'].iloc[0] if pmap['secret_lair_id'].eq(sid).any() else ''
  for m in expected.difference(months):rows.append({'secret_lair_id':sid,'product_name':name,'missing_month':str(m),'gap_type':'Internal Missing Month'})
 return pd.DataFrame(rows,columns=['secret_lair_id','product_name','missing_month','gap_type'])

def _conflicts(raw):
 if raw.empty:return _empty(('observation_date','secret_lair_id','source_count','minimum_price','maximum_price','price_spread_pct'))
 g=raw.groupby(['observation_date','secret_lair_id']).agg(source_count=('source_name','nunique'),minimum_price=('market_price','min'),maximum_price=('market_price','max')).reset_index();g['price_spread_pct']=np.where(g['minimum_price'].gt(0),(g['maximum_price']-g['minimum_price'])/g['minimum_price'],0);return g[(g['source_count']>1)&(g['price_spread_pct']>.25)]

def build_secret_lair_archive(start_date=None,end_date=None,download=False,force=False):
 pmap=_read(PRODUCT_MAP_PATH)
 required=['secret_lair_id','tcgplayer_product_id','tcgcsv_category_id','tcgcsv_group_id','product_name']
 for c in required:
  if c not in pmap:pmap[c]=pd.NA
 pmap=pmap.dropna(subset=required[:4]).copy()
 raw=_read(RAW_PATH,ARCHIVE_CONTRACTS['secret_lair_archive_raw_prices'].required_columns);logs=_read(LOG_PATH,ARCHIVE_CONTRACTS['secret_lair_archive_download_log'].required_columns)
 if download:
  new=[];aud=[]
  for d in month_starts(start_date or TCGCSV_ARCHIVE_START_DATE,end_date):
   if not force and not logs.empty and ((logs['snapshot_date'].astype(str)==d)&(logs['status'].eq('success'))).any():continue
   frame,a=ingest_snapshot(d,pmap,force,force);aud.append(a)
   if not frame.empty:new.append(frame)
  if new:
   raw_frames=[frame for frame in [raw,*new] if frame is not None and not frame.empty]
   raw=pd.concat(raw_frames,ignore_index=True,sort=False) if raw_frames else _contract_empty('secret_lair_archive_raw_prices')
  if aud:
   audit_frame=pd.DataFrame(aud)
   log_frames=[frame for frame in [logs,audit_frame] if frame is not None and not frame.empty]
   logs=pd.concat(log_frames,ignore_index=True,sort=False) if log_frames else _contract_empty('secret_lair_archive_download_log')
 raw=raw.drop_duplicates(['observation_date','secret_lair_id','source_name'],keep='last') if not raw.empty else _contract_empty('secret_lair_archive_raw_prices')
 logs=logs.drop_duplicates('snapshot_date',keep='last') if not logs.empty else _contract_empty('secret_lair_archive_download_log')
 ROOT.mkdir(parents=True,exist_ok=True);raw.to_csv(RAW_PATH,index=False);logs.to_csv(LOG_PATH,index=False)
 monthly=_monthly(raw);coverage=_coverage(raw,pmap);gaps=_gaps(monthly,pmap);conflicts=_conflicts(raw)
 registry,_=load_secret_lair_registry(REGISTRY_PATH)
 valid_registry_ids=set(registry['secret_lair_id'].astype(str)) if not registry.empty else set()
 cand=raw.copy()
 if cand.empty:cand=_empty(('observation_date','secret_lair_id','source_name','market_price','low_price','price_data_quality','import_eligible','import_reason'))
 else:
  cand['price_data_quality']=pd.to_numeric(cand.get('price_data_quality',90),errors='coerce').fillna(90)
  positive_price=pd.to_numeric(cand['market_price'],errors='coerce').gt(0)
  registry_match=cand['secret_lair_id'].astype(str).isin(valid_registry_ids)
  cand['import_eligible']=positive_price & registry_match
  cand['import_reason']=np.select(
   [~positive_price,~registry_match],
   ['Invalid or non-positive market price','Master Database product is not present in the production registry'],
   default='Valid mapped historical archive observation'
  )
  cand=cand[['observation_date','secret_lair_id','source_name','market_price','low_price','price_data_quality','import_eligible','import_reason']]
 ready=int(coverage['coverage_tier'].isin(['Historical Ready','Deep History']).sum()) if not coverage.empty else 0
 summary=pd.DataFrame([{'snapshot_date':datetime.now(timezone.utc).date().isoformat(),'mapped_product_count':pmap['secret_lair_id'].nunique(),'archive_observation_count':len(raw),'covered_product_count':int(coverage['observation_count'].gt(0).sum()),'historical_ready_count':ready,'gap_count':len(gaps),'conflict_count':len(conflicts),'import_candidate_count':int(cand['import_eligible'].sum()) if not cand.empty else 0,'apply_ready':bool(len(cand)>0)}])
 sources=pd.DataFrame([{'source_name':'tcgcsv_archive','base_url':TCGCSV_ARCHIVE_BASE_URL,'start_date':TCGCSV_ARCHIVE_START_DATE,'enabled':True,'status':'Configured'}])
 ds={'secret_lair_archive_sources':sources,'secret_lair_archive_download_log':logs,'secret_lair_archive_raw_prices':raw,'secret_lair_archive_monthly_prices':monthly,'secret_lair_archive_coverage':coverage,'secret_lair_archive_gaps':gaps,'secret_lair_archive_conflicts':conflicts,'secret_lair_archive_import_candidates':cand,'secret_lair_archive_summary':summary}
 ds={name:_conform(name,frame) for name,frame in ds.items()}
 return ArchiveBuildResult(ds,ds['secret_lair_archive_raw_prices'],ds['secret_lair_archive_import_candidates'],bool(summary.iloc[0]['apply_ready']))

def apply_archive_to_production(result=None):
 result=result or build_secret_lair_archive();cand=result.import_candidates
 if not result.apply_ready:raise RuntimeError('Archive has no eligible import candidates.')
 registry,_=load_secret_lair_registry(REGISTRY_PATH)
 valid_ids=set(registry['secret_lair_id'].astype(str)) if not registry.empty else set()
 existing,_=load_price_observations(PRICE_PATH)
 orphan_existing=int((~existing['secret_lair_id'].astype(str).isin(valid_ids)).sum()) if not existing.empty else 0
 existing=existing[existing['secret_lair_id'].astype(str).isin(valid_ids)].copy() if not existing.empty else existing
 new=cand[cand['import_eligible'] & cand['secret_lair_id'].astype(str).isin(valid_ids)].copy()
 new['listing_count']=pd.NA;new['sales_count_30d']=pd.NA;new['currency']='USD';new['source_url']='';new['source_record_id']='';new['notes']='Terminal 2.10.0b registry-validated historical archive import'
 new=new[list(PRICE_COLUMNS)]
 frames=[frame for frame in [existing,new] if frame is not None and not frame.empty]
 combined=pd.concat(frames,ignore_index=True,sort=False) if frames else _empty(PRICE_COLUMNS)
 combined=combined.drop_duplicates(['observation_date','secret_lair_id','source_name'],keep='last')
 BACKUP_ROOT.mkdir(parents=True,exist_ok=True)
 if PRICE_PATH.exists():shutil.copy2(PRICE_PATH,BACKUP_ROOT/f'secret_lair_price_observations_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}.csv')
 combined.to_csv(PRICE_PATH,index=False);return len(new),len(combined),orphan_existing
