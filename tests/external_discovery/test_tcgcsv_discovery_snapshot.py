from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

STAGING_ROOT = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "external_discovery"
    / "tcgcsv"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "external_discovery"
    / "tcgcsv"
)

SNAPSHOT_MANIFEST_PATH = (
    VALIDATION_ROOT
    / "tcgcsv_snapshot_manifest_2026-07-22.json"
)

CANDIDATE_SUMMARY_PATH = (
    VALIDATION_ROOT
    / "tcgcsv_candidate_extraction_summary_2026-07-22.json"
)

CANDIDATE_PATH = (
    STAGING_ROOT
    / "tcgcsv_sealed_product_candidates_2026-07-22.csv"
)

SECRET_LAIR_EVIDENCE_PATH = (
    VALIDATION_ROOT
    / "tcgcsv_secret_lair_product_evidence_2026-07-22.csv"
)

PREMIUM_UNIVERSE_PATH = (
    STAGING_ROOT
    / "tcgcsv_premium_candidate_universe_2026-07-22.csv"
)

PREMIUM_UNIVERSE_SUMMARY_PATH = (
    VALIDATION_ROOT
    / "tcgcsv_premium_candidate_universe_summary_2026-07-22.json"
)

MISSING_REGISTRY_PATH = (
    VALIDATION_ROOT
    / "existing_registry_products_missing_from_snapshot.csv"
)

EXTRACTOR_PATH = (
    ROOT
    / "scripts"
    / "external_discovery"
    / "extract_tcgcsv_sealed_candidates.py"
)


def load_json(path: Path) -> dict:
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def load_extractor_module():
    spec = importlib.util.spec_from_file_location(
        "extract_tcgcsv_sealed_candidates",
        EXTRACTOR_PATH,
    )

    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(
        spec
    )

    spec.loader.exec_module(module)

    return module


def test_complete_tcgcsv_snapshot_manifest() -> None:
    manifest = load_json(
        SNAPSHOT_MANIFEST_PATH
    )

    assert manifest["tcgcsv_category_id"] == "1"
    assert manifest[
        "remote_group_count_before_limit"
    ] == 453
    assert manifest["groups_attempted"] == 453
    assert manifest["successful_groups"] == 453
    assert manifest["failed_groups"] == 0

    assert manifest[
        "captured_product_rows"
    ] == 116546

    assert manifest[
        "unique_product_ids"
    ] == 116546

    assert manifest[
        "unique_snapshot_record_ids"
    ] == 116546

    assert manifest[
        "duplicate_product_id_rows"
    ] == 0

    assert manifest[
        "duplicate_snapshot_id_rows"
    ] == 0

    assert manifest["limited_run"] is False
    assert manifest[
        "classification_applied"
    ] is False
    assert manifest[
        "eligibility_changed"
    ] is False
    assert manifest[
        "prices_requested"
    ] is False
    assert manifest["snapshot_status"] == (
        "COMPLETE"
    )


def test_candidate_summary_reconciles() -> None:
    summary = load_json(
        CANDIDATE_SUMMARY_PATH
    )

    expected_counts = {
        "bundle": 173,
        "collector_booster_display": 78,
        "commander_deck": 210,
        "draft_booster_display": 25,
        "jumpstart_booster_display": 11,
        "play_booster_display": 20,
        "sealed_case": 205,
        "set_booster_display": 18,
        "theme_booster_display": 14,
        "traditional_booster_display": 138,
    }

    assert summary["source_product_rows"] == (
        116546
    )
    assert summary["candidate_rows"] == 892
    assert summary[
        "unique_candidate_product_ids"
    ] == 892
    assert summary[
        "excluded_candidate_rows"
    ] == 1

    assert summary[
        "candidate_type_counts"
    ] == expected_counts

    assert sum(
        expected_counts.values()
    ) == 892


def test_candidate_extraction_changes_no_state() -> None:
    summary = load_json(
        CANDIDATE_SUMMARY_PATH
    )

    assert summary[
        "classification_status"
    ] == "CANDIDATE_EXTRACTION_ONLY"

    assert summary[
        "eligibility_changed"
    ] is False
    assert summary[
        "registry_changed"
    ] is False
    assert summary[
        "database_changed"
    ] is False


def test_secret_lair_records_are_not_sealed_candidates() -> None:
    candidates = pd.read_csv(
        CANDIDATE_PATH,
        low_memory=False,
    )

    assert len(candidates) == 892

    assert not candidates[
        "candidate_product_type"
    ].eq("secret_lair").any()


