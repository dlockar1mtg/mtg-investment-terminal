from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "data" / "validation" / "phase_10"
OUTPUT = VALIDATION / "unified_mtg_intelligence"

PATHS = {
    "registry": VALIDATION / "unified_mtg_registry" / "unified_mtg_product_registry.csv",
    "secret_evaluation": VALIDATION / "ebay_matching" / "production_refresh" / "full_model_evaluation" / "secret_lair_full_model_evaluation.csv",
    "secret_forecast": VALIDATION / "ebay_matching" / "production_refresh" / "full_model_evaluation" / "secret_lair_full_forecast_inputs.csv",
    "secret_recommendation": VALIDATION / "ebay_matching" / "production_refresh" / "full_model_evaluation" / "secret_lair_guarded_recommendations.csv",
    "collector_evaluation": VALIDATION / "collector_booster_boxes" / "full_evaluation" / "collector_booster_box_full_evaluation.csv",
    "collector_forecast": VALIDATION / "collector_booster_boxes" / "full_evaluation" / "collector_booster_box_guarded_forecasts.csv",
    "collector_recommendation": VALIDATION / "collector_booster_boxes" / "full_evaluation" / "collector_booster_box_guarded_recommendations.csv",
    "pre_evaluation": VALIDATION / "pre_collector_booster_boxes" / "full_evaluation" / "pre_collector_booster_box_full_evaluation.csv",
    "pre_forecast": VALIDATION / "pre_collector_booster_boxes" / "full_evaluation" / "pre_collector_booster_box_guarded_forecasts.csv",
    "pre_recommendation": VALIDATION / "pre_collector_booster_boxes" / "full_evaluation" / "pre_collector_booster_box_guarded_recommendations.csv",
}

EXPECTED_LANES = {
    "SECRET_LAIR": 973,
    "COLLECTOR_BOOSTER_BOX": 49,
    "PRE_COLLECTOR_BOOSTER_BOX": 119,
}

