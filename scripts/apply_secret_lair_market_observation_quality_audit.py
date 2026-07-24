from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDITOR = ROOT / "scripts/audit_secret_lair_market_observations.py"
TESTS = ROOT / "tests/test_secret_lair_market_observation_quality_audit.py"

AUDITOR_CONTENT = r'''from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OBSERVATIONS = ROOT / "data/validation/phase_10/ebay_matching/market_observations/secret_lair_market_observations.csv"
DEFAULT_SUMMARY = ROOT / "data/validation/phase_10/ebay_matching/market_observations/secret_lair_market_observation_summary.json"
DEFAULT_OUTPUT_ROOT = ROOT / "data/validation/phase_10/ebay_matching/market_observation_quality_audit"

REVIEW_FLAGS = {
    "SINGLE_OBSERVATION",
    "VERY_LOW_CONFIDENCE",
    "LOW_CONFIDENCE",
    "WEAK_SELLER_DIVERSITY",
    "HIGH_DISPERSION",
    "HIGH_MEDIAN_VALUE",
    "EXTREME_MEDIAN_VALUE",
    "WIDE_PRICE_RANGE",
    "OUTLIER_HEAVY",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def number(row: dict[str, str], key: str) -> float:
    value = (row.get(key) or "").strip()
    if not value:
        return 0.0
    return float(value)


def integer(row: dict[str, str], key: str) -> int:
    value = (row.get(key) or "").strip()
    if not value:
        return 0
    return int(float(value))


def classify_row(row: dict[str, str]) -> tuple[list[str], str, str]:
    observations = integer(row, "observation_count")
    sellers = integer(row, "seller_count")
    median_value = number(row, "market_value_median")
    low_value = number(row, "market_value_low")
    high_value = number(row, "market_value_high")
    dispersion = number(row, "price_dispersion_cv")
    confidence_state = (row.get("confidence_state") or "").strip()
    sample_state = (row.get("sample_state") or "").strip()
    outliers = integer(row, "outlier_count")
    accepted_before_outliers = integer(row, "accepted_observation_count") or observations + outliers

    flags: list[str] = []

    if observations == 0:
        return ["NO_ACCEPTED_EVIDENCE"], "EXCLUDE_FROM_MODEL", "No accepted market evidence is available."

    if sample_state == "SINGLE_OBSERVATION" or observations == 1:
        flags.append("SINGLE_OBSERVATION")
    if confidence_state == "VERY_LOW":
        flags.append("VERY_LOW_CONFIDENCE")
    elif confidence_state == "LOW":
        flags.append("LOW_CONFIDENCE")
    if sellers <= 1:
        flags.append("WEAK_SELLER_DIVERSITY")
    if dispersion >= 0.50:
        flags.append("HIGH_DISPERSION")
    if median_value >= 250:
        flags.append("HIGH_MEDIAN_VALUE")
    if median_value >= 750:
        flags.append("EXTREME_MEDIAN_VALUE")
    if low_value > 0 and high_value / low_value >= 3.0:
        flags.append("WIDE_PRICE_RANGE")
    if accepted_before_outliers > 0 and outliers / accepted_before_outliers >= 0.40:
        flags.append("OUTLIER_HEAVY")

    severe = {
        "VERY_LOW_CONFIDENCE",
        "EXTREME_MEDIAN_VALUE",
    }
    if severe.intersection(flags):
        decision = "EXCLUDE_FROM_MODEL"
        rationale = "One or more severe quality-risk conditions require exclusion pending manual resolution."
    elif flags:
        decision = "REVIEW_REQUIRED"
        rationale = "One or more market-observation quality conditions require governed review."
    else:
        decision = "PASS"
        rationale = "Observation evidence passed all automated quality thresholds."

    return sorted(set(flags)), decision, rationale


def audit(observations_path: Path, summary_path: Path, output_root: Path) -> dict[str, Any]:
    source_summary = read_json(summary_path)
    observations = read_csv(observations_path)

    rows: list[dict[str, Any]] = []
    decision_counts: Counter[str] = Counter()
    flag_counts: Counter[str] = Counter()

    for source in observations:
        flags, decision, rationale = classify_row(source)
        decision_counts[decision] += 1
        flag_counts.update(flags)
        rows.append({
            "canonical_product_id": source.get("canonical_product_id", ""),
            "canonical_product_name": source.get("canonical_product_name", ""),
            "observation_count": source.get("observation_count", ""),
            "seller_count": source.get("seller_count", ""),
            "market_value_median": source.get("market_value_median", ""),
            "market_value_low": source.get("market_value_low", ""),
            "market_value_high": source.get("market_value_high", ""),
            "price_dispersion_cv": source.get("price_dispersion_cv", ""),
            "outlier_count": source.get("outlier_count", ""),
            "sample_state": source.get("sample_state", ""),
            "confidence_score": source.get("confidence_score", ""),
            "confidence_state": source.get("confidence_state", ""),
            "quality_flags": "|".join(flags),
            "quality_decision": decision,
            "quality_rationale": rationale,
            "model_eligible": "true" if decision == "PASS" else "false",
        })

    checks = {
        "source_summary_certified": source_summary.get("status") == "CERTIFIED",
        "source_products_equal_973": int(source_summary.get("products", -1)) == 973,
        "audit_rows_equal_973": len(rows) == 973,
        "unique_products_equal_973": len({row["canonical_product_id"] for row in rows}) == 973,
        "decision_counts_sum_to_rows": sum(decision_counts.values()) == len(rows),
        "no_blank_decisions": all(row["quality_decision"] for row in rows),
        "no_api_calls": True,
    }

    output_root.mkdir(parents=True, exist_ok=True)
    audit_path = output_root / "secret_lair_market_observation_quality_audit.csv"
    review_path = output_root / "secret_lair_market_observation_review_queue.csv"
    summary_output = output_root / "secret_lair_market_observation_quality_audit_summary.json"

    fieldnames = list(rows[0]) if rows else []
    with audit_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    review_rows = [row for row in rows if row["quality_decision"] != "PASS"]
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(review_rows)

    payload = {
        "status": "CERTIFIED" if all(checks.values()) else "FAILED",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_observations": str(observations_path.resolve()),
        "source_summary": str(summary_path.resolve()),
        "products": len(rows),
        "decision_counts": dict(sorted(decision_counts.items())),
        "flag_counts": dict(sorted(flag_counts.items())),
        "model_eligible_products": decision_counts["PASS"],
        "review_queue_products": len(review_rows),
        "quota_calls": 0,
        "checks": checks,
        "outputs": {
            "audit_csv": str(audit_path.resolve()),
            "review_queue_csv": str(review_path.resolve()),
            "summary_json": str(summary_output.resolve()),
        },
    }
    summary_output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observations", type=Path, default=DEFAULT_OBSERVATIONS)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()

    payload = audit(args.observations, args.summary, args.output_root)
    print("SECRET LAIR MARKET OBSERVATION QUALITY AUDIT: COMPLETE")
    print(json.dumps(payload, indent=2))
    if payload["status"] != "CERTIFIED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
'''

