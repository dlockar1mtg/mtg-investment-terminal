import hashlib
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
from terminal2.secret_lair.identifiers import normalize_text,slug
from terminal2.secret_lair.registry import REGISTRY_PATH,load_secret_lair_registry
from terminal2.secret_lair.backfill.sources import SOURCE_CATALOG_PATH
from .config import DISCOVERY_CONFIG_PATH,DISCOVERY_STATE_PATH,DISCOVERY_CACHE_ROOT,DISCOVERY_RAW_ROOT,DISCOVERY_STAGE_PATH,load_discovery_config,parse_query
from .connectors import get_discovery_connector
from .http_client import CachedHttpClient
from .parsers import COLUMNS,parse_discovery_payload
@dataclass(frozen=True)
class DiscoveryBuildResult: datasets:dict[str,pd.DataFrame]; config_exists:bool
@dataclass(frozen=True)
class DiscoveryStageResult: output_path:str; staged_rows:int
SOURCE_HEALTH_COLUMNS=['source_name','connector_type','parser_name','enabled','status','records_received','records_normalized','from_cache','raw_snapshot_path','error_message']
RUN_LOG_COLUMNS=['run_id','source_name','started_at_utc','completed_at_utc','status','records_received','records_normalized','from_cache','raw_snapshot_path','error_message']
def has_enabled_discovery_sources(config_path=DISCOVERY_CONFIG_PATH):
    cfg,_=load_discovery_config(config_path)
    return bool(not cfg.empty and 'enabled' in cfg.columns and cfg['enabled'].fillna(False).astype(bool).any())
def _cid(v):return 'SLD'+hashlib.sha1(v.encode()).hexdigest()[:12].upper()
def _raw(name,data,ctype,run):
    suffix='.html' if 'html' in ctype.lower() else '.jsonl' if 'ndjson' in ctype.lower() else '.json' if 'json' in ctype.lower() else '.bin'; p=DISCOVERY_RAW_ROOT/name/f'{run}{suffix}'; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data); return str(p)
def _known():
    exact={}; names={}; reg,_=load_secret_lair_registry(REGISTRY_PATH)
    if not reg.empty:
        for _,r in reg.iterrows():
            sk=(normalize_text(r.get('source_name')).lower(),normalize_text(r.get('source_record_id')))
            if all(sk):exact[sk]=str(r['secret_lair_id'])
            nk=(slug(r.get('drop_name')),slug(r.get('variant_name')),normalize_text(r.get('finish')).lower())
            if nk[0]:names[nk]=str(r['secret_lair_id'])
    if SOURCE_CATALOG_PATH.exists():
        f=pd.read_csv(SOURCE_CATALOG_PATH,dtype=str).fillna('')
        for _,r in f.iterrows():
            k=(normalize_text(r.get('source_name')).lower(),normalize_text(r.get('source_record_id')))
            if all(k):exact.setdefault(k,'')
    return exact,names
def _classify(catalog):
    cc=list(COLUMNS)+['candidate_status','candidate_confidence','candidate_reason']; kc=list(COLUMNS)+['known_match_type','known_secret_lair_id']; fc=['conflict_id','source_name','source_record_id','conflict_type','message']
    if catalog.empty:return pd.DataFrame(columns=cc),pd.DataFrame(columns=kc),pd.DataFrame(columns=fc)
    exact,names=_known(); cand=[]; known=[]; conflicts=[]
    dup=catalog[catalog.duplicated(['source_name','source_record_id'],keep=False)]
    for _,r in dup.iterrows():conflicts.append({'conflict_id':_cid(f"dup|{r['source_name']}|{r['source_record_id']}"),'source_name':r['source_name'],'source_record_id':r['source_record_id'],'conflict_type':'duplicate_source_identity','message':'The same source identity was discovered more than once.'})
    for _,r in catalog.drop_duplicates(['source_name','source_record_id']).iterrows():
        sk=(str(r['source_name']).lower(),str(r['source_record_id'])); nk=(slug(r['drop_name']),slug(r['variant_name']),normalize_text(r['finish']).lower()); missing=[x for x in ('source_record_id','drop_name','variant_name','finish') if not normalize_text(r.get(x))]
        if missing:
            conflicts.append({'conflict_id':_cid(f"missing|{r['source_name']}|{r['source_record_id']}|{'|'.join(missing)}"),'source_name':r['source_name'],'source_record_id':r['source_record_id'],'conflict_type':'missing_required_metadata','message':'Missing discovery fields: '+', '.join(missing)}); cand.append({**r.to_dict(),'candidate_status':'review','candidate_confidence':25.0,'candidate_reason':'Required discovery metadata is incomplete.'}); continue
        if sk in exact:known.append({**r.to_dict(),'known_match_type':'exact_source_identity','known_secret_lair_id':exact[sk]}); continue
        if nk in names:known.append({**r.to_dict(),'known_match_type':'exact_canonical_identity','known_secret_lair_id':names[nk]}); continue
        confidence=min(float(r.get('source_quality') or 0)+(10 if r.get('release_date') else 0)+(10 if r.get('official_url') else 0)+(5 if r.get('artist_names') else 0),100); review=normalize_text(r['finish']).lower()=='unknown' or normalize_text(r['variant_name']).lower() in {'card metadata set','standard edition'}
        cand.append({**r.to_dict(),'candidate_status':'review' if review else 'new','candidate_confidence':round(confidence,2),'candidate_reason':'Metadata-only discovery requires product-variant confirmation.' if review else 'No known source or canonical identity matched.'})
    return pd.DataFrame(cand,columns=cc),pd.DataFrame(known,columns=kc),pd.DataFrame(conflicts,columns=fc).drop_duplicates('conflict_id')
