from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = Path(__file__).resolve().parent / "phase_8_2_1b_3_payload"

COLLECTOR_TARGET = ROOT / "terminal2" / "market_sources" / "collector_box_evaluation.py"
UNIFIED_TARGET = ROOT / "scripts" / "build_unified_mtg_intelligence.py"
HOSTED_TARGET = ROOT / "scripts" / "build_mtg_hosted_uip_delivery.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one replacement target, found {count}")
    return text.replace(old, new, 1)


def patch_unified(text: str) -> str:
    old = """                    "forecast_method": clean(forecast.get("forecast_method")),
                    "forecast_eligible": normalize_bool(forecast.get("forecast_eligible")),
                    "one_year_downside_usd": clean(forecast.get("1y_downside_usd")),
                    "one_year_base_usd": clean(forecast.get("1y_base_usd")),
                    "one_year_upside_usd": clean(forecast.get("1y_upside_usd")),
                    "three_year_downside_usd": clean(forecast.get("3y_downside_usd")),
                    "three_year_base_usd": clean(forecast.get("3y_base_usd")),
                    "three_year_upside_usd": clean(forecast.get("3y_upside_usd")),
                    "five_year_downside_usd": clean(forecast.get("5y_downside_usd")),
                    "five_year_base_usd": clean(forecast.get("5y_base_usd")),
                    "five_year_upside_usd": clean(forecast.get("5y_upside_usd")),
"""
    new = """                    "current_market_value_usd": clean(forecast.get("current_market_value_usd")) or clean(evaluation.get("current_market_value_usd")),
                    "forecast_method": clean(forecast.get("forecast_method")),
                    "forecast_status": clean(forecast.get("forecast_status")) or clean(evaluation.get("forecast_status")),
                    "forecast_eligible": normalize_bool(forecast.get("forecast_eligible")),
                    "native_forecast_low_usd": clean(forecast.get("native_forecast_low_usd")),
                    "native_forecast_base_usd": clean(forecast.get("native_forecast_base_usd")),
                    "native_forecast_high_usd": clean(forecast.get("native_forecast_high_usd")),
                    "one_year_downside_usd": clean(forecast.get("1y_downside_usd")) if normalize_bool(forecast.get("horizon_model_certified")) == "YES" else "",
                    "one_year_base_usd": clean(forecast.get("1y_base_usd")) if normalize_bool(forecast.get("horizon_model_certified")) == "YES" else "",
                    "one_year_upside_usd": clean(forecast.get("1y_upside_usd")) if normalize_bool(forecast.get("horizon_model_certified")) == "YES" else "",
                    "three_year_downside_usd": clean(forecast.get("3y_downside_usd")) if normalize_bool(forecast.get("horizon_model_certified")) == "YES" else "",
                    "three_year_base_usd": clean(forecast.get("3y_base_usd")) if normalize_bool(forecast.get("horizon_model_certified")) == "YES" else "",
                    "three_year_upside_usd": clean(forecast.get("3y_upside_usd")) if normalize_bool(forecast.get("horizon_model_certified")) == "YES" else "",
                    "five_year_downside_usd": clean(forecast.get("5y_downside_usd")) if normalize_bool(forecast.get("horizon_model_certified")) == "YES" else "",
                    "five_year_base_usd": clean(forecast.get("5y_base_usd")) if normalize_bool(forecast.get("horizon_model_certified")) == "YES" else "",
                    "five_year_upside_usd": clean(forecast.get("5y_upside_usd")) if normalize_bool(forecast.get("horizon_model_certified")) == "YES" else "",
"""
    collector_mapping_count = text.count(old)

    if collector_mapping_count < 1:
        raise RuntimeError(
            "unified collector mapping: replacement target was not found"
        )

    # The same schema block is used by collector and pre-collector lanes.
    # Replace only the first occurrence, which belongs to COLLECTOR_BOOSTER_BOX.
    text = text.replace(old, new, 1)

    old_check = """        "collector_numeric_forecasts_equal_47": numeric_forecast_counts["COLLECTOR_BOOSTER_BOX"] == 47,
        "collector_recommendation_eligible_equal_36": recommendation_counts["COLLECTOR_BOOSTER_BOX"] == 36,
"""
    new_check = """        "collector_native_ranges_present": numeric_forecast_counts["COLLECTOR_BOOSTER_BOX"] > 0,
        "collector_recommendations_fail_closed": recommendation_counts["COLLECTOR_BOOSTER_BOX"] == 0,
        "collector_false_horizon_values_zero": all(
            not any(is_number(r[field]) for field in (
                "one_year_base_usd", "three_year_base_usd", "five_year_base_usd"
            ))
            for r in rows
            if r["lane"] == "COLLECTOR_BOOSTER_BOX"
        ),
"""
    return replace_once(text, old_check, new_check, "unified collector checks")


