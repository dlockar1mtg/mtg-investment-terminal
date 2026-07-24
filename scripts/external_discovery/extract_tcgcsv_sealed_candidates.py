from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_SNAPSHOT_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "external_discovery"
    / "tcgcsv"
    / "tcgcsv_magic_products_2026-07-22.csv"
)

OUTPUT_ROOT = (
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


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value).strip(),
    )


def normalize_name(value: object) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        clean_text(value).casefold(),
    ).strip()


def contains_any(
    text: str,
    terms: tuple[str, ...],
) -> bool:
    return any(
        term in text
        for term in terms
    )


def classify_candidate(
    group_name: object,
    product_name: object,
) -> tuple[str, str]:
    group = normalize_name(group_name)
    product = normalize_name(product_name)
    combined = f"{group} {product}".strip()

    if contains_any(
        combined,
        (
            "booster case",
            "case of booster",
            "sealed case",
            "display case",
            "booster box case",
            "box case",
            "draft booster case",
            "collector booster case",
            "set booster case",
            "play booster case",
        ),
    ):
        return (
            "sealed_case",
            "case_candidate",
        )

    if (
        "collector booster" in combined
        and contains_any(
            product,
            (
                "display",
                "booster box",
                "display box",
            ),
        )
    ):
        return (
            "collector_booster_display",
            "sealed_display_candidate",
        )

    if (
        "play booster" in combined
        and contains_any(
            product,
            (
                "display",
                "booster box",
                "display box",
            ),
        )
    ):
        return (
            "play_booster_display",
            "sealed_display_candidate",
        )

    if (
        "set booster" in combined
        and contains_any(
            product,
            (
                "display",
                "booster box",
                "display box",
            ),
        )
    ):
        return (
            "set_booster_display",
            "sealed_display_candidate",
        )

    if (
        "draft booster" in combined
        and contains_any(
            product,
            (
                "display",
                "booster box",
                "display box",
            ),
        )
    ):
        return (
            "draft_booster_display",
            "sealed_display_candidate",
        )

    if (
        "theme booster" in combined
        and contains_any(
            product,
            (
                "display",
                "box",
            ),
        )
    ):
        return (
            "theme_booster_display",
            "sealed_display_candidate",
        )

    if (
        "jumpstart" in combined
        and contains_any(
            product,
            (
                "booster display",
                "booster box",
                "display box",
            ),
        )
    ):
        return (
            "jumpstart_booster_display",
            "sealed_display_candidate",
        )

    if contains_any(
        product,
        (
            "booster display",
            "booster box",
            "display box",
        ),
    ):
        return (
            "traditional_booster_display",
            "sealed_display_candidate",
        )

    if re.search(
        r"\bbundle\b",
        product,
    ):
        return (
            "bundle",
            "sealed_bundle_candidate",
        )

    if contains_any(
        product,
        (
            "commander deck",
            "commander decks",
        ),
    ):
        return (
            "commander_deck",
            "sealed_deck_candidate",
        )

    return (
        "",
        "",
    )


