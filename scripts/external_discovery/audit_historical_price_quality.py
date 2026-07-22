from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

PRICE_ENRICHMENT_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_tcgcsv_price_enrichment"
    / "historical_tcgcsv_current_price_enrichment_2026-07-22.csv"
)

AUTHORITATIVE_QUEUE_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "premium_universe_eligibility"
    / "historical_booster_review_2026-07-22.csv"
)

GOVERNED_COHORT_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_cohort_policy"
    / "historical_governed_candidate_cohorts_2026-07-22.csv"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_price_quality"
)

SCHEMA_VERSION = "10.5R.1F.5C.1"

EXPECTED_ROWS = 140
EXPECTED_DRAFT_ROWS = 9
EXPECTED_STRUCTURAL_EXCLUSION_ROWS = 0


PRICE_QUALITY_COLUMNS = [
    "canonical_product_id",
    "canonical_product_name",
    "tcgplayer_product_id",
    "canonical_product_type",
    "market_price",
    "low_price",
    "mid_price",
    "high_price",
    "direct_low_price",
    "current_price_candidate",
    "price_source_type",
    "has_market_price",
    "has_candidate_price",
    "price_evidence_state",
    "historical_eligibility_decision",
    "scoring_allowed",
    "universal_investable_allowed",
]

SPREAD_COLUMNS = [
    "canonical_product_id",
    "canonical_product_name",
    "market_price",
    "low_price",
    "mid_price",
    "low_to_market_ratio",
    "mid_to_market_ratio",
    "extreme_spread",
]

DRAFT_COLUMNS = [
    "canonical_product_id",
    "canonical_product_name",
    "canonical_product_type",
    "governed_candidate_cohort",
    "cohort_reason",
    "specialty_basis",
    "current_price_candidate",
    "market_price",
    "price_evidence_state",
    "preliminary_specialty_indicator",
    "commander_policy_review",
    "historical_eligibility_decision",
    "scoring_allowed",
    "universal_investable_allowed",
]

STRUCTURAL_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_set_name",
    "canonical_product_name",
    "canonical_product_class",
    "canonical_product_family",
    "canonical_product_type",
    "canonical_packaging_level",
    "structural_eligibility_state",
    "structural_eligibility_reason",
    "historical_eligibility_decision",
    "scoring_allowed",
    "universal_investable_allowed",
]


