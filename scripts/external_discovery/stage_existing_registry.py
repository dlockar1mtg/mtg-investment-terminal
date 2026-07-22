from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

SOURCE_PATH = (
    ROOT
    / "data"
    / "product_master"
    / "investment_products.csv"
)

STAGING_ROOT = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "external_discovery"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "external_discovery"
)

CANONICAL_COLUMNS = [
    "canonical_stage_id",
    "source_system",
    "source_record_id",
    "investment_product_id",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "tcgplayer_product_id",
    "source_set_name",
    "source_box_name",
    "source_product_name",
    "source_product_type",
    "source_approval_status",
    "source_approval_method",
    "source_notes",
    "normalized_set_name",
    "normalized_product_name",
    "normalized_match_name",
    "canonical_product_family",
    "canonical_product_subtype",
    "sealed_unit_candidate",
    "secret_lair_candidate",
    "collector_booster_candidate",
    "masters_candidate",
    "traditional_booster_candidate",
    "draft_booster_candidate",
    "play_booster_candidate",
    "set_booster_candidate",
    "jumpstart_candidate",
    "theme_booster_candidate",
    "bundle_candidate",
    "commander_candidate",
    "case_candidate",
    "single_pack_candidate",
    "language",
    "foil_variant",
    "edition_variant",
    "duplicate_group_key",
    "duplicate_group_size",
    "staging_status",
    "review_reason",
]


LANGUAGE_PATTERNS = {
    "Japanese": (
        "japanese",
        "japan",
        " jp ",
    ),
    "French": (
        "french",
        " fr ",
    ),
    "German": (
        "german",
        " de ",
    ),
    "Italian": (
        "italian",
        " it ",
    ),
    "Spanish": (
        "spanish",
        " es ",
    ),
    "Portuguese": (
        "portuguese",
        " pt ",
    ),
    "Korean": (
        "korean",
        " kr ",
    ),
    "Chinese Simplified": (
        "simplified chinese",
        "chinese simplified",
    ),
    "Chinese Traditional": (
        "traditional chinese",
        "chinese traditional",
    ),
    "Russian": (
        "russian",
        " ru ",
    ),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: object) -> str:
    if pd.isna(value):
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value).strip(),
    )


