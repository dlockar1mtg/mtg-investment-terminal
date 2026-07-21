from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import json
import sqlite3

import pandas as pd

from terminal2.config import DB_FILE, PRODUCT_MASTER_FILE
from terminal2.db.loaders import insert_price_observations


DEFAULT_MODEL_INPUT = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "product_master"
    / "product_master_model_input.csv"
)

SOURCE_NAME = "product_master_local_snapshot"


@dataclass(frozen=True)
class LocalSnapshotImportResult:
    source_rows: int
    valid_rows: int
    matched_rows: int
    inserted_rows: int
    observation_date: str
    source_file: Path


def _normalize_identifier(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
    )


def _load_database_products(
    database_path: Path = DB_FILE,
) -> pd.DataFrame:
    if not Path(database_path).exists():
        raise FileNotFoundError(
            f"Terminal 2 database not found: {database_path}"
        )

    connection = sqlite3.connect(database_path)

    try:
        products = pd.read_sql_query(
            """
            SELECT
                investment_product_id,
                box_name,
                set_name,
                tcgplayer_product_id,
                approval_status
            FROM products
            """,
            connection,
        )
    finally:
        connection.close()

    if products.empty:
        raise RuntimeError(
            "Terminal 2 products table contains zero rows."
        )

    return products


def _validate_observation_date(
    value: str,
) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            "Observation date must use YYYY-MM-DD format."
        ) from exc

    return parsed.isoformat()


def prepare_local_snapshot_rows(
    *,
    model_input_path: Path = DEFAULT_MODEL_INPUT,
    database_path: Path = DB_FILE,
    observation_date: str,
) -> tuple[list[dict], LocalSnapshotImportResult]:
    model_input_path = Path(model_input_path)
    database_path = Path(database_path)
    normalized_date = _validate_observation_date(
        observation_date
    )

    if not model_input_path.exists():
        raise FileNotFoundError(
            f"Model-input file not found: {model_input_path}"
        )

    source = pd.read_csv(
        model_input_path,
        dtype={
            "investment_product_id": str,
            "tcgplayer_product_id": str,
            "approved_tcgplayer_product_id": str,
        },
    )

    required = {
        "investment_product_id",
        "box_name",
        "current_price",
    }
    missing = sorted(required - set(source.columns))

    if missing:
        raise ValueError(
            f"Model-input file is missing columns: {missing}"
        )

    source["investment_product_id"] = (
        _normalize_identifier(
            source["investment_product_id"]
        )
    )
    source["current_price"] = pd.to_numeric(
        source["current_price"],
        errors="coerce",
    )

    invalid_identifier = source[
        source["investment_product_id"].eq("")
    ]
    if not invalid_identifier.empty:
        raise ValueError(
            "Model-input file contains blank "
            "investment_product_id values."
        )

    duplicate_ids = source[
        source["investment_product_id"].duplicated(
            keep=False
        )
    ]
    if not duplicate_ids.empty:
        values = sorted(
            duplicate_ids[
                "investment_product_id"
            ].unique()
        )
        raise ValueError(
            "Model-input file contains duplicate product IDs: "
            + ", ".join(values)
        )

    invalid_prices = source[
        source["current_price"].isna()
        | source["current_price"].le(0)
    ]
    if not invalid_prices.empty:
        values = invalid_prices[
            "investment_product_id"
        ].tolist()
        raise ValueError(
            "Model-input file contains missing or nonpositive "
            "prices for: "
            + ", ".join(values)
        )

    products = _load_database_products(database_path)
    products["investment_product_id"] = (
        _normalize_identifier(
            products["investment_product_id"]
        )
    )
    products["tcgplayer_product_id"] = (
        _normalize_identifier(
            products["tcgplayer_product_id"]
        )
    )

    approved = products[
        products["approval_status"]
        .fillna("")
        .astype(str)
        .str.casefold()
        .eq("approved")
    ].copy()

    merged = source.merge(
        approved[
            [
                "investment_product_id",
                "tcgplayer_product_id",
            ]
        ],
        on="investment_product_id",
        how="left",
        indicator=True,
        suffixes=("_source", "_database"),
    )

    unmatched = merged[
        merged["_merge"].ne("both")
    ]
    if not unmatched.empty:
        values = unmatched[
            "investment_product_id"
        ].tolist()
        raise ValueError(
            "Model-input rows do not map to approved products: "
            + ", ".join(values)
        )

    source_tcg_column = next(
        (
            column
            for column in (
                "approved_tcgplayer_product_id",
                "tcgplayer_product_id",
            )
            if column in merged.columns
        ),
        None,
    )

    rows: list[dict] = []

    for _, record in merged.iterrows():
        source_tcg = (
            record.get(source_tcg_column)
            if source_tcg_column
            else None
        )
        database_tcg = record.get(
            "tcgplayer_product_id_database"
        )

        tcgplayer_product_id = (
            str(source_tcg).replace(".0", "").strip()
            if pd.notna(source_tcg)
            and str(source_tcg).strip()
            else str(database_tcg).replace(".0", "").strip()
        )

        low_price = record.get(
            "estimated_floor_price"
        )
        if pd.isna(low_price):
            low_price = record.get("low_price")

        rows.append(
            {
                "observation_date": normalized_date,
                "investment_product_id": record[
                    "investment_product_id"
                ],
                "tcgplayer_product_id": (
                    tcgplayer_product_id
                ),
                "price_source": SOURCE_NAME,
                "market_price": float(
                    record["current_price"]
                ),
                "low_price": (
                    float(low_price)
                    if pd.notna(low_price)
                    else None
                ),
                "mid_price": (
                    float(record["mid_price"])
                    if "mid_price" in merged.columns
                    and pd.notna(record.get("mid_price"))
                    else None
                ),
                "high_price": (
                    float(record["high_price"])
                    if "high_price" in merged.columns
                    and pd.notna(record.get("high_price"))
                    else None
                ),
                "price_data_quality": float(
                    record.get(
                        "price_data_quality",
                        95,
                    )
                    if pd.notna(
                        record.get(
                            "price_data_quality",
                            95,
                        )
                    )
                    else 95
                ),
                "raw_payload": json.dumps(
                    {
                        "source_file": str(
                            model_input_path
                        ),
                        "import_type": (
                            "controlled_local_snapshot"
                        ),
                    },
                    sort_keys=True,
                ),
            }
        )

    result = LocalSnapshotImportResult(
        source_rows=len(source),
        valid_rows=len(rows),
        matched_rows=len(merged),
        inserted_rows=0,
        observation_date=normalized_date,
        source_file=model_input_path,
    )

    return rows, result


def import_local_snapshot(
    *,
    model_input_path: Path = DEFAULT_MODEL_INPUT,
    database_path: Path = DB_FILE,
    observation_date: str,
    dry_run: bool = False,
) -> LocalSnapshotImportResult:
    rows, prepared = prepare_local_snapshot_rows(
        model_input_path=model_input_path,
        database_path=database_path,
        observation_date=observation_date,
    )

    inserted = 0

    if not dry_run:
        inserted = insert_price_observations(
            rows,
            source_run_id=(
                f"{SOURCE_NAME}:{prepared.observation_date}"
            ),
            db_file=database_path,
        )

    return LocalSnapshotImportResult(
        source_rows=prepared.source_rows,
        valid_rows=prepared.valid_rows,
        matched_rows=prepared.matched_rows,
        inserted_rows=inserted,
        observation_date=prepared.observation_date,
        source_file=prepared.source_file,
    )