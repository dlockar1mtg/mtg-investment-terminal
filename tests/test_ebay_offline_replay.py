from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.replay_ebay_matching_offline import replay_row, run


def _write_listing_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "canonical_product_id": "SL-1",
            "canonical_product_name": "Astrology Lands (Sagittarius) Bundle — Traditional Foil Edition",
            "canonical_set_name": "Astrology Lands",
            "product_class": "SEALED_SECRET_LAIR",
            "tcgplayer_product_id": "1",
            "release_date": "",
            "ebay_query": "",
            "ebay_item_id": "A",
            "title": "MTG Secret Lair Astrology Lands Sagittarius Bundle Traditional Foil Sealed",
            "item_url": "",
            "price": "100",
            "currency": "USD",
            "condition": "New",
            "match_score": "0.90",
            "match_state": "ACCEPTED",
            "exclusion_reasons": "",
            "source_run_id": "TEST",
            "observed_at_utc": "2026-07-26T00:00:00+00:00",
        },
        {
            "canonical_product_id": "SL-1",
            "canonical_product_name": "Astrology Lands (Sagittarius) Bundle — Traditional Foil Edition",
            "canonical_set_name": "Astrology Lands",
            "product_class": "SEALED_SECRET_LAIR",
            "tcgplayer_product_id": "1",
            "release_date": "",
            "ebay_query": "",
            "ebay_item_id": "B",
            "title": "Secret Lair Astrology Lands Sagittarius single drop nonfoil sealed",
            "item_url": "",
            "price": "30",
            "currency": "USD",
            "condition": "New",
            "match_score": "0.85",
            "match_state": "ACCEPTED",
            "exclusion_reasons": "",
            "source_run_id": "TEST",
            "observed_at_utc": "2026-07-26T00:00:00+00:00",
        },
        {
            "canonical_product_id": "FF-JP",
            "canonical_product_name": "FINAL FANTASY - Collector Booster Display (Japanese)",
            "canonical_set_name": "FINAL FANTASY",
            "product_class": "COLLECTOR_BOOSTER_BOX",
            "tcgplayer_product_id": "2",
            "release_date": "",
            "ebay_query": "",
            "ebay_item_id": "C",
            "title": "MTG Final Fantasy Collector Booster Box English Factory Sealed",
            "item_url": "",
            "price": "500",
            "currency": "USD",
            "condition": "New/Factory Sealed",
            "match_score": "0.82",
            "match_state": "REVIEW",
            "exclusion_reasons": "",
            "source_run_id": "TEST",
            "observed_at_utc": "2026-07-26T00:00:00+00:00",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_full_universe_replay_emits_migration_package_without_quota(tmp_path: Path) -> None:
    input_root = tmp_path / "evidence"
    _write_listing_file(input_root / "batch_0001" / "ebay_listing_match_results_2026-07-26.csv")
    output_root = tmp_path / "output"

    summary = run(input_root, output_root)

    assert summary["status"] == "PASS"
    assert summary["mode"] == "FULL_UNIVERSE_PRODUCTION_MIGRATION"
    assert summary["quota_calls"] == 0
    assert summary["baseline_matcher_version"] == "precision-v2"
    assert summary["migration_matcher_version"] == "precision-v3-universal"
    assert summary["migration_policy_mode"] == "downgrade_only"
    assert summary["listing_row_count"] == 3
    assert summary["unique_product_count"] == 2
    assert summary["classification_changed_row_count"] >= 1
    assert summary["evidence_changed_row_count"] >= summary["classification_changed_row_count"]
    assert summary["upgrade_transition_count"] == 0
    assert summary["v2_to_v3_upgrade_transition_count"] == 0
    assert summary["state_counts_migrated"]["REJECTED"] >= 1

    replay_root = Path(str(summary["output_root"]))
    payload = json.loads(
        (replay_root / "ebay_full_universe_migration_summary.json").read_text(encoding="utf-8")
    )
    assert payload["quota_calls"] == 0
    assert payload["upgrade_transition_count"] == 0
    assert payload["v2_to_v3_upgrade_transition_count"] == 0
    assert (replay_root / "ebay_full_universe_migration.csv").is_file()
    assert (replay_root / "ebay_v2_v3_changed_listings.csv").is_file()
    assert (replay_root / "ebay_migrated_classification_changes.csv").is_file()
    assert (replay_root / "ebay_migration_evidence_changes.csv").is_file()
    assert (replay_root / "ebay_migration_product_summary.csv").is_file()
    assert (replay_root / "ebay_precision_v3_reason_summary.csv").is_file()


def test_replay_never_upgrades_saved_state_and_records_both_matchers() -> None:
    row = {
        "canonical_product_id": "SL-2",
        "canonical_product_name": "Secret Lair Example Drop",
        "canonical_set_name": "",
        "product_class": "SEALED_SECRET_LAIR",
        "tcgplayer_product_id": "2",
        "release_date": "",
        "ebay_query": "",
        "ebay_item_id": "C",
        "title": "MTG Secret Lair Example Drop Sealed",
        "item_url": "",
        "price": "40",
        "currency": "USD",
        "condition": "New",
        "match_score": "0.70",
        "match_state": "REVIEW",
        "exclusion_reasons": "",
        "source_run_id": "TEST",
        "observed_at_utc": "2026-07-26T00:00:00+00:00",
    }

    replayed = replay_row(row)

    assert replayed["match_state"] == "REVIEW"
    assert replayed["saved_match_state"] == "REVIEW"
    assert replayed["precision_v2_match_state"] in {"ACCEPTED", "REVIEW", "REJECTED"}
    assert replayed["precision_v3_match_state"] in {"ACCEPTED", "REVIEW", "REJECTED"}
    assert replayed["migration_matcher_version"] == "precision-v3-universal"
    assert replayed["migration_policy_mode"] == "downgrade_only"
    assert "offline_upgrade_blocked" in str(replayed["exclusion_reasons"])
    assert replayed["classification_changed"] == "false"
