from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

DEFAULT_PRIOR_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "canonical_registry_governance"
    / "governed_canonical_mtg_registry_2026-07-22.csv"
)

DEFAULT_CURRENT_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "canonical_registry"
    / "canonical_mtg_product_registry_2026-07-22.csv"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "canonical_registry_refresh"
)

REFRESH_VERSION = "10.5R.1C.2.3"

CHANGE_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "change_type",
    "review_required",
    "prior_product_name",
    "current_product_name",
    "prior_product_class",
    "current_product_class",
    "prior_product_family",
    "current_product_family",
    "prior_product_type",
    "current_product_type",
    "prior_packaging_level",
    "current_packaging_level",
    "prior_lifecycle_status",
    "resulting_lifecycle_status",
    "prior_source_availability",
    "resulting_source_availability",
    "change_reason",
]


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).replace(
        microsecond=0
    ).isoformat().replace(
        "+00:00",
        "Z",
    )


def clean_text(value: object) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip()


def build_index(
    frame: pd.DataFrame,
    key: str,
    label: str,
) -> dict[str, pd.Series]:
    index: dict[str, pd.Series] = {}

    for _, row in frame.iterrows():
        value = clean_text(
            row.get(key)
        )

        if not value:
            raise RuntimeError(
                f"{label} contains blank {key}."
            )

        if value in index:
            raise RuntimeError(
                f"{label} contains duplicate "
                f"{key}: {value}"
            )

        index[value] = row

    return index


def classify_shared_identity(
    prior: pd.Series,
    current: pd.Series,
) -> tuple[str, bool, str]:
    changes: list[str] = []

    comparisons = [
        (
            "name_changed",
            "canonical_product_name",
        ),
        (
            "class_changed",
            "canonical_product_class",
        ),
        (
            "family_changed",
            "canonical_product_family",
        ),
        (
            "type_changed",
            "canonical_product_type",
        ),
        (
            "packaging_changed",
            "canonical_packaging_level",
        ),
        (
            "tcgplayer_id_changed",
            "tcgplayer_product_id",
        ),
    ]

    for change_name, column in comparisons:
        prior_value = clean_text(
            prior.get(column)
        )

        current_value = clean_text(
            current.get(column)
        )

        if prior_value != current_value:
            changes.append(change_name)

    if not changes:
        return (
            "unchanged",
            False,
            "",
        )

    identity_conflicts = {
        "class_changed",
        "tcgplayer_id_changed",
    }

    review_required = bool(
        identity_conflicts.intersection(
            changes
        )
    )

    if review_required:
        change_type = "identity_conflict"
    elif changes == ["name_changed"]:
        change_type = "source_name_changed"
    else:
        change_type = "classification_changed"

    return (
        change_type,
        review_required,
        "|".join(changes),
    )


def build_change_report(
    prior: pd.DataFrame,
    current: pd.DataFrame,
) -> pd.DataFrame:
    prior_index = build_index(
        prior,
        "canonical_product_id",
        "Prior governed registry",
    )

    current_index = build_index(
        current,
        "canonical_product_id",
        "Current canonical registry",
    )

    all_ids = sorted(
        set(prior_index)
        | set(current_index)
    )

    rows: list[dict[str, Any]] = []

    for canonical_id in all_ids:
        prior_row = prior_index.get(
            canonical_id
        )

        current_row = current_index.get(
            canonical_id
        )

        if prior_row is None:
            change_type = "new_identity"
            review_required = True
            change_reason = (
                "canonical_identity_not_in_prior_registry"
            )
            resulting_lifecycle = "active"
            resulting_availability = "available"

        elif current_row is None:
            change_type = "source_unavailable"
            review_required = False
            change_reason = (
                "canonical_identity_not_in_current_source"
            )
            resulting_lifecycle = (
                clean_text(
                    prior_row.get(
                        "identity_lifecycle_status"
                    )
                )
                or "active"
            )
            resulting_availability = "unavailable"

        else:
            (
                change_type,
                review_required,
                change_reason,
            ) = classify_shared_identity(
                prior_row,
                current_row,
            )

            resulting_lifecycle = (
                "identity_review_required"
                if review_required
                else (
                    clean_text(
                        prior_row.get(
                            "identity_lifecycle_status"
                        )
                    )
                    or "active"
                )
            )

            resulting_availability = "available"

        source_row = (
            current_row
            if current_row is not None
            else prior_row
        )

        rows.append(
            {
                "canonical_product_id": (
                    canonical_id
                ),
                "tcgplayer_product_id": (
                    clean_text(
                        source_row.get(
                            "tcgplayer_product_id"
                        )
                    )
                ),
                "change_type": change_type,
                "review_required": (
                    review_required
                ),
                "prior_product_name": (
                    clean_text(
                        prior_row.get(
                            "canonical_product_name"
                        )
                    )
                    if prior_row is not None
                    else ""
                ),
                "current_product_name": (
                    clean_text(
                        current_row.get(
                            "canonical_product_name"
                        )
                    )
                    if current_row is not None
                    else ""
                ),
                "prior_product_class": (
                    clean_text(
                        prior_row.get(
                            "canonical_product_class"
                        )
                    )
                    if prior_row is not None
                    else ""
                ),
                "current_product_class": (
                    clean_text(
                        current_row.get(
                            "canonical_product_class"
                        )
                    )
                    if current_row is not None
                    else ""
                ),
                "prior_product_family": (
                    clean_text(
                        prior_row.get(
                            "canonical_product_family"
                        )
                    )
                    if prior_row is not None
                    else ""
                ),
                "current_product_family": (
                    clean_text(
                        current_row.get(
                            "canonical_product_family"
                        )
                    )
                    if current_row is not None
                    else ""
                ),
                "prior_product_type": (
                    clean_text(
                        prior_row.get(
                            "canonical_product_type"
                        )
                    )
                    if prior_row is not None
                    else ""
                ),
                "current_product_type": (
                    clean_text(
                        current_row.get(
                            "canonical_product_type"
                        )
                    )
                    if current_row is not None
                    else ""
                ),
                "prior_packaging_level": (
                    clean_text(
                        prior_row.get(
                            "canonical_packaging_level"
                        )
                    )
                    if prior_row is not None
                    else ""
                ),
                "current_packaging_level": (
                    clean_text(
                        current_row.get(
                            "canonical_packaging_level"
                        )
                    )
                    if current_row is not None
                    else ""
                ),
                "prior_lifecycle_status": (
                    clean_text(
                        prior_row.get(
                            "identity_lifecycle_status"
                        )
                    )
                    if prior_row is not None
                    else ""
                ),
                "resulting_lifecycle_status": (
                    resulting_lifecycle
                ),
                "prior_source_availability": (
                    clean_text(
                        prior_row.get(
                            "source_availability_status"
                        )
                    )
                    if prior_row is not None
                    else ""
                ),
                "resulting_source_availability": (
                    resulting_availability
                ),
                "change_reason": change_reason,
            }
        )

    return pd.DataFrame(
        rows,
        columns=CHANGE_COLUMNS,
    )


