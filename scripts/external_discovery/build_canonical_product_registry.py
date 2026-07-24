from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_CANDIDATE_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "external_discovery"
    / "tcgcsv"
    / "tcgcsv_premium_candidate_universe_2026-07-22.csv"
)

DEFAULT_RECONCILIATION_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "external_discovery"
    / "tcgcsv"
    / "reconciliation"
    / "tcgcsv_candidate_reconciliation_2026-07-22.csv"
)

DEFAULT_EXISTING_REGISTRY_PATH = (
    ROOT
    / "data"
    / "product_master"
    / "investment_products.csv"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "canonical_registry"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "canonical_registry"
)

REGISTRY_VERSION = "10.5R.1C.1"

CANONICAL_COLUMNS = [
    "canonical_product_id",
    "canonical_registry_version",
    "canonical_identity_status",
    "canonical_set_name",
    "canonical_product_name",
    "canonical_product_class",
    "canonical_product_family",
    "canonical_product_type",
    "canonical_packaging_level",
    "language",
    "foil_variant",
    "edition_variant",
    "tcgplayer_product_id",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "candidate_record_id",
    "source_system",
    "source_snapshot_record_id",
    "registry_relationship",
    "reconciliation_status",
    "type_alignment",
    "existing_investment_product_id",
    "existing_product_type",
    "existing_approval_status",
    "existing_approval_method",
    "existing_registry_notes",
    "identity_review_status",
    "identity_review_reason",
    "investment_eligibility_status",
    "investment_approval_status",
    "scoring_status",
    "source_lineage",
]


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def is_missing(value: object) -> bool:
    if value is None:
        return True

    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False

    try:
        return bool(result)
    except (TypeError, ValueError):
        return False


def clean_text(value: object) -> str:
    if is_missing(value):
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value).strip(),
    )


def normalize_identifier(value: object) -> str:
    text = clean_text(value)

    if re.fullmatch(
        r"\d+\.0",
        text,
    ):
        return text[:-2]

    return text


def ascii_fold(value: object) -> str:
    return (
        unicodedata.normalize(
            "NFKD",
            clean_text(value),
        )
        .encode(
            "ascii",
            "ignore",
        )
        .decode("ascii")
    )


