from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

HISTORICAL_QUEUE_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "premium_universe_eligibility"
    / "historical_booster_review_2026-07-22.csv"
)

ASSET_PREVIEW_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "universal_mapping"
    / "asset_master_preview_2026-07-22.csv"
)

PRODUCT_MASTER_PATH = (
    ROOT
    / "data"
    / "product_master"
    / "product_master_model_input.csv"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_evidence_bridge"
)

SCHEMA_VERSION = "10.5R.1D.2.2B"

PRODUCT_MASTER_IDENTITY_CANDIDATES = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "tcgplayer_product_id_str",
    "approved_tcgplayer_product_id",
    "approved_tcgplayer_product_id_str",
    "investment_product_id",
    "product_id",
    "asset_id",
    "platform_asset_id",
]

PRODUCT_MASTER_NAME_CANDIDATES = [
    "canonical_product_name",
    "official_product_name",
    "approved_product_name",
    "box_name_master",
    "box_name",
    "source_product_name",
    "product_name",
    "asset_name",
    "name",
]

PRODUCT_MASTER_SET_CANDIDATES = [
    "canonical_set_name",
    "set_name",
    "set",
]

PRICE_COLUMNS = [
    "market_price",
    "current_market_price",
    "current_price",
    "latest_price",
    "low_price",
    "mid_price",
    "high_price",
    "listed_median_price",
    "current_value",
    "market_value",
    "current_price_db",
    "current_price_history",
    "last_price_checked",
    "price_source",
]

PERFORMANCE_COLUMNS = [
    "return",
    "return_1y",
    "return_3y",
    "return_5y",
    "cagr",
    "cagr_1y",
    "cagr_3y",
    "cagr_5y",
    "growth_rate",
    "appreciation",
    "price_trend_signal_score",
    "price_stability_score",
    "estimated_floor_price",
    "estimated_ceiling_price",
]

OUTPUT_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_set_name",
    "canonical_product_name",
    "canonical_product_type",
    "asset_preview_identity_match_status",
    "first_available_date",
    "timing_match_status",
    "product_master_match_status",
    "product_master_match_method",
    "product_master_row_index",
    "product_master_identity_field",
    "product_master_identity_value",
    "product_master_name_field",
    "product_master_name_value",
    "product_master_set_field",
    "product_master_set_value",
    "available_price_fields",
    "available_price_field_count",
    "available_performance_fields",
    "available_performance_field_count",
    "current_price_candidate",
    "price_date_candidate",
    "price_source_candidate",
    "evidence_bridge_state",
    "historical_eligibility_decision",
    "scoring_allowed",
    "universal_investable_allowed",
]


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


