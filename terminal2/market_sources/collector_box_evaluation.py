from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

FULL = "FULL_MODEL"
PROVISIONAL = "PROVISIONAL_MODEL"
STRUCTURAL = "STRUCTURAL_ONLY"

SCENARIOS = {
    FULL: {"1y": (0.85, 1.08, 1.25), "3y": (0.80, 1.25, 1.65), "5y": (0.75, 1.45, 2.10)},
    PROVISIONAL: {"1y": (0.70, 1.05, 1.40), "3y": (0.60, 1.15, 1.90), "5y": (0.50, 1.25, 2.50)},
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _money(value: float | None) -> object:
    return "" if value is None else round(value, 2)


def build_evaluation(admission_ledger: Path, output_root: Path) -> dict[str, object]:
    rows = _read_csv(admission_ledger)
    evaluation_rows: list[dict[str, object]] = []
    forecast_rows: list[dict[str, object]] = []
    recommendation_rows: list[dict[str, object]] = []

    for row in rows:
        tier = row["admission_tier"]
        raw_value = row.get("market_value_usd", "").strip()
        value = float(raw_value) if raw_value else None
        numeric = tier in {FULL, PROVISIONAL} and value is not None

        evaluation_rows.append({
            "canonical_product_id": row["canonical_product_id"],
            "canonical_product_name": row["canonical_product_name"],
            "canonical_set_name": row.get("canonical_set_name", ""),
            "admission_tier": tier,
            "valuation_basis": row.get("valuation_basis", ""),
            "confidence": row.get("confidence", ""),
            "retained_observations": row.get("retained_observations", ""),
            "current_market_value_usd": _money(value),
            "evaluation_status": "EVALUATED" if numeric else "STRUCTURAL_SUPPRESSED",
            "forecast_status": "SCENARIO_READY" if numeric else "SUPPRESSED",
            "recommendation_status": "ELIGIBLE" if tier == FULL else "GUARDED",
        })

        forecast: dict[str, object] = {
            "canonical_product_id": row["canonical_product_id"],
            "canonical_product_name": row["canonical_product_name"],
            "admission_tier": tier,
            "current_market_value_usd": _money(value),
            "forecast_method": "TIER_GUARDED_SCENARIO_BANDS" if numeric else "NO_NUMERIC_FORECAST",
            "forecast_eligible": "YES" if numeric else "NO",
        }
        for horizon in ("1y", "3y", "5y"):
            if numeric:
                downside, base, upside = SCENARIOS[tier][horizon]
                forecast[f"{horizon}_downside_usd"] = _money(value * downside)
                forecast[f"{horizon}_base_usd"] = _money(value * base)
                forecast[f"{horizon}_upside_usd"] = _money(value * upside)
            else:
                forecast[f"{horizon}_downside_usd"] = ""
                forecast[f"{horizon}_base_usd"] = ""
                forecast[f"{horizon}_upside_usd"] = ""
        forecast_rows.append(forecast)

        if tier == FULL:
            action = "HOLD_REVIEW"
            eligible = "YES"
            rationale = "Observed governed value with sufficient evidence; directional trading signal withheld until historical-return features are certified."
        elif tier == PROVISIONAL:
            action = "WATCH"
            eligible = "NO"
            rationale = "Observed value exists but evidence is limited; recommendation remains guarded."
        else:
            action = "NO_ACTION"
            eligible = "NO"
            rationale = "No accepted observed market value; numerical forecast and recommendation are suppressed."

        recommendation_rows.append({
            "canonical_product_id": row["canonical_product_id"],
            "canonical_product_name": row["canonical_product_name"],
            "admission_tier": tier,
            "action": action,
            "recommendation_eligible": eligible,
            "market_value_usd": _money(value),
            "confidence": row.get("confidence", ""),
            "rationale": rationale,
        })

    output_root.mkdir(parents=True, exist_ok=True)
    evaluation_path = output_root / "collector_booster_box_full_evaluation.csv"
    forecast_path = output_root / "collector_booster_box_guarded_forecasts.csv"
    recommendation_path = output_root / "collector_booster_box_guarded_recommendations.csv"
    _write_csv(evaluation_path, evaluation_rows)
    _write_csv(forecast_path, forecast_rows)
    _write_csv(recommendation_path, recommendation_rows)

    tiers = Counter(row["admission_tier"] for row in rows)
    checks = {
        "rows_equal_49": len(rows) == 49,
        "evaluation_rows_equal_49": len(evaluation_rows) == 49,
        "forecast_rows_equal_49": len(forecast_rows) == 49,
        "recommendation_rows_equal_49": len(recommendation_rows) == 49,
        "tier_counts_match": tiers == Counter({FULL: 36, PROVISIONAL: 11, STRUCTURAL: 2}),
        "numeric_forecasts_equal_47": sum(row["forecast_eligible"] == "YES" for row in forecast_rows) == 47,
        "structural_forecasts_suppressed": all(row["forecast_eligible"] == "NO" for row in forecast_rows if row["admission_tier"] == STRUCTURAL),
        "only_full_model_recommendation_eligible": all((row["recommendation_eligible"] == "YES") == (row["admission_tier"] == FULL) for row in recommendation_rows),
        "no_directional_trade_actions": all(row["action"] not in {"BUY", "SELL"} for row in recommendation_rows),
        "quota_calls_zero": True,
    }
    status = "CERTIFIED" if all(checks.values()) else "FAILED"
    manifest = {
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "10.7.5",
        "lane": "COLLECTOR_BOOSTER_BOX",
        "products": len(rows),
        "tier_counts": dict(sorted(tiers.items())),
        "numeric_forecast_products": sum(row["forecast_eligible"] == "YES" for row in forecast_rows),
        "recommendation_eligible_products": sum(row["recommendation_eligible"] == "YES" for row in recommendation_rows),
        "quota_calls": 0,
        "checks": checks,
        "admission_ledger_sha256": hashlib.sha256(admission_ledger.read_bytes()).hexdigest(),
        "outputs": {"evaluation": str(evaluation_path.resolve()), "forecasts": str(forecast_path.resolve()), "recommendations": str(recommendation_path.resolve())},
    }
    manifest_path = output_root / "collector_booster_box_full_evaluation_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    certification_path = output_root / "PHASE_10_7_5_COLLECTOR_BOX_EVALUATION_CERTIFICATION.md"
    lines = ["# Phase 10.7.5 Collector Booster Box Full Evaluation Certification", "", f"**Status:** {status}", "", f"- Products: {len(rows)}", f"- Full model: {tiers[FULL]}", f"- Provisional model: {tiers[PROVISIONAL]}", f"- Structural only: {tiers[STRUCTURAL]}", f"- Numeric forecast products: {manifest['numeric_forecast_products']}", f"- Recommendation-eligible products: {manifest['recommendation_eligible_products']}", "- API quota calls: 0", "", "## Checks", ""]
    lines += [f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in checks.items()]
    lines += ["", "## Interpretation", "", "Forecasts are guarded scenario bands, not claims of realized future returns. Directional trading actions remain withheld until historical-return and liquidity features are separately certified."]
    certification_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest["outputs"]["manifest"] = str(manifest_path.resolve())
    manifest["outputs"]["certification"] = str(certification_path.resolve())
    return manifest