def discover_secret_lairs(config_path=DISCOVERY_CONFIG_PATH):
    cfg,exists=load_discovery_config(config_path); started=datetime.now(timezone.utc); run=started.strftime('SLD%Y%m%dT%H%M%S%f'); client=CachedHttpClient(DISCOVERY_CACHE_ROOT); cats=[]; health=[]; logs=[]
    previous=set()
    if DISCOVERY_STATE_PATH.exists():
        s=pd.read_csv(DISCOVERY_STATE_PATH,dtype=str).fillna(''); previous={(r['source_name'],r['source_record_id']) for _,r in s.iterrows()}
    for _,src in cfg.sort_values(['priority','source_name']).iterrows():
        name=str(src['source_name']); rs=datetime.now(timezone.utc); status='disabled'; err=''; recv=norm=0; cache=False; raw=''
        if bool(src['enabled']):
            status='success'
            try:
                payload=get_discovery_connector(str(src['connector_type'])).load(src,client); recv=payload.records_received; cache=payload.from_cache; raw=_raw(name,payload.content,payload.content_type,run); parsed=parse_discovery_payload(str(src['parser_name']),name,str(src['endpoint']),payload.content,payload.fetched_at_utc,float(src['source_quality']),parse_query(src['query_json'])); norm=len(parsed.catalog); cats.append(parsed.catalog)
            except Exception as exc:status='failed';err=str(exc)
        done=datetime.now(timezone.utc); health.append({**src.to_dict(),'status':status,'records_received':recv,'records_normalized':norm,'from_cache':cache,'raw_snapshot_path':raw,'error_message':err}); logs.append({'run_id':run,'source_name':name,'started_at_utc':rs.isoformat(),'completed_at_utc':done.isoformat(),'status':status,'records_received':recv,'records_normalized':norm,'from_cache':cache,'raw_snapshot_path':raw,'error_message':err})
    catalog=pd.concat(cats,ignore_index=True) if cats else pd.DataFrame(columns=COLUMNS); candidates,known,conflicts=_classify(catalog); keys={(r['source_name'],r['source_record_id']) for _,r in catalog.iterrows()}; incremental=keys-previous
    candidates['incremental_new']=candidates.apply(lambda r:(r['source_name'],r['source_record_id']) in incremental,axis=1) if not candidates.empty else pd.Series(dtype=bool)
    state=catalog[['source_name','source_record_id']].drop_duplicates(); DISCOVERY_STATE_PATH.parent.mkdir(parents=True,exist_ok=True); state.to_csv(DISCOVERY_STATE_PATH,index=False)
    enabled=int(cfg.get('enabled',pd.Series(dtype=bool)).fillna(False).astype(bool).sum()); successful=sum(x['status']=='success' for x in health); summary=pd.DataFrame([{'snapshot_date':started.date().isoformat(),'enabled_sources':enabled,'successful_sources':successful,'discovered_rows':len(catalog),'new_candidate_rows':int(candidates['candidate_status'].eq('new').sum()) if not candidates.empty else 0,'review_candidate_rows':int(candidates['candidate_status'].eq('review').sum()) if not candidates.empty else 0,'incremental_new_rows':len(incremental),'known_rows':len(known),'conflict_rows':len(conflicts),'acquisition_stage_ready':bool(len(candidates)>0 and len(conflicts)==0 and enabled>0 and successful==enabled)}])
    return DiscoveryBuildResult({'secret_lair_discovery_source_health':pd.DataFrame(health,columns=SOURCE_HEALTH_COLUMNS),'secret_lair_discovery_catalog':catalog,'secret_lair_discovery_candidates':candidates,'secret_lair_discovery_known':known,'secret_lair_discovery_conflicts':conflicts,'secret_lair_discovery_run_log':pd.DataFrame(logs,columns=RUN_LOG_COLUMNS),'secret_lair_discovery_summary':summary},exists)
def stage_discovery_to_acquisition(result,output_path=DISCOVERY_STAGE_PATH):
    f=result.datasets['secret_lair_discovery_candidates']; f=f[f['candidate_status'].isin(['new','review'])].copy(); cols=['source_name','source_record_id','drop_name','variant_name','finish','product_family','release_date','sale_start_date','sale_end_date','msrp_usd','currency','franchise','ip_category','universes_beyond','artist_names','card_count','superdrop_name','event_type','availability_model','status','official_url','notes']
    for c in cols:
        if c not in f.columns:f[c]=''
    f['notes']=f.apply(lambda r:f"Discovered by Terminal 2.7.1; status={r['candidate_status']}; confidence={r['candidate_confidence']}",axis=1); staged=f[cols].drop_duplicates(['source_name','source_record_id']); output_path.parent.mkdir(parents=True,exist_ok=True); staged.to_csv(output_path,index=False); return DiscoveryStageResult(str(output_path),len(staged))
