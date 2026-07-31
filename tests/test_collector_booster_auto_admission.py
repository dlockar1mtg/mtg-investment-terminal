from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.run_collector_booster_auto_admission import run


FIELDNAMES = [
    "investment_product_id",
    "set_name",
    "box_name",
    "approved_tcgplayer_product_id",
    "approved_product_name",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "investment_product_type",
    "approval_status",
    "approval_method",
    "notes",
]


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def write_config(path: Path) -> None:
    payload = {
        "policy_name": "collector_booster_auto_admission",
        "policy_version": "1.0.0",
        "allowed_product_types": [
            "Collector Booster Display"
        ],
        "required_approval_statuses": ["approved"],
        "allowed_discovery_methods": [
            "auto_high_confidence_v9",
            "governed_auto_admission_v1",
        ],
        "minimum_candidate_score": 200.0,
        "minimum_market_price": 1.0,
        "required_fields": FIELDNAMES[:-1],
        "identity_conflict_terms": [
            "case",
            "single pack",
            "booster pack",
            "bundle",
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def registry_row() -> dict[str, str]:
    return {
        "investment_product_id": "TCGCSV-100-1000",
        "set_name": "Existing Set",
        "box_name": "Existing Set Collector Booster Display",
        "approved_tcgplayer_product_id": "1000",
        "approved_product_name": (
            "Existing Set - Collector Booster Display"
        ),
        "tcgcsv_category_id": "1",
        "tcgcsv_group_id": "100",
        "investment_product_type": (
            "Collector Booster Display"
        ),
        "approval_status": "approved",
        "approval_method": "governed_auto_admission_v1",
        "notes": (
            "candidate_score=240.0; market_price=300.00"
        ),
    }


def valid_candidate() -> dict[str, str]:
    return {
        "investment_product_id": "TCGCSV-24766-706142",
        "set_name": "Star Trek",
        "box_name": "Star Trek Collector Booster Display",
        "approved_tcgplayer_product_id": "706142",
        "approved_product_name": (
            "Star Trek - Collector Booster Display"
        ),
        "tcgcsv_category_id": "1",
        "tcgcsv_group_id": "24766",
        "investment_product_type": (
            "Collector Booster Display"
        ),
        "approval_status": "approved",
        "approval_method": "auto_high_confidence_v9",
        "notes": (
            "candidate_score=240.0; market_price=701.58"
        ),
    }


def test_valid_product_is_proposed_without_mutation(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.csv"
    candidates = tmp_path / "candidates.csv"
    config = tmp_path / "config.json"
    output = tmp_path / "output"

    write_csv(registry, [registry_row()])
    write_csv(candidates, [valid_candidate()])
    write_config(config)

    before = registry.read_bytes()

    manifest = run(
        candidate_path=candidates,
        registry_path=registry,
        config_path=config,
        output_root=output,
        apply=False,
    )

    assert manifest["auto_admitted_count"] == 1
    assert manifest["manual_review_count"] == 0
    assert manifest["production_registry_changed"] is False
    assert registry.read_bytes() == before


def test_apply_creates_backup_and_updates_registry(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.csv"
    candidates = tmp_path / "candidates.csv"
    config = tmp_path / "config.json"
    output = tmp_path / "output"

    write_csv(registry, [registry_row()])
    write_csv(candidates, [valid_candidate()])
    write_config(config)

    manifest = run(
        candidate_path=candidates,
        registry_path=registry,
        config_path=config,
        output_root=output,
        apply=True,
    )

    with registry.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle))

    assert manifest["production_registry_changed"] is True
    assert manifest["registry_rows_after"] == 2
    assert len(rows) == 2
    assert Path(manifest["backup_path"]).exists()


def test_pack_identity_fails_closed(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.csv"
    candidates = tmp_path / "candidates.csv"
    config = tmp_path / "config.json"
    output = tmp_path / "output"

    candidate = valid_candidate()
    candidate["box_name"] = (
        "Star Trek Collector Booster Pack"
    )
    candidate["approved_product_name"] = (
        "Star Trek - Collector Booster Pack"
    )

    write_csv(registry, [registry_row()])
    write_csv(candidates, [candidate])
    write_config(config)

    manifest = run(
        candidate_path=candidates,
        registry_path=registry,
        config_path=config,
        output_root=output,
        apply=False,
    )

    assert manifest["auto_admitted_count"] == 0
    assert manifest["manual_review_count"] == 1


def test_duplicate_product_fails_closed(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.csv"
    candidates = tmp_path / "candidates.csv"
    config = tmp_path / "config.json"
    output = tmp_path / "output"

    duplicate = registry_row()

    write_csv(registry, [registry_row()])
    write_csv(candidates, [duplicate])
    write_config(config)

    manifest = run(
        candidate_path=candidates,
        registry_path=registry,
        config_path=config,
        output_root=output,
        apply=False,
    )

    assert manifest["auto_admitted_count"] == 0
    assert manifest["manual_review_count"] == 1