def normalize_name(value: object) -> str:
    text = ascii_fold(
        value
    ).casefold()

    text = text.replace(
        "&",
        " and ",
    )

    text = re.sub(
        r"\bmagic\s*:\s*the\s+gathering\b",
        " ",
        text,
    )

    text = re.sub(
        r"\bmtg\b",
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


def first_available(
    row: pd.Series | None,
    columns: tuple[str, ...],
) -> str:
    if row is None:
        return ""

    for column in columns:
        if column not in row.index:
            continue

        value = clean_text(
            row[column]
        )

        if value:
            return value

    return ""


def stable_canonical_id(
    tcgplayer_product_id: str,
    candidate_record_id: str,
) -> str:
    if tcgplayer_product_id:
        return (
            "MTG-CANON-TCGPLAYER-"
            + tcgplayer_product_id
        )

    digest = hashlib.sha256(
        (
            "mtg_canonical_product|"
            + candidate_record_id
        ).encode("utf-8")
    ).hexdigest()[:20]

    return (
        "MTG-CANON-SOURCE-"
        + digest.upper()
    )


def infer_packaging_level(
    product_class: str,
    product_type: str,
    product_name: str,
) -> str:
    combined = normalize_name(
        " ".join(
            (
                product_class,
                product_type,
                product_name,
            )
        )
    )

    if "case" in combined:
        return "case"

    if any(
        term in combined
        for term in (
            "booster display",
            "booster box",
        )
    ):
        return "display"

    if "bundle" in combined:
        return "bundle"

    if "commander deck" in combined:
        return "deck"

    if (
        product_class
        == "secret_lair_product"
    ):
        if "insert" in combined:
            return "individual_card_insert"

        if "card" in combined:
            return "individual_card_or_variant"

        return "secret_lair_product"

    return "sealed_product"


def infer_product_family(
    product_class: str,
    product_type: str,
) -> str:
    if (
        product_class
        == "secret_lair_product"
    ):
        return "secret_lair"

    if product_type in {
        "collector_booster_display",
        "draft_booster_display",
        "jumpstart_booster_display",
        "play_booster_display",
        "set_booster_display",
        "theme_booster_display",
        "traditional_booster_display",
    }:
        return "booster_display"

    if product_type == "sealed_case":
        return "sealed_case"

    if product_type == "bundle":
        return "bundle"

    if product_type == "commander_deck":
        return "preconstructed_deck"

    return "sealed_product"


def infer_language(
    product_name: str,
) -> str:
    normalized = (
        " "
        + normalize_name(product_name)
        + " "
    )

    patterns = {
        "Japanese": (
            " japanese ",
            " jp ",
        ),
        "French": (
            " french ",
            " fr ",
        ),
        "German": (
            " german ",
            " de ",
        ),
        "Italian": (
            " italian ",
            " it ",
        ),
        "Spanish": (
            " spanish ",
            " es ",
        ),
        "Portuguese": (
            " portuguese ",
            " pt ",
        ),
        "Korean": (
            " korean ",
            " kr ",
        ),
        "Chinese Simplified": (
            " simplified chinese ",
        ),
        "Chinese Traditional": (
            " traditional chinese ",
        ),
        "Russian": (
            " russian ",
            " ru ",
        ),
    }

    for language, terms in patterns.items():
        if any(
            term in normalized
            for term in terms
        ):
            return language

    return "English_or_unspecified"


def infer_foil_variant(
    product_name: str,
) -> str:
    normalized = normalize_name(
        product_name
    )

    if "non foil" in normalized:
        return "non_foil"

    if "etched foil" in normalized:
        return "etched_foil"

    if "galaxy foil" in normalized:
        return "galaxy_foil"

    if "rainbow foil" in normalized:
        return "rainbow_foil"

    if "halo foil" in normalized:
        return "halo_foil"

    if "traditional foil" in normalized:
        return "traditional_foil"

    if "foil" in normalized:
        return "foil"

    return "unspecified"


def infer_edition_variant(
    product_name: str,
) -> str:
    normalized = normalize_name(
        product_name
    )

    variants = {
        "gift_edition": (
            "gift bundle",
            "gift edition",
        ),
        "special_edition": (
            "special edition",
        ),
        "convention_edition": (
            "convention edition",
        ),
        "retail_exclusive": (
            "retail exclusive",
        ),
        "first_printing": (
            "first printing",
        ),
        "second_printing": (
            "second printing",
        ),
    }

    for variant, terms in variants.items():
        if any(
            term in normalized
            for term in terms
        ):
            return variant

    return "standard_or_unspecified"


def build_existing_registry_index(
    registry: pd.DataFrame,
) -> dict[str, pd.Series]:
    index: dict[
        str,
        pd.Series,
    ] = {}

    for _, row in registry.iterrows():
        product_id = normalize_identifier(
            row.get(
                "approved_tcgplayer_product_id"
            )
        )

        if not product_id:
            continue

        if product_id in index:
            raise RuntimeError(
                "Duplicate TCGplayer product ID "
                "in existing registry: "
                f"{product_id}"
            )

        index[product_id] = row

    return index


def build_reconciliation_index(
    reconciliation: pd.DataFrame,
) -> dict[str, pd.Series]:
    index: dict[
        str,
        pd.Series,
    ] = {}

    for _, row in reconciliation.iterrows():
        candidate_id = clean_text(
            row.get(
                "candidate_record_id"
            )
        )

        if not candidate_id:
            raise RuntimeError(
                "Reconciliation row is missing "
                "candidate_record_id."
            )

        if candidate_id in index:
            raise RuntimeError(
                "Duplicate reconciliation candidate: "
                f"{candidate_id}"
            )

        index[candidate_id] = row

    return index


def determine_identity_status(
    reconciliation_status: str,
) -> str:
    if reconciliation_status == (
        "exact_id_match"
    ):
        return "established_existing_identity"

    if reconciliation_status == (
        "new_candidate"
    ):
        return "new_source_identity"

    return "identity_review_required"


def determine_review_status(
    reconciliation_status: str,
    type_alignment: str,
) -> tuple[str, str]:
    if reconciliation_status in {
        "exact_id_match",
        "new_candidate",
    } and type_alignment in {
        "compatible",
        "compatible_registry_generic_secret_lair",
        "compatible_registry_generic_booster_display",
        "compatible_registry_generic_case_packaging",
        "not_applicable",
    }:
        return (
            "identity_complete",
            "",
        )

    reasons = [
        value
        for value in (
            reconciliation_status,
            type_alignment,
        )
        if value
    ]

    return (
        "identity_review_required",
        "|".join(reasons),
    )


def determine_investment_statuses(
    *,
    reconciliation_status: str,
    existing_approval_status: str,
    candidate_eligibility_status: str,
    candidate_scoring_status: str,
) -> tuple[str, str, str]:
    if reconciliation_status == (
        "exact_id_match"
    ):
        eligibility = (
            candidate_eligibility_status
            or "not_evaluated"
        )

        approval = (
            existing_approval_status
            or "review_required"
        )

        scoring = (
            candidate_scoring_status
            or "not_scored"
        )

        return (
            eligibility,
            approval,
            scoring,
        )

    return (
        "not_evaluated",
        "review_required",
        "not_scored",
    )


def build_canonical_registry(
    *,
    candidates: pd.DataFrame,
    reconciliation: pd.DataFrame,
    existing_registry: pd.DataFrame,
) -> pd.DataFrame:
    reconciliation_index = (
        build_reconciliation_index(
            reconciliation
        )
    )

    existing_index = (
        build_existing_registry_index(
            existing_registry
        )
    )

    output_rows: list[
        dict[str, Any]
    ] = []

    for _, candidate in candidates.iterrows():
        candidate_record_id = clean_text(
            candidate.get(
                "candidate_record_id"
            )
        )

        if (
            candidate_record_id
            not in reconciliation_index
        ):
            raise RuntimeError(
                "Candidate missing from reconciliation: "
                f"{candidate_record_id}"
            )

        reconciled = reconciliation_index[
            candidate_record_id
        ]

        product_id = normalize_identifier(
            candidate.get(
                "tcgplayer_product_id"
            )
        )

        existing = existing_index.get(
            product_id
        )

        reconciliation_status = clean_text(
            reconciled.get(
                "reconciliation_status"
            )
        )

        type_alignment = clean_text(
            reconciled.get(
                "type_alignment"
            )
        )

        product_class = clean_text(
            candidate.get(
                "candidate_class"
            )
        )

        product_type = clean_text(
            candidate.get(
                "candidate_product_type"
            )
        )

        product_name = clean_text(
            candidate.get(
                "product_name"
            )
        )

        set_name = clean_text(
            candidate.get(
                "group_name"
            )
        )

        existing_product_id = (
            first_available(
                existing,
                (
                    "investment_product_id",
                ),
            )
        )

        existing_product_type = (
            first_available(
                existing,
                (
                    "investment_product_type",
                ),
            )
        )

        existing_approval_status = (
            first_available(
                existing,
                (
                    "approval_status",
                ),
            )
        )

        existing_approval_method = (
            first_available(
                existing,
                (
                    "approval_method",
                ),
            )
        )

        existing_notes = (
            first_available(
                existing,
                (
                    "notes",
                ),
            )
        )

        identity_status = (
            determine_identity_status(
                reconciliation_status
            )
        )

        (
            identity_review_status,
            identity_review_reason,
        ) = determine_review_status(
            reconciliation_status,
            type_alignment,
        )

        (
            eligibility_status,
            approval_status,
            scoring_status,
        ) = determine_investment_statuses(
            reconciliation_status=(
                reconciliation_status
            ),
            existing_approval_status=(
                existing_approval_status
            ),
            candidate_eligibility_status=(
                clean_text(
                    candidate.get(
                        "eligibility_status"
                    )
                )
            ),
            candidate_scoring_status=(
                clean_text(
                    candidate.get(
                        "scoring_status"
                    )
                )
            ),
        )

        registry_relationship = (
            "existing_registry_exact_id"
            if reconciliation_status
            == "exact_id_match"
            else "new_candidate_not_in_registry"
        )

        source_lineage = json.dumps(
            {
                "candidate_source": (
                    clean_text(
                        candidate.get(
                            "source_name"
                        )
                    )
                    or "tcgcsv"
                ),
                "candidate_record_id": (
                    candidate_record_id
                ),
                "tcgplayer_product_id": (
                    product_id
                ),
                "existing_registry_record_id": (
                    existing_product_id
                ),
                "reconciliation_status": (
                    reconciliation_status
                ),
                "type_alignment": (
                    type_alignment
                ),
            },
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        )

        output_rows.append(
            {
                "canonical_product_id": (
                    stable_canonical_id(
                        product_id,
                        candidate_record_id,
                    )
                ),
                "canonical_registry_version": (
                    REGISTRY_VERSION
                ),
                "canonical_identity_status": (
                    identity_status
                ),
                "canonical_set_name": (
                    set_name
                ),
                "canonical_product_name": (
                    product_name
                ),
                "canonical_product_class": (
                    product_class
                ),
                "canonical_product_family": (
                    infer_product_family(
                        product_class,
                        product_type,
                    )
                ),
                "canonical_product_type": (
                    product_type
                ),
                "canonical_packaging_level": (
                    infer_packaging_level(
                        product_class,
                        product_type,
                        product_name,
                    )
                ),
                "language": infer_language(
                    product_name
                ),
                "foil_variant": (
                    infer_foil_variant(
                        product_name
                    )
                ),
                "edition_variant": (
                    infer_edition_variant(
                        product_name
                    )
                ),
                "tcgplayer_product_id": (
                    product_id
                ),
                "tcgcsv_category_id": (
                    normalize_identifier(
                        candidate.get(
                            "tcgcsv_category_id"
                        )
                    )
                ),
                "tcgcsv_group_id": (
                    normalize_identifier(
                        candidate.get(
                            "tcgcsv_group_id"
                        )
                    )
                ),
                "candidate_record_id": (
                    candidate_record_id
                ),
                "source_system": (
                    clean_text(
                        candidate.get(
                            "source_name"
                        )
                    )
                    or "tcgcsv"
                ),
                "source_snapshot_record_id": (
                    clean_text(
                        candidate.get(
                            "source_snapshot_record_id"
                        )
                    )
                ),
                "registry_relationship": (
                    registry_relationship
                ),
                "reconciliation_status": (
                    reconciliation_status
                ),
                "type_alignment": (
                    type_alignment
                ),
                "existing_investment_product_id": (
                    existing_product_id
                ),
                "existing_product_type": (
                    existing_product_type
                ),
                "existing_approval_status": (
                    existing_approval_status
                ),
                "existing_approval_method": (
                    existing_approval_method
                ),
                "existing_registry_notes": (
                    existing_notes
                ),
                "identity_review_status": (
                    identity_review_status
                ),
                "identity_review_reason": (
                    identity_review_reason
                ),
                "investment_eligibility_status": (
                    eligibility_status
                ),
                "investment_approval_status": (
                    approval_status
                ),
                "scoring_status": (
                    scoring_status
                ),
                "source_lineage": (
                    source_lineage
                ),
            }
        )

    canonical = pd.DataFrame(
        output_rows,
        columns=CANONICAL_COLUMNS,
    )

    return canonical.sort_values(
        [
            "canonical_product_class",
            "canonical_product_family",
            "canonical_product_type",
            "canonical_set_name",
            "canonical_product_name",
            "tcgplayer_product_id",
        ],
        kind="stable",
    ).reset_index(drop=True)


def write_outputs(
    *,
    canonical: pd.DataFrame,
    candidate_path: Path,
    reconciliation_path: Path,
    existing_registry_path: Path,
) -> dict[str, Any]:
    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    VALIDATION_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    canonical_path = (
        OUTPUT_ROOT
        / "canonical_mtg_product_registry_2026-07-22.csv"
    )

    new_path = (
        VALIDATION_ROOT
        / "canonical_registry_new_products_2026-07-22.csv"
    )


    identity_review_path = (
        VALIDATION_ROOT
        / "canonical_registry_identity_review_queue_2026-07-22.csv"
    )

    summary_path = (
        VALIDATION_ROOT
        / "canonical_registry_summary_2026-07-22.json"
    )

    canonical.to_csv(
        canonical_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    new_products = canonical[
        canonical[
            "canonical_identity_status"
        ].eq("new_source_identity")
    ].copy()

    existing_products = canonical[
        canonical[
            "canonical_identity_status"
        ].eq(
            "established_existing_identity"
        )
    ].copy()

    identity_review = canonical[
        canonical[
            "identity_review_status"
        ].eq("identity_review_required")
    ].copy()

    new_products.to_csv(
        new_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )


    identity_review.to_csv(
        identity_review_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    def counts(
        column: str,
    ) -> dict[str, int]:
        return {
            str(key): int(value)
            for key, value in (
                canonical[column]
                .value_counts(
                    dropna=False
                )
                .to_dict()
                .items()
            )
        }

    duplicate_canonical_ids = int(
        canonical[
            "canonical_product_id"
        ].duplicated(
            keep=False
        ).sum()
    )

    duplicate_tcgplayer_ids = int(
        canonical[
            "tcgplayer_product_id"
        ].duplicated(
            keep=False
        ).sum()
    )

    summary = {
        "schema_version": (
            REGISTRY_VERSION
        ),
        "generated_at_utc": utc_now(),
        "canonical_registry_status": (
            "IDENTITY_REGISTRY_COMPLETE"
        ),
        "canonical_registry_rows": int(
            len(canonical)
        ),
        "unique_canonical_product_ids": int(
            canonical[
                "canonical_product_id"
            ].nunique()
        ),
        "unique_tcgplayer_product_ids": int(
            canonical[
                "tcgplayer_product_id"
            ].nunique()
        ),
        "duplicate_canonical_id_rows": (
            duplicate_canonical_ids
        ),
        "duplicate_tcgplayer_id_rows": (
            duplicate_tcgplayer_ids
        ),
        "established_existing_identity_rows": int(
            len(existing_products)
        ),
        "new_source_identity_rows": int(
            len(new_products)
        ),
        "identity_review_rows": int(
            len(identity_review)
        ),
        "canonical_product_class_counts": (
            counts(
                "canonical_product_class"
            )
        ),
        "canonical_product_family_counts": (
            counts(
                "canonical_product_family"
            )
        ),
        "canonical_product_type_counts": (
            counts(
                "canonical_product_type"
            )
        ),
        "canonical_packaging_level_counts": (
            counts(
                "canonical_packaging_level"
            )
        ),
        "investment_approval_status_counts": (
            counts(
                "investment_approval_status"
            )
        ),
        "input_files": {
            "candidate_universe": str(
                candidate_path
            ),
            "reconciliation": str(
                reconciliation_path
            ),
            "existing_registry": str(
                existing_registry_path
            ),
        },
        "output_files": {
            "canonical_registry": str(
                canonical_path
            ),
            "new_products": str(
                new_path
            ),

            "identity_review_queue": str(
                identity_review_path
            ),
        },
        "production_registry_changed": False,
        "database_changed": False,
        "eligibility_recalculated": False,
        "scoring_applied": False,
        "recommendations_created": False,
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
        "Phase 10.5R.1C.1 "
        "Canonical MTG Product Registry"
    )
    print("=" * 76)
    print(
        f"Canonical rows: "
        f"{len(canonical)}"
    )
    print(
        "Established existing identities: "
        f"{len(existing_products)}"
    )
    print(
        f"New source identities: "
        f"{len(new_products)}"
    )
    print(
        f"Identity review rows: "
        f"{len(identity_review)}"
    )
    print(
        "Duplicate canonical IDs: "
        f"{duplicate_canonical_ids}"
    )
    print(
        "Duplicate TCGplayer IDs: "
        f"{duplicate_tcgplayer_ids}"
    )
    print()
    print("Product classes:")

    for name, count in sorted(
        summary[
            "canonical_product_class_counts"
        ].items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        print(
            f"  {name}: {count}"
        )

    print()
    print(
        f"Canonical registry: "
        f"{canonical_path}"
    )
    print(
        f"Summary: {summary_path}"
    )
    print()
    print(
        "PHASE 10.5R.1C.1 "
        "CANONICAL REGISTRY BUILD: PASS"
    )
    print(
        "Production registry: UNCHANGED"
    )
    print(
        "Eligibility: NOT RECALCULATED"
    )
    print(
        "Scoring: NOT APPLIED"
    )

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--candidates",
        type=Path,
        default=DEFAULT_CANDIDATE_PATH,
    )

    parser.add_argument(
        "--reconciliation",
        type=Path,
        default=DEFAULT_RECONCILIATION_PATH,
    )

    parser.add_argument(
        "--existing-registry",
        type=Path,
        default=DEFAULT_EXISTING_REGISTRY_PATH,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    candidate_path = (
        args.candidates.resolve()
    )

    reconciliation_path = (
        args.reconciliation.resolve()
    )

    existing_registry_path = (
        args.existing_registry.resolve()
    )

    for label, path in (
        (
            "Candidate universe",
            candidate_path,
        ),
        (
            "Reconciliation",
            reconciliation_path,
        ),
        (
            "Existing registry",
            existing_registry_path,
        ),
    ):
        if not path.is_file():
            raise FileNotFoundError(
                f"{label} not found: {path}"
            )

    candidates = pd.read_csv(
        candidate_path,
        low_memory=False,
    )

    reconciliation = pd.read_csv(
        reconciliation_path,
        low_memory=False,
    )

    existing_registry = pd.read_csv(
        existing_registry_path,
        low_memory=False,
    )

    if len(candidates) != 5239:
        raise RuntimeError(
            "Expected 5,239 candidate rows; "
            f"found {len(candidates)}."
        )

    if len(reconciliation) != 5239:
        raise RuntimeError(
            "Expected 5,239 reconciliation rows; "
            f"found {len(reconciliation)}."
        )

    if len(existing_registry) != 4675:
        raise RuntimeError(
            "Expected 4,675 existing registry rows; "
            f"found {len(existing_registry)}."
        )

    canonical = build_canonical_registry(
        candidates=candidates,
        reconciliation=reconciliation,
        existing_registry=existing_registry,
    )

    if len(canonical) != 5239:
        raise RuntimeError(
            "Canonical registry row count "
            "does not equal candidate count."
        )

    if canonical[
        "canonical_product_id"
    ].duplicated().any():
        raise RuntimeError(
            "Canonical product identifiers "
            "are not unique."
        )

    if canonical[
        "tcgplayer_product_id"
    ].duplicated().any():
        raise RuntimeError(
            "TCGplayer product identifiers "
            "are not unique."
        )

    write_outputs(
        canonical=canonical,
        candidate_path=candidate_path,
        reconciliation_path=(
            reconciliation_path
        ),
        existing_registry_path=(
            existing_registry_path
        ),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())