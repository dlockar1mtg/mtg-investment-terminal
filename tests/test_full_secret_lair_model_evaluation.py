from __future__ import annotations

import csv
from pathlib import Path

from scripts.build_full_secret_lair_model_evaluation import build
from terminal2.market_sources.full_secret_lair_evaluation import FullSecretLairEvaluationStore


def write_ledger(path: Path) -> None:
    fields = [
        "canonical_product_id", "canonical_product_name", "quality_decision", "admission_decision",
        "suppression_reason", "market_value_usd", "observation_count", "seller_count", "confidence_score",
        "confidence_state", "sample_state", "price_dispersion_cv", "market_value_low", "market_value_high",
        "quality_flags", "source", "valuation_method", "currency",
    ]
    rows = []
    counts = [("PASS", 214), ("REVIEW_REQUIRED", 380), ("EXCLUDE_FROM_MODEL", 379)]
    index = 0
    for decision, count in counts:
        for _ in range(count):
            rows.append({
                "canonical_product_id": f"SL-{index:014X}",
                "canonical_product_name": f"Product {index} - {'Non-Foil' if index % 2 else 'Traditional Foil'} Edition",
                "quality_decision": decision,
                "admission_decision": "ADMITTED" if decision == "PASS" else "SUPPRESSED",
                "suppression_reason": "" if decision == "PASS" else decision,
                "market_value_usd": str(40 + index % 50) if decision == "PASS" else "",
                "observation_count": "4" if decision == "PASS" else ("1" if decision == "REVIEW_REQUIRED" else "0"),
                "seller_count": "4" if decision == "PASS" else ("1" if decision == "REVIEW_REQUIRED" else "0"),
                "confidence_score": "70" if decision == "PASS" else ("40" if decision == "REVIEW_REQUIRED" else "0"),
                "confidence_state": "MEDIUM" if decision != "EXCLUDE_FROM_MODEL" else "NO_EVIDENCE",
                "sample_state": "LIMITED_EVIDENCE" if decision == "PASS" else "NO_ACCEPTED_EVIDENCE",
                "price_dispersion_cv": "0.1" if decision == "PASS" else "",
                "market_value_low": str(35 + index % 50) if decision == "REVIEW_REQUIRED" else "",
                "market_value_high": str(45 + index % 50) if decision == "REVIEW_REQUIRED" else "",
                "quality_flags": "" if decision == "PASS" else decision,
                "source": "TEST",
                "valuation_method": "TEST",
                "currency": "USD",
            })
            index += 1
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def test_builds_all_973_products(tmp_path: Path):
    ledger = tmp_path / "ledger.csv"; write_ledger(ledger)
    result = build(ledger, tmp_path / "out")
    assert result["status"] == "CERTIFIED"
    assert result["products"] == 973


def test_tier_counts_reconcile(tmp_path: Path):
    ledger = tmp_path / "ledger.csv"; write_ledger(ledger)
    result = build(ledger, tmp_path / "out")
    assert result["full_model_products"] == 214
    assert result["provisional_model_products"] == 380
    assert result["structural_only_products"] == 379


def test_every_product_has_value_forecast_and_recommendation(tmp_path: Path):
    ledger = tmp_path / "ledger.csv"; write_ledger(ledger)
    result = build(ledger, tmp_path / "out")
    path = Path(result["outputs"]["full_evaluation"])
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert len(rows) == 973
    assert all(float(row["evaluated_market_value_usd"]) > 0 for row in rows)
    assert all(float(row["forecast_low_usd"]) > 0 for row in rows)
    assert all(row["guarded_recommendation"] for row in rows)


def test_only_full_model_can_receive_buy_review(tmp_path: Path):
    ledger = tmp_path / "ledger.csv"; write_ledger(ledger)
    result = build(ledger, tmp_path / "out")
    rows = list(csv.DictReader(Path(result["outputs"]["recommendation_inputs"]).open(encoding="utf-8")))
    assert all(row["evaluation_tier"] == "FULL_MODEL" for row in rows if row["guarded_recommendation"] == "REVIEW_FOR_BUY")


def test_store_loads_and_groups_all_products(tmp_path: Path):
    ledger = tmp_path / "ledger.csv"; write_ledger(ledger)
    result = build(ledger, tmp_path / "out")
    store = FullSecretLairEvaluationStore(result["outputs"]["full_evaluation"])
    assert len(store.load()) == 973
    assert len(store.by_product_id()) == 973
    assert len(store.by_tier("FULL_MODEL")) == 214


def test_no_api_quota_calls(tmp_path: Path):
    ledger = tmp_path / "ledger.csv"; write_ledger(ledger)
    result = build(ledger, tmp_path / "out")
    assert result["quota_calls"] == 0
