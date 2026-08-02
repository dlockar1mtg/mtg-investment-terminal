from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median, pstdev
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_lorwyn_target_specific_comparable_contract_v1.json"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_lorwyn_target_specific_comparable_certification"


def clean(value: Any) -> str:
    return str(value or "").strip()


def norm(value: Any) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in clean(value)).split())


def number(value: Any) -> float | None:
    text = clean(value).replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        result = float(text)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(clean(value)[:10])
    except ValueError:
        return None


def categorical_similarity(left: str, right: str) -> tuple[float, bool]:
    if not left or not right or left == "UNKNOWN" or right == "UNKNOWN":
        return 0.0, False
    return (1.0 if left == right else 0.0), True


def bounded_similarity(distance: float, scale: float) -> float:
    return max(0.0, min(1.0, 1.0 - distance / scale))


def classify_name(name: str, contract: dict[str, Any]) -> dict[str, str]:
    upper = name.upper()
    rules = contract["governed_name_proxy_rules"]
    ub = any(pattern in upper for pattern in rules["universes_beyond_patterns"])
    premium = any(pattern in upper for pattern in rules["premium_patterns"])
    remastered = any(pattern in upper for pattern in rules["remastered_patterns"])
    lower_reprint = any(pattern in upper for pattern in rules["lower_reprint_exposure_patterns"])
    return {
        "product_configuration": "SEALED_COLLECTOR_BOOSTER_DISPLAY",
        "franchise_class": "UNIVERSES_BEYOND" if ub else "STANDARD_OR_CORE_MAGIC",
        "premium_content_class": "PREMIUM" if premium or ub else "STANDARD_COLLECTOR_TREATMENTS",
        "reprint_exposure_class": "ELEVATED" if remastered else ("LOWER_LICENSED_PRODUCT" if lower_reprint else "UNKNOWN"),
    }


def release_era(release: date) -> str:
    if release.year <= 2022:
        return "2020_2022"
    if release.year <= 2024:
        return "2023_2024"
    return "2025_2026"


def lifecycle_stage(release: date, snapshot: date) -> str:
    age = (snapshot - release).days
    if age < 180:
        return "EARLY_RELEASE"
    if age < 730:
        return "ESTABLISHING"
    return "MATURE"


def price_band(price: float, prices: list[float]) -> str:
    ordered = sorted(prices)
    q1 = ordered[max(0, int((len(ordered) - 1) * 0.25))]
    q2 = ordered[max(0, int((len(ordered) - 1) * 0.50))]
    q3 = ordered[max(0, int((len(ordered) - 1) * 0.75))]
    if price <= q1:
        return "LOW"
    if price <= q2:
        return "MID"
    if price <= q3:
        return "HIGH"
    return "PREMIUM"


