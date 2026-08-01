"""Adjudicate bridged Collector history and build dynamic product history tiers.

This script never authorizes purchases or UIP delivery. It recomputes lifecycle
state as of the latest observation month, preserves material-change annotations,
blocks extreme continuity breaks, and quarantines unresolved name-only rows.
"""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config/mtg/governance/collector_history_adjudication_tiering_policy_v1.json"
DEFAULT_HISTORY = ROOT / "data/governance/permanence/certification/collector_historical_bridge_certification/collector_bridged_analytical_history_candidate.csv"
DEFAULT_AUTHORITY = ROOT / "data/governance/permanence/certification/collector_current_authority/collector_current_authority_all.csv"
DEFAULT_ALIAS_REVIEW = ROOT / "data/governance/permanence/certification/collector_historical_bridge_certification/collector_name_only_alias_review_queue.csv"
DEFAULT_OUT = ROOT / "data/governance/permanence/certification/collector_history_adjudication_tiering"

def parser():
    p=argparse.ArgumentParser(description="Adjudicate Collector history and build tiers")
    p.add_argument("--policy",type=Path,default=DEFAULT_POLICY); p.add_argument("--history",type=Path,default=DEFAULT_HISTORY)
    p.add_argument("--authority",type=Path,default=DEFAULT_AUTHORITY); p.add_argument("--alias-review",type=Path,default=DEFAULT_ALIAS_REVIEW)
    p.add_argument("--output-dir",type=Path,default=DEFAULT_OUT); p.add_argument("--strict",action="store_true"); return p

def read(path): return pd.read_csv(path,dtype=str,encoding="utf-8-sig",low_memory=False).fillna("")
def norm_id(v):
    s=str(v).strip(); return s[:-2] if s.endswith(".0") else s

def month_diff(a,b): return (b.year-a.year)*12+(b.month-a.month)

