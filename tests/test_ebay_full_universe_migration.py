from __future__ import annotations

from scripts.validate_ebay_full_universe_migration import validate_summary


def valid_summary() -> dict[str, object]:
    return {
        "status": "PASS",
        "mode": "FULL_UNIVERSE_PRODUCTION_MIGRATION",
        "quota_calls": 0,
        "baseline_matcher_version": "precision-v2",
        "migration_matcher_version": "precision-v3-universal",
        "migration_policy_mode": "downgrade_only",
        "listing_row_count": 1330,
        "unique_product_count": 147,
        "upgrade_transition_count": 0,
        "v2_to_v3_upgrade_transition_count": 0,
        "state_counts_saved": {"ACCEPTED": 700, "REVIEW": 100, "REJECTED": 530},
        "state_counts_precision_v2": {"ACCEPTED": 690, "REVIEW": 105, "REJECTED": 535},
        "state_counts_precision_v3": {"ACCEPTED": 650, "REVIEW": 120, "REJECTED": 560},
        "state_counts_migrated": {"ACCEPTED": 640, "REVIEW": 120, "REJECTED": 570},
        "saved_to_v2_transitions": {"ACCEPTED->ACCEPTED": 600},
        "v2_to_v3_transitions": {"ACCEPTED->REVIEW": 40},
        "saved_to_migrated_transitions": {"ACCEPTED->REJECTED": 20},
        "output_root": "C:/tmp/migration",
    }


def test_validator_accepts_certified_full_universe_migration() -> None:
    assert validate_summary(valid_summary()) == []


def test_validator_fails_closed_on_unsafe_migration() -> None:
    summary = valid_summary()
    summary.update(
        {
            "status": "FAIL",
            "quota_calls": 1,
            "migration_matcher_version": "legacy",
            "migration_policy_mode": "upgrade_allowed",
            "upgrade_transition_count": 2,
            "v2_to_v3_upgrade_transition_count": 1,
            "listing_row_count": 0,
            "state_counts_precision_v3": [],
            "output_root": "",
        }
    )

    errors = validate_summary(summary)

    assert "status must be PASS" in errors
    assert "quota_calls must equal 0" in errors
    assert "migration_matcher_version must be precision-v3-universal" in errors
    assert "migration_policy_mode must be downgrade_only" in errors
    assert "upgrade_transition_count must equal 0" in errors
    assert "v2_to_v3_upgrade_transition_count must equal 0" in errors
    assert "listing_row_count must be a positive integer" in errors
    assert "state_counts_precision_v3 must be an object" in errors
    assert "output_root must be populated" in errors