def normalize_text(value: object) -> str:
    text = clean_text(value)

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        character
        for character in text
        if not unicodedata.combining(
            character
        )
    )

    text = text.casefold()

    replacements = {
        "booster display box": "booster box",
        "booster display": "booster box",
        "draft booster box": "booster box",
        "draft booster display": "booster box",
        "basic booster display": "booster box",
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new,
        )

    text = text.replace(
        "&",
        " and ",
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


def first_existing_column(
    frame: pd.DataFrame,
    candidates: list[str],
) -> str:
    for column in candidates:
        if column in frame.columns:
            return column

    return ""


def populated_columns(
    row: pd.Series,
    candidates: list[str],
) -> list[str]:
    return [
        column
        for column in candidates
        if column in row.index
        and clean_text(row.get(column))
    ]


def first_populated_value(
    row: pd.Series,
    candidates: list[str],
) -> str:
    for column in candidates:
        if column not in row.index:
            continue

        value = clean_text(
            row.get(column)
        )

        if value:
            return value

    return ""


def build_asset_timing_indexes(
    asset_preview: pd.DataFrame,
) -> dict[str, dict[str, str]]:
    required = {
        "platform_asset_id",
        "asset_name",
        "first_available_date",
    }

    missing = required - set(
        asset_preview.columns
    )

    if missing:
        raise RuntimeError(
            "Asset preview missing required columns: "
            + ", ".join(
                sorted(missing)
            )
        )

    id_index: dict[str, str] = {}
    name_index: dict[str, str] = {}

    for _, row in asset_preview.iterrows():
        platform_asset_id = clean_text(
            row.get(
                "platform_asset_id"
            )
        )

        normalized_name = normalize_text(
            row.get(
                "asset_name"
            )
        )

        release_date = clean_text(
            row.get(
                "first_available_date"
            )
        )

        if (
            platform_asset_id
            and platform_asset_id
            not in id_index
        ):
            id_index[
                platform_asset_id
            ] = release_date

        if (
            normalized_name
            and normalized_name
            not in name_index
        ):
            name_index[
                normalized_name
            ] = release_date

    return {
        "platform_asset_id": id_index,
        "asset_name": name_index,
    }


def build_product_master_indexes(
    product_master: pd.DataFrame,
) -> dict[str, Any]:
    id_columns = [
        column
        for column in (
            PRODUCT_MASTER_IDENTITY_CANDIDATES
        )
        if column in product_master.columns
    ]

    name_column = first_existing_column(
        product_master,
        PRODUCT_MASTER_NAME_CANDIDATES,
    )

    set_column = first_existing_column(
        product_master,
        PRODUCT_MASTER_SET_CANDIDATES,
    )

    id_indexes: dict[str, dict[str, int]] = {}

    for column in id_columns:
        index: dict[str, int] = {}

        for row_index, value in (
            product_master[column].items()
        ):
            cleaned = clean_text(value)

            if (
                cleaned
                and cleaned not in index
            ):
                index[cleaned] = int(
                    row_index
                )

        id_indexes[column] = index

    name_index: dict[str, list[int]] = {}

    if name_column:
        for row_index, value in (
            product_master[name_column].items()
        ):
            normalized = normalize_text(value)

            if normalized:
                name_index.setdefault(
                    normalized,
                    [],
                ).append(
                    int(row_index)
                )

    set_name_index: dict[
        tuple[str, str],
        list[int],
    ] = {}

    if name_column and set_column:
        for row_index, row in (
            product_master.iterrows()
        ):
            normalized_name = normalize_text(
                row.get(name_column)
            )

            normalized_set = normalize_text(
                row.get(set_column)
            )

            if (
                normalized_name
                and normalized_set
            ):
                key = (
                    normalized_set,
                    normalized_name,
                )

                set_name_index.setdefault(
                    key,
                    [],
                ).append(
                    int(row_index)
                )

    return {
        "id_columns": id_columns,
        "id_indexes": id_indexes,
        "name_column": name_column,
        "set_column": set_column,
        "name_index": name_index,
        "set_name_index": set_name_index,
    }


def find_product_master_match(
    *,
    historical_row: pd.Series,
    product_master: pd.DataFrame,
    indexes: dict[str, Any],
) -> tuple[int | None, str, str]:
    canonical_id = clean_text(
        historical_row.get(
            "canonical_product_id"
        )
    )

    tcgplayer_id = clean_text(
        historical_row.get(
            "tcgplayer_product_id"
        )
    )

    identity_values = [
        canonical_id,
        tcgplayer_id,
    ]

    for column in indexes[
        "id_columns"
    ]:
        column_index = indexes[
            "id_indexes"
        ][column]

        for identity_value in identity_values:
            if (
                identity_value
                and identity_value
                in column_index
            ):
                return (
                    column_index[
                        identity_value
                    ],
                    "exact_identity",
                    column,
                )

    normalized_name = normalize_text(
        historical_row.get(
            "canonical_product_name"
        )
    )

    normalized_set = normalize_text(
        historical_row.get(
            "canonical_set_name"
        )
    )

    if normalized_name and normalized_set:
        key = (
            normalized_set,
            normalized_name,
        )

        candidates = indexes[
            "set_name_index"
        ].get(
            key,
            [],
        )

        if len(candidates) == 1:
            return (
                candidates[0],
                "normalized_set_and_name",
                "",
            )

    if normalized_name:
        candidates = indexes[
            "name_index"
        ].get(
            normalized_name,
            [],
        )

        if len(candidates) == 1:
            return (
                candidates[0],
                "normalized_name",
                "",
            )

    return None, "unmatched", ""


def main() -> int:
    for path in (
        HISTORICAL_QUEUE_PATH,
        ASSET_PREVIEW_PATH,
        PRODUCT_MASTER_PATH,
    ):
        if not path.is_file():
            raise FileNotFoundError(
                f"Required evidence file missing: {path}"
            )

    historical = pd.read_csv(
        HISTORICAL_QUEUE_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    asset_preview = pd.read_csv(
        ASSET_PREVIEW_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    product_master = pd.read_csv(
        PRODUCT_MASTER_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    if len(historical) != 140:
        raise RuntimeError(
            "Expected 140 corrected historical products; "
            f"found {len(historical)}."
        )

    timing_indexes = (
        build_asset_timing_indexes(
            asset_preview
        )
    )

    product_master_indexes = (
        build_product_master_indexes(
            product_master
        )
    )

    name_column = product_master_indexes[
        "name_column"
    ]

    set_column = product_master_indexes[
        "set_column"
    ]

    output_rows: list[
        dict[str, Any]
    ] = []

    for _, historical_row in (
        historical.iterrows()
    ):
        canonical_product_id = clean_text(
            historical_row.get(
                "canonical_product_id"
            )
        )

        normalized_name = normalize_text(
            historical_row.get(
                "canonical_product_name"
            )
        )

        asset_preview_identity_match = (
            canonical_product_id
            in timing_indexes[
                "platform_asset_id"
            ]
            or normalized_name
            in timing_indexes[
                "asset_name"
            ]
        )

        first_available_date = (
            timing_indexes[
                "platform_asset_id"
            ].get(
                canonical_product_id,
                "",
            )
        )

        if not first_available_date:
            first_available_date = (
                timing_indexes[
                    "asset_name"
                ].get(
                    normalized_name,
                    "",
                )
            )

        (
            product_master_row_index,
            match_method,
            identity_field,
        ) = find_product_master_match(
            historical_row=historical_row,
            product_master=product_master,
            indexes=product_master_indexes,
        )

        product_master_match = (
            product_master_row_index
            is not None
        )

        if product_master_match:
            product_row = product_master.loc[
                product_master_row_index
            ]

            price_fields = populated_columns(
                product_row,
                PRICE_COLUMNS,
            )

            performance_fields = (
                populated_columns(
                    product_row,
                    PERFORMANCE_COLUMNS,
                )
            )
        else:
            product_row = pd.Series(
                dtype=object
            )

            price_fields = []
            performance_fields = []

        identity_value = (
            clean_text(
                product_row.get(
                    identity_field
                )
            )
            if identity_field
            else ""
        )

        product_master_name_value = (
            clean_text(
                product_row.get(
                    name_column
                )
            )
            if name_column
            else ""
        )

        product_master_set_value = (
            clean_text(
                product_row.get(
                    set_column
                )
            )
            if set_column
            else ""
        )

        if (
            first_available_date
            and price_fields
            and performance_fields
        ):
            evidence_state = (
                "timing_price_performance_available"
            )
        elif (
            first_available_date
            and price_fields
        ):
            evidence_state = (
                "timing_and_price_available"
            )
        elif first_available_date:
            evidence_state = (
                "timing_only"
            )
        else:
            evidence_state = (
                "identity_only"
            )

        output_rows.append(
            {
                "canonical_product_id": clean_text(
                    historical_row.get(
                        "canonical_product_id"
                    )
                ),
                "tcgplayer_product_id": clean_text(
                    historical_row.get(
                        "tcgplayer_product_id"
                    )
                ),
                "canonical_set_name": clean_text(
                    historical_row.get(
                        "canonical_set_name"
                    )
                ),
                "canonical_product_name": clean_text(
                    historical_row.get(
                        "canonical_product_name"
                    )
                ),
                "canonical_product_type": clean_text(
                    historical_row.get(
                        "canonical_product_type"
                    )
                ),
                "asset_preview_identity_match_status": (
                    "matched"
                    if asset_preview_identity_match
                    else "unmatched"
                ),
                "first_available_date": (
                    first_available_date
                ),
                "timing_match_status": (
                    "matched"
                    if first_available_date
                    else "unmatched"
                ),
                "product_master_match_status": (
                    "matched"
                    if product_master_match
                    else "unmatched"
                ),
                "product_master_match_method": (
                    match_method
                ),
                "product_master_row_index": (
                    product_master_row_index
                    if product_master_match
                    else ""
                ),
                "product_master_identity_field": (
                    identity_field
                ),
                "product_master_identity_value": (
                    identity_value
                ),
                "product_master_name_field": (
                    name_column
                ),
                "product_master_name_value": (
                    product_master_name_value
                ),
                "product_master_set_field": (
                    set_column
                ),
                "product_master_set_value": (
                    product_master_set_value
                ),
                "available_price_fields": "|".join(
                    price_fields
                ),
                "available_price_field_count": len(
                    price_fields
                ),
                "available_performance_fields": "|".join(
                    performance_fields
                ),
                "available_performance_field_count": len(
                    performance_fields
                ),
                "current_price_candidate": (
                    first_populated_value(
                        product_row,
                        [
                            "current_market_price",
                            "market_price",
                            "current_price",
                            "latest_price",
                            "current_value",
                            "market_value",
                        ],
                    )
                ),
                "price_date_candidate": (
                    first_populated_value(
                        product_row,
                        [
                            "price_date",
                            "last_price_checked",
                        ],
                    )
                ),
                "price_source_candidate": (
                    first_populated_value(
                        product_row,
                        [
                            "price_source",
                        ],
                    )
                ),
                "evidence_bridge_state": (
                    evidence_state
                ),
                "historical_eligibility_decision": (
                    "not_decided"
                ),
                "scoring_allowed": False,
                "universal_investable_allowed": False,
            }
        )

    audit = (
        pd.DataFrame(
            output_rows,
            columns=OUTPUT_COLUMNS,
        )
        .sort_values(
            [
                "evidence_bridge_state",
                "canonical_product_type",
                "canonical_product_name",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit_path = (
        OUTPUT_ROOT
        / "historical_existing_evidence_bridge_audit_2026-07-22.csv"
    )

    matched_path = (
        OUTPUT_ROOT
        / "historical_product_master_matches_2026-07-22.csv"
    )

    unmatched_path = (
        OUTPUT_ROOT
        / "historical_product_master_unmatched_2026-07-22.csv"
    )

    summary_path = (
        OUTPUT_ROOT
        / "historical_existing_evidence_bridge_summary_2026-07-22.json"
    )

    matched = audit[
        audit[
            "product_master_match_status"
        ].eq("matched")
    ].copy()

    unmatched = audit[
        audit[
            "product_master_match_status"
        ].eq("unmatched")
    ].copy()

    audit.to_csv(
        audit_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    matched.to_csv(
        matched_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    unmatched.to_csv(
        unmatched_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    bridge_state_counts = {
        str(key): int(value)
        for key, value in (
            audit[
                "evidence_bridge_state"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    match_method_counts = {
        str(key): int(value)
        for key, value in (
            audit[
                "product_master_match_method"
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
        "historical_rows": int(
            len(audit)
        ),
        "unique_canonical_product_ids": int(
            audit[
                "canonical_product_id"
            ].nunique()
        ),
        "asset_preview_identity_match_rows": int(
            audit[
                "asset_preview_identity_match_status"
            ].eq("matched").sum()
        ),
        "timing_match_rows": int(
            audit[
                "timing_match_status"
            ].eq("matched").sum()
        ),
        "product_master_match_rows": int(
            len(matched)
        ),
        "product_master_unmatched_rows": int(
            len(unmatched)
        ),
        "rows_with_price_evidence": int(
            audit[
                "available_price_field_count"
            ].astype(int).gt(0).sum()
        ),
        "rows_with_performance_evidence": int(
            audit[
                "available_performance_field_count"
            ].astype(int).gt(0).sum()
        ),
        "rows_with_current_price_candidate": int(
            audit[
                "current_price_candidate"
            ].astype(str).str.strip().ne("").sum()
        ),
        "bridge_state_counts": (
            bridge_state_counts
        ),
        "match_method_counts": (
            match_method_counts
        ),
        "product_master_identity_columns": (
            product_master_indexes[
                "id_columns"
            ]
        ),
        "product_master_name_column": (
            name_column
        ),
        "product_master_set_column": (
            set_column
        ),
        "final_eligibility_assigned": False,
        "scoring_allowed_rows": 0,
        "universal_investable_allowed_rows": 0,
        "output_files": {
            "bridge_audit": str(
                audit_path
            ),
            "matched_products": str(
                matched_path
            ),
            "unmatched_products": str(
                unmatched_path
            ),
        },
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
        "Phase 10.5R.1D.2.2B "
        "Existing Evidence Identity Bridge Audit"
    )
    print("=" * 76)
    print(
        f"Historical rows: {len(audit)}"
    )
    print(
        "Timing matches: "
        f"{audit['timing_match_status'].eq('matched').sum()}"
    )
    print(
        "Product-master matches: "
        f"{len(matched)}"
    )
    print(
        "Product-master unmatched: "
        f"{len(unmatched)}"
    )
    print(
        "Rows with price evidence: "
        + str(
            summary[
                "rows_with_price_evidence"
            ]
        )
    )
    print(
        "Rows with performance evidence: "
        + str(
            summary[
                "rows_with_performance_evidence"
            ]
        )
    )
    print()
    print(
        "PHASE 10.5R.1D.2.2B "
        "IDENTITY BRIDGE AUDIT: PASS"
    )
    print(
        "Final eligibility: NOT ASSIGNED"
    )
    print(
        "Production registry: UNCHANGED"
    )
    print(
        "Universal database: UNCHANGED"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())