from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

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

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_evidence_discovery"
)

SCHEMA_VERSION = "10.5R.1D.2.2A"

SEARCH_ROOTS = [
    ROOT / "data",
    ROOT / "exports",
    ROOT / "exchange",
    ROOT / "output",
    ROOT / "outputs",
]

EXCLUDED_PATH_PARTS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "historical_evidence_discovery",
}

SUPPORTED_SUFFIXES = {
    ".csv",
    ".json",
    ".jsonl",
    ".parquet",
    ".xlsx",
}

IDENTITY_TERMS = {
    "canonical_product_id",
    "tcgplayer_product_id",
    "product_id",
    "tcgplayer_id",
    "asset_id",
    "platform_asset_id",
    "product_name",
    "canonical_product_name",
    "set_name",
    "canonical_set_name",
}

TIMING_TERMS = {
    "release_date",
    "release_year",
    "released_at",
    "product_release_date",
    "first_available_date",
    "first_available_date_utc",
    "date_released",
    "set_release_date",
    "published_at",
}

PRICING_TERMS = {
    "market_price",
    "current_market_price",
    "low_price",
    "mid_price",
    "high_price",
    "listed_median_price",
    "latest_price",
    "price",
    "price_date",
    "market_value",
    "current_value",
    "tcg_market_price",
    "tcgplayer_market_price",
    "historical_price_points",
}

LIQUIDITY_TERMS = {
    "sales_count",
    "sale_count",
    "listing_count",
    "listings",
    "transaction_count",
    "market_liquidity",
    "liquidity_tier",
    "volume",
    "sales_volume",
    "units_sold",
    "days_to_sell",
    "turnover",
}

SUPPLY_TERMS = {
    "print_run",
    "supply_status",
    "scarcity_indicator",
    "limited_release_indicator",
    "specialty_release_indicator",
    "inventory",
    "available_quantity",
    "quantity_available",
    "supply",
    "scarcity",
}

PERFORMANCE_TERMS = {
    "return",
    "return_1y",
    "return_3y",
    "return_5y",
    "cagr",
    "cagr_1y",
    "cagr_3y",
    "cagr_5y",
    "appreciation",
    "growth_rate",
    "forecast",
    "projected_value",
}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def normalized_name(value: object) -> str:
    return (
        str(value)
        .strip()
        .casefold()
        .replace(" ", "_")
        .replace("-", "_")
        .replace(".", "_")
        .replace("/", "_")
    )


def is_excluded(path: Path) -> bool:
    return any(
        part in EXCLUDED_PATH_PARTS
        for part in path.parts
    )


def candidate_files() -> list[Path]:
    discovered: set[Path] = set()

    for search_root in SEARCH_ROOTS:
        if not search_root.exists():
            continue

        for path in search_root.rglob("*"):
            if (
                path.is_file()
                and path.suffix.casefold()
                in SUPPORTED_SUFFIXES
                and not is_excluded(path)
            ):
                discovered.add(path.resolve())

    return sorted(
        discovered,
        key=lambda value: str(value).casefold(),
    )


def csv_columns(path: Path) -> list[str]:
    with path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:
        reader = csv.reader(handle)

        try:
            return [
                str(value).strip()
                for value in next(reader)
            ]
        except StopIteration:
            return []


def json_columns(path: Path) -> list[str]:
    text = path.read_text(
        encoding="utf-8-sig",
        errors="replace",
    ).strip()

    if not text:
        return []

    if path.suffix.casefold() == ".jsonl":
        first_line = text.splitlines()[0]
        value = json.loads(first_line)
    else:
        value = json.loads(text)

    if isinstance(value, dict):
        if isinstance(
            value.get("records"),
            list,
        ) and value["records"]:
            first = value["records"][0]

            if isinstance(first, dict):
                return list(first.keys())

        return list(value.keys())

    if (
        isinstance(value, list)
        and value
        and isinstance(value[0], dict)
    ):
        return list(value[0].keys())

    return []