TEST_CONTENT = r'''from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "audit_secret_lair_market_observations",
    ROOT / "scripts/audit_secret_lair_market_observations.py",
)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def row(**overrides):
    base = {
        "observation_count": "5",
        "seller_count": "5",
        "market_value_median": "60",
        "market_value_low": "50",
        "market_value_high": "70",
        "price_dispersion_cv": "0.15",
        "outlier_count": "0",
        "accepted_observation_count": "5",
        "sample_state": "MODERATE_EVIDENCE",
        "confidence_state": "MEDIUM",
    }
    base.update(overrides)
    return base


def test_pass_decision():
    flags, decision, _ = AUDIT.classify_row(row())
    assert flags == []
    assert decision == "PASS"


def test_no_evidence_excluded():
    flags, decision, _ = AUDIT.classify_row(row(observation_count="0", seller_count="0", market_value_median=""))
    assert flags == ["NO_ACCEPTED_EVIDENCE"]
    assert decision == "EXCLUDE_FROM_MODEL"


def test_single_observation_reviewed():
    flags, decision, _ = AUDIT.classify_row(row(observation_count="1", seller_count="1", sample_state="SINGLE_OBSERVATION"))
    assert "SINGLE_OBSERVATION" in flags
    assert "WEAK_SELLER_DIVERSITY" in flags
    assert decision == "REVIEW_REQUIRED"


def test_very_low_confidence_excluded():
    flags, decision, _ = AUDIT.classify_row(row(confidence_state="VERY_LOW"))
    assert "VERY_LOW_CONFIDENCE" in flags
    assert decision == "EXCLUDE_FROM_MODEL"


def test_high_dispersion_and_value_reviewed():
    flags, decision, _ = AUDIT.classify_row(row(
        market_value_median="500",
        market_value_low="100",
        market_value_high="500",
        price_dispersion_cv="0.70",
    ))
    assert {"HIGH_DISPERSION", "HIGH_MEDIAN_VALUE", "WIDE_PRICE_RANGE"}.issubset(flags)
    assert decision == "REVIEW_REQUIRED"


def test_outlier_heavy_reviewed():
    flags, decision, _ = AUDIT.classify_row(row(outlier_count="4", accepted_observation_count="8"))
    assert "OUTLIER_HEAVY" in flags
    assert decision == "REVIEW_REQUIRED"
'''


def apply() -> None:
    if AUDITOR.exists() or TESTS.exists():
        raise RuntimeError("Quality-audit source already exists; refusing to overwrite")
    AUDITOR.write_text(AUDITOR_CONTENT, encoding="utf-8")
    TESTS.write_text(TEST_CONTENT, encoding="utf-8")
    print("SECRET LAIR MARKET OBSERVATION QUALITY AUDIT: APPLIED")
    print(f"Created: {AUDITOR.relative_to(ROOT)}")
    print(f"Created: {TESTS.relative_to(ROOT)}")


if __name__ == "__main__":
    apply()
