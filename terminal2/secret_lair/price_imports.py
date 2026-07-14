from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .identifiers import normalize_text
from .pricing import PRICE_COLUMNS
from .registry import load_secret_lair_registry


@dataclass(frozen=True)
class PriceImportResult:
    input_path: str
    output_path: str
    imported_rows: int
    rejected_rows: int
    duplicate_rows_removed: int


def import_secret_lair_prices(
    input_path: Path,
    *,
    output_path: Path,
    registry_path: Path,
    rejection_path: Path | None = None,
) -> PriceImportResult:
    input_path = Path(input_path)
    output_path = Path(output_path)
    rejection_path = (
        Path(rejection_path)
        if rejection_path is not None
        else output_path.with_name(
            "secret_lair_price_import_rejections.csv"
        )
    )

    frame = pd.read_csv(input_path, dtype=str).fillna("")
    for column in PRICE_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame = frame[list(PRICE_COLUMNS)].copy()

    for column in frame.columns:
        frame[column] = frame[column].map(normalize_text)

    frame["source_name"] = frame["source_name"].str.lower()
    frame["currency"] = (
        frame["currency"].where(
            frame["currency"].str.strip().ne(""),
            "USD",
        ).str.upper()
    )

    for column in (
        "market_price",
        "low_price",
        "listing_count",
        "sales_count_30d",
        "price_data_quality",
    ):
        frame[column] = pd.to_numeric(
            frame[column],
            errors="coerce",
        )

    parsed = pd.to_datetime(
        frame["observation_date"],
        errors="coerce",
    )
    frame["observation_date"] = (
        parsed.dt.date.astype("string").fillna("")
    )

    registry, _ = load_secret_lair_registry(registry_path)
    valid_ids = set(
        registry["secret_lair_id"].astype(str)
        if not registry.empty else []
    )

    rejected_mask = (
        frame["observation_date"].eq("")
        | frame["secret_lair_id"].eq("")
        | frame["source_name"].eq("")
        | frame["market_price"].isna()
        | frame["market_price"].le(0)
    )
    if valid_ids:
        rejected_mask = rejected_mask | (
            ~frame["secret_lair_id"].isin(valid_ids)
        )
    elif not frame.empty:
        rejected_mask = pd.Series(
            True,
            index=frame.index,
        )

    rejected = frame.loc[rejected_mask].copy()
    accepted = frame.loc[~rejected_mask].copy()

    key = [
        "observation_date",
        "secret_lair_id",
        "source_name",
    ]
    before = len(accepted)
    accepted = accepted.sort_values(
        key + ["price_data_quality"]
    ).drop_duplicates(key, keep="last")
    duplicates_removed = before - len(accepted)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    accepted.to_csv(output_path, index=False)

    if not rejected.empty:
        rejection_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        rejected.to_csv(rejection_path, index=False)
    elif rejection_path.exists():
        rejection_path.unlink()

    return PriceImportResult(
        input_path=str(input_path),
        output_path=str(output_path),
        imported_rows=len(accepted),
        rejected_rows=len(rejected),
        duplicate_rows_removed=duplicates_removed,
    )
