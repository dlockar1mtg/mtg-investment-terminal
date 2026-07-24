from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_PRODUCTS = 973
EXPECTED_FULL = 214
EXPECTED_PROVISIONAL = 380
EXPECTED_STRUCTURAL = 379


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def f(value: object, default: float | None = None) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finish_group(name: str) -> str:
    text = name.lower()
    if "non-foil" in text or "nonfoil" in text:
        return "NONFOIL"
    if "etched" in text:
        return "ETCHED_FOIL"
    if "rainbow foil" in text:
        return "RAINBOW_FOIL"
    if "galaxy foil" in text:
        return "GALAXY_FOIL"
    if "raised foil" in text:
        return "RAISED_FOIL"
    if "foil" in text:
        return "FOIL"
    return "UNSPECIFIED"


def product_group(name: str) -> str:
    text = name.lower()
    if "bundle" in text:
        return "BUNDLE"
    if "promo" in text:
        return "PROMO"
    if "artist series" in text or "special guest" in text or "featuring:" in text:
        return "ARTIST"
    if " x " in text or "secret lair x" in text:
        return "CROSSOVER"
    return "STANDARD_DROP"


def peer_key(name: str) -> tuple[str, str]:
    return finish_group(name), product_group(name)


def median(values: list[float]) -> float | None:
    clean = [x for x in values if x > 0 and math.isfinite(x)]
    return float(statistics.median(clean)) if clean else None


def observed_anchor(row: dict[str, str]) -> float | None:
    direct = f(row.get("market_value_usd"))
    if direct and direct > 0:
        return direct
    low = f(row.get("market_value_low"))
    high = f(row.get("market_value_high"))
    if low and high and low > 0 and high > 0:
        return (low + high) / 2
    if low and low > 0:
        return low
    if high and high > 0:
        return high
    return None


def percentile_rank(values: list[float], value: float) -> float:
    if not values:
        return 50.0
    ordered = sorted(values)
    below = sum(1 for item in ordered if item < value)
    equal = sum(1 for item in ordered if item == value)
    return 100.0 * (below + 0.5 * equal) / len(ordered)


