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
    if summary.get("upgrade_transition_count") != 0:
        errors.append("upgrade_transition_count must equal 0")
    if summary.get("v2_to_v3_upgrade_transition_count") != 0:
        errors.append("v2_to_v3_upgrade_transition_count must equal 0")

    row_count = summary.get("listing_row_count")
    if not isinstance(row_count, int) or row_count < 1:
        errors.append("listing_row_count must be a positive integer")

    product_count = summary.get("unique_product_count")
    if not isinstance(product_count, int) or product_count < 1:
        errors.append("unique_product_count must be a positive integer")

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
    parser = argparse.ArgumentParser(
        description="Fail-closed validation for the precision-v3 full-universe migration"
    )
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