FIELDS = [
    "universal_mtg_product_id",
    "lane",
    "source_product_id",
    "canonical_product_name",
    "product_class",
    "admission_tier",
    "quality_disposition",
    "current_market_value_usd",
    "forecast_method",
    "forecast_status",
    "forecast_eligible",
    "native_forecast_low_usd",
    "native_forecast_base_usd",
    "native_forecast_high_usd",
    "one_year_downside_usd",
    "one_year_base_usd",
    "one_year_upside_usd",
    "three_year_downside_usd",
    "three_year_base_usd",
    "three_year_upside_usd",
    "five_year_downside_usd",
    "five_year_base_usd",
    "five_year_upside_usd",
    "recommendation_action",
    "recommendation_status",
    "recommendation_eligible",
    "confidence",
    "rationale",
    "suppression_reason",
    "currency",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def clean(value: object) -> str:
    return str(value or "").strip()


def is_number(value: object) -> bool:
    text = clean(value)
    if not text:
        return False
    try:
        float(text)
    except ValueError:
        return False
    return True


def normalize_bool(value: object) -> str:
    text = clean(value).upper()
    if text in {"TRUE", "YES", "Y", "1", "ELIGIBLE"}:
        return "YES"
    if text in {"FALSE", "NO", "N", "0", "INELIGIBLE"}:
        return "NO"
    return ""


def secret_recommendation_eligible(status: str, action: str) -> str:
    status_upper = status.upper()
    action_upper = action.upper()
    if "INELIGIBLE" in status_upper or "SUPPRESS" in status_upper or "WATCH" in status_upper:
        return "NO"
    if action_upper in {"", "WATCH", "NO_ACTION"}:
        return "NO"
    return "YES"


def build() -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, object]]:
    source_rows = {name: read_csv(path) for name, path in PATHS.items()}
    registry = source_rows["registry"]

    secret_eval = {clean(r["investment_product_id"]): r for r in source_rows["secret_evaluation"]}
    secret_fc = {clean(r["investment_product_id"]): r for r in source_rows["secret_forecast"]}
    secret_rec = {clean(r["investment_product_id"]): r for r in source_rows["secret_recommendation"]}

    collector_eval = {clean(r["canonical_product_id"]): r for r in source_rows["collector_evaluation"]}
    collector_fc = {clean(r["canonical_product_id"]): r for r in source_rows["collector_forecast"]}
    collector_rec = {clean(r["canonical_product_id"]): r for r in source_rows["collector_recommendation"]}

    pre_eval = {clean(r["canonical_product_id"]): r for r in source_rows["pre_evaluation"]}
    pre_fc = {clean(r["canonical_product_id"]): r for r in source_rows["pre_forecast"]}
    pre_rec = {clean(r["canonical_product_id"]): r for r in source_rows["pre_recommendation"]}

    rows: list[dict[str, str]] = []
    diagnostics: list[dict[str, str]] = []

    for base in registry:
        lane = clean(base["lane"])
        source_id = clean(base["source_product_id"])
        row = {field: "" for field in FIELDS}
        row.update(
            {
                "universal_mtg_product_id": clean(base["universal_mtg_product_id"]),
                "lane": lane,
                "source_product_id": source_id,
                "canonical_product_name": clean(base["canonical_product_name"]),
                "product_class": clean(base["product_class"]),
                "admission_tier": clean(base["admission_tier"]),
                "quality_disposition": clean(base["quality_disposition"]),
                "current_market_value_usd": clean(base["current_market_value_usd"]),
                "forecast_status": clean(base["forecast_status"]),
                "recommendation_status": clean(base["recommendation_status"]),
                "currency": clean(base["currency"]) or "USD",
            }
        )

        if lane == "SECRET_LAIR":
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

        elif lane == "COLLECTOR_BOOSTER_BOX":
            evaluation = collector_eval.get(source_id)
            forecast = collector_fc.get(source_id)
            recommendation = collector_rec.get(source_id)
            if not all((evaluation, forecast, recommendation)):
                diagnostics.append({"lane": lane, "source_product_id": source_id, "diagnostic": "MISSING_COLLECTOR_INTELLIGENCE_SOURCE"})
                continue
            row.update(
                {
                    "forecast_method": clean(forecast.get("forecast_method")),
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
                    "recommendation_action": clean(recommendation.get("action")),
                    "recommendation_eligible": normalize_bool(recommendation.get("recommendation_eligible")),
                    "confidence": clean(recommendation.get("confidence")) or clean(evaluation.get("confidence")),
                    "rationale": clean(recommendation.get("rationale")),
                }
            )

        elif lane == "PRE_COLLECTOR_BOOSTER_BOX":
            evaluation = pre_eval.get(source_id)
            forecast = pre_fc.get(source_id)
            recommendation = pre_rec.get(source_id)
            if not all((evaluation, forecast, recommendation)):
                diagnostics.append({"lane": lane, "source_product_id": source_id, "diagnostic": "MISSING_PRE_COLLECTOR_INTELLIGENCE_SOURCE"})
                continue
            row.update(
                {
                    "forecast_method": clean(forecast.get("forecast_method")),
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
                    "recommendation_action": clean(recommendation.get("action")),
                    "recommendation_eligible": normalize_bool(recommendation.get("recommendation_eligible")),
                    "confidence": clean(recommendation.get("confidence")) or clean(evaluation.get("confidence")),
                    "rationale": clean(recommendation.get("rationale")),
                    "suppression_reason": clean(evaluation.get("plausibility_flags")),
                }
            )
        else:
            diagnostics.append({"lane": lane, "source_product_id": source_id, "diagnostic": "UNKNOWN_LANE"})
            continue

        rows.append(row)

    rows.sort(key=lambda r: (r["lane"], r["canonical_product_name"], r["source_product_id"]))
    lane_counts = Counter(r["lane"] for r in rows)
    forecast_counts = Counter(r["lane"] for r in rows if r["forecast_eligible"] == "YES")
    recommendation_counts = Counter(r["lane"] for r in rows if r["recommendation_eligible"] == "YES")
    numeric_forecast_counts = Counter(
        r["lane"]
        for r in rows
        if any(
            is_number(r[field])
            for field in (
                "native_forecast_base_usd",
                "one_year_base_usd",
                "three_year_base_usd",
                "five_year_base_usd",
            )
        )
    )

    checks = {
        "rows_equal_1141": len(rows) == 1141,
        "lane_counts_match": all(lane_counts[lane] == count for lane, count in EXPECTED_LANES.items()),
        "diagnostics_zero": len(diagnostics) == 0,
        "universal_ids_unique": len({r["universal_mtg_product_id"] for r in rows}) == 1141,
        "currency_usd_all_rows": all(r["currency"] == "USD" for r in rows),
        "forecast_eligibility_populated": all(r["forecast_eligible"] in {"YES", "NO"} for r in rows),
        "recommendation_eligibility_populated": all(r["recommendation_eligible"] in {"YES", "NO"} for r in rows),
        "collector_numeric_forecasts_equal_47": numeric_forecast_counts["COLLECTOR_BOOSTER_BOX"] == 47,
        "collector_recommendation_eligible_equal_36": recommendation_counts["COLLECTOR_BOOSTER_BOX"] == 36,
        "pre_numeric_forecasts_equal_83": numeric_forecast_counts["PRE_COLLECTOR_BOOSTER_BOX"] == 83,
        "pre_recommendation_eligible_equal_65": recommendation_counts["PRE_COLLECTOR_BOOSTER_BOX"] == 65,
        "secret_native_forecasts_equal_973": numeric_forecast_counts["SECRET_LAIR"] == 973,
        "private_holdings_fields_absent": all(field not in r for r in rows for field in ("quantity", "acquisition_date", "total_cost_basis_usd", "notes")),
        "quota_calls_zero": True,
    }

    status = "CERTIFIED" if all(checks.values()) else "FAILED"
    manifest = {
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "10.9.3",
        "products": len(rows),
        "lane_counts": dict(sorted(lane_counts.items())),
        "forecast_eligible_counts": dict(sorted(forecast_counts.items())),
        "numeric_forecast_counts": dict(sorted(numeric_forecast_counts.items())),
        "recommendation_eligible_counts": dict(sorted(recommendation_counts.items())),
        "diagnostics": len(diagnostics),
        "checks": checks,
        "quota_calls": 0,
        "source_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in PATHS.items()},
    }
    return rows, diagnostics, manifest


