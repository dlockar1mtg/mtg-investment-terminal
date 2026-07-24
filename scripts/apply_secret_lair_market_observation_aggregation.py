from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts/aggregate_secret_lair_market_observations.py"
TESTS = ROOT / "tests/test_secret_lair_market_observation_aggregation.py"

TARGET_CONTENT = r'''from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CERTIFICATION = ROOT / "data/validation/phase_10/ebay_matching/certification/secret_lair_ebay_lane_certification.json"
DEFAULT_OUTPUT_ROOT = ROOT / "data/validation/phase_10/ebay_matching/market_observations"

OUTPUT_FIELDS = [
    "canonical_product_id", "canonical_product_name", "canonical_set_name", "product_class",
    "tcgplayer_product_id", "release_date", "ebay_query", "accepted_listing_count_raw",
    "accepted_listing_count_deduped", "outlier_listing_count", "observation_count",
    "seller_count", "market_value_median", "market_value_mean", "market_value_low",
    "market_value_high", "price_dispersion_cv", "sample_state", "confidence_score",
    "confidence_state", "observed_at_utc", "source_lane_certification_status",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def to_float(value: Any) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def percentile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def outlier_bounds(values: list[float]) -> tuple[float, float]:
    if len(values) < 4:
        return (min(values), max(values)) if values else (0.0, 0.0)
    q1 = percentile(values, 0.25)
    q3 = percentile(values, 0.75)
    iqr = q3 - q1
    if iqr <= 0:
        return min(values), max(values)
    return max(0.0, q1 - 1.5 * iqr), q3 + 1.5 * iqr


def dedupe_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    selected: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        product_id = (row.get("canonical_product_id") or "").strip()
        item_id = (row.get("ebay_item_id") or "").strip()
        if not product_id or not item_id:
            continue
        key = (product_id, item_id)
        current = selected.get(key)
        if current is None:
            selected[key] = row
            continue
        current_score = to_float(current.get("match_score")) or 0.0
        candidate_score = to_float(row.get("match_score")) or 0.0
        if candidate_score > current_score:
            selected[key] = row
    return list(selected.values())


def sample_state(count: int, sellers: int) -> str:
    if count == 0:
        return "NO_ACCEPTED_EVIDENCE"
    if count == 1:
        return "SINGLE_OBSERVATION"
    if count < 5 or sellers < 2:
        return "LIMITED_EVIDENCE"
    if count < 10 or sellers < 3:
        return "MODERATE_EVIDENCE"
    return "STRONG_EVIDENCE"


def confidence(count: int, sellers: int, cv: float | None, outlier_share: float) -> tuple[float, str]:
    sample_component = min(count / 10.0, 1.0) * 45.0
    seller_component = min(sellers / 4.0, 1.0) * 25.0
    dispersion_component = 20.0 if cv is None else max(0.0, 20.0 * (1.0 - min(cv, 1.0)))
    outlier_component = max(0.0, 10.0 * (1.0 - min(outlier_share, 1.0)))
    score = round(sample_component + seller_component + dispersion_component + outlier_component, 2)
    if count == 0:
        return 0.0, "NO_EVIDENCE"
    if score >= 80:
        state = "HIGH"
    elif score >= 60:
        state = "MEDIUM"
    elif score >= 35:
        state = "LOW"
    else:
        state = "VERY_LOW"
    return score, state


def aggregate_product(product: dict[str, str], accepted: list[dict[str, str]], observed: str) -> dict[str, Any]:
    raw_count = len(accepted)
    deduped = dedupe_rows(accepted)
    priced = [(row, to_float(row.get("landed_price"))) for row in deduped]
    priced = [(row, price) for row, price in priced if price is not None]
    values = [price for _, price in priced]
    low_bound, high_bound = outlier_bounds(values)
    retained = [(row, price) for row, price in priced if low_bound <= price <= high_bound]
    retained_values = [price for _, price in retained]
    sellers = {(row.get("seller_hash") or "").strip() for row, _ in retained if (row.get("seller_hash") or "").strip()}
    outliers = len(priced) - len(retained)
    count = len(retained_values)
    mean = statistics.fmean(retained_values) if retained_values else None
    median = statistics.median(retained_values) if retained_values else None
    cv = (statistics.pstdev(retained_values) / mean) if count > 1 and mean else None
    outlier_share = outliers / len(priced) if priced else 0.0
    score, confidence_state = confidence(count, len(sellers), cv, outlier_share)
    row: dict[str, Any] = {field: product.get(field, "") for field in OUTPUT_FIELDS}
    row.update({
        "accepted_listing_count_raw": raw_count,
        "accepted_listing_count_deduped": len(deduped),
        "outlier_listing_count": outliers,
        "observation_count": count,
        "seller_count": len(sellers),
        "market_value_median": round(median, 2) if median is not None else "",
        "market_value_mean": round(mean, 2) if mean is not None else "",
        "market_value_low": round(min(retained_values), 2) if retained_values else "",
        "market_value_high": round(max(retained_values), 2) if retained_values else "",
        "price_dispersion_cv": round(cv, 4) if cv is not None else "",
        "sample_state": sample_state(count, len(sellers)),
        "confidence_score": score,
        "confidence_state": confidence_state,
        "observed_at_utc": observed,
        "source_lane_certification_status": "CERTIFIED",
    })
    return row


def run(certification_path: Path, output_root: Path) -> dict[str, Any]:
    certification = json.loads(certification_path.read_text(encoding="utf-8"))
    if certification.get("status") != "CERTIFIED":
        raise RuntimeError("Secret Lair eBay lane certification is not CERTIFIED")

    products: dict[str, dict[str, str]] = {}
    accepted_by_product: dict[str, list[dict[str, str]]] = defaultdict(list)
    source_listing_rows = 0

    for batch in certification.get("batches", []):
        for product in read_csv(Path(batch["coverage_path"])):
            product_id = (product.get("canonical_product_id") or "").strip()
            if product_id:
                products.setdefault(product_id, product)
        listings = read_csv(Path(batch["listings_path"]))
        source_listing_rows += len(listings)
        for row in listings:
            if row.get("match_state") == "ACCEPTED":
                product_id = (row.get("canonical_product_id") or "").strip()
                if product_id:
                    accepted_by_product[product_id].append(row)

    observed = datetime.now(timezone.utc).isoformat()
    rows = [aggregate_product(products[product_id], accepted_by_product.get(product_id, []), observed) for product_id in sorted(products)]
    output_root.mkdir(parents=True, exist_ok=True)
    csv_path = output_root / "secret_lair_market_observations.csv"
    json_path = output_root / "secret_lair_market_observation_summary.json"
    write_csv(csv_path, rows)

    state_counts: dict[str, int] = defaultdict(int)
    confidence_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        state_counts[str(row["sample_state"])] += 1
        confidence_counts[str(row["confidence_state"])] += 1

    summary = {
        "status": "COMPLETE",
        "generated_at_utc": observed,
        "source_certification": str(certification_path.resolve()),
        "source_lane_status": certification.get("status"),
        "source_products": certification.get("products"),
        "source_listing_rows": source_listing_rows,
        "products": len(rows),
        "products_with_market_value": sum(bool(row["market_value_median"] != "") for row in rows),
        "products_without_market_value": sum(bool(row["market_value_median"] == "") for row in rows),
        "accepted_rows_input": sum(len(rows_) for rows_ in accepted_by_product.values()),
        "accepted_rows_deduped": sum(int(row["accepted_listing_count_deduped"]) for row in rows),
        "outlier_rows_removed": sum(int(row["outlier_listing_count"]) for row in rows),
        "observation_rows_retained": sum(int(row["observation_count"]) for row in rows),
        "sample_states": dict(sorted(state_counts.items())),
        "confidence_states": dict(sorted(confidence_counts.items())),
        "quota_calls": 0,
        "checks": {
            "source_lane_certified": certification.get("status") == "CERTIFIED",
            "products_equal_973": len(rows) == 973,
            "unique_products_equal_973": len({row["canonical_product_id"] for row in rows}) == 973,
            "accepted_input_matches_lane": sum(len(rows_) for rows_ in accepted_by_product.values()) == int(certification.get("accepted_rows", -1)),
            "states_sum_to_products": sum(state_counts.values()) == len(rows),
            "confidence_sum_to_products": sum(confidence_counts.values()) == len(rows),
            "quota_calls_zero": True,
        },
        "outputs": {"csv": str(csv_path.resolve()), "summary": str(json_path.resolve())},
    }
    summary["status"] = "CERTIFIED" if all(summary["checks"].values()) else "FAILED"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("SECRET LAIR MARKET OBSERVATION AGGREGATION: COMPLETE")
    print(json.dumps(summary, indent=2))
    if summary["status"] != "CERTIFIED":
        raise SystemExit(1)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--certification", type=Path, default=DEFAULT_CERTIFICATION)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    run(args.certification, args.output_root)


if __name__ == "__main__":
    main()
'''