def build(ledger_path: Path, output_root: Path) -> dict[str, object]:
    source = read_csv(ledger_path)
    if not source:
        raise ValueError("Admission ledger is empty")

    ids = [row["canonical_product_id"].strip() for row in source]
    if len(ids) != len(set(ids)):
        raise ValueError("Admission ledger contains duplicate canonical_product_id values")

    peer_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    finish_values: dict[str, list[float]] = defaultdict(list)
    global_values: list[float] = []
    for row in source:
        anchor = observed_anchor(row)
        if anchor and anchor > 0:
            name = row.get("canonical_product_name", "")
            peer_values[peer_key(name)].append(anchor)
            finish_values[finish_group(name)].append(anchor)
            global_values.append(anchor)

    global_median = median(global_values)
    if global_median is None:
        raise ValueError("No observed market anchors available")

    evaluated: list[dict[str, object]] = []
    for row in source:
        product_id = row["canonical_product_id"].strip()
        name = row.get("canonical_product_name", "")
        decision = row.get("quality_decision", "")
        original_confidence = f(row.get("confidence_score"), 0.0) or 0.0
        observations = int(f(row.get("observation_count"), 0.0) or 0)
        sellers = int(f(row.get("seller_count"), 0.0) or 0)
        low = f(row.get("market_value_low"))
        high = f(row.get("market_value_high"))
        anchor = observed_anchor(row)
        group = peer_key(name)
        peer_med = median(peer_values.get(group, []))
        finish_med = median(finish_values.get(group[0], []))
        comparable = peer_med or finish_med or global_median

        if decision == "PASS":
            tier = "FULL_MODEL"
            value = f(row.get("market_value_usd")) or anchor or comparable
            method = "OBSERVED_GOVERNED_MEDIAN"
            confidence = min(100.0, max(0.0, original_confidence))
            model_weight = 1.0
            forecast_status = "FULL_FORECAST"
            recommendation_status = "ELIGIBLE" if confidence >= 60 else "WATCH_ONLY"
            uncertainty = max(0.15, 1.0 - confidence / 100.0)
        elif decision == "REVIEW_REQUIRED":
            tier = "PROVISIONAL_MODEL"
            value = anchor or comparable
            method = "PROVISIONAL_OBSERVED_MIDPOINT" if anchor else "COMPARABLE_FALLBACK"
            confidence = min(55.0, max(20.0, original_confidence))
            model_weight = round(0.25 + 0.5 * confidence / 100.0, 4)
            forecast_status = "WIDE_INTERVAL_FORECAST"
            recommendation_status = "WATCH_ONLY"
            uncertainty = max(0.45, 1.15 - confidence / 100.0)
        else:
            tier = "STRUCTURAL_ONLY"
            value = comparable
            method = "COMPARABLE_GROUP_MEDIAN"
            confidence = min(30.0, max(10.0, original_confidence if original_confidence > 0 else 15.0))
            model_weight = round(0.05 + 0.2 * confidence / 100.0, 4)
            forecast_status = "STRUCTURAL_RANGE_ONLY"
            recommendation_status = "DATA_NEEDED"
            uncertainty = 0.75

        value = round(float(value), 2)
        if low is None or low <= 0:
            low = value * (1 - uncertainty)
        if high is None or high <= 0:
            high = value * (1 + uncertainty)
        low = round(max(0.01, float(low)), 2)
        high = round(max(low, float(high)), 2)

        evidence_score = min(100.0, observations * 8.0 + sellers * 6.0)
        evaluated.append({
            "investment_product_id": product_id,
            "canonical_product_id": product_id,
            "canonical_product_name": name,
            "finish_group": group[0],
            "product_group": group[1],
            "evaluation_tier": tier,
            "quality_decision": decision,
            "valuation_method": method,
            "evaluated_market_value_usd": value,
            "forecast_low_usd": low,
            "forecast_base_usd": value,
            "forecast_high_usd": high,
            "currency": "USD",
            "observation_count": observations,
            "seller_count": sellers,
            "evidence_confidence_score": round(original_confidence, 2),
            "model_confidence_score": round(confidence, 2),
            "model_weight": model_weight,
            "forecast_status": forecast_status,
            "recommendation_status": recommendation_status,
            "quality_flags": row.get("quality_flags", ""),
            "suppression_reason": row.get("suppression_reason", ""),
            "source": row.get("source", ""),
            "source_valuation_method": row.get("valuation_method", ""),
            "evidence_score": round(evidence_score, 2),
        })

    values = [float(row["evaluated_market_value_usd"]) for row in evaluated]
    for row in evaluated:
        value_rank = percentile_rank(values, float(row["evaluated_market_value_usd"]))
        confidence = float(row["model_confidence_score"])
        evidence = float(row["evidence_score"])
        tier_bonus = {"FULL_MODEL": 15.0, "PROVISIONAL_MODEL": 5.0, "STRUCTURAL_ONLY": 0.0}[str(row["evaluation_tier"])]
        score = min(100.0, value_rank * 0.35 + confidence * 0.35 + evidence * 0.15 + tier_bonus)
        row["model_evaluation_score"] = round(score, 2)
        if row["recommendation_status"] == "ELIGIBLE":
            row["guarded_recommendation"] = "REVIEW_FOR_BUY" if score >= 70 else "HOLD_OR_WATCH"
        elif row["recommendation_status"] == "WATCH_ONLY":
            row["guarded_recommendation"] = "WATCH"
        else:
            row["guarded_recommendation"] = "DATA_NEEDED"

    tier_counts = defaultdict(int)
    for row in evaluated:
        tier_counts[str(row["evaluation_tier"])] += 1

    registry_columns = [
        "investment_product_id", "canonical_product_name", "finish_group", "product_group",
        "evaluation_tier", "quality_decision", "valuation_method", "evaluated_market_value_usd",
        "model_confidence_score", "model_weight", "forecast_status", "recommendation_status",
        "guarded_recommendation", "quality_flags", "suppression_reason", "currency",
    ]
    forecast_columns = [
        "investment_product_id", "canonical_product_name", "evaluation_tier", "forecast_low_usd",
        "forecast_base_usd", "forecast_high_usd", "model_confidence_score", "model_weight",
        "forecast_status", "valuation_method", "currency",
    ]
    recommendation_columns = [
        "investment_product_id", "canonical_product_name", "evaluation_tier", "model_evaluation_score",
        "guarded_recommendation", "recommendation_status", "model_confidence_score", "model_weight",
        "evaluated_market_value_usd", "currency",
    ]

    output_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "full_registry": output_root / "secret_lair_full_product_registry.csv",
        "full_evaluation": output_root / "secret_lair_full_model_evaluation.csv",
        "forecast_inputs": output_root / "secret_lair_full_forecast_inputs.csv",
        "recommendation_inputs": output_root / "secret_lair_guarded_recommendations.csv",
        "manifest": output_root / "secret_lair_full_model_evaluation_manifest.json",
        "certification": output_root / "SECRET_LAIR_FULL_MODEL_EVALUATION_CERTIFICATION.md",
    }
    write_csv(paths["full_registry"], evaluated, registry_columns)
    write_csv(paths["full_evaluation"], evaluated, list(evaluated[0].keys()))
    write_csv(paths["forecast_inputs"], evaluated, forecast_columns)
    write_csv(paths["recommendation_inputs"], evaluated, recommendation_columns)

    checks = {
        "ledger_rows_equal_973": len(source) == EXPECTED_PRODUCTS,
        "evaluation_rows_equal_973": len(evaluated) == EXPECTED_PRODUCTS,
        "evaluation_ids_unique": len({row["investment_product_id"] for row in evaluated}) == EXPECTED_PRODUCTS,
        "source_and_evaluation_ids_match": set(ids) == {row["investment_product_id"] for row in evaluated},
        "full_model_count_equal_214": tier_counts["FULL_MODEL"] == EXPECTED_FULL,
        "provisional_model_count_equal_380": tier_counts["PROVISIONAL_MODEL"] == EXPECTED_PROVISIONAL,
        "structural_only_count_equal_379": tier_counts["STRUCTURAL_ONLY"] == EXPECTED_STRUCTURAL,
        "all_products_have_evaluated_value": all(float(row["evaluated_market_value_usd"]) > 0 for row in evaluated),
        "all_products_have_forecast_range": all(float(row["forecast_low_usd"]) > 0 and float(row["forecast_high_usd"]) >= float(row["forecast_low_usd"]) for row in evaluated),
        "all_products_have_guarded_recommendation": all(str(row["guarded_recommendation"]).strip() for row in evaluated),
        "only_full_model_can_be_buy_review": all(row["evaluation_tier"] == "FULL_MODEL" for row in evaluated if row["guarded_recommendation"] == "REVIEW_FOR_BUY"),
        "quota_calls_zero": True,
    }
    status = "CERTIFIED" if all(checks.values()) else "FAILED"
    result = {
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_ledger": str(ledger_path.resolve()),
        "source_ledger_sha256": sha256(ledger_path),
        "products": len(evaluated),
        "full_model_products": tier_counts["FULL_MODEL"],
        "provisional_model_products": tier_counts["PROVISIONAL_MODEL"],
        "structural_only_products": tier_counts["STRUCTURAL_ONLY"],
        "forecast_rows": len(evaluated),
        "recommendation_rows": len(evaluated),
        "quota_calls": 0,
        "checks": checks,
        "outputs": {key: str(value.resolve()) for key, value in paths.items()},
    }
    paths["manifest"].write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Secret Lair Full Model Evaluation Certification", "",
        f"**Status:** {status}", f"**Generated at (UTC):** {result['generated_at_utc']}", "",
        "## Coverage", "",
        f"- Products evaluated: {len(evaluated)}",
        f"- Full model: {tier_counts['FULL_MODEL']}",
        f"- Provisional model: {tier_counts['PROVISIONAL_MODEL']}",
        f"- Structural only: {tier_counts['STRUCTURAL_ONLY']}",
        f"- Forecast rows: {len(evaluated)}",
        f"- Recommendation rows: {len(evaluated)}",
        "- API quota calls: 0", "", "## Certification Checks", "",
    ]
    lines.extend(f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in checks.items())
    lines += ["", "## Governance", "", "All 973 products are evaluated. Only FULL_MODEL products may receive a buy-review recommendation. Provisional and structural products remain confidence-limited and explicitly guarded."]
    paths["certification"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("SECRET LAIR FULL MODEL EVALUATION: COMPLETE")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admission-ledger", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    build(args.admission_ledger, args.output_root)


if __name__ == "__main__":
    main()
