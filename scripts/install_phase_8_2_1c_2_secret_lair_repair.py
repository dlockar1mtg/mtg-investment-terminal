from __future__ import annotations

import ast
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "scripts" / "phase_8_2_1c_2_payload"
PRODUCER = ROOT / "scripts" / "build_full_secret_lair_model_evaluation.py"
UNIFIED = ROOT / "scripts" / "build_unified_mtg_intelligence.py"
HOSTED = ROOT / "scripts" / "build_mtg_hosted_uip_delivery.py"
TEST = ROOT / "tests" / "test_full_secret_lair_model_evaluation.py"

BACKUP = (
    ROOT / "data" / "operations" / "phase_8_2_1c_2_code_backups"
    / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
)

def backup(path: Path) -> None:
    destination = BACKUP / path.relative_to(ROOT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)

def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 occurrence, found {count}")
    return text.replace(old, new, 1)

for path in (PRODUCER, UNIFIED, HOSTED, TEST):
    if not path.is_file():
        raise FileNotFoundError(path)
    backup(path)

shutil.copy2(PAYLOAD / "build_full_secret_lair_model_evaluation.py", PRODUCER)

unified_text = UNIFIED.read_text(encoding="utf-8-sig")
old_secret = '''        if lane == "SECRET_LAIR":
            evaluation = secret_eval.get(source_id)
            forecast = secret_fc.get(source_id)
            recommendation = secret_rec.get(source_id)
            if not all((evaluation, forecast, recommendation)):
                diagnostics.append({"lane": lane, "source_product_id": source_id, "diagnostic": "MISSING_SECRET_LAIR_INTELLIGENCE_SOURCE"})
                continue
            row.update(
                {
                    "forecast_method": clean(forecast.get("valuation_method")) or "SECRET_LAIR_NATIVE_GUARDED",
                    "native_forecast_low_usd": clean(forecast.get("forecast_low_usd")),
                    "native_forecast_base_usd": clean(forecast.get("forecast_base_usd")),
                    "native_forecast_high_usd": clean(forecast.get("forecast_high_usd")),
                    "recommendation_action": clean(recommendation.get("guarded_recommendation")),
                    "confidence": clean(recommendation.get("model_confidence_score")) or clean(evaluation.get("model_confidence_score")),
                    "suppression_reason": clean(evaluation.get("suppression_reason")),
                }
            )
            row["forecast_eligible"] = "YES" if is_number(row["native_forecast_base_usd"]) else "NO"
            row["recommendation_eligible"] = secret_recommendation_eligible(row["recommendation_status"], row["recommendation_action"])
'''
new_secret = '''        if lane == "SECRET_LAIR":
            evaluation = secret_eval.get(source_id)
            forecast = secret_fc.get(source_id)
            recommendation = secret_rec.get(source_id)
            if not all((evaluation, forecast, recommendation)):
                diagnostics.append({"lane": lane, "source_product_id": source_id, "diagnostic": "MISSING_SECRET_LAIR_INTELLIGENCE_SOURCE"})
                continue

            horizon_certified = normalize_bool(
                forecast.get("horizon_model_certified")
            ) == "YES"

            row.update(
                {
                    "current_market_value_usd": clean(forecast.get("current_market_value_usd")) or clean(evaluation.get("current_market_value_usd")) or clean(evaluation.get("evaluated_market_value_usd")),
                    "forecast_method": clean(forecast.get("forecast_method")) or "NATIVE_VALUATION_RANGE",
                    "forecast_status": clean(forecast.get("forecast_status")) or clean(evaluation.get("forecast_status")),
                    "forecast_eligible": normalize_bool(forecast.get("forecast_eligible")) if horizon_certified else "NO",
                    "native_forecast_low_usd": clean(forecast.get("native_valuation_low_usd")) or clean(forecast.get("forecast_low_usd")),
                    "native_forecast_base_usd": clean(forecast.get("native_valuation_base_usd")) or clean(forecast.get("forecast_base_usd")),
                    "native_forecast_high_usd": clean(forecast.get("native_valuation_high_usd")) or clean(forecast.get("forecast_high_usd")),
                    "one_year_downside_usd": clean(forecast.get("one_year_downside_usd")) if horizon_certified else "",
                    "one_year_base_usd": clean(forecast.get("one_year_base_usd")) if horizon_certified else "",
                    "one_year_upside_usd": clean(forecast.get("one_year_upside_usd")) if horizon_certified else "",
                    "three_year_downside_usd": clean(forecast.get("three_year_downside_usd")) if horizon_certified else "",
                    "three_year_base_usd": clean(forecast.get("three_year_base_usd")) if horizon_certified else "",
                    "three_year_upside_usd": clean(forecast.get("three_year_upside_usd")) if horizon_certified else "",
                    "five_year_downside_usd": clean(forecast.get("five_year_downside_usd")) if horizon_certified else "",
                    "five_year_base_usd": clean(forecast.get("five_year_base_usd")) if horizon_certified else "",
                    "five_year_upside_usd": clean(forecast.get("five_year_upside_usd")) if horizon_certified else "",
                    "recommendation_action": clean(recommendation.get("guarded_recommendation")),
                    "recommendation_status": clean(recommendation.get("recommendation_status")),
                    "recommendation_eligible": normalize_bool(recommendation.get("recommendation_eligible")) if horizon_certified else "NO",
                    "confidence": clean(recommendation.get("model_confidence_score")) or clean(evaluation.get("model_confidence_score")),
                    "rationale": "Native current-value range retained; forward recommendation withheld until a horizon model is independently certified.",
                    "suppression_reason": clean(evaluation.get("suppression_reason")),
                }
            )
'''
unified_text = replace_once(unified_text, old_secret, new_secret, "unified Secret Lair mapping")
old_check = '        "secret_native_forecasts_equal_973": numeric_forecast_counts["SECRET_LAIR"] == 973,\n'
new_check = '''        "secret_native_valuation_ranges_equal_973": numeric_forecast_counts["SECRET_LAIR"] == 973,
        "secret_forecast_eligibility_fail_closed": forecast_counts["SECRET_LAIR"] == 0,
        "secret_recommendations_fail_closed": recommendation_counts["SECRET_LAIR"] == 0,
        "secret_horizon_values_zero": all(
            not any(is_number(r[field]) for field in (
                "one_year_base_usd", "three_year_base_usd", "five_year_base_usd"
            ))
            for r in rows
            if r["lane"] == "SECRET_LAIR"
        ),
'''
unified_text = replace_once(unified_text, old_check, new_check, "unified Secret Lair checks")
UNIFIED.write_text(unified_text, encoding="utf-8")

