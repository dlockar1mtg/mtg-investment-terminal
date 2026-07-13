from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .identifiers import normalize_text, stable_secret_lair_id
from .registry import REGISTRY_COLUMNS


@dataclass(frozen=True)
class ImportResult:
    input_path: str
    output_path: str
    imported_rows: int
    rejected_rows: int
    duplicate_rows_removed: int


def _boolean(value: object) -> bool:
    text = normalize_text(value).lower()
    return text in {"1", "true", "yes", "y"}


def import_secret_lair_registry(
    input_path: Path,
    *,
    output_path: Path,
    rejection_path: Path | None = None,
) -> ImportResult:
    input_path = Path(input_path)
    output_path = Path(output_path)
    rejection_path = (
        Path(rejection_path)
        if rejection_path is not None
        else output_path.with_name(
            "secret_lair_import_rejections.csv"
        )
    )

    frame = pd.read_csv(input_path, dtype=str).fillna("")
    for column in REGISTRY_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""

    frame = frame[list(REGISTRY_COLUMNS)].copy()
    for column in frame.columns:
        frame[column] = frame[column].map(normalize_text)

    frame["finish"] = frame["finish"].str.lower()
    frame["product_family"] = frame["product_family"].str.lower()
    frame["availability_model"] = (
        frame["availability_model"].str.lower()
    )
    frame["status"] = frame["status"].str.lower()
    frame["event_type"] = frame["event_type"].str.lower()
    frame["universes_beyond"] = frame[
        "universes_beyond"
    ].map(_boolean)

    frame["msrp_usd"] = pd.to_numeric(
        frame["msrp_usd"],
        errors="coerce",
    )
    frame["card_count"] = pd.to_numeric(
        frame["card_count"],
        errors="coerce",
    ).astype("Int64")

    for column in (
        "release_date",
        "sale_start_date",
        "sale_end_date",
    ):
        parsed = pd.to_datetime(frame[column], errors="coerce")
        frame[column] = parsed.dt.date.astype("string").fillna("")

    missing_identity = (
        frame["drop_name"].eq("")
        | frame["variant_name"].eq("")
        | frame["finish"].eq("")
    )
    rejected = frame.loc[missing_identity].copy()
    accepted = frame.loc[~missing_identity].copy()

    generated = accepted.apply(
        lambda row: stable_secret_lair_id(
            drop_name=row["drop_name"],
            variant_name=row["variant_name"],
            finish=row["finish"],
            source_record_id=row["source_record_id"],
        ),
        axis=1,
    )
    accepted["secret_lair_id"] = accepted[
        "secret_lair_id"
    ].where(
        accepted["secret_lair_id"].str.strip().ne(""),
        generated,
    )

    before = len(accepted)
    accepted = accepted.drop_duplicates(
        "secret_lair_id",
        keep="last",
    )
    duplicates_removed = before - len(accepted)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    accepted.to_csv(output_path, index=False)

    if not rejected.empty:
        rejection_path.parent.mkdir(parents=True, exist_ok=True)
        rejected.to_csv(rejection_path, index=False)
    elif rejection_path.exists():
        rejection_path.unlink()

    return ImportResult(
        input_path=str(input_path),
        output_path=str(output_path),
        imported_rows=len(accepted),
        rejected_rows=len(rejected),
        duplicate_rows_removed=duplicates_removed,
    )
