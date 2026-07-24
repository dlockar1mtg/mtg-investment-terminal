from __future__ import annotations

from collections import Counter
from pathlib import Path
import json
import re

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

PRODUCT_REGISTRY = (
    ROOT
    / "data"
    / "product_master"
    / "investment_products.csv"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "premium_universe"
)


def normalize_text(value: object) -> str:
    if pd.isna(value):
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value).strip(),
    )


def contains_any(
    value: object,
    terms: tuple[str, ...],
) -> bool:
    normalized = normalize_text(value).casefold()

    return any(
        term.casefold() in normalized
        for term in terms
    )


def main() -> int:
    if not PRODUCT_REGISTRY.is_file():
        raise FileNotFoundError(
            f"Product registry not found: "
            f"{PRODUCT_REGISTRY}"
        )

    frame = pd.read_csv(
        PRODUCT_REGISTRY,
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
        required_columns
        - set(frame.columns)
    )

    if missing:
        raise ValueError(
            "Product registry is missing required "
            "columns: "
            + ", ".join(missing)
        )

    approved = frame.loc[
        frame["approval_status"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.casefold()
        .eq("approved")
    ].copy()

    approved["combined_name"] = (
        approved["box_name"]
        .fillna("")
        .astype(str)
        + " | "
        + approved["approved_product_name"]
        .fillna("")
        .astype(str)
    )

    collector_terms = (
        "collector booster display",
        "collector booster box",
        "collector display",
    )

    draft_terms = (
        "draft booster",
        "draft display",
    )

    play_terms = (
        "play booster",
        "play display",
    )

    set_terms = (
        "set booster",
        "set display",
    )

    booster_terms = (
        "booster box",
        "booster display",
    )

    case_terms = (
        "case of",
        "booster case",
        "display case",
        "sealed case",
        "6-box case",
        "6 box case",
        "12-box case",
        "12 box case",
    )

    excluded_terms = (
        "bundle",
        "gift bundle",
        "commander deck",
        "deck",
        "prerelease",
        "pre-release",
        "theme booster",
        "jumpstart",
        "sample pack",
        "single booster",
        "booster pack",
        "fat pack",
        "starter kit",
        "accessory",
        "sleeves",
        "playmat",
    )

    approved["collector_name_candidate"] = (
        approved["combined_name"].map(
            lambda value: contains_any(
                value,
                collector_terms,
            )
        )
    )

    approved["draft_candidate"] = (
        approved["combined_name"].map(
            lambda value: contains_any(
                value,
                draft_terms,
            )
        )
    )

    approved["play_candidate"] = (
        approved["combined_name"].map(
            lambda value: contains_any(
                value,
                play_terms,
            )
        )
    )

    approved["set_booster_candidate"] = (
        approved["combined_name"].map(
            lambda value: contains_any(
                value,
                set_terms,
            )
        )
    )

    approved["generic_booster_candidate"] = (
        approved["combined_name"].map(
            lambda value: contains_any(
                value,
                booster_terms,
            )
        )
    )

    approved["case_candidate"] = (
        approved["combined_name"].map(
            lambda value: contains_any(
                value,
                case_terms,
            )
        )
    )

    approved["explicit_exclusion_candidate"] = (
        approved["combined_name"].map(
            lambda value: contains_any(
                value,
                excluded_terms,
            )
        )
    )

    approved["secret_lair_name_candidate"] = (
        approved["combined_name"]
        .fillna("")
        .astype(str)
        .str.casefold()
        .str.contains(
            "secret lair",
            regex=False,
        )
    )

    approved["release_date_available"] = False
    approved["release_year_available"] = False
    approved["secret_lair_card_count_available"] = False

    type_counts = (
        approved[
            "investment_product_type"
        ]
        .fillna("(blank)")
        .astype(str)
        .str.strip()
        .value_counts(dropna=False)
        .rename_axis("investment_product_type")
        .reset_index(name="product_count")
    )

    audit_columns = [
        "investment_product_id",
        "set_name",
        "box_name",
        "approved_tcgplayer_product_id",
        "approved_product_name",
        "investment_product_type",
        "approval_status",
        "approval_method",
        "notes",
        "collector_name_candidate",
        "generic_booster_candidate",
        "draft_candidate",
        "play_candidate",
        "set_booster_candidate",
        "case_candidate",
        "explicit_exclusion_candidate",
        "secret_lair_name_candidate",
        "release_date_available",
        "release_year_available",
        "secret_lair_card_count_available",
    ]

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit_path = (
        OUTPUT_ROOT
        / "premium_universe_candidate_audit.csv"
    )

    type_path = (
        OUTPUT_ROOT
        / "investment_product_type_counts.csv"
    )

    summary_path = (
        OUTPUT_ROOT
        / "premium_universe_audit_summary.json"
    )

    approved.loc[
        :,
        audit_columns,
    ].to_csv(
        audit_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    type_counts.to_csv(
        type_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    duplicate_ids = int(
        approved[
            "investment_product_id"
        ].duplicated(keep=False).sum()
    )

    summary = {
        "source_file": str(PRODUCT_REGISTRY),
        "source_rows": int(len(frame)),
        "approved_rows": int(len(approved)),
        "unique_approved_investment_product_ids": int(
            approved[
                "investment_product_id"
            ].nunique()
        ),
        "duplicate_approved_id_rows": duplicate_ids,
        "investment_product_type_count": int(
            approved[
                "investment_product_type"
            ].nunique(dropna=False)
        ),
        "collector_name_candidates": int(
            approved[
                "collector_name_candidate"
            ].sum()
        ),
        "generic_booster_candidates": int(
            approved[
                "generic_booster_candidate"
            ].sum()
        ),
        "draft_candidates": int(
            approved[
                "draft_candidate"
            ].sum()
        ),
        "play_candidates": int(
            approved[
                "play_candidate"
            ].sum()
        ),
        "set_booster_candidates": int(
            approved[
                "set_booster_candidate"
            ].sum()
        ),
        "case_candidates": int(
            approved[
                "case_candidate"
            ].sum()
        ),
        "explicit_exclusion_candidates": int(
            approved[
                "explicit_exclusion_candidate"
            ].sum()
        ),
        "secret_lair_name_candidates": int(
            approved[
                "secret_lair_name_candidate"
            ].sum()
        ),
        "release_date_coverage": 0,
        "release_year_coverage": 0,
        "secret_lair_card_count_coverage": 0,
        "classification_status": (
            "AUDIT_ONLY_NOT_CERTIFIED"
        ),
        "known_metadata_gaps": [
            "The product registry has no release-date field.",
            "The product registry has no release-year field.",
            "The product registry has no Secret Lair card-count field.",
            (
                "Legacy booster eligibility cannot be certified "
                "without release-date evidence."
            ),
            (
                "Secret Lair multi-card eligibility cannot be "
                "certified without a populated Secret Lair registry."
            ),
        ],
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

    print("=" * 72)
    print("Phase 10.5R.1 Premium Universe Audit")
    print("=" * 72)
    print(f"Source rows: {len(frame)}")
    print(f"Approved rows: {len(approved)}")
    print(
        "Unique approved IDs: "
        f"{summary['unique_approved_investment_product_ids']}"
    )
    print(
        "Duplicate approved-ID rows: "
        f"{duplicate_ids}"
    )
    print(
        "Distinct product types: "
        f"{summary['investment_product_type_count']}"
    )
    print()
    print(
        "Collector name candidates: "
        f"{summary['collector_name_candidates']}"
    )
    print(
        "Generic booster candidates: "
        f"{summary['generic_booster_candidates']}"
    )
    print(
        "Draft candidates: "
        f"{summary['draft_candidates']}"
    )
    print(
        "Play candidates: "
        f"{summary['play_candidates']}"
    )
    print(
        "Set Booster candidates: "
        f"{summary['set_booster_candidates']}"
    )
    print(
        "Case candidates: "
        f"{summary['case_candidates']}"
    )
    print(
        "Secret Lair name candidates: "
        f"{summary['secret_lair_name_candidates']}"
    )
    print()
    print(f"Candidate audit: {audit_path}")
    print(f"Type counts: {type_path}")
    print(f"Summary: {summary_path}")
    print()
    print(
        "Classification status: "
        "AUDIT ONLY — NOT CERTIFIED"
    )
    print(
        "PHASE 10.5R.1 PREMIUM UNIVERSE AUDIT: PASS"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())