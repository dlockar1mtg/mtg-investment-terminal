
from __future__ import annotations

from pathlib import Path
import math

import numpy as np
import pandas as pd

from config import (
    HISTORY_DIR,
    INVESTMENT_FEATURES_FILE,
    HISTORICAL_METRICS_FILE,
    RELEASE_METADATA_FILE,
)


ROOT = Path(__file__).resolve().parents[1]

UNIVERSAL_HISTORY_FILE = (
    ROOT
    / "data"
    / "operations"
    / "mtg_universal_history_ledger"
    / "universal_mtg_daily_consolidated_ledger.csv"
)

CURRENT_OBSERVATIONS_FILE = (
    ROOT
    / "data"
    / "market_database"
    / "daily_price_observations.csv"
)


def _clean_id_series(series: pd.Series) -> pd.Series:
    return (
        series.astype("string")
        .fillna("")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


def _normalize_history_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()

    result = frame.copy()

    rename_map = {
        "canonical_product_name": "box_name",
        "observation_date": "snapshot_date",
        "consolidated_market_price": "current_price",
    }

    result = result.rename(
        columns={
            old: new
            for old, new in rename_map.items()
            if old in result.columns and new not in result.columns
        }
    )

    required = {
        "box_name",
        "snapshot_date",
        "current_price",
    }

    if not required.issubset(result.columns):
        return pd.DataFrame()

    if "tcgplayer_product_id" not in result.columns:
        result["tcgplayer_product_id"] = ""

    result["tcgplayer_product_id"] = _clean_id_series(
        result["tcgplayer_product_id"]
    )

    result["snapshot_date"] = pd.to_datetime(
        result["snapshot_date"],
        errors="coerce",
        utc=True,
    ).dt.tz_localize(None)

    result["current_price"] = pd.to_numeric(
        result["current_price"],
        errors="coerce",
    )

    result = result.dropna(
        subset=[
            "box_name",
            "snapshot_date",
            "current_price",
        ]
    )

    result = result[result["current_price"] > 0].copy()

    return result


def load_legacy_history_snapshots(
    history_dir=HISTORY_DIR,
) -> pd.DataFrame:
    history_dir = Path(history_dir)

    if not history_dir.exists():
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []

    for file in history_dir.glob("*.csv"):
        try:
            frame = pd.read_csv(file)

            if (
                "snapshot_date" not in frame.columns
                and "observation_date" in frame.columns
            ):
                frame["snapshot_date"] = frame[
                    "observation_date"
                ]

            if "snapshot_date" not in frame.columns:
                inferred = file.stem.replace(
                    "price_snapshot_",
                    "",
                )
                frame["snapshot_date"] = inferred

            if (
                "current_price" not in frame.columns
                and "market_price" in frame.columns
            ):
                frame["current_price"] = frame[
                    "market_price"
                ]

            normalized = _normalize_history_frame(frame)

            if not normalized.empty:
                frames.append(normalized)

        except Exception:
            continue

    if not frames:
        return pd.DataFrame()

    return pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    )


def load_universal_history() -> pd.DataFrame:
    if not UNIVERSAL_HISTORY_FILE.is_file():
        return pd.DataFrame()

    frame = pd.read_csv(UNIVERSAL_HISTORY_FILE)

    return _normalize_history_frame(frame)


def load_current_observations() -> pd.DataFrame:
    if not CURRENT_OBSERVATIONS_FILE.is_file():
        return pd.DataFrame()

    frame = pd.read_csv(CURRENT_OBSERVATIONS_FILE)

    return _normalize_history_frame(frame)


def load_history_snapshots(
    history_dir=HISTORY_DIR,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    universal = load_universal_history()

    if not universal.empty:
        universal["history_source_layer"] = (
            "UNIVERSAL_GOVERNED_LEDGER"
        )
        frames.append(universal)

    legacy = load_legacy_history_snapshots(history_dir)

    if not legacy.empty:
        legacy["history_source_layer"] = (
            "LEGACY_HISTORY_DIRECTORY"
        )
        frames.append(legacy)

    current = load_current_observations()

    if not current.empty:
        current["history_source_layer"] = (
            "CURRENT_TCGCSV_REFRESH"
        )
        frames.append(current)

    if not frames:
        return pd.DataFrame()

    history = pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    )

    history["tcgplayer_product_id"] = _clean_id_series(
        history["tcgplayer_product_id"]
    )

    history = history.sort_values(
        [
            "tcgplayer_product_id",
            "box_name",
            "snapshot_date",
            "history_source_layer",
        ]
    )

    identity_key = history[
        "tcgplayer_product_id"
    ].where(
        history["tcgplayer_product_id"] != "",
        history["box_name"].astype("string"),
    )

    history["_identity_key"] = identity_key

    source_priority = {
        "LEGACY_HISTORY_DIRECTORY": 1,
        "UNIVERSAL_GOVERNED_LEDGER": 2,
        "CURRENT_TCGCSV_REFRESH": 3,
    }

    history["_source_priority"] = (
        history["history_source_layer"]
        .map(source_priority)
        .fillna(0)
    )

    history = history.sort_values(
        [
            "_identity_key",
            "snapshot_date",
            "_source_priority",
        ]
    )

    history = history.drop_duplicates(
        subset=[
            "_identity_key",
            "snapshot_date",
        ],
        keep="last",
    )

    return history.drop(
        columns=[
            "_identity_key",
            "_source_priority",
        ]
    )


