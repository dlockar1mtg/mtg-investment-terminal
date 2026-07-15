from dataclasses import dataclass
from datetime import datetime,timezone
import hashlib
import pandas as pd
from terminal2.secret_lair.backfill.engine import build_secret_lair_backfill
from terminal2.secret_lair.pricing import build_secret_lair_pricing_datasets
from terminal2.secret_lair.datetime_utils import date_string_series,to_utc_naive_series
from terminal2.secret_lair.identifiers import slug
@dataclass(frozen=True)
class PopulationBuildResult: datasets:dict[str,pd.DataFrame]
def _id(prefix,*parts):return prefix+hashlib.sha1("|".join(map(str,parts)).encode()).hexdigest()[:12].upper()
def _canonical(row):return "|".join([slug(row.get("drop_name")),slug(row.get("variant_name")),str(row.get("finish","")).strip().lower()])
def _candidates(backfill):
 m=backfill["secret_lair_match_results"].copy();cols=["source_name","source_record_id","secret_lair_id","drop_name","variant_name","finish","population_status","match_method","match_confidence","best_candidate_id","best_candidate_score","second_candidate_score","ready_for_registry"]
 if m.empty:return pd.DataFrame(columns=cols)
 m["population_status"]=m["match_status"].map({"matched":"accepted_existing","new_asset":"accepted_new","review":"needs_review","rejected":"rejected"}).fillna("needs_review")
 m["ready_for_registry"]=m["population_status"].isin(["accepted_existing","accepted_new"])
 for c in cols:
  if c not in m:m[c]=pd.NA
 return m[cols]
def _duplicates(candidates):
 cols=["duplicate_id","canonical_identity","source_name","source_record_id","secret_lair_id","duplicate_group_size","duplicate_status"]
 if candidates.empty:return pd.DataFrame(columns=cols)
 f=candidates.copy();f["canonical_identity"]=f.apply(_canonical,axis=1);counts=f.groupby("canonical_identity")["source_record_id"].transform("count");f=f[(f["canonical_identity"]!="||")&(counts>1)].copy();f["duplicate_group_size"]=counts.loc[f.index].astype(int);f["duplicate_status"]="review_required";f["duplicate_id"]=[_id("SLDUP",r.canonical_identity,r.source_name,r.source_record_id) for r in f.itertuples()]
 return f[cols]
def _conflicts(backfill,duplicates):
 cols=["conflict_id","source_name","source_record_id","conflict_type","message","blocking"]
 rows=[]
 review=backfill["secret_lair_unmatched_review"]
 for _,r in review.iterrows():rows.append({"conflict_id":_id("SLPC",r.get("source_name"),r.get("source_record_id"),r.get("review_reason")),"source_name":r.get("source_name"),"source_record_id":r.get("source_record_id"),"conflict_type":r.get("review_reason"),"message":f"Population review required: {r.get('review_reason')}","blocking":True})
 for _,r in duplicates.iterrows():rows.append({"conflict_id":_id("SLPC","duplicate",r["duplicate_id"]),"source_name":r["source_name"],"source_record_id":r["source_record_id"],"conflict_type":"duplicate_canonical_identity","message":f"Canonical identity appears {r['duplicate_group_size']} times.","blocking":True})
 return pd.DataFrame(rows,columns=cols).drop_duplicates("conflict_id")
def _review(backfill,duplicates):
 cols=["review_id","source_name","source_record_id","drop_name","variant_name","finish","review_reason","recommended_action","priority"]
 rows=[]
 for _,r in backfill["secret_lair_unmatched_review"].iterrows():rows.append({"review_id":_id("SLR",r.get("source_name"),r.get("source_record_id"),r.get("review_reason")),"source_name":r.get("source_name"),"source_record_id":r.get("source_record_id"),"drop_name":r.get("drop_name"),"variant_name":r.get("variant_name"),"finish":r.get("finish"),"review_reason":r.get("review_reason"),"recommended_action":r.get("recommended_action"),"priority":"High"})
 for _,r in duplicates.iterrows():rows.append({"review_id":_id("SLR","duplicate",r["duplicate_id"]),"source_name":r["source_name"],"source_record_id":r["source_record_id"],"drop_name":"","variant_name":"","finish":"","review_reason":"duplicate_canonical_identity","recommended_action":"select_canonical_record_or_add_override","priority":"High"})
 return pd.DataFrame(rows,columns=cols).drop_duplicates("review_id")
