from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_MODE = "FULL_UNIVERSE_PRODUCTION_MIGRATION"
REQUIRED_BASELINE = "precision-v2"
REQUIRED_MIGRATION = "precision-v3-universal"
REQUIRED_POLICY = "downgrade_only"


def validate_summary(summary: dict[str, object]) -> list[str]:
    errors: list[str] = []

    if summary.get("status") != "PASS":
        errors.append("status must be PASS")
    if summary.get("mode") != REQUIRED_MODE:
        errors.append(f"mode must be {REQUIRED_MODE}")
    if summary.get("quota_calls") != 0:
        errors.append("quota_calls must equal 0")
    if summary.get("baseline_matcher_version") != REQUIRED_BASELINE:
        errors.append(f"baseline_matcher_version must be {REQUIRED_BASELINE}")
    if summary.get("migration_matcher_version") != REQUIRED_MIGRATION:
        errors.append(f"migration_matcher_version must be {REQUIRED_MIGRATION}")
    if summary.get("migration_policy_mode") != REQUIRED_POLICY:
        errors.append(f"migration_policy_mode must be {REQUIRED_POLICY}")
    if summary.get("evidence_canonicalization") is not True:
        errors.append("evidence_canonicalization must be true")
    if summary.get("deduplication_key") != ["canonical_product_id", "ebay_item_id"]:
        errors.append("deduplication_key must be canonical_product_id plus ebay_item_id")
    if summary.get("upgrade_transition_count") != 0:
        errors.append("upgrade_transition_count must equal 0")
    if summary.get("v2_to_v3_upgrade_transition_count") != 0:
        errors.append("v2_to_v3_upgrade_transition_count must equal 0")

    raw_count = summary.get("raw_listing_row_count")
    canonical_count = summary.get("canonical_listing_row_count")
    duplicate_count = summary.get("duplicate_listing_row_count")
    listing_count = summary.get("listing_row_count")
    if not isinstance(raw_count, int) or raw_count < 1:
        errors.append("raw_listing_row_count must be a positive integer")
    if not isinstance(canonical_count, int) or canonical_count < 1:
        errors.append("canonical_listing_row_count must be a positive integer")
    if not isinstance(duplicate_count, int) or duplicate_count < 0:
        errors.append("duplicate_listing_row_count must be a nonnegative integer")
    if canonical_count != listing_count:
        errors.append("listing_row_count must equal canonical_listing_row_count")
    if isinstance(raw_count, int) and isinstance(canonical_count, int) and isinstance(duplicate_count, int):
        if raw_count != canonical_count + duplicate_count:
            errors.append("raw rows must equal canonical rows plus duplicate rows")

    product_count = summary.get("unique_product_count")
    if not isinstance(product_count, int) or product_count < 1:
        errors.append("unique_product_count must be a positive integer")

    for field in (
        "discovered_source_file_count",
        "included_source_file_count",
        "excluded_source_file_count",
        "missing_ebay_item_id_row_count",
    ):
        value = summary.get(field)
        if not isinstance(value, int) or value < 0:
            errors.append(f"{field} must be a nonnegative integer")

    discovered = summary.get("discovered_source_file_count")
    included = summary.get("included_source_file_count")
    excluded = summary.get("excluded_source_file_count")
    if isinstance(discovered, int) and isinstance(included, int) and isinstance(excluded, int):
        if discovered != included + excluded:
            errors.append("discovered files must equal included files plus excluded files")

    for field in (
        "state_counts_saved",
        "state_counts_precision_v2",
        "state_counts_precision_v3",
        "state_counts_migrated",
        "saved_to_v2_transitions",
        "v2_to_v3_transitions",
        "saved_to_migrated_transitions",
    ):
        if not isinstance(summary.get(field), dict):
            errors.append(f"{field} must be an object")

    output_root = summary.get("output_root")
    if not isinstance(output_root, str) or not output_root.strip():
        errors.append("output_root must be populated")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed validation for the canonical precision-v3 full-universe migration")
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--result-output", type=Path)
    args = parser.parse_args(argv)

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    errors = validate_summary(summary)
    result = {
        "status": "PASS" if not errors else "FAIL",
        "mode": "FULL_UNIVERSE_MIGRATION_CERTIFICATION",
        "summary": str(args.summary.resolve()),
        "baseline_matcher_version": REQUIRED_BASELINE,
        "migration_matcher_version": REQUIRED_MIGRATION,
        "migration_policy_mode": REQUIRED_POLICY,
        "evidence_canonicalization": True,
        "errors": errors,
    }

    rendered = json.dumps(result, indent=2)
    if args.result_output:
        args.result_output.parent.mkdir(parents=True, exist_ok=True)
        args.result_output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