def workbook_columns(path: Path) -> list[str]:
    workbook = pd.ExcelFile(path)

    columns: list[str] = []

    for sheet_name in workbook.sheet_names[:10]:
        frame = pd.read_excel(
            path,
            sheet_name=sheet_name,
            nrows=0,
        )

        for column in frame.columns:
            columns.append(
                f"{sheet_name}:{column}"
            )

    return columns


def parquet_columns(path: Path) -> list[str]:
    frame = pd.read_parquet(path)

    return [
        str(column)
        for column in frame.columns
    ]


def inspect_columns(path: Path) -> tuple[list[str], str]:
    try:
        suffix = path.suffix.casefold()

        if suffix == ".csv":
            return csv_columns(path), ""

        if suffix in {".json", ".jsonl"}:
            return json_columns(path), ""

        if suffix == ".xlsx":
            return workbook_columns(path), ""

        if suffix == ".parquet":
            return parquet_columns(path), ""

        return [], "unsupported_suffix"

    except Exception as exc:
        return [], (
            f"{type(exc).__name__}: {exc}"
        )


def matched_terms(
    columns: Iterable[str],
    terms: set[str],
) -> list[str]:
    matches: list[str] = []

    for column in columns:
        normalized = normalized_name(column)

        for term in terms:
            normalized_term = normalized_name(term)

            if (
                normalized == normalized_term
                or normalized_term in normalized
            ):
                matches.append(str(column))
                break

    return sorted(set(matches))


def product_overlap(
    *,
    path: Path,
    historical: pd.DataFrame,
    columns: list[str],
) -> dict[str, Any]:
    result = {
        "rows_sampled": 0,
        "tcgplayer_id_overlap": 0,
        "canonical_id_overlap": 0,
        "product_name_overlap": 0,
        "overlap_error": "",
    }

    suffix = path.suffix.casefold()

    try:
        if suffix == ".csv":
            frame = pd.read_csv(
                path,
                dtype=str,
                keep_default_na=False,
                low_memory=False,
                nrows=250000,
            )
        elif suffix == ".parquet":
            frame = pd.read_parquet(path)
        elif suffix == ".xlsx":
            frame = pd.read_excel(
                path,
                dtype=str,
                nrows=250000,
            ).fillna("")
        elif suffix == ".json":
            frame = pd.read_json(path)
        elif suffix == ".jsonl":
            frame = pd.read_json(
                path,
                lines=True,
            )
        else:
            return result

        if frame.empty:
            return result

        result["rows_sampled"] = int(
            len(frame)
        )

        normalized_columns = {
            normalized_name(column): column
            for column in frame.columns
        }

        historical_tcg_ids = set(
            historical[
                "tcgplayer_product_id"
            ].astype(str).str.strip()
        )

        historical_canonical_ids = set(
            historical[
                "canonical_product_id"
            ].astype(str).str.strip()
        )

        historical_names = set(
            historical[
                "canonical_product_name"
            ].astype(str).str.strip().str.casefold()
        )

        for candidate in (
            "tcgplayer_product_id",
            "tcgplayer_id",
            "product_id",
        ):
            column = normalized_columns.get(
                candidate
            )

            if column is not None:
                values = set(
                    frame[column]
                    .astype(str)
                    .str.strip()
                )

                result[
                    "tcgplayer_id_overlap"
                ] = max(
                    result[
                        "tcgplayer_id_overlap"
                    ],
                    len(
                        values
                        & historical_tcg_ids
                    ),
                )

        for candidate in (
            "canonical_product_id",
            "universal_asset_id",
        ):
            column = normalized_columns.get(
                candidate
            )

            if column is not None:
                values = set(
                    frame[column]
                    .astype(str)
                    .str.strip()
                )

                result[
                    "canonical_id_overlap"
                ] = max(
                    result[
                        "canonical_id_overlap"
                    ],
                    len(
                        values
                        & historical_canonical_ids
                    ),
                )

        for candidate in (
            "canonical_product_name",
            "product_name",
            "asset_name",
            "name",
        ):
            column = normalized_columns.get(
                candidate
            )

            if column is not None:
                values = set(
                    frame[column]
                    .astype(str)
                    .str.strip()
                    .str.casefold()
                )

                result[
                    "product_name_overlap"
                ] = max(
                    result[
                        "product_name_overlap"
                    ],
                    len(
                        values
                        & historical_names
                    ),
                )

    except Exception as exc:
        result["overlap_error"] = (
            f"{type(exc).__name__}: {exc}"
        )

    return result