SPECIALTY_DRAFT_PATTERNS = (
    "commander",
    "masters",
    "remastered",
    "modern horizons",
    "mystery booster",
    "convention edition",
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
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


def parse_bool(value: object) -> bool:
    return clean_text(value).casefold() in {
        "true",
        "1",
        "yes",
    }


def numeric_or_none(
    value: object,
) -> float | None:
    cleaned = clean_text(value)

    if not cleaned:
        return None

    try:
        return float(cleaned)
    except ValueError:
        return None


def output_number(
    value: float | None,
) -> float | str:
    if value is None:
        return ""

    return value


def price_source_type(
    row: pd.Series,
) -> str:
    market = numeric_or_none(
        row.get("market_price")
    )

    candidate = numeric_or_none(
        row.get("current_price_candidate")
    )

    mid = numeric_or_none(
        row.get("mid_price")
    )

    low = numeric_or_none(
        row.get("low_price")
    )

    if market is not None:
        return "market_price"

    if candidate is None:
        return "no_price"

    if (
        mid is not None
        and abs(candidate - mid) < 0.000001
    ):
        return "mid_price_fallback"

    if (
        low is not None
        and abs(candidate - low) < 0.000001
    ):
        return "low_price_fallback"

    return "candidate_price"


def safe_ratio(
    numerator: float | None,
    denominator: float | None,
) -> float | None:
    if (
        numerator is None
        or denominator is None
        or denominator == 0
    ):
        return None

    return numerator / denominator


def is_specialty_draft(
    product_name: object,
) -> bool:
    normalized = clean_text(
        product_name
    ).casefold()

    return any(
        pattern in normalized
        for pattern in SPECIALTY_DRAFT_PATTERNS
    )


def write_csv(
    frame: pd.DataFrame,
    path: Path,
) -> None:
    frame.to_csv(
        path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )


def main() -> int:
    if not PRICE_ENRICHMENT_PATH.is_file():
        raise FileNotFoundError(
            "Corrected historical price enrichment "
            f"not found: {PRICE_ENRICHMENT_PATH}"
        )

    if not AUTHORITATIVE_QUEUE_PATH.is_file():
        raise FileNotFoundError(
            "Authoritative historical queue not found: "
            f"{AUTHORITATIVE_QUEUE_PATH}"
        )

    if not GOVERNED_COHORT_PATH.is_file():
        raise FileNotFoundError(
            "Governed historical cohort file not found: "
            f"{GOVERNED_COHORT_PATH}"
        )

    pricing = pd.read_csv(
        PRICE_ENRICHMENT_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    authoritative = pd.read_csv(
        AUTHORITATIVE_QUEUE_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    cohorts = pd.read_csv(
        GOVERNED_COHORT_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    if len(pricing) != EXPECTED_ROWS:
        raise RuntimeError(
            "Expected 140 corrected pricing rows; "
            f"found {len(pricing)}."
        )

    if len(authoritative) != EXPECTED_ROWS:
        raise RuntimeError(
            "Expected 140 authoritative historical rows; "
            f"found {len(authoritative)}."
        )

    if len(cohorts) != EXPECTED_ROWS:
        raise RuntimeError(
            "Expected 140 governed cohort rows; "
            f"found {len(cohorts)}."
        )

    if pricing[
        "canonical_product_id"
    ].duplicated().any():
        raise RuntimeError(
            "Pricing enrichment contains duplicate "
            "canonical product IDs."
        )

    if authoritative[
        "canonical_product_id"
    ].duplicated().any():
        raise RuntimeError(
            "Authoritative queue contains duplicate "
            "canonical product IDs."
        )

    if cohorts[
        "canonical_product_id"
    ].duplicated().any():
        raise RuntimeError(
            "Governed cohorts contain duplicate "
            "canonical product IDs."
        )

    pricing_ids = set(
        pricing[
            "canonical_product_id"
        ]
        .astype(str)
        .str.strip()
    )

    authoritative_ids = set(
        authoritative[
            "canonical_product_id"
        ]
        .astype(str)
        .str.strip()
    )

    cohort_ids = set(
        cohorts[
            "canonical_product_id"
        ]
        .astype(str)
        .str.strip()
    )

    if cohort_ids != authoritative_ids:
        missing = sorted(
            authoritative_ids - cohort_ids
        )

        obsolete = sorted(
            cohort_ids - authoritative_ids
        )

        raise RuntimeError(
            "Governed-cohort identity boundary mismatch. "
            f"Missing={missing}; obsolete={obsolete}."
        )

    if pricing_ids != authoritative_ids:
        missing = sorted(
            authoritative_ids - pricing_ids
        )

        obsolete = sorted(
            pricing_ids - authoritative_ids
        )

        raise RuntimeError(
            "Price-quality identity boundary mismatch. "
            f"Missing={missing}; obsolete={obsolete}."
        )

    identity_columns = [
        "canonical_product_id",
        "canonical_set_name",
        "canonical_product_name",
        "canonical_product_class",
        "canonical_product_family",
        "canonical_product_type",
        "canonical_packaging_level",
        "structural_eligibility_state",
        "structural_eligibility_reason",
    ]

    identity = authoritative[
        identity_columns
    ].copy()

    cohort_columns = [
        "canonical_product_id",
        "governed_candidate_cohort",
        "cohort_reason",
        "specialty_basis",
    ]

    governed = cohorts[
        cohort_columns
    ].copy()

    merged = pricing.merge(
        identity,
        on=[
            "canonical_product_id",
            "canonical_product_name",
        ],
        how="left",
        validate="one_to_one",
    )

    merged = merged.merge(
        governed,
        on="canonical_product_id",
        how="left",
        validate="one_to_one",
    )

    if len(merged) != EXPECTED_ROWS:
        raise RuntimeError(
            "Merged price-quality row count mismatch."
        )

    if merged[
        "canonical_product_type"
    ].astype(str).str.strip().eq("").any():
        raise RuntimeError(
            "At least one pricing row did not match "
            "the authoritative queue."
        )

    if merged[
        "governed_candidate_cohort"
    ].astype(str).str.strip().eq("").any():
        raise RuntimeError(
            "At least one pricing row did not match "
            "the governed cohort artifact."
        )

    quality_rows: list[
        dict[str, Any]
    ] = []

    spread_rows: list[
        dict[str, Any]
    ] = []

    draft_rows: list[
        dict[str, Any]
    ] = []

    for _, row in merged.iterrows():
        market = numeric_or_none(
            row.get("market_price")
        )

        low = numeric_or_none(
            row.get("low_price")
        )

        mid = numeric_or_none(
            row.get("mid_price")
        )

        candidate = numeric_or_none(
            row.get("current_price_candidate")
        )

        low_ratio = safe_ratio(
            low,
            market,
        )

        mid_ratio = safe_ratio(
            mid,
            market,
        )

        extreme_spread = any(
            ratio is not None
            and (
                ratio >= 2.0
                or ratio <= 0.5
            )
            for ratio in (
                low_ratio,
                mid_ratio,
            )
        )

        quality_rows.append(
            {
                "canonical_product_id": clean_text(
                    row.get("canonical_product_id")
                ),
                "canonical_product_name": clean_text(
                    row.get("canonical_product_name")
                ),
                "tcgplayer_product_id": clean_text(
                    row.get("tcgplayer_product_id")
                ),
                "canonical_product_type": clean_text(
                    row.get("canonical_product_type")
                ),
                "market_price": output_number(
                    market
                ),
                "low_price": output_number(
                    low
                ),
                "mid_price": output_number(
                    mid
                ),
                "high_price": output_number(
                    numeric_or_none(
                        row.get("high_price")
                    )
                ),
                "direct_low_price": output_number(
                    numeric_or_none(
                        row.get("direct_low_price")
                    )
                ),
                "current_price_candidate": (
                    output_number(candidate)
                ),
                "price_source_type": (
                    price_source_type(row)
                ),
                "has_market_price": (
                    market is not None
                ),
                "has_candidate_price": (
                    candidate is not None
                ),
                "price_evidence_state": clean_text(
                    row.get(
                        "price_evidence_state"
                    )
                ),
                "historical_eligibility_decision": (
                    "not_decided"
                ),
                "scoring_allowed": False,
                "universal_investable_allowed": False,
            }
        )

        spread_rows.append(
            {
                "canonical_product_id": clean_text(
                    row.get("canonical_product_id")
                ),
                "canonical_product_name": clean_text(
                    row.get("canonical_product_name")
                ),
                "market_price": output_number(
                    market
                ),
                "low_price": output_number(
                    low
                ),
                "mid_price": output_number(
                    mid
                ),
                "low_to_market_ratio": (
                    ""
                    if low_ratio is None
                    else f"{low_ratio:.4f}"
                ),
                "mid_to_market_ratio": (
                    ""
                    if mid_ratio is None
                    else f"{mid_ratio:.4f}"
                ),
                "extreme_spread": extreme_spread,
            }
        )

        if (
            clean_text(
                row.get("canonical_product_type")
            )
            == "draft_booster_display"
        ):
            draft_rows.append(
                {
                    "canonical_product_id": clean_text(
                        row.get(
                            "canonical_product_id"
                        )
                    ),
                    "canonical_product_name": clean_text(
                        row.get(
                            "canonical_product_name"
                        )
                    ),
                    "canonical_product_type": (
                        "draft_booster_display"
                    ),
                    "governed_candidate_cohort": clean_text(
                        row.get(
                            "governed_candidate_cohort"
                        )
                    ),
                    "cohort_reason": clean_text(
                        row.get("cohort_reason")
                    ),
                    "specialty_basis": clean_text(
                        row.get("specialty_basis")
                    ),
                    "current_price_candidate": (
                        output_number(candidate)
                    ),
                    "market_price": output_number(
                        market
                    ),
                    "price_evidence_state": clean_text(
                        row.get(
                            "price_evidence_state"
                        )
                    ),
                    "preliminary_specialty_indicator": (
                        clean_text(
                            row.get(
                                "governed_candidate_cohort"
                            )
                        )
                        == "explicit_specialty_draft_review"
                    ),
                    "commander_policy_review": (
                        clean_text(
                            row.get(
                                "governed_candidate_cohort"
                            )
                        )
                        == "commander_draft_policy_review"
                    ),
                    "historical_eligibility_decision": (
                        "not_decided"
                    ),
                    "scoring_allowed": False,
                    "universal_investable_allowed": False,
                }
            )

    quality = (
        pd.DataFrame(
            quality_rows,
            columns=PRICE_QUALITY_COLUMNS,
        )
        .sort_values(
            [
                "canonical_product_name",
                "canonical_product_id",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    spreads = (
        pd.DataFrame(
            spread_rows,
            columns=SPREAD_COLUMNS,
        )
        .sort_values(
            [
                "extreme_spread",
                "canonical_product_name",
                "canonical_product_id",
            ],
            ascending=[
                False,
                True,
                True,
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    drafts = (
        pd.DataFrame(
            draft_rows,
            columns=DRAFT_COLUMNS,
        )
        .sort_values(
            [
                "governed_candidate_cohort",
                "canonical_product_name",
                "canonical_product_id",
            ],
            ascending=[
                True,
                True,
                True,
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    structural_exclusions = (
        authoritative[
            ~authoritative[
                "canonical_product_id"
            ]
            .astype(str)
            .str.strip()
            .isin(pricing_ids)
        ]
        .copy()
    )

    structural_output = pd.DataFrame(
        columns=STRUCTURAL_COLUMNS
    )

    if not structural_exclusions.empty:
        structural_output = (
            structural_exclusions[
                [
                    column
                    for column in STRUCTURAL_COLUMNS
                    if column
                    in structural_exclusions.columns
                ]
            ]
            .copy()
        )

        for column in STRUCTURAL_COLUMNS:
            if column not in structural_output.columns:
                if column == "historical_eligibility_decision":
                    structural_output[column] = (
                        "not_decided"
                    )
                elif column in {
                    "scoring_allowed",
                    "universal_investable_allowed",
                }:
                    structural_output[column] = False
                else:
                    structural_output[column] = ""

        structural_output = structural_output[
            STRUCTURAL_COLUMNS
        ]

    if len(quality) != EXPECTED_ROWS:
        raise RuntimeError(
            "Price-quality output must contain 140 rows."
        )

    if len(spreads) != EXPECTED_ROWS:
        raise RuntimeError(
            "Price-spread output must contain 140 rows."
        )

    if len(drafts) != EXPECTED_DRAFT_ROWS:
        raise RuntimeError(
            "Expected 9 governed Draft products; "
            f"found {len(drafts)}."
        )

    draft_cohort_counts = {
        str(key): int(value)
        for key, value in (
            drafts[
                "governed_candidate_cohort"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    expected_draft_cohort_counts = {
        "explicit_specialty_draft_review": 7,
        "commander_draft_policy_review": 2,
    }

    if (
        draft_cohort_counts
        != expected_draft_cohort_counts
    ):
        raise RuntimeError(
            "Unexpected governed Draft cohort counts. "
            f"Expected {expected_draft_cohort_counts}; "
            f"found {draft_cohort_counts}."
        )

    if (
        len(structural_output)
        != EXPECTED_STRUCTURAL_EXCLUSION_ROWS
    ):
        raise RuntimeError(
            "Expected zero structural exclusions in "
            "the authoritative price-quality population; "
            f"found {len(structural_output)}."
        )

    if not quality[
        "historical_eligibility_decision"
    ].eq("not_decided").all():
        raise RuntimeError(
            "Price-quality audit changed historical "
            "eligibility decisions."
        )

    if quality[
        "scoring_allowed"
    ].apply(parse_bool).any():
        raise RuntimeError(
            "Price-quality audit enabled scoring."
        )

    if quality[
        "universal_investable_allowed"
    ].apply(parse_bool).any():
        raise RuntimeError(
            "Price-quality audit enabled Universal "
            "investability."
        )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    quality_path = (
        OUTPUT_ROOT
        / "historical_price_quality_2026-07-22.csv"
    )

    spread_path = (
        OUTPUT_ROOT
        / "historical_price_spread_audit_2026-07-22.csv"
    )

    draft_path = (
        OUTPUT_ROOT
        / "historical_draft_booster_review_2026-07-22.csv"
    )

    structural_path = (
        OUTPUT_ROOT
        / "historical_structural_exclusion_candidates_2026-07-22.csv"
    )

    summary_path = (
        OUTPUT_ROOT
        / "historical_price_quality_summary_2026-07-22.json"
    )

    write_csv(
        quality,
        quality_path,
    )

    write_csv(
        spreads,
        spread_path,
    )

    write_csv(
        drafts,
        draft_path,
    )

    write_csv(
        structural_output,
        structural_path,
    )

    source_counts = {
        str(key): int(value)
        for key, value in (
            quality[
                "price_source_type"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    evidence_counts = {
        str(key): int(value)
        for key, value in (
            quality[
                "price_evidence_state"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "audit_status": "PASS",
        "authoritative_input_rows": int(
            len(authoritative)
        ),
        "price_enrichment_input_rows": int(
            len(pricing)
        ),
        "governed_cohort_input_rows": int(
            len(cohorts)
        ),
        "price_quality_rows": int(
            len(quality)
        ),
        "price_spread_rows": int(
            len(spreads)
        ),
        "draft_review_rows": int(
            len(drafts)
        ),
        "structural_exclusion_candidate_rows": int(
            len(structural_output)
        ),
        "rows_with_market_price": int(
            quality[
                "has_market_price"
            ].apply(parse_bool).sum()
        ),
        "rows_with_candidate_price": int(
            quality[
                "has_candidate_price"
            ].apply(parse_bool).sum()
        ),
        "rows_without_candidate_price": int(
            (~quality[
                "has_candidate_price"
            ].apply(parse_bool)).sum()
        ),
        "extreme_spread_rows": int(
            spreads[
                "extreme_spread"
            ].apply(parse_bool).sum()
        ),
        "explicit_specialty_draft_rows": int(
            drafts[
                "governed_candidate_cohort"
            ]
            .eq(
                "explicit_specialty_draft_review"
            )
            .sum()
        ),
        "commander_draft_policy_review_rows": int(
            drafts[
                "governed_candidate_cohort"
            ]
            .eq(
                "commander_draft_policy_review"
            )
            .sum()
        ),
        "draft_cohort_counts": (
            draft_cohort_counts
        ),
        "price_source_type_counts": source_counts,
        "price_evidence_state_counts": evidence_counts,
        "historical_eligibility_assigned": False,
        "scoring_allowed_rows": 0,
        "universal_investable_allowed_rows": 0,
        "production_registry_changed": False,
        "universal_database_changed": False,
        "output_files": {
            "price_quality": str(
                quality_path
            ),
            "price_spread_audit": str(
                spread_path
            ),
            "draft_review": str(
                draft_path
            ),
            "structural_exclusion_candidates": str(
                structural_path
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
        "Phase 10.5R.1F.5A "
        "Historical Price-Quality Audit"
    )
    print("=" * 76)
    print(
        f"Authoritative rows: {len(authoritative)}"
    )
    print(
        f"Price enrichment rows: {len(pricing)}"
    )
    print(
        f"Governed cohort rows: {len(cohorts)}"
    )
    print(
        f"Price-quality rows: {len(quality)}"
    )
    print(
        f"Price-spread rows: {len(spreads)}"
    )
    print(
        f"Draft review rows: {len(drafts)}"
    )
    print(
        "Structural exclusion candidates: "
        f"{len(structural_output)}"
    )
    print(
        "Rows with candidate price: "
        f"{summary['rows_with_candidate_price']}"
    )
    print(
        "Rows without candidate price: "
        f"{summary['rows_without_candidate_price']}"
    )
    print()
    print("PRICE-QUALITY AUDIT: PASS")
    print("Historical eligibility: NOT ASSIGNED")
    print("Scoring: DISABLED")
    print("Production registry: UNCHANGED")
    print("Universal database: UNCHANGED")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())