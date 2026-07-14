from __future__ import annotations

from pathlib import Path

import pandas as pd

from terminal2.config import ROOT_DIR
from terminal2.secret_lair.identifiers import normalize_text


SOURCE_CATALOG_PATH = (
    Path(ROOT_DIR)
    / "data"
    / "terminal2"
    / "secret_lair_source_catalog.csv"
)
SOURCE_PRICES_PATH = (
    Path(ROOT_DIR)
    / "data"
    / "terminal2"
    / "secret_lair_source_prices.csv"
)
MATCH_OVERRIDES_PATH = (
    Path(ROOT_DIR)
    / "data"
    / "terminal2"
    / "secret_lair_match_overrides.csv"
)
APPLY_LOG_PATH = (
    Path(ROOT_DIR)
    / "data"
    / "terminal2"
    / "secret_lair_backfill_apply_log.csv"
)

CATALOG_COLUMNS = (
    "source_name",
    "source_record_id",
    "drop_name",
    "variant_name",
    "finish",
    "product_family",
    "release_date",
    "sale_start_date",
    "sale_end_date",
    "msrp_usd",
    "currency",
    "franchise",
    "ip_category",
    "universes_beyond",
    "artist_names",
    "card_count",
    "superdrop_name",
    "event_type",
    "availability_model",
    "status",
    "official_url",
    "notes",
)

SOURCE_PRICE_COLUMNS = (
    "source_name",
    "source_record_id",
    "observation_date",
    "market_price",
    "low_price",
    "listing_count",
    "sales_count_30d",
    "currency",
    "source_url",
    "price_data_quality",
    "notes",
)

OVERRIDE_COLUMNS = (
    "source_name",
    "source_record_id",
    "secret_lair_id",
    "override_action",
    "notes",
)


def _empty(columns) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _load(path: Path, columns) -> tuple[pd.DataFrame, bool]:
    path = Path(path)
    if not path.exists():
        return _empty(columns), False
    frame = pd.read_csv(path, dtype=str).fillna("")
    for column in columns:
        if column not in frame.columns:
            frame[column] = ""
    frame = frame[list(columns)].copy()
    for column in frame.columns:
        frame[column] = frame[column].map(normalize_text)
    return frame, True


def load_source_catalog(
    path: Path = SOURCE_CATALOG_PATH,
) -> tuple[pd.DataFrame, bool]:
    frame, exists = _load(path, CATALOG_COLUMNS)
    if frame.empty:
        return frame, exists

    frame["source_name"] = frame["source_name"].str.lower()
    frame["finish"] = frame["finish"].str.lower()
    frame["product_family"] = frame["product_family"].str.lower()
    frame["event_type"] = frame["event_type"].str.lower()
    frame["availability_model"] = (
        frame["availability_model"].str.lower()
    )
    frame["status"] = frame["status"].str.lower()
    frame["currency"] = (
        frame["currency"]
        .where(frame["currency"].ne(""), "USD")
        .str.upper()
    )
    frame["universes_beyond"] = (
        frame["universes_beyond"].str.lower().isin(
            {"1", "true", "yes", "y"}
        )
    )
    for column in ("msrp_usd", "card_count"):
        frame[column] = pd.to_numeric(
            frame[column],
            errors="coerce",
        )
    for column in (
        "release_date",
        "sale_start_date",
        "sale_end_date",
    ):
        parsed = pd.to_datetime(frame[column], errors="coerce")
        frame[column] = parsed.dt.date.astype("string").fillna("")
    return frame, exists


def load_source_prices(
    path: Path = SOURCE_PRICES_PATH,
) -> tuple[pd.DataFrame, bool]:
    frame, exists = _load(path, SOURCE_PRICE_COLUMNS)
    if frame.empty:
        return frame, exists

    frame["source_name"] = frame["source_name"].str.lower()
    frame["currency"] = (
        frame["currency"]
        .where(frame["currency"].ne(""), "USD")
        .str.upper()
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
    return frame, exists


def load_match_overrides(
    path: Path = MATCH_OVERRIDES_PATH,
) -> tuple[pd.DataFrame, bool]:
    frame, exists = _load(path, OVERRIDE_COLUMNS)
    if not frame.empty:
        frame["source_name"] = frame["source_name"].str.lower()
        frame["override_action"] = (
            frame["override_action"].str.lower()
        )
    return frame, exists