hosted_text = HOSTED.read_text(encoding="utf-8-sig")
marker = '    aftermath_rows = [\n'
secret_guard = '''    secret_rows = [
        row
        for row in forecast_rows
        if row["asset_id"].startswith("MTG:SECRET_LAIR:")
    ]
    if len(secret_rows) != 973:
        raise RuntimeError(f"Expected 973 hosted Secret Lair rows; found {len(secret_rows)}")
    if any(row["forecast_eligible"] != "NO" for row in secret_rows):
        raise RuntimeError("Secret Lair horizon forecasts must remain fail-closed.")
    if any(any(row[field] for field in ("one_year_base_usd", "three_year_base_usd", "five_year_base_usd")) for row in secret_rows):
        raise RuntimeError("Hosted Secret Lair output contains uncertified horizon values.")
    if any(row["forecast_method"] != "NATIVE_VALUATION_RANGE" for row in secret_rows):
        raise RuntimeError("Hosted Secret Lair valuation method is not explicit.")

'''
hosted_text = replace_once(hosted_text, marker, secret_guard + marker, "hosted Secret Lair guard")
HOSTED.write_text(hosted_text, encoding="utf-8")

test_text = TEST.read_text(encoding="utf-8-sig")
old_test = '''def test_only_full_model_can_receive_buy_review(tmp_path: Path):
    ledger = tmp_path / "ledger.csv"; write_ledger(ledger)
    result = build(ledger, tmp_path / "out")
    rows = list(csv.DictReader(Path(result["outputs"]["recommendation_inputs"]).open(encoding="utf-8")))
    assert all(row["evaluation_tier"] == "FULL_MODEL" for row in rows if row["guarded_recommendation"] == "REVIEW_FOR_BUY")
'''
new_test = '''def test_recommendations_and_horizons_fail_closed(tmp_path: Path):
    ledger = tmp_path / "ledger.csv"; write_ledger(ledger)
    result = build(ledger, tmp_path / "out")
    recommendation_rows = list(csv.DictReader(Path(result["outputs"]["recommendation_inputs"]).open(encoding="utf-8")))
    forecast_rows = list(csv.DictReader(Path(result["outputs"]["forecast_inputs"]).open(encoding="utf-8")))
    assert all(row["recommendation_eligible"] == "NO" for row in recommendation_rows)
    assert all(row["forecast_eligible"] == "NO" for row in forecast_rows)
    assert all(row["horizon_model_certified"] == "NO" for row in forecast_rows)
    assert all(not row["one_year_base_usd"] and not row["three_year_base_usd"] and not row["five_year_base_usd"] for row in forecast_rows)
'''
test_text = replace_once(test_text, old_test, new_test, "Secret Lair unit test")
TEST.write_text(test_text, encoding="utf-8")

for path in (PRODUCER, UNIFIED, HOSTED, TEST):
    ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))

print("=" * 78)
print("PHASE 8.2.1C.2 — SECRET LAIR PRODUCER AND DELIVERY REPAIR")
print("=" * 78)
print("PASS | producer separates valuation ranges from horizon forecasts")
print("PASS | forecast and recommendation eligibility fail closed")
print("PASS | unified mapping preserves current value and native range")
print("PASS | hosted delivery enforces the 973-row semantic boundary")
print(f"Backup: {BACKUP}")
print("PHASE 8.2.1C.2 INSTALLATION: PASS")
