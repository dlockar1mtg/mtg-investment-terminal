from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FULL = "FULL_MODEL"
PROVISIONAL = "PROVISIONAL_MODEL"
STRUCTURAL = "STRUCTURAL_ONLY"

NATIVE_RANGE = "NATIVE_MONTE_CARLO_RANGE"
OBSERVED_ONLY = "OBSERVED_VALUE_ONLY"
NO_FORECAST = "NO_NUMERIC_FORECAST"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _number(value: Any) -> float | None:
    text = str(value or "").strip().replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        result = float(text)
    except ValueError:
        return None
    return None if math.isnan(result) else result


def _money(value: float | None) -> object:
    return "" if value is None else round(value, 2)


def _source_id(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("MTG:"):
        text = text.split(":")[-1]
    return text


def _default_model_input() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "product_master" / "product_master_model_input.csv"


def _model_index(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None or not path.is_file():
        return {}
    result: dict[str, dict[str, str]] = {}
    for row in _read_csv(path):
        source_id = _source_id(row.get("investment_product_id"))
        if source_id:
            result[source_id] = row
    return result


def _native_values(row: dict[str, str]) -> tuple[float | None, float | None, float | None, float | None]:
    current = (
        _number(row.get("current_price"))
        or _number(row.get("market_price"))
        or _number(row.get("current_price_history"))
        or _number(row.get("current_price_db"))
    )
    low = _number(row.get("mc_p05"))
    base = _number(row.get("mc_median")) or _number(row.get("mc_expected_value"))
    high = _number(row.get("mc_p95"))
    return current, low, base, high


def build_evaluation(
    admission_ledger: Path,
    output_root: Path,
    native_model_input: Path | None = None,
) -> dict[str, object]:
    rows = _read_csv(admission_ledger)
    model_path = native_model_input if native_model_input is not None else _default_model_input()
    native_models = _model_index(model_path)

    evaluation_rows: list[dict[str, object]] = []
    forecast_rows: list[dict[str, object]] = []
    recommendation_rows: list[dict[str, object]] = []

    for row in rows:
        tier = row["admission_tier"]
        source_id = _source_id(row["canonical_product_id"])
        observed = _number(row.get("market_value_usd"))
        model = native_models.get(source_id)

        native_current = native_low = native_base = native_high = None
        if model is not None:
            native_current, native_low, native_base, native_high = _native_values(model)

        current = native_current if native_current is not None else observed
        native_ready = all(
            value is not None
            for value in (native_current, native_low, native_base, native_high)
        )

        if native_ready:
            method = NATIVE_RANGE
            forecast_status = "NATIVE_RANGE_READY"
            # A native Monte Carlo range is a valuation range, not a
            # certified horizon forecast.
            forecast_eligible = "NO"
            consumption_state = "NATIVE_RANGE_ONLY"
        elif current is not None:
            method = OBSERVED_ONLY
            forecast_status = "OBSERVED_VALUE_ONLY"
            forecast_eligible = "NO"
            consumption_state = "NO_CERTIFIED_FORECAST"
        else:
            method = NO_FORECAST
            forecast_status = "SUPPRESSED"
            forecast_eligible = "NO"
            consumption_state = "NO_NUMERIC_VALUE"

        evaluation_rows.append({
            "canonical_product_id": row["canonical_product_id"],
            "canonical_product_name": row["canonical_product_name"],
            "canonical_set_name": row.get("canonical_set_name", ""),
            "admission_tier": tier,
            "valuation_basis": row.get("valuation_basis", ""),
            "confidence": row.get("confidence", ""),
            "retained_observations": row.get("retained_observations", ""),
            "current_market_value_usd": _money(current),
            "evaluation_status": "EVALUATED" if current is not None else "STRUCTURAL_SUPPRESSED",
            "forecast_status": forecast_status,
            "forecast_method": method,
            "forecast_consumption_state": consumption_state,
            "recommendation_status": "AWAITING_HORIZON_FORECAST_CERTIFICATION",
        })

        forecast_rows.append({
            "canonical_product_id": row["canonical_product_id"],
            "canonical_product_name": row["canonical_product_name"],
            "admission_tier": tier,
            "current_market_value_usd": _money(current),
            "forecast_method": method,
            "forecast_status": forecast_status,
            "forecast_eligible": forecast_eligible,
            "native_range_eligible": (
                "YES" if native_ready else "NO"
            ),
            "native_forecast_low_usd": _money(native_low),
            "native_forecast_base_usd": _money(native_base),
            "native_forecast_high_usd": _money(native_high),
            "horizon_model_certified": "NO",
            "horizon_forecast_status": "SUPPRESSED_UNTIL_HORIZON_MODEL_CERTIFIED",
            "1y_downside_usd": "",
            "1y_base_usd": "",
            "1y_upside_usd": "",
            "3y_downside_usd": "",
            "3y_base_usd": "",
            "3y_upside_usd": "",
            "5y_downside_usd": "",
            "5y_base_usd": "",
            "5y_upside_usd": "",
        })

        recommendation_rows.append({
            "canonical_product_id": row["canonical_product_id"],
            "canonical_product_name": row["canonical_product_name"],
            "admission_tier": tier,
            "action": "HOLD_REVIEW" if current is not None else "NO_ACTION",
            "recommendation_eligible": "NO",
            "market_value_usd": _money(current),
            "confidence": row.get("confidence", ""),
            "recommendation_status": "AWAITING_HORIZON_FORECAST_CERTIFICATION",
            "rationale": (
                "Native valuation range retained; directional recommendation is withheld "
                "until horizon-specific forecasts are certified."
                if current is not None
                else "No accepted observed market value; recommendation is suppressed."
            ),
        })

    output_root.mkdir(parents=True, exist_ok=True)
    evaluation_path = output_root / "collector_booster_box_full_evaluation.csv"
    forecast_path = output_root / "collector_booster_box_guarded_forecasts.csv"
    recommendation_path = output_root / "collector_booster_box_guarded_recommendations.csv"
    _write_csv(evaluation_path, evaluation_rows)
    _write_csv(forecast_path, forecast_rows)
    _write_csv(recommendation_path, recommendation_rows)

    tiers = Counter(row["admission_tier"] for row in rows)
    native_count = sum(row["forecast_method"] == NATIVE_RANGE for row in forecast_rows)
    false_horizon_count = sum(
        any(str(row[field]).strip() for field in (
            "1y_downside_usd", "1y_base_usd", "1y_upside_usd",
            "3y_downside_usd", "3y_base_usd", "3y_upside_usd",
            "5y_downside_usd", "5y_base_usd", "5y_upside_usd",
        ))
        for row in forecast_rows
    )

    checks = {
        "row_counts_match": len(rows) == len(evaluation_rows) == len(forecast_rows) == len(recommendation_rows),
        "tier_counts_valid": (
            sum(tiers.values()) == len(rows)
            and set(tiers).issubset(
                {FULL, PROVISIONAL, STRUCTURAL}
            )
        ),
        "no_tier_guarded_scenario_bands": all(row["forecast_method"] != "TIER_GUARDED_SCENARIO_BANDS" for row in forecast_rows),
        "false_horizon_values_zero": false_horizon_count == 0,
        "native_ranges_ordered": all(
            float(row["native_forecast_low_usd"]) <= float(row["native_forecast_base_usd"]) <= float(row["native_forecast_high_usd"])
            for row in forecast_rows
            if row["forecast_method"] == NATIVE_RANGE
        ),
        "recommendations_fail_closed": all(row["recommendation_eligible"] == "NO" for row in recommendation_rows),
        "quota_calls_zero": True,
    }
    status = "CERTIFIED" if all(checks.values()) else "FAILED"

    manifest = {
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "8.2.1B.3",
        "lane": "COLLECTOR_BOOSTER_BOX",
        "products": len(rows),
        "tier_counts": dict(sorted(tiers.items())),
        "native_range_products": native_count,
        "observed_value_only_products": sum(row["forecast_method"] == OBSERVED_ONLY for row in forecast_rows),
        "suppressed_products": sum(row["forecast_method"] == NO_FORECAST for row in forecast_rows),
        "certified_horizon_products": 0,
        "recommendation_eligible_products": 0,
        "quota_calls": 0,
        "checks": checks,
        "admission_ledger_sha256": hashlib.sha256(admission_ledger.read_bytes()).hexdigest(),
        "native_model_input": str(model_path.resolve()) if model_path.is_file() else "",
        "outputs": {
            "evaluation": str(evaluation_path.resolve()),
            "forecasts": str(forecast_path.resolve()),
            "recommendations": str(recommendation_path.resolve()),
        },
    }

    manifest_path = output_root / "collector_booster_box_full_evaluation_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest["outputs"]["manifest"] = str(manifest_path.resolve())
    return manifest

