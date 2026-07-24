from __future__ import annotations

import csv
from pathlib import Path

from terminal2.market_sources.collector_box_admission import build_admission_ledger


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _rows() -> list[dict[str, object]]:
    rows = []
    tiers = (["FULL_MODEL"] * 36 + ["PROVISIONAL_MODEL"] * 11 + ["STRUCTURAL_ONLY"] * 2)
    for index, tier in enumerate(tiers):
        if tier == "FULL_MODEL":
            basis, confidence, retained, value = "OBSERVED_GOVERNED", "HIGH", 5, "100.00"
        elif index < 45:
            basis, confidence, retained, value = "OBSERVED_LIMITED", "MEDIUM", 2, "90.00"
        elif tier == "PROVISIONAL_MODEL":
            basis, confidence, retained, value = "OBSERVED_SINGLE", "LOW", 1, "80.00"
        else:
            basis, confidence, retained, value = "NO_ACCEPTED_OBSERVATION", "STRUCTURAL", 0, ""
        rows.append({
            "canonical_product_id": f"P{index:03d}",
            "canonical_product_name": f"Product {index}",
            "canonical_set_name": f"Set {index}",
            "tcgplayer_product_id": str(1000 + index),
            "raw_accepted_observations": retained,
            "retained_observations": retained,
            "removed_outliers": 0,
            "candidate_market_value_usd": value,
            "candidate_admission_tier": tier,
            "candidate_valuation_basis": basis,
            "candidate_confidence": confidence,
        })
    return rows


def test_build_certified_admission_ledger(tmp_path: Path) -> None:
    profile = tmp_path / "profile.csv"
    _write(profile, _rows())
    result = build_admission_ledger(profile, tmp_path / "out")
    assert result["status"] == "CERTIFIED"
    assert result["products"] == 49
    assert result["tier_counts"] == {
        "FULL_MODEL": 36,
        "PROVISIONAL_MODEL": 11,
        "STRUCTURAL_ONLY": 2,
    }


def test_only_full_model_is_recommendation_eligible(tmp_path: Path) -> None:
    profile = tmp_path / "profile.csv"
    output = tmp_path / "out"
    _write(profile, _rows())
    build_admission_ledger(profile, output)
    with (output / "collector_booster_box_market_value_admission_ledger.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert all(
        (row["recommendation_eligible"] == "YES")
        == (row["admission_tier"] == "FULL_MODEL")
        for row in rows
    )


def test_structural_rows_have_no_market_value(tmp_path: Path) -> None:
    profile = tmp_path / "profile.csv"
    output = tmp_path / "out"
    _write(profile, _rows())
    build_admission_ledger(profile, output)
    with (output / "collector_booster_box_market_value_admission_ledger.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    structural = [row for row in rows if row["admission_tier"] == "STRUCTURAL_ONLY"]
    assert len(structural) == 2
    assert all(row["market_value_usd"] == "" for row in structural)