def main():
    a=parser().parse_args(); out=a.output_dir.resolve(); out.mkdir(parents=True,exist_ok=True)
    required=[a.policy,a.history,a.authority]
    missing=[str(p) for p in required if not p.resolve().is_file()]
    if missing:
        summary={"status":"FAIL","missing_inputs":missing,"purchase_recommendation_authorized":False,"uip_delivery_authorized":False}
        (out/"collector_history_adjudication_tiering_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8"); print(json.dumps(summary,indent=2)); return 1
    policy=json.loads(a.policy.resolve().read_text(encoding="utf-8-sig")); hist=read(a.history.resolve()); auth=read(a.authority.resolve())
    hist["tcgplayer_product_id"]=hist["tcgplayer_product_id"].map(norm_id); auth["tcgplayer_product_id"]=auth["tcgplayer_product_id"].map(norm_id)
    hist["observation_dt"]=pd.to_datetime(hist["observation_month"],errors="coerce")
    hist["market_price_num"]=pd.to_numeric(hist["market_price"],errors="coerce")
    hist["mom_num"]=pd.to_numeric(hist.get("month_over_month_change",""),errors="coerce")
    latest=hist["observation_dt"].max(); latest_month=latest.strftime("%Y-%m-01") if pd.notna(latest) else ""
    release_map=auth.set_index("tcgplayer_product_id")["raw_released_on"].to_dict() if "raw_released_on" in auth.columns else {}
    name_map=auth.set_index("tcgplayer_product_id")["box_name"].to_dict()
    attested=set(policy["owner_attested_high_value_product_ids"])
    mat=float(policy["continuity_thresholds"]["material_absolute_percent_change"]); up=float(policy["continuity_thresholds"]["extreme_up_percent_change"]); down=float(policy["continuity_thresholds"]["extreme_down_percent_change"])
    hist["extreme_break"]=(hist["mom_num"]>up)|(hist["mom_num"]<down)
    hist["material_change"]=hist["mom_num"].abs()>=mat
    hist["owner_attested_high_value"]=hist["tcgplayer_product_id"].isin(attested)
    hist["adjudication_status"]="CONTINUITY_PASS"
    hist.loc[hist["material_change"],"adjudication_status"]="MATERIAL_CHANGE_ANNOTATED"
    hist.loc[hist["material_change"] & hist["owner_attested_high_value"] & hist["source_code"].isin(["JULY_31_CERTIFIED","AUGUST_LIVE_CERTIFIED"]),"adjudication_status"]="OWNER_ATTESTED_MATERIAL_CHANGE"
    hist.loc[hist["extreme_break"],"adjudication_status"]="EXTREME_BREAK_UNRESOLVED"
    hist["forecast_input_row_authorized"]=~hist["extreme_break"]
    hist["purchase_recommendation_authorized"]=False
    hist.to_csv(out/"collector_adjudicated_analytical_history.csv",index=False)
    hist.loc[hist["extreme_break"]].to_csv(out/"collector_extreme_continuity_unresolved.csv",index=False)
    hist.loc[hist["material_change"] & ~hist["extreme_break"]].to_csv(out/"collector_material_change_annotations.csv",index=False)

    rows=[]
    for pid,g in hist.groupby("tcgplayer_product_id"):
        rel_raw=str(release_map.get(pid,"")).strip(); rel=pd.to_datetime(rel_raw,errors="coerce")
        months=int(g["observation_month"].nunique()); first=g["observation_dt"].min(); last=g["observation_dt"].max()
        extreme=int(g["extreme_break"].sum()); material=int(g["material_change"].sum())
        if pd.notna(rel) and pd.notna(latest): age=max(0,month_diff(rel,latest))
        else: age=None
        if age is None: lifecycle="RELEASE_DATE_UNVERIFIED"
        elif rel>latest: lifecycle="PRESALE"
        elif age<int(policy["early_lifecycle_months"]): lifecycle="RELEASED_EARLY_LIFECYCLE"
        else: lifecycle="RELEASED_MATURE"
        if lifecycle=="PRESALE" or months==0: tier="PRESALE_OR_NO_RELEASED_HISTORY"
        elif months>=24: tier="DIRECT_HISTORY_MATURE"
        elif months>=12: tier="DIRECT_HISTORY_DEVELOPING"
        elif months>=3: tier="LIMITED_HISTORY"
        else: tier="EARLY_LIFECYCLE"
        status="FORECAST_INPUT_CANDIDATE" if extreme==0 and lifecycle!="PRESALE" else "FORECAST_INPUT_BLOCKED"
        rows.append({"tcgplayer_product_id":pid,"governed_box_name":name_map.get(pid,""),"release_date":rel_raw,"latest_observation_month":latest_month,"recomputed_lifecycle_state":lifecycle,"released_history_months":months,"first_history_month":first.strftime("%Y-%m-01") if pd.notna(first) else "","last_history_month":last.strftime("%Y-%m-01") if pd.notna(last) else "","material_change_annotations":material,"extreme_unresolved_rows":extreme,"history_tier":tier,"forecast_input_status":status,"purchase_recommendation_authorized":False,"uip_delivery_authorized":False})
    tiers=pd.DataFrame(rows)
    governed_ids=set(auth.loc[auth["identity_authority_status"].eq("CURRENT_IDENTITY_AUTHORIZED"),"tcgplayer_product_id"])
    absent=auth.loc[auth["tcgplayer_product_id"].isin(governed_ids-set(tiers["tcgplayer_product_id"]))].copy()
    for _,r in absent.iterrows():
        rel_raw=str(r.get("raw_released_on","")).strip(); rel=pd.to_datetime(rel_raw,errors="coerce")
        lifecycle="PRESALE" if pd.notna(rel) and pd.notna(latest) and rel>latest else "RELEASED_EARLY_LIFECYCLE" if pd.notna(rel) else "RELEASE_DATE_UNVERIFIED"
        rows.append({"tcgplayer_product_id":r["tcgplayer_product_id"],"governed_box_name":r.get("box_name",""),"release_date":rel_raw,"latest_observation_month":latest_month,"recomputed_lifecycle_state":lifecycle,"released_history_months":0,"first_history_month":"","last_history_month":"","material_change_annotations":0,"extreme_unresolved_rows":0,"history_tier":"PRESALE_OR_NO_RELEASED_HISTORY","forecast_input_status":"FORECAST_INPUT_BLOCKED","purchase_recommendation_authorized":False,"uip_delivery_authorized":False})
    tiers=pd.DataFrame(rows).sort_values(["history_tier","governed_box_name"]); tiers.to_csv(out/"collector_product_history_tiers.csv",index=False)
    tiers.loc[tiers["forecast_input_status"].eq("FORECAST_INPUT_CANDIDATE")].to_csv(out/"collector_forecast_input_candidates.csv",index=False)
    tiers.loc[tiers["forecast_input_status"].eq("FORECAST_INPUT_BLOCKED")].to_csv(out/"collector_forecast_input_blocked.csv",index=False)
    alias=read(a.alias_review.resolve()) if a.alias_review.resolve().is_file() else pd.DataFrame()
    alias.to_csv(out/"collector_unresolved_name_only_quarantine.csv",index=False)
    dup=int(hist.duplicated(["tcgplayer_product_id","observation_month"]).sum()); extreme_rows=int(hist["extreme_break"].sum())
    summary={"block_name":"Collector History Adjudication and Tiering","block_version":"1.0.0","generated_at":datetime.now(timezone.utc).isoformat(),"latest_observation_month":latest_month,"governed_products":int(len(governed_ids)),"adjudicated_history_rows":int(len(hist)),"adjudicated_products":int(hist["tcgplayer_product_id"].nunique()),"duplicate_product_month_keys":dup,"material_change_annotation_rows":int((hist["material_change"] & ~hist["extreme_break"]).sum()),"owner_attested_material_change_rows":int(hist["adjudication_status"].eq("OWNER_ATTESTED_MATERIAL_CHANGE").sum()),"extreme_unresolved_rows":extreme_rows,"product_tier_rows":int(len(tiers)),"forecast_input_candidate_products":int(tiers["forecast_input_status"].eq("FORECAST_INPUT_CANDIDATE").sum()),"forecast_input_blocked_products":int(tiers["forecast_input_status"].eq("FORECAST_INPUT_BLOCKED").sum()),"unresolved_name_only_rows":int(len(alias)),"absolute_price_cap_applied":False,"historical_append_authorized":False,"purchase_recommendation_authorized":False,"uip_delivery_authorized":False,"status":"PASS_ADJUDICATION_TIERING_CANDIDATE_ONLY" if dup==0 else "REVIEW_REQUIRED"}
    (out/"collector_history_adjudication_tiering_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8"); print(json.dumps(summary,indent=2))
    return 1 if a.strict and (dup>0 or extreme_rows>0) else 0

if __name__=="__main__": raise SystemExit(main())
