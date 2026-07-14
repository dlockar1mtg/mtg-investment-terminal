from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from terminal2.config import ROOT_DIR

from .identifiers import stable_key
from .registry import (
    REGISTRY_PATH,
    load_secret_lair_registry,
)


PRICE_PATH = (
    Path(ROOT_DIR)
    / "data"
    / "terminal2"
    / "secret_lair_price_observations.csv"
)
PRICE_TEMPLATE_PATH = (
    Path(ROOT_DIR)
    / "data"
    / "templates"
    / "secret_lair_price_observations_template.csv"
)

PRICE_COLUMNS = (
    "observation_date",
    "secret_lair_id",
    "source_name",
    "market_price",
    "low_price",
    "listing_count",
    "sales_count_30d",
    "currency",
    "source_url",
    "source_record_id",
    "price_data_quality",
    "notes",
)


@dataclass(frozen=True)
class PricingBuildResult:
    datasets: dict[str, pd.DataFrame]
    price_path: str
    price_file_exists: bool


def create_price_template(
    destination: Path = PRICE_PATH,
    *,
    overwrite: bool = False,
) -> Path:
    destination = Path(destination)
    if destination.exists() and not overwrite:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    pd.read_csv(
        PRICE_TEMPLATE_PATH,
        dtype=str,
    ).to_csv(destination, index=False)
    return destination