def test_secret_lair_evidence_is_preserved_separately() -> None:
    summary = load_json(
        CANDIDATE_SUMMARY_PATH
    )

    evidence = pd.read_csv(
        SECRET_LAIR_EVIDENCE_PATH,
        low_memory=False,
    )

    assert len(evidence) == 4347

    assert summary[
        "secret_lair_product_evidence_rows"
    ] == 4347

    assert summary[
        "secret_lair_sealed_drop_count"
    ] == "NOT_DETERMINED"

    assert evidence[
        "sealed_drop_status"
    ].eq("not_determined").all()

    assert evidence[
        "evidence_class"
    ].eq(
        "secret_lair_product_record"
    ).all()


def test_one_registry_record_is_absent_from_snapshot() -> None:
    missing = pd.read_csv(
        MISSING_REGISTRY_PATH,
        low_memory=False,
    )

    assert len(missing) == 1

    record = missing.iloc[0]

    assert str(
        record[
            "approved_tcgplayer_product_id"
        ]
    ) == "704940"

    assert record[
        "approved_product_name"
    ] == "Path of Ancestry (2684)"

    assert record[
        "approval_status"
    ] == "review_required"


def test_case_classification_precedes_display_classification() -> None:
    module = load_extractor_module()

    candidate_type, _ = (
        module.classify_candidate(
            "Commander Masters",
            (
                "Commander Masters - "
                "Set Booster Box Case"
            ),
        )
    )

    assert candidate_type == "sealed_case"


def test_play_and_set_booster_displays_are_supported() -> None:
    module = load_extractor_module()

    play_type, _ = (
        module.classify_candidate(
            "Aetherdrift",
            (
                "Aetherdrift - "
                "Play Booster Display"
            ),
        )
    )

    set_type, _ = (
        module.classify_candidate(
            "Commander Masters",
            (
                "Commander Masters - "
                "Set Booster Box"
            ),
        )
    )

    assert play_type == (
        "play_booster_display"
    )
    assert set_type == (
        "set_booster_display"
    )


def test_individual_secret_lair_card_is_not_candidate() -> None:
    module = load_extractor_module()

    candidate_type, candidate_status = (
        module.classify_candidate(
            "Secret Lair Countdown Kit",
            "Sol Ring (Halo Foil)",
        )
    )

    assert candidate_type == ""
    assert candidate_status == ""

def test_premium_candidate_universe_totals() -> None:
    summary = load_json(
        PREMIUM_UNIVERSE_SUMMARY_PATH
    )

    assert summary[
        "sealed_product_candidate_rows"
    ] == 892

    assert summary[
        "secret_lair_candidate_rows"
    ] == 4347

    assert summary[
        "total_candidate_rows"
    ] == 5239

    assert summary[
        "unique_candidate_record_ids"
    ] == 5239

    assert summary[
        "unique_tcgplayer_product_ids"
    ] == 5239

    assert summary[
        "duplicate_candidate_id_rows"
    ] == 0


def test_secret_lair_products_are_candidates() -> None:
    universe = pd.read_csv(
        PREMIUM_UNIVERSE_PATH,
        low_memory=False,
    )

    secret_lair = universe[
        universe[
            "candidate_class"
        ].eq("secret_lair_product")
    ]

    assert len(secret_lair) == 4347

    assert secret_lair[
        "candidate_status"
    ].eq("potential_candidate").all()

    assert secret_lair[
        "eligibility_status"
    ].eq("not_evaluated").all()

    assert secret_lair[
        "scoring_status"
    ].eq("not_scored").all()


def test_sealed_and_secret_lair_candidates_reconcile() -> None:
    universe = pd.read_csv(
        PREMIUM_UNIVERSE_PATH,
        low_memory=False,
    )

    counts = (
        universe[
            "candidate_class"
        ]
        .value_counts()
        .to_dict()
    )

    assert counts == {
        "secret_lair_product": 4347,
        "sealed_product": 892,
    }


def test_candidate_universe_creates_no_buy_decisions() -> None:
    summary = load_json(
        PREMIUM_UNIVERSE_SUMMARY_PATH
    )

    assert summary[
        "candidate_universe_status"
    ] == "POTENTIAL_CANDIDATES_ONLY"

    assert summary[
        "eligibility_evaluated"
    ] is False

    assert summary[
        "scoring_applied"
    ] is False

    assert summary[
        "buy_recommendations_created"
    ] is False

    assert summary[
        "registry_changed"
    ] is False

    assert summary[
        "database_changed"
    ] is False