def _price_days_ago(
    group: pd.DataFrame,
    days: int,
) -> float:
    if group.empty:
        return np.nan

    latest_date = group["snapshot_date"].max()
    target_date = latest_date - pd.Timedelta(days=days)

    eligible = group[
        group["snapshot_date"] <= target_date
    ]

    if eligible.empty:
        return np.nan

    return float(
        eligible.iloc[-1]["current_price"]
    )


def _safe_return(
    current: float,
    previous: float,
) -> float:
    if (
        pd.isna(previous)
        or previous <= 0
        or pd.isna(current)
    ):
        return np.nan

    return (current / previous) - 1


def _infer_observation_frequency(
    dates: pd.Series,
) -> tuple[str, float]:
    clean_dates = (
        pd.to_datetime(dates, errors="coerce")
        .dropna()
        .sort_values()
        .drop_duplicates()
    )

    if len(clean_dates) < 2:
        return "INSUFFICIENT", np.nan

    day_gaps = (
        clean_dates.diff()
        .dt.total_seconds()
        .div(86400)
        .dropna()
    )

    if day_gaps.empty:
        return "INSUFFICIENT", np.nan

    median_gap = float(day_gaps.median())

    if median_gap <= 2:
        return "DAILY", math.sqrt(365)

    if median_gap <= 10:
        return "WEEKLY", math.sqrt(52)

    if median_gap <= 45:
        return "MONTHLY", math.sqrt(12)

    if median_gap <= 100:
        return "QUARTERLY", math.sqrt(4)

    return "IRREGULAR", np.nan


def build_historical_metrics(
    history_df: pd.DataFrame,
) -> pd.DataFrame:
    if history_df is None or history_df.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []

    id_available = (
        "tcgplayer_product_id"
        in history_df.columns
    )

    group_field = (
        "tcgplayer_product_id"
        if id_available
        else "box_name"
    )

    for group_id, group in history_df.groupby(
        group_field,
        dropna=False,
    ):
        group = (
            group.sort_values("snapshot_date")
            .drop_duplicates(
                subset=["snapshot_date"],
                keep="last",
            )
            .copy()
        )

        if group.empty:
            continue

        latest = group.iloc[-1]
        current = float(
            latest["current_price"]
        )

        prices = pd.to_numeric(
            group["current_price"],
            errors="coerce",
        ).dropna()

        if prices.empty:
            continue

        high = float(prices.max())
        low = float(prices.min())

        returns = (
            prices.pct_change()
            .replace(
                [np.inf, -np.inf],
                np.nan,
            )
            .dropna()
        )

        frequency, annualization_factor = (
            _infer_observation_frequency(
                group["snapshot_date"]
            )
        )

        volatility = np.nan

        if (
            len(returns) >= 2
            and not pd.isna(
                annualization_factor
            )
        ):
            volatility = float(
                returns.std()
                * annualization_factor
            )

        p30 = _price_days_ago(group, 30)
        p90 = _price_days_ago(group, 90)
        p180 = _price_days_ago(group, 180)
        p365 = _price_days_ago(group, 365)

        source_layers = ""

        if "history_source_layer" in group.columns:
            source_layers = "|".join(
                sorted(
                    {
                        str(value).strip()
                        for value in group[
                            "history_source_layer"
                        ].dropna()
                        if str(value).strip()
                    }
                )
            )

        rows.append(
            {
                "tcgplayer_product_id": (
                    str(group_id).strip()
                    if id_available
                    else ""
                ),
                "box_name": str(
                    latest["box_name"]
                ).strip(),
                "history_observations": len(
                    group
                ),
                "first_snapshot_date": (
                    group["snapshot_date"]
                    .min()
                    .date()
                    .isoformat()
                ),
                "latest_snapshot_date": (
                    group["snapshot_date"]
                    .max()
                    .date()
                    .isoformat()
                ),
                "current_price_history": round(
                    current,
                    2,
                ),
                "history_high_price": round(
                    high,
                    2,
                ),
                "history_low_price": round(
                    low,
                    2,
                ),
                "drawdown_from_high": round(
                    (current / high) - 1,
                    4,
                )
                if high > 0
                else np.nan,
                "distance_from_low": round(
                    (current / low) - 1,
                    4,
                )
                if low > 0
                else np.nan,
                "return_30d": round(
                    _safe_return(
                        current,
                        p30,
                    ),
                    4,
                )
                if not pd.isna(p30)
                else np.nan,
                "return_90d": round(
                    _safe_return(
                        current,
                        p90,
                    ),
                    4,
                )
                if not pd.isna(p90)
                else np.nan,
                "return_180d": round(
                    _safe_return(
                        current,
                        p180,
                    ),
                    4,
                )
                if not pd.isna(p180)
                else np.nan,
                "return_365d": round(
                    _safe_return(
                        current,
                        p365,
                    ),
                    4,
                )
                if not pd.isna(p365)
                else np.nan,
                "annualized_volatility": round(
                    volatility,
                    4,
                )
                if not pd.isna(volatility)
                else np.nan,
                "observation_frequency": (
                    frequency
                ),
                "annualization_factor": round(
                    annualization_factor,
                    6,
                )
                if not pd.isna(
                    annualization_factor
                )
                else np.nan,
                "history_source_layers": (
                    source_layers
                ),
            }
        )

    metrics = pd.DataFrame(rows)

    Path(
        HISTORICAL_METRICS_FILE
    ).parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    metrics.to_csv(
        HISTORICAL_METRICS_FILE,
        index=False,
    )

    return metrics