def main() -> int:
    if not HISTORICAL_QUEUE_PATH.is_file():
        raise FileNotFoundError(
            "Historical review queue not found: "
            f"{HISTORICAL_QUEUE_PATH}"
        )

    historical = pd.read_csv(
        HISTORICAL_QUEUE_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    if len(historical) != 140:
        raise RuntimeError(
            "Expected 140 corrected historical products; "
            f"found {len(historical)}."
        )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    inventory_rows: list[dict[str, Any]] = []

    for path in candidate_files():
        columns, inspection_error = (
            inspect_columns(path)
        )

        identity_matches = matched_terms(
            columns,
            IDENTITY_TERMS,
        )

        timing_matches = matched_terms(
            columns,
            TIMING_TERMS,
        )

        pricing_matches = matched_terms(
            columns,
            PRICING_TERMS,
        )

        liquidity_matches = matched_terms(
            columns,
            LIQUIDITY_TERMS,
        )

        supply_matches = matched_terms(
            columns,
            SUPPLY_TERMS,
        )

        performance_matches = matched_terms(
            columns,
            PERFORMANCE_TERMS,
        )

        evidence_group_count = sum(
            [
                bool(timing_matches),
                bool(pricing_matches),
                bool(liquidity_matches),
                bool(supply_matches),
                bool(performance_matches),
            ]
        )

        overlap = product_overlap(
            path=path,
            historical=historical,
            columns=columns,
        )

        inventory_rows.append(
            {
                "relative_path": str(
                    path.relative_to(ROOT)
                ),
                "suffix": path.suffix.casefold(),
                "size_bytes": path.stat().st_size,
                "column_count": len(columns),
                "columns": "|".join(columns),
                "identity_matches": "|".join(
                    identity_matches
                ),
                "timing_matches": "|".join(
                    timing_matches
                ),
                "pricing_matches": "|".join(
                    pricing_matches
                ),
                "liquidity_matches": "|".join(
                    liquidity_matches
                ),
                "supply_matches": "|".join(
                    supply_matches
                ),
                "performance_matches": "|".join(
                    performance_matches
                ),
                "evidence_group_count": (
                    evidence_group_count
                ),
                "rows_sampled": overlap[
                    "rows_sampled"
                ],
                "tcgplayer_id_overlap": overlap[
                    "tcgplayer_id_overlap"
                ],
                "canonical_id_overlap": overlap[
                    "canonical_id_overlap"
                ],
                "product_name_overlap": overlap[
                    "product_name_overlap"
                ],
                "inspection_error": (
                    inspection_error
                ),
                "overlap_error": overlap[
                    "overlap_error"
                ],
            }
        )

    inventory = pd.DataFrame(
        inventory_rows
    )

    if inventory.empty:
        inventory = pd.DataFrame(
            columns=[
                "relative_path",
                "suffix",
                "size_bytes",
                "column_count",
                "columns",
                "identity_matches",
                "timing_matches",
                "pricing_matches",
                "liquidity_matches",
                "supply_matches",
                "performance_matches",
                "evidence_group_count",
                "rows_sampled",
                "tcgplayer_id_overlap",
                "canonical_id_overlap",
                "product_name_overlap",
                "inspection_error",
                "overlap_error",
            ]
        )

    relevant = inventory[
        (
            inventory[
                "evidence_group_count"
            ].astype(int)
            > 0
        )
        | (
            inventory[
                "tcgplayer_id_overlap"
            ].astype(int)
            > 0
        )
        | (
            inventory[
                "canonical_id_overlap"
            ].astype(int)
            > 0
        )
        | (
            inventory[
                "product_name_overlap"
            ].astype(int)
            > 0
        )
    ].copy()

    ranked = relevant.sort_values(
        [
            "canonical_id_overlap",
            "tcgplayer_id_overlap",
            "product_name_overlap",
            "evidence_group_count",
            "relative_path",
        ],
        ascending=[
            False,
            False,
            False,
            False,
            True,
        ],
        kind="stable",
    ).reset_index(drop=True)

    inventory_path = (
        OUTPUT_ROOT
        / "repository_evidence_file_inventory_2026-07-22.csv"
    )

    ranked_path = (
        OUTPUT_ROOT
        / "ranked_historical_evidence_sources_2026-07-22.csv"
    )

    summary_path = (
        OUTPUT_ROOT
        / "historical_evidence_discovery_summary_2026-07-22.json"
    )

    inventory.to_csv(
        inventory_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    ranked.to_csv(
        ranked_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "discovery_status": "PASS",
        "historical_product_rows": int(
            len(historical)
        ),
        "files_inspected": int(
            len(inventory)
        ),
        "relevant_files_found": int(
            len(relevant)
        ),
        "files_with_timing_fields": int(
            inventory[
                "timing_matches"
            ].astype(str).str.strip().ne("").sum()
        ),
        "files_with_pricing_fields": int(
            inventory[
                "pricing_matches"
            ].astype(str).str.strip().ne("").sum()
        ),
        "files_with_liquidity_fields": int(
            inventory[
                "liquidity_matches"
            ].astype(str).str.strip().ne("").sum()
        ),
        "files_with_supply_fields": int(
            inventory[
                "supply_matches"
            ].astype(str).str.strip().ne("").sum()
        ),
        "files_with_performance_fields": int(
            inventory[
                "performance_matches"
            ].astype(str).str.strip().ne("").sum()
        ),
        "files_with_any_historical_overlap": int(
            (
                inventory[
                    "tcgplayer_id_overlap"
                ].astype(int)
                + inventory[
                    "canonical_id_overlap"
                ].astype(int)
                + inventory[
                    "product_name_overlap"
                ].astype(int)
            ).gt(0).sum()
        ),
        "maximum_tcgplayer_id_overlap": int(
            inventory[
                "tcgplayer_id_overlap"
            ].astype(int).max()
            if len(inventory)
            else 0
        ),
        "maximum_canonical_id_overlap": int(
            inventory[
                "canonical_id_overlap"
            ].astype(int).max()
            if len(inventory)
            else 0
        ),
        "maximum_product_name_overlap": int(
            inventory[
                "product_name_overlap"
            ].astype(int).max()
            if len(inventory)
            else 0
        ),
        "output_files": {
            "complete_inventory": str(
                inventory_path
            ),
            "ranked_sources": str(
                ranked_path
            ),
        },
        "eligibility_changed": False,
        "production_registry_changed": False,
        "scoring_applied": False,
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
        "Phase 10.5R.1D.2.2A "
        "Existing Evidence Source Discovery"
    )
    print("=" * 76)
    print(
        f"Historical products: {len(historical)}"
    )
    print(
        f"Files inspected: {len(inventory)}"
    )
    print(
        f"Relevant files found: {len(relevant)}"
    )
    print(
        "Files with historical overlap: "
        + str(
            summary[
                "files_with_any_historical_overlap"
            ]
        )
    )
    print(
        "Maximum TCGplayer ID overlap: "
        + str(
            summary[
                "maximum_tcgplayer_id_overlap"
            ]
        )
    )
    print(
        "Maximum canonical ID overlap: "
        + str(
            summary[
                "maximum_canonical_id_overlap"
            ]
        )
    )
    print(
        "Maximum product-name overlap: "
        + str(
            summary[
                "maximum_product_name_overlap"
            ]
        )
    )
    print()
    print(
        "PHASE 10.5R.1D.2.2A "
        "SOURCE DISCOVERY: PASS"
    )
    print(
        "Eligibility decisions: UNCHANGED"
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