def exclusion_reasons(
    product_name: object,
    candidate_type: str,
) -> list[str]:
    product = normalize_name(product_name)
    reasons: list[str] = []

    if contains_any(
        product,
        (
            "single booster pack",
            "sample booster",
            "collector booster sample pack",
        ),
    ):
        reasons.append(
            "single_or_sample_pack"
        )

    if (
        "booster pack" in product
        and not contains_any(
            product,
            (
                "display",
                "box",
                "case",
            ),
        )
    ):
        reasons.append(
            "single_booster_pack"
        )

    if contains_any(
        product,
        (
            "empty box",
            "box only",
            "wrapper",
            "display only",
        ),
    ):
        reasons.append(
            "empty_packaging"
        )

    if (
        candidate_type == "commander_deck"
        and contains_any(
            product,
            (
                "decklist",
                "deck list",
                "display commander card",
            ),
        )
    ):
        reasons.append(
            "not_sealed_commander_deck"
        )

    return reasons


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--snapshot",
        type=Path,
        default=DEFAULT_SNAPSHOT_PATH,
    )

    args = parser.parse_args()

    snapshot_path = args.snapshot.resolve()

    if not snapshot_path.is_file():
        raise FileNotFoundError(
            f"Snapshot not found: "
            f"{snapshot_path}"
        )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    VALIDATION_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    source = pd.read_csv(
        snapshot_path,
        low_memory=False,
    )

    required_columns = {
        "snapshot_record_id",
        "tcgcsv_category_id",
        "tcgcsv_group_id",
        "tcgplayer_product_id",
        "group_name",
        "group_published_on",
        "product_name",
    }

    missing_columns = sorted(
        required_columns - set(source.columns)
    )

    if missing_columns:
        raise ValueError(
            "Snapshot missing columns: "
            + ", ".join(missing_columns)
        )

    candidate_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    secret_lair_source_rows: list[
        dict[str, Any]
    ] = []

    for row in source.itertuples(index=False):
        combined_name = normalize_name(
            f"{row.group_name} {row.product_name}"
        )

        if "secret lair" in combined_name:
            secret_lair_source_rows.append(
                {
                    "snapshot_record_id": (
                        row.snapshot_record_id
                    ),
                    "tcgcsv_category_id": (
                        row.tcgcsv_category_id
                    ),
                    "tcgcsv_group_id": (
                        row.tcgcsv_group_id
                    ),
                    "tcgplayer_product_id": (
                        row.tcgplayer_product_id
                    ),
                    "group_name": row.group_name,
                    "group_published_on": (
                        row.group_published_on
                    ),
                    "product_name": (
                        row.product_name
                    ),
                    "evidence_class": (
                        "secret_lair_product_record"
                    ),
                    "sealed_drop_status": (
                        "not_determined"
                    ),
                    "review_reason": (
                        "tcgcsv_product_may_be_"
                        "individual_card_not_drop"
                    ),
                }
            )

            continue
        candidate_type, candidate_status = (
            classify_candidate(
                row.group_name,
                row.product_name,
            )
        )

        if not candidate_type:
            continue

        reasons = exclusion_reasons(
            row.product_name,
            candidate_type,
        )

        output = {
            "snapshot_record_id": (
                row.snapshot_record_id
            ),
            "tcgcsv_category_id": (
                row.tcgcsv_category_id
            ),
            "tcgcsv_group_id": (
                row.tcgcsv_group_id
            ),
            "tcgplayer_product_id": (
                row.tcgplayer_product_id
            ),
            "group_name": row.group_name,
            "group_published_on": (
                row.group_published_on
            ),
            "product_name": row.product_name,
            "candidate_product_type": (
                candidate_type
            ),
            "candidate_status": (
                candidate_status
            ),
            "exclusion_reason": "|".join(
                reasons
            ),
        }

        if reasons:
            rejected_rows.append(output)
        else:
            candidate_rows.append(output)

    candidates = pd.DataFrame(
        candidate_rows
    )

    rejected = pd.DataFrame(
        rejected_rows
    )

    secret_lair_source = pd.DataFrame(
        secret_lair_source_rows
    )

    sort_columns = [
        "candidate_product_type",
        "group_name",
        "product_name",
        "tcgplayer_product_id",
    ]

    if not candidates.empty:
        candidates = candidates.sort_values(
            sort_columns,
            kind="stable",
        ).reset_index(drop=True)

    if not rejected.empty:
        rejected = rejected.sort_values(
            sort_columns,
            kind="stable",
        ).reset_index(drop=True)

    candidates_path = (
        OUTPUT_ROOT
        / "tcgcsv_sealed_product_candidates_2026-07-22.csv"
    )

    rejected_path = (
        VALIDATION_ROOT
        / "tcgcsv_candidate_exclusions_2026-07-22.csv"
    )

    summary_path = (
        VALIDATION_ROOT
        / "tcgcsv_candidate_extraction_summary_2026-07-22.json"
    )

    secret_lair_source_path = (
        VALIDATION_ROOT
        / "tcgcsv_secret_lair_product_evidence_2026-07-22.csv"
    )

    candidates.to_csv(
        candidates_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    rejected.to_csv(
        rejected_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    secret_lair_source.to_csv(
        secret_lair_source_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    candidate_counts = {
        str(key): int(value)
        for key, value in (
            candidates[
                "candidate_product_type"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    summary = {
        "generated_at_utc": utc_now(),
        "source_snapshot": str(
            snapshot_path
        ),
        "source_product_rows": int(
            len(source)
        ),
        "candidate_rows": int(
            len(candidates)
        ),
        "excluded_candidate_rows": int(
            len(rejected)
        ),
        "secret_lair_product_evidence_rows": int(
            len(secret_lair_source)
        ),
        "secret_lair_sealed_drop_count": (
            "NOT_DETERMINED"
        ),
        "unique_candidate_product_ids": int(
            candidates[
                "tcgplayer_product_id"
            ].nunique()
        ),
        "candidate_type_counts": (
            candidate_counts
        ),
        "classification_status": (
            "CANDIDATE_EXTRACTION_ONLY"
        ),
        "eligibility_changed": False,
        "registry_changed": False,
        "database_changed": False,
        "output_files": {
            "candidates": str(
                candidates_path
            ),
            "excluded_candidates": str(
                rejected_path
            ),
            "secret_lair_product_evidence": str(
                secret_lair_source_path
            ),
        },
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
        "Phase 10.5R.1B.2.2 TCGCSV "
        "Sealed-Product Candidate Extraction"
    )
    print("=" * 76)
    print(
        f"Source products: {len(source)}"
    )
    print(
        f"Candidate rows: {len(candidates)}"
    )
    print(
        f"Excluded candidate rows: "
        f"{len(rejected)}"
    )
    print()
    print("Candidate types:")

    for name, count in sorted(
        candidate_counts.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        print(f"  {name}: {count}")

    print()
    print(f"Candidates: {candidates_path}")
    print(f"Excluded: {rejected_path}")
    print(f"Summary: {summary_path}")
    print()
    print(
        "PHASE 10.5R.1B.2.2 TCGCSV "
        "CANDIDATE EXTRACTION: PASS"
    )
    print(
        "Eligibility: UNCHANGED"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())