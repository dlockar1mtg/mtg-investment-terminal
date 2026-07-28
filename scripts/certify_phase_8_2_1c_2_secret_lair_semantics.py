from __future__ import annotations
import csv, json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "validation" / "phase_10" / "ebay_matching" / "production_refresh" / "full_model_evaluation"
UNIFIED = ROOT / "data" / "validation" / "phase_10" / "unified_mtg_intelligence" / "unified_mtg_intelligence_interface.csv"
UIP_FC = ROOT / "data" / "operations" / "mtg_uip_delivery" / "latest" / "forecasts.csv"
UIP_REC = ROOT / "data" / "operations" / "mtg_uip_delivery" / "latest" / "recommendations.csv"
OUTPUT = ROOT / "docs" / "phase_8" / "mtg_intelligence_recovery" / "secret_lair_intelligence_recovery" / "PHASE_8_2_1C_2_CERTIFICATION.json"

def read(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))

def secret(rows):
    return [r for r in rows if "SECRET_LAIR" in (r.get("lane","")+r.get("asset_id","")+r.get("universal_mtg_product_id",""))]

def blank_horizons(r):
    fields=("one_year_downside_usd","one_year_base_usd","one_year_upside_usd","three_year_downside_usd","three_year_base_usd","three_year_upside_usd","five_year_downside_usd","five_year_base_usd","five_year_upside_usd")
    return not any(str(r.get(f,"") or "").strip() for f in fields)

source_fc=read(SOURCE/"secret_lair_full_forecast_inputs.csv")
source_rec=read(SOURCE/"secret_lair_guarded_recommendations.csv")
unified=secret(read(UNIFIED))
uip_fc=secret(read(UIP_FC))
uip_rec=secret(read(UIP_REC))
checks={
"source_forecast_rows_equal_973":len(source_fc)==973,
"source_recommendation_rows_equal_973":len(source_rec)==973,
"unified_rows_equal_973":len(unified)==973,
"uip_forecast_rows_equal_973":len(uip_fc)==973,
"uip_recommendation_rows_equal_973":len(uip_rec)==973,
"source_method_explicit":all(r["forecast_method"]=="NATIVE_VALUATION_RANGE" for r in source_fc),
"unified_method_explicit":all(r["forecast_method"]=="NATIVE_VALUATION_RANGE" for r in unified),
"uip_method_explicit":all(r["forecast_method"]=="NATIVE_VALUATION_RANGE" for r in uip_fc),
"source_horizons_suppressed":all(blank_horizons(r) for r in source_fc),
"unified_horizons_suppressed":all(blank_horizons(r) for r in unified),
"uip_horizons_suppressed":all(blank_horizons(r) for r in uip_fc),
"source_forecast_eligibility_fail_closed":all(r["forecast_eligible"]=="NO" for r in source_fc),
"unified_forecast_eligibility_fail_closed":all(r["forecast_eligible"]=="NO" for r in unified),
"uip_forecast_eligibility_fail_closed":all(r["forecast_eligible"]=="NO" for r in uip_fc),
"source_recommendations_fail_closed":all(r["recommendation_eligible"]=="NO" for r in source_rec),
"unified_recommendations_fail_closed":all(r["recommendation_eligible"]=="NO" for r in unified),
"uip_recommendations_fail_closed":all(r["recommendation_eligible"]=="NO" for r in uip_rec),
"native_ranges_ordered":all(float(r["native_forecast_low_usd"])<=float(r["native_forecast_base_usd"])<=float(r["native_forecast_high_usd"]) for r in unified),
}
result={"status":"CERTIFIED" if all(checks.values()) else "FAILED","phase":"8.2.1C.2","generated_at_utc":datetime.now(timezone.utc).isoformat(),"checks":checks}
OUTPUT.parent.mkdir(parents=True,exist_ok=True)
OUTPUT.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
print("="*78)
print("PHASE 8.2.1C.2 — SECRET LAIR SEMANTIC CERTIFICATION")
print("="*78)
for k,v in checks.items(): print(f"{'PASS' if v else 'FAIL'} | {k}")
print(f"PHASE 8.2.1C.2 CERTIFICATION: {result['status']}")
raise SystemExit(0 if result["status"]=="CERTIFIED" else 1)
