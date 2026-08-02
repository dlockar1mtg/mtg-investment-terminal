"""Audit whether current Collector data is sufficient for V1 forecasting work."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_v1_data_sufficiency"
PATHS = {
    "routes": ROOT / "data/operations/collector_forecast_method_routing/candidate_v1_0_0/collector_forecast_method_routes.csv",
    "scarcity": ROOT / "data/governance/permanence/certification/collector_supply_scarcity_index_v1/collector_supply_scarcity_index_v1.csv",
    "snapshot": ROOT / "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline/collector_ebay_day_one_product_supply_snapshot.csv",
    "history": ROOT / "data/operations/mtg_history_foundation/universal_mtg_price_history.csv",
    "model": ROOT / "data/product_master/product_master_model_input.csv",
    "normalized": ROOT / "data/operations/collector_evidence_normalization/candidate_v1_0_0/collector_normalized_evidence.csv",
    "comparables": ROOT / "data/operations/collector_comparable_selection/candidate_v1_0_0/collector_selected_comparables.csv",
    "release": ROOT / "data/governance/permanence/certification/collector_official_release_date_authority/collector_official_release_date_authority.csv",
}
ALIASES = {
    "id": ["tcgplayer_product_id","product_id","canonical_product_id","resolved_tcgplayer_product_id"],
    "price": ["market_price","price","value","market","low_price","median_price"],
    "date": ["observation_date","date","price_date","snapshot_date","as_of_date","observed_at"],
    "seller": ["seller_hash","seller_id_hash","seller_id","seller_username","seller"],
}

def pick(df, names):
    return next((c for c in names if c in df.columns), None)

def norm(v):
    s=str(v or "").strip()
    return s.removeprefix("TCGPLAYER-")[:-2] if s.removeprefix("TCGPLAYER-").endswith(".0") else s.removeprefix("TCGPLAYER-")

def load(path):
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")

def native_bool(value):
    return bool(value)

def main():
    p=argparse.ArgumentParser(); p.add_argument("--strict",action="store_true"); a=p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    diagnostics=[]; frames={}
    for k,v in PATHS.items():
        if v.is_file():
            df=load(v); frames[k]=df
            diagnostics.append({"artifact":k,"path":str(v.relative_to(ROOT)),"rows":int(len(df)),"columns":int(len(df.columns)),"id_column":pick(df,ALIASES["id"]) or ""})
    routes=frames.get("routes",pd.DataFrame()); scarcity=frames.get("scarcity",pd.DataFrame()); snapshot=frames.get("snapshot",pd.DataFrame())
    route_id=pick(routes,ALIASES["id"]); scarcity_id=pick(scarcity,ALIASES["id"])
    route_ids=set(routes[route_id].map(norm)) if route_id else set(); scarcity_ids=set(scarcity[scarcity_id].map(norm)) if scarcity_id else set()
    routed_not_ebay=sorted(route_ids-scarcity_ids); ebay_not_routed=sorted(scarcity_ids-route_ids)
    recon=[]
    for pid in sorted(route_ids|scarcity_ids):
        r=routes[routes[route_id].map(norm)==pid].iloc[0].to_dict() if route_id and pid in route_ids else {}
        s=scarcity[scarcity[scarcity_id].map(norm)==pid].iloc[0].to_dict() if scarcity_id and pid in scarcity_ids else {}
        in_routes = pid in route_ids
        in_scarcity = pid in scarcity_ids
        recon.append({"tcgplayer_product_id":pid,"in_forecast_routes":native_bool(in_routes),"in_ebay_scarcity_v1":native_bool(in_scarcity),"forecast_method":r.get("forecast_method",r.get("method","")),"product_name":r.get("canonical_product_name",r.get("product_name",s.get("governed_box_name",""))),"reconciliation_state":"MATCHED" if in_routes and in_scarcity else ("ROUTED_WITHOUT_EBAY_V1" if in_routes else "EBAY_V1_WITHOUT_ROUTE")})
    pd.DataFrame(recon).to_csv(OUT/"collector_v1_universe_reconciliation.csv",index=False)
    history=frames.get("history",pd.DataFrame()); hid=pick(history,ALIASES["id"]); hprice=pick(history,ALIASES["price"]); hdate=pick(history,ALIASES["date"])
    hist_stats=[]
    if hid:
        history["__pid"]=history[hid].map(norm)
        for pid,g in history.groupby("__pid"):
            dates=pd.to_datetime(g[hdate],errors="coerce",utc=True) if hdate else pd.Series(dtype="datetime64[ns, UTC]")
            prices=pd.to_numeric(g[hprice],errors="coerce") if hprice else pd.Series(dtype=float)
            hist_stats.append({"tcgplayer_product_id":pid,"history_rows":int(len(g)),"valid_price_rows":int(prices.notna().sum()),"first_observation":str(dates.min()) if not dates.empty and dates.notna().any() else "","last_observation":str(dates.max()) if not dates.empty and dates.notna().any() else "","history_price_column":hprice or "","history_date_column":hdate or ""})
    pd.DataFrame(hist_stats).to_csv(OUT/"collector_v1_history_coverage.csv",index=False)
    seller_cols=[c for c in snapshot.columns if c in ALIASES["seller"]]
    seller_ready=False
    if seller_cols:
        seller_ready=any(native_bool(snapshot[c].astype(str).str.strip().ne("").any()) for c in seller_cols)
    elif "observable_seller_count" in snapshot.columns:
        seller_ready=native_bool(pd.to_numeric(snapshot["observable_seller_count"],errors="coerce").fillna(0).gt(0).any())
    horizons=[30,90,180,365,1095,1825]
    requirements={
      "routes_present":native_bool(not routes.empty),
      "scarcity_v1_present":native_bool(not scarcity.empty and len(scarcity)==50),
      "snapshot_present":native_bool(not snapshot.empty and len(snapshot)==50),
      "universe_reconciliation_complete":native_bool(len(route_ids)>0 and len(scarcity_ids)>0),
      "historical_price_artifact_present":native_bool(not history.empty),
      "historical_id_column_present":native_bool(hid is not None),
      "historical_price_column_present":native_bool(hprice is not None),
      "historical_date_column_present":native_bool(hdate is not None),
      "normalized_evidence_present":native_bool(not frames.get("normalized",pd.DataFrame()).empty),
      "comparables_present":native_bool(not frames.get("comparables",pd.DataFrame()).empty),
      "release_authority_present":native_bool(not frames.get("release",pd.DataFrame()).empty),
      "seller_identity_or_counts_usable":native_bool(seller_ready),
      "explicit_forecast_horizons_defined":True,
    }
    critical=[k for k in ("routes_present","scarcity_v1_present","historical_price_artifact_present","historical_id_column_present","historical_price_column_present","historical_date_column_present","normalized_evidence_present","comparables_present","release_authority_present") if not requirements[k]]
    current_gaps=[]
    if routed_not_ebay: current_gaps.append("Reconcile routed products absent from certified eBay V1 universe")
    if not seller_ready: current_gaps.append("Repair or formally remove the non-informative seller component")
    if critical: current_gaps.extend(critical)
    summary={"block_name":"Collector V1 Data Sufficiency Audit","block_version":"1.0.1","generated_at":datetime.now(timezone.utc).isoformat(),"artifact_diagnostics":diagnostics,"forecast_horizons_days":horizons,"routed_product_count":int(len(route_ids)),"ebay_v1_product_count":int(len(scarcity_ids)),"routed_not_in_ebay_v1":routed_not_ebay,"ebay_v1_not_routed":ebay_not_routed,"seller_feature_usable":native_bool(seller_ready),"requirements":requirements,"critical_missing_requirements":critical,"current_v1_gaps":current_gaps,"future_v2_only":["Temporal listing persistence","Observational entry and exit","Seller-count change over time","Supply Scarcity Index V2"],"v1_data_sufficient_for_feature_matrix":native_bool(len(critical)==0),"v1_data_sufficient_for_forecast_experiments":native_bool(len(critical)==0),"production_forecasting_authorized":False,"status":"PASS_V1_CURRENT_DATA_SUFFICIENT_WITH_GOVERNED_GAPS" if len(critical)==0 else "FAIL_V1_CURRENT_DATA_INSUFFICIENT"}
    (OUT/"collector_v1_data_sufficiency_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    pd.DataFrame(diagnostics).to_csv(OUT/"collector_v1_artifact_diagnostics.csv",index=False)
    print(json.dumps(summary,indent=2))
    return 0 if len(critical)==0 else (1 if a.strict else 0)
if __name__=="__main__": raise SystemExit(main())