TEST_CONTENT = r'''from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("aggregation", ROOT / "scripts/aggregate_secret_lair_market_observations.py")
assert SPEC and SPEC.loader
AGG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AGG)


def test_percentile_interpolates():
    assert AGG.percentile([10, 20, 30, 40], 0.25) == 17.5


def test_outlier_bounds_reject_high_extreme():
    low, high = AGG.outlier_bounds([10, 11, 12, 13, 100])
    assert low <= 10
    assert high < 100


def test_dedupe_keeps_highest_match_score():
    rows = [
        {"canonical_product_id": "A", "ebay_item_id": "1", "match_score": "0.8"},
        {"canonical_product_id": "A", "ebay_item_id": "1", "match_score": "0.9"},
    ]
    result = AGG.dedupe_rows(rows)
    assert len(result) == 1
    assert result[0]["match_score"] == "0.9"


def test_sample_state_thresholds():
    assert AGG.sample_state(0, 0) == "NO_ACCEPTED_EVIDENCE"
    assert AGG.sample_state(1, 1) == "SINGLE_OBSERVATION"
    assert AGG.sample_state(4, 2) == "LIMITED_EVIDENCE"
    assert AGG.sample_state(7, 3) == "MODERATE_EVIDENCE"
    assert AGG.sample_state(10, 4) == "STRONG_EVIDENCE"


def test_aggregate_product_retains_zero_evidence_product():
    product = {"canonical_product_id": "A", "canonical_product_name": "Example"}
    row = AGG.aggregate_product(product, [], "2026-07-24T00:00:00+00:00")
    assert row["canonical_product_id"] == "A"
    assert row["market_value_median"] == ""
    assert row["sample_state"] == "NO_ACCEPTED_EVIDENCE"
    assert row["confidence_score"] == 0.0
'''


def apply() -> None:
    if TARGET.exists() or TESTS.exists():
        raise RuntimeError("Market observation aggregation source already exists; refusing to overwrite")
    TARGET.write_text(TARGET_CONTENT, encoding="utf-8")
    TESTS.write_text(TEST_CONTENT, encoding="utf-8")
    print("SECRET LAIR MARKET OBSERVATION AGGREGATION: APPLIED")
    print(f"Created: {TARGET.relative_to(ROOT)}")
    print(f"Created: {TESTS.relative_to(ROOT)}")


if __name__ == "__main__":
    apply()