def _price_readiness(registry,prices):
 cols=["secret_lair_id","drop_name","variant_name","current_price_available","current_price","price_observation_count","distinct_price_months","source_count","history_span_days","latest_observation_date","ready_for_scoring","ready_for_forecasting","ready_for_calibration"]
 if registry.empty:return pd.DataFrame(columns=cols)
 f=registry[["secret_lair_id","drop_name","variant_name"]].copy()
 obs=prices.get("secret_lair_price_observations",pd.DataFrame())
 if obs.empty:
  for c in cols[3:]:f[c]=False if c.startswith("ready_") or c=="current_price_available" else 0
  f["latest_observation_date"]="";return f[cols]
 o=obs.copy();o["observation_date"]=to_utc_naive_series(o["observation_date"]);o["market_price"]=pd.to_numeric(o["market_price"],errors="coerce")
 g=o.groupby("secret_lair_id").agg(current_price=("market_price","last"),price_observation_count=("market_price","count"),source_count=("source_name","nunique"),first_date=("observation_date","min"),latest_observation_date=("observation_date","max"))
 g["distinct_price_months"]=o.assign(month=o["observation_date"].dt.to_period("M")).groupby("secret_lair_id")["month"].nunique();g["history_span_days"]=(g["latest_observation_date"]-g["first_date"]).dt.days;g=g.reset_index();f=f.merge(g,on="secret_lair_id",how="left")
 f["current_price_available"]=pd.to_numeric(f["current_price"],errors="coerce").gt(0);f["ready_for_scoring"]=f["current_price_available"]&f["price_observation_count"].fillna(0).ge(2);f["ready_for_forecasting"]=f["distinct_price_months"].fillna(0).ge(6)&f["history_span_days"].fillna(0).ge(150);f["ready_for_calibration"]=f["distinct_price_months"].fillna(0).ge(12)&f["history_span_days"].fillna(0).ge(330)
 f["latest_observation_date"]=date_string_series(f["latest_observation_date"]).fillna("")
 for c in cols:
  if c not in f:f[c]=0
 return f[cols]
def _coverage(backfill,candidates,duplicates,readiness):
 base=backfill["secret_lair_backfill_coverage"].copy();cols=["source_name","catalog_rows","accepted_rows","review_rows","duplicate_rows","priced_records","completeness_score","source_status"]
 sources=sorted(set(base.get("source_name",pd.Series(dtype=str)).astype(str))|set(candidates.get("source_name",pd.Series(dtype=str)).astype(str)))
 rows=[]
 for s in sources:
  b=base[base["source_name"].astype(str).eq(s)];c=candidates[candidates["source_name"].astype(str).eq(s)];d=duplicates[duplicates["source_name"].astype(str).eq(s)]
  cat=int(b["catalog_rows"].iloc[0]) if not b.empty else len(c);accepted=int(c["ready_for_registry"].fillna(False).sum()) if not c.empty else 0;review=int(c["population_status"].eq("needs_review").sum()) if not c.empty else 0;score=round((accepted/max(cat,1))*100,2)
  rows.append({"source_name":s,"catalog_rows":cat,"accepted_rows":accepted,"review_rows":review,"duplicate_rows":len(d),"priced_records":int(b["priced_source_records"].iloc[0]) if not b.empty else 0,"completeness_score":score,"source_status":"ready" if cat and review==0 and len(d)==0 else "review" if cat else "empty"})
 return pd.DataFrame(rows,columns=cols)
def build_secret_lair_population():
 b=build_secret_lair_backfill().datasets;p=build_secret_lair_pricing_datasets().datasets;c=_candidates(b);d=_duplicates(c);x=_conflicts(b,d);r=_review(b,d);registry=b["secret_lair_backfill_registry"];ready=_price_readiness(registry,p);cov=_coverage(b,c,d,ready)
 accepted=int(c["ready_for_registry"].fillna(False).sum()) if not c.empty else 0;summary=pd.DataFrame([{"snapshot_date":datetime.now(timezone.utc).date().isoformat(),"catalog_rows":len(c),"accepted_rows":accepted,"review_rows":len(r),"duplicate_rows":len(d),"conflict_rows":len(x),"registry_assets":len(registry),"priced_assets":int(ready["current_price_available"].sum()) if not ready.empty else 0,"scoring_ready_assets":int(ready["ready_for_scoring"].sum()) if not ready.empty else 0,"forecast_ready_assets":int(ready["ready_for_forecasting"].sum()) if not ready.empty else 0,"calibration_ready_assets":int(ready["ready_for_calibration"].sum()) if not ready.empty else 0,"apply_ready":bool(len(c)>0 and len(r)==0 and len(d)==0 and len(x)==0)}])
 return PopulationBuildResult({"secret_lair_population_candidates":c,"secret_lair_population_duplicates":d,"secret_lair_population_conflicts":x,"secret_lair_population_review_queue":r,"secret_lair_population_source_coverage":cov,"secret_lair_population_price_readiness":ready,"secret_lair_population_summary":summary})