def load_price_observations(
    path: Path = PRICE_PATH,
) -> tuple[pd.DataFrame, bool]:
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=PRICE_COLUMNS), False

    frame = pd.read_csv(path)
    for column in PRICE_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame = frame[list(PRICE_COLUMNS)].copy()

    frame["observation_date"] = pd.to_datetime(
        frame["observation_date"],
        errors="coerce",
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

    frame = frame.dropna(
        subset=[
            "observation_date",
            "secret_lair_id",
            "source_name",
            "market_price",
        ]
    )
    frame = frame[frame["market_price"] > 0].copy()
    frame["observation_date"] = (
        frame["observation_date"].dt.date.astype(str)
    )

    key = [
        "observation_date",
        "secret_lair_id",
        "source_name",
    ]
    frame = (
        frame.sort_values(key + ["price_data_quality"])
        .drop_duplicates(key, keep="last")
        .sort_values(key)
        .reset_index(drop=True)
    )
    return frame, True


def _enrich(
    observations: pd.DataFrame,
    registry: pd.DataFrame,
) -> pd.DataFrame:
    if observations.empty:
        columns = list(PRICE_COLUMNS) + [
            "drop_name",
            "variant_name",
            "finish",
            "release_date",
            "msrp_usd",
            "franchise",
        ]
        return pd.DataFrame(columns=columns)

    metadata_columns = [
        "secret_lair_id",
        "drop_name",
        "variant_name",
        "finish",
        "release_date",
        "msrp_usd",
        "franchise",
        "product_family",
    ]
    metadata = registry.copy()
    for column in metadata_columns:
        if column not in metadata.columns:
            metadata[column] = pd.NA

    return observations.merge(
        metadata[metadata_columns],
        on="secret_lair_id",
        how="left",
        validate="many_to_one",
    )


def _current_prices(enriched: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "secret_lair_id",
        "drop_name",
        "variant_name",
        "finish",
        "observation_date",
        "source_name",
        "market_price",
        "low_price",
        "listing_count",
        "sales_count_30d",
        "currency",
        "msrp_usd",
        "premium_to_msrp",
        "premium_to_msrp_pct",
        "price_age_days",
        "price_freshness",
        "price_data_quality",
    ]
    if enriched.empty:
        return pd.DataFrame(columns=columns)

    frame = enriched.copy()
    frame["_date"] = pd.to_datetime(
        frame["observation_date"],
        errors="coerce",
    )
    frame = (
        frame.sort_values(
            [
                "secret_lair_id",
                "_date",
                "price_data_quality",
            ]
        )
        .groupby(
            "secret_lair_id",
            as_index=False,
        )
        .tail(1)
        .copy()
    )

    frame["msrp_usd"] = pd.to_numeric(
        frame["msrp_usd"],
        errors="coerce",
    )
    frame["premium_to_msrp"] = (
        frame["market_price"] - frame["msrp_usd"]
    ).round(2)
    frame["premium_to_msrp_pct"] = np.where(
        frame["msrp_usd"] > 0,
        frame["premium_to_msrp"] / frame["msrp_usd"],
        np.nan,
    )
    today = pd.Timestamp.now(
        tz="UTC"
    ).tz_localize(None).normalize()
    frame["price_age_days"] = (
        today - frame["_date"]
    ).dt.days
    frame["price_freshness"] = np.select(
        [
            frame["price_age_days"] <= 7,
            frame["price_age_days"] <= 30,
            frame["price_age_days"] <= 90,
        ],
        ["Fresh", "Current", "Aging"],
        default="Stale",
    )
    return frame[columns].sort_values(
        "secret_lair_id"
    ).reset_index(drop=True)


def _monthly_prices(enriched: pd.DataFrame) -> pd.DataFrame:
    columns = list(enriched.columns) + ["year_month"]
    if enriched.empty:
        return pd.DataFrame(columns=columns)

    frame = enriched.copy()
    frame["_date"] = pd.to_datetime(
        frame["observation_date"],
        errors="coerce",
    )
    frame["year_month"] = (
        frame["_date"].dt.to_period("M").astype(str)
    )
    key = [
        "year_month",
        "secret_lair_id",
        "source_name",
    ]
    return (
        frame.sort_values(key + ["_date"])
        .groupby(key, as_index=False)
        .tail(1)
        .drop(columns=["_date"])
        .sort_values(key)
        .reset_index(drop=True)
    )


def _nearest_return(
    group: pd.DataFrame,
    latest_date: pd.Timestamp,
    latest_price: float,
    days: int,
) -> float:
    target = latest_date - pd.Timedelta(days=days)
    eligible = group[group["_date"] <= target]
    if eligible.empty:
        return np.nan
    prior = eligible.sort_values("_date").iloc[-1]
    prior_price = float(prior["market_price"])
    if prior_price <= 0:
        return np.nan
    return latest_price / prior_price - 1


def _returns(
    enriched: pd.DataFrame,
    current: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "secret_lair_id",
        "drop_name",
        "variant_name",
        "finish",
        "current_price",
        "msrp_usd",
        "inception_return",
        "annualized_return",
        "return_30d",
        "return_90d",
        "return_365d",
        "peak_price",
        "drawdown_from_peak",
        "observation_count",
    ]
    if enriched.empty:
        return pd.DataFrame(columns=columns)

    frame = enriched.copy()
    frame["_date"] = pd.to_datetime(
        frame["observation_date"],
        errors="coerce",
    )
    rows = []
    current_map = current.set_index("secret_lair_id")
    for asset_id, group in frame.groupby("secret_lair_id"):
        group = group.sort_values("_date")
        latest = current_map.loc[asset_id]
        latest_price = float(latest["market_price"])
        latest_date = pd.to_datetime(
            latest["observation_date"]
        )
        msrp = pd.to_numeric(
            pd.Series([latest.get("msrp_usd")]),
            errors="coerce",
        ).iloc[0]
        release = pd.to_datetime(
            group["release_date"].dropna().iloc[0]
            if group["release_date"].notna().any()
            else group["_date"].min(),
            errors="coerce",
        )
        years = max(
            (latest_date - release).days / 365.25,
            0,
        )
        inception = (
            latest_price / float(msrp) - 1
            if pd.notna(msrp) and msrp > 0
            else np.nan
        )
        annualized = (
            (latest_price / float(msrp)) ** (1 / years) - 1
            if pd.notna(msrp)
            and msrp > 0
            and years >= 0.25
            else np.nan
        )
        peak = float(group["market_price"].max())
        rows.append({
            "secret_lair_id": asset_id,
            "drop_name": latest.get("drop_name"),
            "variant_name": latest.get("variant_name"),
            "finish": latest.get("finish"),
            "current_price": round(latest_price, 2),
            "msrp_usd": msrp,
            "inception_return": inception,
            "annualized_return": annualized,
            "return_30d": _nearest_return(
                group, latest_date, latest_price, 30
            ),
            "return_90d": _nearest_return(
                group, latest_date, latest_price, 90
            ),
            "return_365d": _nearest_return(
                group, latest_date, latest_price, 365
            ),
            "peak_price": round(peak, 2),
            "drawdown_from_peak": (
                latest_price / peak - 1
                if peak > 0 else np.nan
            ),
            "observation_count": int(len(group)),
        })
    return pd.DataFrame(rows, columns=columns)


def _coverage(enriched: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "secret_lair_id",
        "drop_name",
        "variant_name",
        "finish",
        "observation_count",
        "source_count",
        "first_observation_date",
        "latest_observation_date",
        "history_span_days",
        "latest_price_age_days",
        "coverage_status",
    ]
    if enriched.empty:
        return pd.DataFrame(columns=columns)

    frame = enriched.copy()
    frame["_date"] = pd.to_datetime(
        frame["observation_date"],
        errors="coerce",
    )
    grouped = frame.groupby(
        "secret_lair_id",
        as_index=False,
    ).agg(
        drop_name=("drop_name", "first"),
        variant_name=("variant_name", "first"),
        finish=("finish", "first"),
        observation_count=("market_price", "count"),
        source_count=("source_name", "nunique"),
        first_observation_date=("_date", "min"),
        latest_observation_date=("_date", "max"),
    )
    grouped["history_span_days"] = (
        grouped["latest_observation_date"]
        - grouped["first_observation_date"]
    ).dt.days
    today = pd.Timestamp.now(
        tz="UTC"
    ).tz_localize(None).normalize()
    grouped["latest_price_age_days"] = (
        today - grouped["latest_observation_date"]
    ).dt.days
    grouped["coverage_status"] = np.select(
        [
            (grouped["observation_count"] >= 12)
            & (grouped["history_span_days"] >= 180),
            grouped["observation_count"] >= 6,
            grouped["observation_count"] >= 2,
        ],
        ["Strong", "Moderate", "Limited"],
        default="Insufficient",
    )
    grouped["first_observation_date"] = (
        grouped["first_observation_date"].dt.date.astype(str)
    )
    grouped["latest_observation_date"] = (
        grouped["latest_observation_date"].dt.date.astype(str)
    )
    return grouped[columns]


def _quality(
    observations: pd.DataFrame,
    registry: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "validation_id",
        "secret_lair_id",
        "severity",
        "rule_name",
        "message",
    ]
    rows = []

    def add(asset_id, severity, rule, message):
        rows.append({
            "validation_id": stable_key(
                "SLP",
                f"{asset_id}|{rule}|{message}",
            ),
            "secret_lair_id": asset_id or "UNASSIGNED",
            "severity": severity,
            "rule_name": rule,
            "message": message,
        })

    if registry.empty:
        add(
            "UNASSIGNED",
            "Warning",
            "empty_registry",
            "Secret Lair registry is empty.",
        )
    if observations.empty:
        add(
            "UNASSIGNED",
            "Warning",
            "empty_price_history",
            "No Secret Lair price observations have been imported.",
        )
        return pd.DataFrame(rows, columns=columns)

    valid_ids = set(registry["secret_lair_id"].astype(str))
    unknown = sorted(
        set(observations["secret_lair_id"].astype(str))
        - valid_ids
    )
    for asset_id in unknown:
        add(
            asset_id,
            "Error",
            "unknown_secret_lair_id",
            "Price observation references an unknown registry asset.",
        )

    duplicates = observations[
        observations.duplicated(
            [
                "observation_date",
                "secret_lair_id",
                "source_name",
            ],
            keep=False,
        )
    ]
    for asset_id in sorted(
        duplicates["secret_lair_id"].astype(str).unique()
    ):
        add(
            asset_id,
            "Error",
            "duplicate_price_key",
            "Duplicate asset/date/source observation exists.",
        )

    for asset_id, group in observations.groupby(
        "secret_lair_id"
    ):
        if group["source_name"].nunique() == 1:
            add(
                asset_id,
                "Info",
                "single_source",
                "Pricing currently relies on one source.",
            )
        quality = pd.to_numeric(
            group["price_data_quality"],
            errors="coerce",
        )
        if quality.notna().any() and quality.mean() < 50:
            add(
                asset_id,
                "Warning",
                "low_source_quality",
                "Average source quality is below 50.",
            )

    return pd.DataFrame(rows, columns=columns)


def _summary(
    current: pd.DataFrame,
    observations: pd.DataFrame,
    quality: pd.DataFrame,
) -> pd.DataFrame:
    premiums = pd.to_numeric(
        current.get(
            "premium_to_msrp_pct",
            pd.Series(dtype=float),
        ),
        errors="coerce",
    )
    prices = pd.to_numeric(
        current.get(
            "market_price",
            pd.Series(dtype=float),
        ),
        errors="coerce",
    )
    return pd.DataFrame([{
        "snapshot_date": datetime.now(
            timezone.utc
        ).date().isoformat(),
        "priced_asset_count": int(len(current)),
        "observation_count": int(len(observations)),
        "source_count": int(
            observations["source_name"].nunique()
            if not observations.empty else 0
        ),
        "average_market_price": round(
            float(prices.mean()), 2
        ) if prices.notna().any() else 0.0,
        "average_premium_to_msrp": round(
            float(premiums.mean()), 4
        ) if premiums.notna().any() else 0.0,
        "fresh_price_count": int(
            current["price_freshness"].isin(
                ["Fresh", "Current"]
            ).sum()
        ) if not current.empty else 0,
        "quality_error_count": int(
            quality["severity"].eq("Error").sum()
        ) if not quality.empty else 0,
        "quality_warning_count": int(
            quality["severity"].eq("Warning").sum()
        ) if not quality.empty else 0,
    }])


def build_secret_lair_pricing_datasets(
    *,
    registry_path: Path = REGISTRY_PATH,
    price_path: Path = PRICE_PATH,
) -> PricingBuildResult:
    registry, _ = load_secret_lair_registry(
        registry_path
    )
    observations, exists = load_price_observations(
        price_path
    )
    enriched = _enrich(observations, registry)
    current = _current_prices(enriched)
    monthly = _monthly_prices(enriched)
    returns = _returns(enriched, current)
    coverage = _coverage(enriched)
    quality = _quality(observations, registry)
    summary = _summary(current, observations, quality)

    return PricingBuildResult(
        datasets={
            "secret_lair_price_observations": enriched,
            "secret_lair_current_prices": current,
            "secret_lair_monthly_prices": monthly,
            "secret_lair_returns": returns,
            "secret_lair_price_coverage": coverage,
            "secret_lair_price_quality": quality,
            "secret_lair_market_summary": summary,
        },
        price_path=str(price_path),
        price_file_exists=exists,
    )