def ascii_fold(value: object) -> str:
    text = clean_text(value)

    return (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def normalize_name(value: object) -> str:
    text = ascii_fold(value).casefold()

    text = text.replace("&", " and ")

    text = re.sub(
        r"[\[\]{}()_:;,/\\|]+",
        " ",
        text,
    )

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def contains_any(
    value: object,
    terms: tuple[str, ...],
) -> bool:
    normalized = (
        " "
        + normalize_name(value)
        + " "
    )

    return any(
        normalize_name(term) in normalized
        for term in terms
    )


def first_value(
    row: pd.Series,
    *columns: str,
) -> str:
    for column in columns:
        if column not in row.index:
            continue

        value = clean_text(row[column])

        if value:
            return value

    return ""


def infer_language(value: str) -> str:
    padded = (
        " "
        + normalize_name(value)
        + " "
    )

    for language, patterns in (
        LANGUAGE_PATTERNS.items()
    ):
        if any(
            pattern in padded
            for pattern in patterns
        ):
            return language

    return "English_or_unspecified"


def infer_foil_variant(value: str) -> str:
    normalized = normalize_name(value)

    if "non foil" in normalized:
        return "non_foil"

    if "etched foil" in normalized:
        return "etched_foil"

    if "galaxy foil" in normalized:
        return "galaxy_foil"

    if "rainbow foil" in normalized:
        return "rainbow_foil"

    if "foil" in normalized:
        return "foil"

    return "unspecified"


def infer_edition_variant(value: str) -> str:
    normalized = normalize_name(value)

    variants = [
        (
            "special_edition",
            (
                "special edition",
                "special edition collector",
            ),
        ),
        (
            "convention_edition",
            (
                "convention edition",
                "convention exclusive",
            ),
        ),
        (
            "retail_exclusive",
            (
                "retail exclusive",
            ),
        ),
        (
            "first_printing",
            (
                "first printing",
            ),
        ),
        (
            "second_printing",
            (
                "second printing",
            ),
        ),
    ]

    for variant, terms in variants:
        if any(
            term in normalized
            for term in terms
        ):
            return variant

    return "standard_or_unspecified"


def infer_product_family(
    source_type: str,
    combined_name: str,
) -> tuple[str, str]:
    normalized_type = normalize_name(source_type)
    normalized_name = normalize_name(
        combined_name
    )

    combined = (
        normalized_type
        + " "
        + normalized_name
    )

    if "secret lair" in combined:
        return (
            "secret_lair",
            "secret_lair_drop",
        )

    if (
        "collector booster" in combined
        and (
            "display" in combined
            or "box" in combined
        )
    ):
        return (
            "booster_display",
            "collector_booster_display",
        )

    if (
        "masters booster" in combined
        or (
            "masters" in combined
            and (
                "booster box" in combined
                or "booster display" in combined
            )
        )
    ):
        return (
            "booster_display",
            "masters_booster_display",
        )

    if (
        "draft booster" in combined
        and (
            "display" in combined
            or "box" in combined
        )
    ):
        return (
            "booster_display",
            "draft_booster_display",
        )

    if (
        "play booster" in combined
        and (
            "display" in combined
            or "box" in combined
        )
    ):
        return (
            "booster_display",
            "play_booster_display",
        )

    if (
        "set booster" in combined
        and (
            "display" in combined
            or "box" in combined
        )
    ):
        return (
            "booster_display",
            "set_booster_display",
        )

    if (
        "jumpstart" in combined
        and (
            "display" in combined
            or "box" in combined
        )
    ):
        return (
            "booster_display",
            "jumpstart_booster_display",
        )

    if (
        "theme booster" in combined
        and (
            "display" in combined
            or "box" in combined
        )
    ):
        return (
            "booster_display",
            "theme_booster_display",
        )

    if (
        "booster box" in combined
        or "booster display" in combined
        or "traditional booster display"
        in combined
    ):
        return (
            "booster_display",
            "traditional_booster_display",
        )

    if "bundle" in combined:
        return (
            "bundle",
            "bundle",
        )

    if (
        "commander" in combined
        and "deck" in combined
    ):
        return (
            "preconstructed_deck",
            "commander_deck",
        )

    return (
        "unclassified",
        "unclassified",
    )


def build_duplicate_key(
    set_name: str,
    product_name: str,
    product_family: str,
    product_subtype: str,
    language: str,
    foil_variant: str,
    edition_variant: str,
) -> str:
    components = [
        normalize_name(set_name),
        normalize_name(product_name),
        normalize_name(product_family),
        normalize_name(product_subtype),
        normalize_name(language),
        normalize_name(foil_variant),
        normalize_name(edition_variant),
    ]

    return "|".join(components)


def stable_stage_id(
    source_record_id: str,
) -> str:
    digest = hashlib.sha256(
        (
            "existing_registry|"
            + source_record_id
        ).encode("utf-8")
    ).hexdigest()[:20]

    return f"MTG-STAGE-{digest.upper()}"


def build_review_reason(
    product_family: str,
    duplicate_group_size: int,
    source_approval_status: str,
    language: str,
) -> str:
    reasons: list[str] = []

    if product_family == "unclassified":
        reasons.append(
            "unclassified_product_family"
        )

    if duplicate_group_size > 1:
        reasons.append(
            "possible_duplicate_or_variant"
        )

    if (
        source_approval_status.casefold()
        != "approved"
    ):
        reasons.append(
            "existing_status_not_approved"
        )

    if language != "English_or_unspecified":
        reasons.append(
            "language_variant_review"
        )

    return "|".join(reasons)


def main() -> int:
    if not SOURCE_PATH.is_file():
        raise FileNotFoundError(
            f"Existing registry not found: "
            f"{SOURCE_PATH}"
        )

    source = pd.read_csv(
        SOURCE_PATH,
        low_memory=False,
    )

    required_columns = {
        "investment_product_id",
        "set_name",
        "box_name",
        "approved_tcgplayer_product_id",
        "approved_product_name",
        "investment_product_type",
        "approval_status",
    }

    missing = sorted(
        required_columns - set(source.columns)
    )

    if missing:
        raise ValueError(
            "Registry missing required columns: "
            + ", ".join(missing)
        )

    stage_rows: list[dict[str, Any]] = []

    for _, row in source.iterrows():
        investment_product_id = first_value(
            row,
            "investment_product_id",
        )

        tcgplayer_product_id = first_value(
            row,
            "approved_tcgplayer_product_id",
        )

        source_set_name = first_value(
            row,
            "set_name",
        )

        source_box_name = first_value(
            row,
            "box_name",
        )

        source_product_name = first_value(
            row,
            "approved_product_name",
            "box_name",
        )

        source_product_type = first_value(
            row,
            "investment_product_type",
        )

        source_approval_status = first_value(
            row,
            "approval_status",
        )

        source_approval_method = first_value(
            row,
            "approval_method",
        )

        source_notes = first_value(
            row,
            "notes",
        )

        tcgcsv_category_id = first_value(
            row,
            "tcgcsv_category_id",
        )

        tcgcsv_group_id = first_value(
            row,
            "tcgcsv_group_id",
        )

        combined_name = " | ".join(
            value
            for value in (
                source_set_name,
                source_box_name,
                source_product_name,
                source_product_type,
            )
            if value
        )

        (
            product_family,
            product_subtype,
        ) = infer_product_family(
            source_product_type,
            combined_name,
        )

        language = infer_language(
            combined_name
        )

        foil_variant = infer_foil_variant(
            combined_name
        )

        edition_variant = infer_edition_variant(
            combined_name
        )

        normalized_product_name = (
            normalize_name(
                source_product_name
                or source_box_name
            )
        )

        normalized_set_name = normalize_name(
            source_set_name
        )

        normalized_match_name = " | ".join(
            value
            for value in (
                normalized_set_name,
                normalized_product_name,
                normalize_name(product_subtype),
                normalize_name(language),
                normalize_name(foil_variant),
                normalize_name(edition_variant),
            )
            if value
        )

        duplicate_group_key = (
            build_duplicate_key(
                source_set_name,
                source_product_name
                or source_box_name,
                product_family,
                product_subtype,
                language,
                foil_variant,
                edition_variant,
            )
        )

        stage_rows.append(
            {
                "canonical_stage_id": (
                    stable_stage_id(
                        investment_product_id
                    )
                ),
                "source_system": (
                    "existing_product_registry"
                ),
                "source_record_id": (
                    investment_product_id
                ),
                "investment_product_id": (
                    investment_product_id
                ),
                "tcgcsv_category_id": (
                    tcgcsv_category_id
                ),
                "tcgcsv_group_id": (
                    tcgcsv_group_id
                ),
                "tcgplayer_product_id": (
                    tcgplayer_product_id
                ),
                "source_set_name": (
                    source_set_name
                ),
                "source_box_name": (
                    source_box_name
                ),
                "source_product_name": (
                    source_product_name
                ),
                "source_product_type": (
                    source_product_type
                ),
                "source_approval_status": (
                    source_approval_status
                ),
                "source_approval_method": (
                    source_approval_method
                ),
                "source_notes": source_notes,
                "normalized_set_name": (
                    normalized_set_name
                ),
                "normalized_product_name": (
                    normalized_product_name
                ),
                "normalized_match_name": (
                    normalized_match_name
                ),
                "canonical_product_family": (
                    product_family
                ),
                "canonical_product_subtype": (
                    product_subtype
                ),
                "sealed_unit_candidate": (
                    product_family
                    in {
                        "booster_display",
                        "secret_lair",
                        "bundle",
                        "preconstructed_deck",
                    }
                ),
                "secret_lair_candidate": (
                    product_family
                    == "secret_lair"
                ),
                "collector_booster_candidate": (
                    product_subtype
                    == "collector_booster_display"
                ),
                "masters_candidate": (
                    product_subtype
                    == "masters_booster_display"
                ),
                "traditional_booster_candidate": (
                    product_subtype
                    == "traditional_booster_display"
                ),
                "draft_booster_candidate": (
                    product_subtype
                    == "draft_booster_display"
                ),
                "play_booster_candidate": (
                    product_subtype
                    == "play_booster_display"
                ),
                "set_booster_candidate": (
                    product_subtype
                    == "set_booster_display"
                ),
                "jumpstart_candidate": (
                    product_subtype
                    == "jumpstart_booster_display"
                ),
                "theme_booster_candidate": (
                    product_subtype
                    == "theme_booster_display"
                ),
                "bundle_candidate": (
                    product_family == "bundle"
                ),
                "commander_candidate": (
                    product_subtype
                    == "commander_deck"
                ),
                "case_candidate": contains_any(
                    combined_name,
                    (
                        "case of",
                        "sealed case",
                        "booster case",
                        "display case",
                        "6 box case",
                        "12 box case",
                    ),
                ),
                "single_pack_candidate": (
                    contains_any(
                        combined_name,
                        (
                            "single booster",
                            "booster pack",
                            "sample pack",
                        ),
                    )
                    and not contains_any(
                        combined_name,
                        (
                            "booster box",
                            "booster display",
                            "display box",
                        ),
                    )
                ),
                "language": language,
                "foil_variant": foil_variant,
                "edition_variant": (
                    edition_variant
                ),
                "duplicate_group_key": (
                    duplicate_group_key
                ),
                "duplicate_group_size": 0,
                "staging_status": "staged",
                "review_reason": "",
            }
        )

    staged = pd.DataFrame(stage_rows)

    duplicate_sizes = (
        staged["duplicate_group_key"]
        .value_counts()
        .to_dict()
    )

    staged["duplicate_group_size"] = (
        staged["duplicate_group_key"].map(
            duplicate_sizes
        )
    )

    staged["review_reason"] = staged.apply(
        lambda row: build_review_reason(
            product_family=row[
                "canonical_product_family"
            ],
            duplicate_group_size=int(
                row["duplicate_group_size"]
            ),
            source_approval_status=str(
                row["source_approval_status"]
            ),
            language=str(row["language"]),
        ),
        axis=1,
    )

    staged["staging_status"] = staged[
        "review_reason"
    ].map(
        lambda value: (
            "review_required"
            if clean_text(value)
            else "staged_clean"
        )
    )

    staged = staged.loc[
        :,
        CANONICAL_COLUMNS,
    ].sort_values(
        [
            "canonical_product_family",
            "canonical_product_subtype",
            "normalized_set_name",
            "normalized_product_name",
            "source_record_id",
        ],
        kind="stable",
    )

    duplicate_candidates = staged.loc[
        staged["duplicate_group_size"].gt(1)
    ].copy()

    unclassified = staged.loc[
        staged[
            "canonical_product_family"
        ].eq("unclassified")
    ].copy()

    review_queue = staged.loc[
        staged["staging_status"].eq(
            "review_required"
        )
    ].copy()

    approved_snapshot = staged.loc[
        staged[
            "source_approval_status"
        ].fillna("")
        .astype(str)
        .str.strip()
        .str.casefold()
        .eq("approved")
    ].copy()

    STAGING_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    VALIDATION_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    canonical_path = (
        STAGING_ROOT
        / "existing_registry_canonical_stage.csv"
    )

    duplicate_path = (
        VALIDATION_ROOT
        / "existing_registry_duplicate_candidates.csv"
    )

    unclassified_path = (
        VALIDATION_ROOT
        / "existing_registry_unclassified.csv"
    )

    review_path = (
        VALIDATION_ROOT
        / "existing_registry_review_queue.csv"
    )

    approved_path = (
        VALIDATION_ROOT
        / "existing_registry_approved_snapshot.csv"
    )

    summary_path = (
        VALIDATION_ROOT
        / "existing_registry_staging_summary.json"
    )

    staged.to_csv(
        canonical_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    duplicate_candidates.to_csv(
        duplicate_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    unclassified.to_csv(
        unclassified_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    review_queue.to_csv(
        review_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    approved_snapshot.to_csv(
        approved_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    family_counts = {
        str(key): int(value)
        for key, value in (
            staged[
                "canonical_product_family"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    subtype_counts = {
        str(key): int(value)
        for key, value in (
            staged[
                "canonical_product_subtype"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    approval_counts = {
        str(key): int(value)
        for key, value in (
            staged[
                "source_approval_status"
            ]
            .fillna("(blank)")
            .replace("", "(blank)")
            .value_counts()
            .to_dict()
            .items()
        )
    }

    summary = {
        "generated_at": utc_now(),
        "source_path": str(SOURCE_PATH),
        "source_row_count": int(len(source)),
        "staged_row_count": int(len(staged)),
        "unique_stage_id_count": int(
            staged[
                "canonical_stage_id"
            ].nunique()
        ),
        "unique_source_record_id_count": int(
            staged[
                "source_record_id"
            ].nunique()
        ),
        "unique_tcgplayer_product_id_count": int(
            staged[
                "tcgplayer_product_id"
            ].nunique()
        ),
        "approved_snapshot_count": int(
            len(approved_snapshot)
        ),
        "review_queue_count": int(
            len(review_queue)
        ),
        "unclassified_count": int(
            len(unclassified)
        ),
        "duplicate_candidate_row_count": int(
            len(duplicate_candidates)
        ),
        "duplicate_group_count": int(
            duplicate_candidates[
                "duplicate_group_key"
            ].nunique()
        ),
        "product_family_counts": (
            family_counts
        ),
        "product_subtype_counts": (
            subtype_counts
        ),
        "approval_status_counts": (
            approval_counts
        ),
        "certification_status": (
            "STAGING_COMPLETE_NOT_ELIGIBILITY_CERTIFIED"
        ),
        "invariants": {
            "all_source_rows_preserved": (
                len(source) == len(staged)
            ),
            "source_ids_unique": (
                staged[
                    "source_record_id"
                ].nunique()
                == len(staged)
            ),
            "stage_ids_unique": (
                staged[
                    "canonical_stage_id"
                ].nunique()
                == len(staged)
            ),
            "approval_status_preserved": (
                approval_counts
                == {
                    str(key): int(value)
                    for key, value in (
                        source[
                            "approval_status"
                        ]
                        .fillna("(blank)")
                        .replace(
                            "",
                            "(blank)",
                        )
                        .value_counts()
                        .to_dict()
                        .items()
                    )
                }
            ),
        },
        "output_files": {
            "canonical_stage": str(
                canonical_path
            ),
            "duplicate_candidates": str(
                duplicate_path
            ),
            "unclassified": str(
                unclassified_path
            ),
            "review_queue": str(
                review_path
            ),
            "approved_snapshot": str(
                approved_path
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

    if not all(summary["invariants"].values()):
        raise RuntimeError(
            "Canonical staging invariant failed."
        )

    print("=" * 76)
    print(
        "Phase 10.5R.1B.1 Existing Registry "
        "Canonical Staging"
    )
    print("=" * 76)
    print(
        f"Source rows: {len(source)}"
    )
    print(
        f"Staged rows: {len(staged)}"
    )
    print(
        f"Approved snapshot: "
        f"{len(approved_snapshot)}"
    )
    print(
        f"Review queue: "
        f"{len(review_queue)}"
    )
    print(
        f"Unclassified: "
        f"{len(unclassified)}"
    )
    print(
        f"Duplicate candidate rows: "
        f"{len(duplicate_candidates)}"
    )
    print(
        f"Duplicate groups: "
        f"{summary['duplicate_group_count']}"
    )
    print()
    print("Product families:")

    for family_name, count in sorted(
        family_counts.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        print(
            f"  {family_name}: {count}"
        )

    print()
    print(f"Canonical stage: {canonical_path}")
    print(f"Review queue: {review_path}")
    print(
        f"Duplicate candidates: "
        f"{duplicate_path}"
    )
    print(f"Unclassified: {unclassified_path}")
    print(f"Summary: {summary_path}")
    print()
    print(
        "PHASE 10.5R.1B.1 EXISTING REGISTRY "
        "STAGING: PASS"
    )
    print(
        "Certification: STAGING COMPLETE — "
        "ELIGIBILITY UNCHANGED"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())