def load_release_metadata() -> pd.DataFrame:
    path = Path(RELEASE_METADATA_FILE)

    if not path.exists():
        return pd.DataFrame(
            columns=[
                "box_name",
                "release_date",
                "release_msrp",
                "notes",
            ]
        )

    return pd.read_csv(path)


def _score_momentum(
    row: pd.Series,
) -> float:
    score = 50

    for value, weight in [
        (row.get("return_90d"), 60),
        (row.get("return_180d"), 40),
    ]:
        if pd.isna(value):
            continue

        score += max(
            -20,
            min(20, value * weight),
        )

    r30 = row.get("return_30d")

    if (
        not pd.isna(r30)
        and r30 > 0.35
    ):
        score -= 10

    return round(
        max(0, min(100, score)),
        2,
    )


def _score_drawdown(
    row: pd.Series,
) -> float:
    drawdown = row.get(
        "drawdown_from_high"
    )

    if pd.isna(drawdown):
        return 50

    if drawdown >= -0.05:
        return 55

    if drawdown >= -0.20:
        return 70

    if drawdown >= -0.40:
        return 55

    return 35


def _score_volatility(
    row: pd.Series,
) -> float:
    volatility = row.get(
        "annualized_volatility"
    )

    if pd.isna(volatility):
        return 50

    if volatility < 0.15:
        return 75

    if volatility < 0.30:
        return 65

    if volatility < 0.55:
        return 50

    return 35


def build_investment_features(
    model_df: pd.DataFrame,
) -> pd.DataFrame:
    model = model_df.copy()

    model["tcgplayer_product_id"] = (
        _clean_id_series(
            model.get(
                "tcgplayer_product_id",
                model.get(
                    "approved_tcgplayer_product_id",
                    pd.Series(
                        "",
                        index=model.index,
                    ),
                ),
            )
        )
    )

    history = load_history_snapshots()
    metrics = build_historical_metrics(
        history
    )

    metric_columns = [
        "history_observations",
        "first_snapshot_date",
        "latest_snapshot_date",
        "current_price_history",
        "history_high_price",
        "history_low_price",
        "drawdown_from_high",
        "distance_from_low",
        "return_30d",
        "return_90d",
        "return_180d",
        "return_365d",
        "annualized_volatility",
        "observation_frequency",
        "annualization_factor",
        "history_source_layers",
    ]

    if not metrics.empty:
        metrics[
            "tcgplayer_product_id"
        ] = _clean_id_series(
            metrics[
                "tcgplayer_product_id"
            ]
        )

        metrics = metrics.drop_duplicates(
            subset=[
                "tcgplayer_product_id"
            ],
            keep="last",
        )

        model = model.merge(
            metrics[
                [
                    "tcgplayer_product_id",
                    *metric_columns,
                ]
            ],
            on="tcgplayer_product_id",
            how="left",
            validate="one_to_one",
        )

    else:
        for column in metric_columns:
            model[column] = np.nan

    release = load_release_metadata()

    if not release.empty:
        model = model.merge(
            release,
            on="box_name",
            how="left",
        )

    model["momentum_score"] = (
        model.apply(
            _score_momentum,
            axis=1,
        )
    )

    model["drawdown_score"] = (
        model.apply(
            _score_drawdown,
            axis=1,
        )
    )

    model["price_stability_score"] = (
        model.apply(
            _score_volatility,
            axis=1,
        )
    )

    observations = pd.to_numeric(
        model.get(
            "history_observations"
        ),
        errors="coerce",
    ).fillna(0)

    model["history_confidence"] = (
        observations
        .div(30)
        .mul(100)
        .clip(
            lower=0,
            upper=100,
        )
        .round(1)
    )

    model["investment_feature_score"] = (
        model["momentum_score"] * 0.35
        + model["drawdown_score"] * 0.30
        + model["price_stability_score"] * 0.20
        + model["history_confidence"] * 0.15
    ).round(2)

    Path(
        INVESTMENT_FEATURES_FILE
    ).parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    model.to_csv(
        INVESTMENT_FEATURES_FILE,
        index=False,
    )

    return model