def patch_hosted(text: str) -> str:
    old = """            current_value = first(
                evaluation_row,
                "evaluated_market_value_usd",
                "current_market_value_usd",
                "current_unit_value_usd",
                "market_value_usd",
                "current_price",
                default=first(base, "current_market_value_usd"),
            )
"""
    new = """            current_value = first(
                evaluation_row,
                "current_market_value_usd",
                "current_unit_value_usd",
                "market_value_usd",
                "current_price",
                "evaluated_market_value_usd",
                default=first(base, "current_market_value_usd"),
            )
"""
    text = replace_once(text, old, new, "hosted current-value precedence")

    text = replace_once(
        text,
        "            forecast_rows.append({\n",
        """            horizon_certified = normalize_bool(
                first(evaluation_row, "horizon_model_certified", default="NO")
            ) == "YES"

            forecast_rows.append({
""",
        "hosted horizon certification",
    )

    replacements = {
        """first(
                    evaluation_row, "1y_downside_usd", "one_year_downside_usd"
                )""": """first(evaluation_row, "1y_downside_usd", "one_year_downside_usd") if horizon_certified else """"",
        """first(
                    evaluation_row, "1y_base_usd", "one_year_base_usd"
                )""": """first(evaluation_row, "1y_base_usd", "one_year_base_usd") if horizon_certified else """"",
        """first(
                    evaluation_row, "1y_upside_usd", "one_year_upside_usd"
                )""": """first(evaluation_row, "1y_upside_usd", "one_year_upside_usd") if horizon_certified else """"",
        """first(
                    evaluation_row, "3y_downside_usd", "three_year_downside_usd"
                )""": """first(evaluation_row, "3y_downside_usd", "three_year_downside_usd") if horizon_certified else """"",
        """first(
                    evaluation_row, "3y_base_usd", "three_year_base_usd"
                )""": """first(evaluation_row, "3y_base_usd", "three_year_base_usd") if horizon_certified else """"",
        """first(
                    evaluation_row, "3y_upside_usd", "three_year_upside_usd"
                )""": """first(evaluation_row, "3y_upside_usd", "three_year_upside_usd") if horizon_certified else """"",
        """first(
                    evaluation_row, "5y_downside_usd", "five_year_downside_usd"
                )""": """first(evaluation_row, "5y_downside_usd", "five_year_downside_usd") if horizon_certified else """"",
        """first(
                    evaluation_row, "5y_base_usd", "five_year_base_usd"
                )""": """first(evaluation_row, "5y_base_usd", "five_year_base_usd") if horizon_certified else """"",
        """first(
                    evaluation_row, "5y_upside_usd", "five_year_upside_usd"
                )""": """first(evaluation_row, "5y_upside_usd", "five_year_upside_usd") if horizon_certified else """"",
    }
    for old_value, new_value in replacements.items():
        text = replace_once(text, old_value, new_value, "hosted horizon field")
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = ROOT / "data" / "operations" / "phase_8_2_1b_3_code_backups" / timestamp

    collector_new = (PAYLOAD / "collector_box_evaluation.py").read_text(encoding="utf-8")
    unified_new = patch_unified(UNIFIED_TARGET.read_text(encoding="utf-8"))
    hosted_new = patch_hosted(HOSTED_TARGET.read_text(encoding="utf-8"))

    print("Permanent producer repair prepared:")
    print(f"  {COLLECTOR_TARGET.relative_to(ROOT)}")
    print(f"  {UNIFIED_TARGET.relative_to(ROOT)}")
    print(f"  {HOSTED_TARGET.relative_to(ROOT)}")

    if not args.apply:
        print("Mode: DRY_RUN")
        print("PHASE 8.2.1B.3 INSTALLER: PASS")
        return 0

    for target in (COLLECTOR_TARGET, UNIFIED_TARGET, HOSTED_TARGET):
        destination = backup / target.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, destination)

    COLLECTOR_TARGET.write_text(collector_new, encoding="utf-8")
    UNIFIED_TARGET.write_text(unified_new, encoding="utf-8")
    HOSTED_TARGET.write_text(hosted_new, encoding="utf-8")

    print("Mode: APPLIED")
    print(f"Backup: {backup}")
    print("PHASE 8.2.1B.3 INSTALLER: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