def write_outputs(
    changes: pd.DataFrame,
    prior_path: Path,
    current_path: Path,
) -> dict[str, Any]:
    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_path = (
        OUTPUT_ROOT
        / "canonical_registry_change_report_2026-07-22.csv"
    )

    review_path = (
        OUTPUT_ROOT
        / "canonical_registry_change_review_queue_2026-07-22.csv"
    )

    summary_path = (
        OUTPUT_ROOT
        / "canonical_registry_refresh_summary_2026-07-22.json"
    )

    change_exceptions = changes[
        changes[
            "change_type"
        ].ne("unchanged")
    ].copy()

    change_exceptions.to_csv(
        report_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    review_queue = changes[
        changes[
            "review_required"
        ].eq(True)
    ].copy()

    review_queue.to_csv(
        review_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    counts = {
        str(key): int(value)
        for key, value in (
            changes[
                "change_type"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    summary = {
        "schema_version": (
            REFRESH_VERSION
        ),
        "generated_at_utc": utc_now(),
        "refresh_validation_status": (
            "PASS"
        ),
        "comparison_rows": int(
            len(changes)
        ),
        "change_report_rows": int(
            len(change_exceptions)
        ),
        "change_type_counts": counts,
        "review_queue_rows": int(
            len(review_queue)
        ),
        "new_identity_rows": int(
            counts.get(
                "new_identity",
                0,
            )
        ),
        "source_unavailable_rows": int(
            counts.get(
                "source_unavailable",
                0,
            )
        ),
        "identity_conflict_rows": int(
            counts.get(
                "identity_conflict",
                0,
            )
        ),
        "source_name_changed_rows": int(
            counts.get(
                "source_name_changed",
                0,
            )
        ),
        "classification_changed_rows": int(
            counts.get(
                "classification_changed",
                0,
            )
        ),
        "unchanged_rows": int(
            counts.get(
                "unchanged",
                0,
            )
        ),
        "input_files": {
            "prior_governed_registry": str(
                prior_path
            ),
            "current_canonical_registry": str(
                current_path
            ),
        },
        "output_files": {
            "change_report": str(
                report_path
            ),
            "review_queue": str(
                review_path
            ),
        },
        "silent_deletions_applied": False,
        "canonical_registry_changed": False,
        "production_registry_changed": False,
        "universal_database_changed": False,
    }

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print("=" * 76)
    print(
        "Phase 10.5R.1C.2.3 "
        "Refresh and Change Detection"
    )
    print("=" * 76)

    for name, count in sorted(
        counts.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        print(
            f"{name}: {count}"
        )

    print(
        f"Change report rows: "
        f"{len(change_exceptions)}"
    )
    print(
        f"Review queue rows: "
        f"{len(review_queue)}"
    )
    print()
    print(
        "PHASE 10.5R.1C.2.3 "
        "REFRESH CONTROL: PASS"
    )
    print(
        "Silent deletions: NOT APPLIED"
    )
    print(
        "Canonical registry: UNCHANGED"
    )
    print(
        "Production registry: UNCHANGED"
    )
    print(
        "Universal database: UNCHANGED"
    )

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--prior-governed-registry",
        type=Path,
        default=DEFAULT_PRIOR_PATH,
    )

    parser.add_argument(
        "--current-canonical-registry",
        type=Path,
        default=DEFAULT_CURRENT_PATH,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    prior_path = (
        args.prior_governed_registry.resolve()
    )

    current_path = (
        args.current_canonical_registry.resolve()
    )

    if not prior_path.is_file():
        raise FileNotFoundError(
            f"Prior governed registry not found: "
            f"{prior_path}"
        )

    if not current_path.is_file():
        raise FileNotFoundError(
            f"Current canonical registry not found: "
            f"{current_path}"
        )

    prior = pd.read_csv(
        prior_path,
        low_memory=False,
        dtype=str,
        keep_default_na=False,
    )

    current = pd.read_csv(
        current_path,
        low_memory=False,
        dtype=str,
        keep_default_na=False,
    )

    changes = build_change_report(
        prior,
        current,
    )

    summary = write_outputs(
        changes,
        prior_path,
        current_path,
    )

    if (
        summary[
            "identity_conflict_rows"
        ]
        > 0
    ):
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())