def history_metrics(rows: list[dict[str, str]]) -> dict[str, float | int | None]:
    ordered = sorted(
        [(parse_date(row.get("observation_date")), number(row.get("market_price"))) for row in rows],
        key=lambda item: item[0] or date.min,
    )
    prices = [price for observation_date, price in ordered if observation_date and price and price > 0]
    returns = [math.log(prices[index] / prices[index - 1]) for index in range(1, len(prices))]
    return {
        "observation_count": len(prices),
        "median_log_return": median(returns) if returns else None,
        "volatility": pstdev(returns) if len(returns) >= 2 else None,
    }


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    paths = {name: ROOT / relative for name, relative in contract["authorities"].items()}
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise SystemExit("MISSING_REQUIRED_AUTHORITY:" + ";".join(missing))

    current_rows = read_csv(paths["product_and_current_price"])
    release_rows = read_csv(paths["release_date"])
    history_rows = read_csv(paths["historical_observations"])
    supply_rows = read_csv(paths["current_supply"])
    existing_pool_rows = read_csv(paths["existing_comparable_pool"])

    current_by_id = {clean(row["canonical_product_id"]): row for row in current_rows}
    release_by_id = {clean(row["canonical_product_id"]): row for row in release_rows}
    supply_by_id = {clean(row["canonical_product_id"]): row for row in supply_rows}
    history_by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in history_rows:
        history_by_id[clean(row["canonical_product_id"])].append(row)

    requested = norm(contract["requested_product_name"])
    target_matches = [row for row in current_rows if norm(row["product_name"]) == requested]
    failures: list[str] = []
    if len(target_matches) != 1:
        failures.append(f"TARGET_AUTHORITY_RESOLUTION_COUNT:{len(target_matches)}")
    target = target_matches[0] if len(target_matches) == 1 else None
    target_id = clean(target.get("canonical_product_id")) if target else ""
    target_release = parse_date(release_by_id.get(target_id, {}).get("official_release_date"))
    snapshot_date = date(2026, 8, 1)
    all_prices = [value for value in (number(row.get("current_price")) for row in current_rows) if value and value > 0]

    existing_hash_before = sha256(paths["existing_comparable_pool"])
    candidate_rows: list[dict[str, Any]] = []
    exclusion_rows: list[dict[str, Any]] = []

    if target and target_release:
        target_price = number(target.get("current_price"))
        target_supply = supply_by_id.get(target_id, {})
        target_name_classes = classify_name(clean(target.get("product_name")), contract)
        target_metrics = history_metrics(history_by_id.get(target_id, []))
        target_features = {
            **target_name_classes,
            "release_era": release_era(target_release),
            "lifecycle_stage": lifecycle_stage(target_release, snapshot_date),
            "price_band": price_band(target_price or 0.0, all_prices),
            "supply_profile": clean(target_supply.get("supply_category")) or "UNKNOWN",
            "liquidity_listings": number(target_supply.get("accepted_listing_count")),
            "liquidity_sellers": number(target_supply.get("distinct_seller_count")),
            **target_metrics,
        }

        for peer_id, peer in sorted(current_by_id.items()):
            if peer_id == target_id:
                exclusion_rows.append({"canonical_product_id": peer_id, "product_name": peer["product_name"], "exclusion_reason": "SELF_COMPARISON_PROHIBITED"})
                continue
            peer_release = parse_date(release_by_id.get(peer_id, {}).get("official_release_date"))
            peer_history = history_metrics(history_by_id.get(peer_id, []))
            reasons: list[str] = []
            if peer_release is None:
                reasons.append("MISSING_RELEASE_AUTHORITY")
            elif peer_release >= target_release:
                reasons.append("PEER_RELEASE_NOT_BEFORE_TARGET")
            if int(peer_history["observation_count"] or 0) < int(contract["minimum_history_observations"]):
                reasons.append("INSUFFICIENT_HISTORICAL_OBSERVATIONS")
            if reasons:
                exclusion_rows.append({"canonical_product_id": peer_id, "product_name": peer["product_name"], "exclusion_reason": "|".join(reasons)})
                continue

            peer_price = number(peer.get("current_price"))
            peer_supply = supply_by_id.get(peer_id, {})
            peer_features = {
                **classify_name(clean(peer.get("product_name")), contract),
                "release_era": release_era(peer_release),
                "lifecycle_stage": lifecycle_stage(peer_release, snapshot_date),
                "price_band": price_band(peer_price or 0.0, all_prices),
                "supply_profile": clean(peer_supply.get("supply_category")) or "UNKNOWN",
                "liquidity_listings": number(peer_supply.get("accepted_listing_count")),
                "liquidity_sellers": number(peer_supply.get("distinct_seller_count")),
                **peer_history,
            }

            dimensions: dict[str, tuple[float, bool]] = {}
            for field in ["product_configuration", "franchise_class", "premium_content_class", "reprint_exposure_class", "release_era", "lifecycle_stage", "price_band", "supply_profile"]:
                dimensions[field] = categorical_similarity(clean(target_features[field]), clean(peer_features[field]))

            target_listing = target_features["liquidity_listings"]
            peer_listing = peer_features["liquidity_listings"]
            target_sellers = target_features["liquidity_sellers"]
            peer_sellers = peer_features["liquidity_sellers"]
            if None not in (target_listing, peer_listing, target_sellers, peer_sellers):
                listing_sim = bounded_similarity(abs(float(target_listing) - float(peer_listing)), 30.0)
                seller_sim = bounded_similarity(abs(float(target_sellers) - float(peer_sellers)), 20.0)
                dimensions["liquidity_profile"] = ((listing_sim + seller_sim) / 2.0, True)
            else:
                dimensions["liquidity_profile"] = (0.0, False)

            target_return = target_features["median_log_return"]
            peer_return = peer_features["median_log_return"]
            target_vol = target_features["volatility"]
            peer_vol = peer_features["volatility"]
            if None not in (target_return, peer_return, target_vol, peer_vol):
                return_sim = bounded_similarity(abs(float(target_return) - float(peer_return)), 0.15)
                vol_sim = bounded_similarity(abs(float(target_vol) - float(peer_vol)), 0.25)
                dimensions["historical_behavior"] = ((return_sim + vol_sim) / 2.0, True)
            else:
                dimensions["historical_behavior"] = (0.0, False)

            weights = contract["weights"]
            total_weight = sum(float(weights[key]) for key in weights)
            observed_weight = sum(float(weights[key]) for key, (_, observed) in dimensions.items() if observed)
            weighted = sum(score * float(weights[key]) for key, (score, observed) in dimensions.items() if observed)
            score = 100.0 * weighted / total_weight
            coverage = observed_weight / total_weight
            meets = score >= float(contract["minimum_similarity_score"]) and coverage >= float(contract["minimum_dimension_coverage"])
            row = {
                "target_canonical_product_id": target_id,
                "target_product_name": target["product_name"],
                "target_release_date": target_release.isoformat(),
                "comparable_canonical_product_id": peer_id,
                "comparable_product_name": peer["product_name"],
                "comparable_release_date": peer_release.isoformat(),
                "comparable_observation_count": peer_history["observation_count"],
                "release_distance_days": (target_release - peer_release).days,
                "dimension_coverage": round(coverage, 6),
                "selection_score": round(score, 6),
                "meets_similarity_threshold": meets,
                "product_configuration_similarity": round(dimensions["product_configuration"][0] * 100, 6),
                "franchise_class_similarity": round(dimensions["franchise_class"][0] * 100, 6),
                "premium_content_similarity": round(dimensions["premium_content_class"][0] * 100, 6),
                "reprint_exposure_similarity": round(dimensions["reprint_exposure_class"][0] * 100, 6),
                "release_era_similarity": round(dimensions["release_era"][0] * 100, 6),
                "lifecycle_similarity": round(dimensions["lifecycle_stage"][0] * 100, 6),
                "price_band_similarity": round(dimensions["price_band"][0] * 100, 6),
                "supply_profile_similarity": round(dimensions["supply_profile"][0] * 100, 6),
                "liquidity_similarity": round(dimensions["liquidity_profile"][0] * 100, 6),
                "historical_behavior_similarity": round(dimensions["historical_behavior"][0] * 100, 6),
                "selection_basis": "GOVERNED_WEIGHTED_TARGET_SPECIFIC_SIMILARITY",
                "time_safe_rule": "PEER_RELEASE_BEFORE_TARGET;EVIDENCE_CUTOFF_2026-08-01",
                "certification_status": "CANDIDATE_THRESHOLD_PASS" if meets else "CANDIDATE_THRESHOLD_FAIL",
            }
            candidate_rows.append(row)

    candidate_rows.sort(key=lambda row: (-float(row["selection_score"]), clean(row["comparable_canonical_product_id"])))
    eligible = [row for row in candidate_rows if row["meets_similarity_threshold"]]
    selected = eligible[: int(contract["maximum_comparables"])]
    for rank, row in enumerate(selected, start=1):
        row["comparable_rank"] = rank
        row["certification_status"] = "CERTIFIED_SUPPLEMENTAL_COMPARABLE"
        row["confidence_penalty"] = "ELEVATED_UNCERTAINTY_NO_DIRECT_TARGET_HISTORY"
        row["limitations"] = "Target has no direct historical series; governed proxy dimensions and older certified-history peers used."

    if len(selected) < int(contract["minimum_comparables"]):
        failures.append(f"INSUFFICIENT_CERTIFIED_COMPARABLES:{len(selected)}")
    if target is None or target_release is None:
        failures.append("TARGET_IDENTITY_OR_RELEASE_UNRESOLVED")
    if any(row["comparable_canonical_product_id"] == target_id for row in selected):
        failures.append("SELF_COMPARISON_SELECTED")
    if len({row["comparable_canonical_product_id"] for row in selected}) != len(selected):
        failures.append("DUPLICATE_COMPARABLE_SELECTED")
    if sha256(paths["existing_comparable_pool"]) != existing_hash_before:
        failures.append("EXISTING_COMPARABLE_AUTHORITY_MODIFIED")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_lorwyn_comparable_candidate_audit.csv", candidate_rows)
    write_csv(OUTPUT / "collector_lorwyn_certified_comparable_group.csv", selected)
    write_csv(OUTPUT / "collector_lorwyn_comparable_exclusion_ledger.csv", exclusion_rows)
    write_csv(OUTPUT / "collector_lorwyn_comparable_score_components.csv", candidate_rows)

    status = contract["expected_status"] if not failures else "FAIL_COLLECTOR_LORWYN_TARGET_SPECIFIC_COMPARABLE_CERTIFICATION"
    summary = {
        "contract_name": contract["contract_name"],
        "contract_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "resolved_target_canonical_product_id": target_id,
        "candidate_rows": len(candidate_rows),
        "excluded_rows": len(exclusion_rows),
        "threshold_pass_rows": len(eligible),
        "certified_comparable_rows": len(selected),
        "minimum_comparables": contract["minimum_comparables"],
        "maximum_comparables": contract["maximum_comparables"],
        "minimum_similarity_score": contract["minimum_similarity_score"],
        "existing_comparable_authority_sha256_before": existing_hash_before,
        "existing_comparable_authority_sha256_after": sha256(paths["existing_comparable_pool"]),
        "projection_authorized": False,
        "production_forecast_authorized": False,
        "ranking_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": status,
    }
    (OUTPUT / "collector_lorwyn_comparable_certification_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
