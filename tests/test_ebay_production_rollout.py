from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.build_ebay_rollout_map import build_rollout_map
from scripts.validate_ebay_rollout_summary import validate_summary


def write_source(path: Path, count: int) -> None:
    fieldnames = ["tcgplayer_product_id", "source_product_name", "mapping_status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index in range(count):
            writer.writerow(
                {
                    "tcgplayer_product_id": str(1000 + index),
                    "source_product_name": f"Product {index:02d}",
                    "mapping_status": "READY",
                }
            )


def valid_summary() -> dict[str, object]:
    return {
        "status": "PASS",
        "live_api_called": True,
        "selection_mode": "PRODUCT_MAP_TARGETED",
        "missing_tcgplayer_product_ids": [],
        "products": 25,
        "expected_products": 25,
        "aborted_early": False,
        "listing_rows": 125,
        "credentials_printed": False,
        "matcher_version": "precision-v2",
        "matcher_fail_closed": True,
        "progress_log": ["[1/25] Example: LIMITED_MATCH_COVERAGE"],
    }


def test_builder_selects_exact_unique_bounded_count(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    output = tmp_path / "rollout.csv"
    summary_output = tmp_path / "summary.json"
    write_source(source, 30)

    summary = build_rollout_map(source, output, summary_output, product_count=25)
    rows = list(csv.DictReader(output.open("r", encoding="utf-8")))

    assert summary["status"] == "PASS"
    assert summary["selected_product_count"] == 25
    assert summary["unique_product_id_count"] == 25
    assert len(rows) == 25
    assert len({row["tcgplayer_product_id"] for row in rows}) == 25
    assert json.loads(summary_output.read_text(encoding="utf-8"))["status"] == "PASS"


def test_builder_fails_when_source_is_too_small(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    write_source(source, 24)

    with pytest.raises(RuntimeError, match="25 required"):
        build_rollout_map(
            source,
            tmp_path / "rollout.csv",
            tmp_path / "summary.json",
            product_count=25,
        )


def test_validator_accepts_certified_bounded_summary() -> None:
    assert validate_summary(valid_summary(), 25, 5) == []


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("status", "FAIL", "status must be PASS"),
        ("matcher_version", "legacy", "matcher_version must be precision-v2"),
        ("matcher_fail_closed", False, "matcher_fail_closed must be true"),
        ("aborted_early", True, "aborted_early must be false"),
        ("credentials_printed", True, "credentials_printed must be false"),
        ("listing_rows", 126, "listing_rows exceeds bounded maximum 125"),
    ],
)
def test_validator_fails_closed(field: str, value: object, message: str) -> None:
    summary = valid_summary()
    summary[field] = value
    assert message in validate_summary(summary, 25, 5)


def test_validator_rejects_missing_products_and_source_errors() -> None:
    summary = valid_summary()
    summary["missing_tcgplayer_product_ids"] = ["123"]
    summary["progress_log"] = ["[4/25] Example: SOURCE_ERROR"]

    errors = validate_summary(summary, 25, 5)
    assert "missing_tcgplayer_product_ids must be empty" in errors
    assert "progress_log contains SOURCE_ERROR" in errors