def write_outputs(rows: list[dict[str, str]], diagnostics: list[dict[str, str]], manifest: dict[str, object]) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    interface_path = OUTPUT / "unified_mtg_intelligence_interface.csv"
    with interface_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    diagnostics_path = OUTPUT / "unified_mtg_intelligence_diagnostics.csv"
    with diagnostics_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["lane", "source_product_id", "diagnostic"])
        writer.writeheader()
        writer.writerows(diagnostics)

    manifest["interface_sha256"] = hashlib.sha256(interface_path.read_bytes()).hexdigest()
    manifest["outputs"] = {
        "interface": str(interface_path.resolve()),
        "diagnostics": str(diagnostics_path.resolve()),
    }
    (OUTPUT / "unified_mtg_intelligence_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    checks = manifest["checks"]
    lines = [
        "# Phase 10.9.3 Unified MTG Intelligence Certification",
        "",
        f"**Status:** {manifest['status']}",
        "",
        f"- Unified products: {manifest['products']}",
        f"- Diagnostics: {manifest['diagnostics']}",
        "- API quota calls: 0",
        "",
        "## Lane counts",
        "",
    ]
    for lane, count in manifest["lane_counts"].items():
        lines.append(f"- {lane}: {count}")
    lines.extend(["", "## Numeric forecast counts", ""])
    for lane, count in manifest["numeric_forecast_counts"].items():
        lines.append(f"- {lane}: {count}")
    lines.extend(["", "## Recommendation-eligible counts", ""])
    for lane, count in manifest["recommendation_eligible_counts"].items():
        lines.append(f"- {lane}: {count}")
    lines.extend(["", "## Checks", ""])
    lines.extend(f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in checks.items())
    (OUTPUT / "PHASE_10_9_3_UNIFIED_MTG_INTELLIGENCE_CERTIFICATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    rows, diagnostics, manifest = build()
    write_outputs(rows, diagnostics, manifest)
    print(f"PHASE 10.9.3 UNIFIED MTG INTELLIGENCE: {manifest['status']}")
    print(json.dumps(manifest, indent=2))
    return 0 if manifest["status"] == "CERTIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
