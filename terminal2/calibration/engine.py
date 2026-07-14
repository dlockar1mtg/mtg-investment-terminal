from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib

import numpy as np
import pandas as pd

from terminal2.config import ROOT_DIR


MODEL_VERSION = "2.9.0"
ARCHIVE_ROOT = (
    Path(ROOT_DIR)
    / "data"
    / "terminal2"
    / "calibration"
)
VINTAGE_ARCHIVE_PATH = (
    ARCHIVE_ROOT / "forecast_vintages.csv"
)

VINTAGE_COLUMNS = (
    "forecast_run_id",
    "forecast_as_of_date",
    "forecast_created_at_utc",
    "investment_product_id",
    "box_name",
    "set_name",
    "product_type",
    "horizon_months",
    "target_date",
    "current_price",
    "forecast_price",
    "forecast_expected_return",
    "forecast_expected_cagr",
    "probability_of_loss",
    "forecast_confidence",
    "conviction_score",
    "recommendation",
    "recommendation_score",
    "overall_confidence_score",
    "overall_risk_score",
    "model_version",
)

OUTCOME_COLUMNS = (
    "forecast_run_id",
    "forecast_as_of_date",
    "investment_product_id",
    "box_name",
    "product_type",
    "horizon_months",
    "target_date",
    "realized_observation_date",
    "realized_price",
    "realized_return",
    "days_from_target",
    "maturity_status",
)

ERROR_COLUMNS = (
    "forecast_run_id",
    "forecast_as_of_date",
    "investment_product_id",
    "box_name",
    "product_type",
    "horizon_months",
    "model_version",
    "forecast_price",
    "realized_price",
    "absolute_price_error",
    "percentage_price_error",
    "absolute_percentage_error",
    "squared_price_error",
    "forecast_expected_return",
    "realized_return",
    "return_error",
    "direction_correct",
)

RECOMMENDATION_COLUMNS = (
    "forecast_run_id",
    "forecast_as_of_date",
    "investment_product_id",
    "box_name",
    "product_type",
    "horizon_months",
    "recommendation",
    "recommendation_score",
    "overall_confidence_score",
    "realized_return",
    "recommendation_success",
)


@dataclass(frozen=True)
class CalibrationBuildResult:
    datasets: dict[str, pd.DataFrame]
    archive_path: str
    new_vintage_rows: int


def _empty(columns) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))


def _read_csv(path: Path, columns=()) -> pd.DataFrame:
    if not path.exists():
        return _empty(columns)
    frame = pd.read_csv(path)
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame


def _current_path(category: str, name: str) -> Path:
    return (
        Path(ROOT_DIR)
        / "data"
        / "warehouse"
        / "current"
        / category
        / f"{name}.csv"
    )


def _forecast_run_id(
    as_of_date: str,
    model_version: str,
    horizons: pd.DataFrame,
) -> str:
    product_ids = "|".join(
        sorted(
            horizons["investment_product_id"]
            .astype(str)
            .unique()
            .tolist()
        )
    )
    digest = hashlib.sha1(
        f"{as_of_date}|{model_version}|{product_ids}".encode(
            "utf-8"
        )
    ).hexdigest()[:12].upper()
    return f"CAL-{as_of_date.replace('-', '')}-{digest}"


def _build_current_vintage(
    as_of_date: str | None = None,
    model_version: str = MODEL_VERSION,
) -> pd.DataFrame:
    horizons = _read_csv(
        _current_path(
            "intelligence",
            "forecast_horizons",
        )
    )
    summary = _read_csv(
        _current_path(
            "intelligence",
            "forecast_product_summary",
        )
    )
    recommendations = _read_csv(
        _current_path(
            "intelligence",
            "intelligence_recommendations",
        )
    )

    if horizons.empty:
        return _empty(VINTAGE_COLUMNS)

    as_of = pd.Timestamp(
        as_of_date
        or datetime.now(timezone.utc).date().isoformat()
    )
    run_id = _forecast_run_id(
        as_of.date().isoformat(),
        model_version,
        horizons,
    )

    summary_columns = [
        column
        for column in (
            "investment_product_id",
            "set_name",
            "product_type",
            "forecast_expected_cagr",
            "conviction_score",
        )
        if column in summary.columns
    ]
    recommendation_columns = [
        column
        for column in (
            "investment_product_id",
            "recommendation",
            "recommendation_score",
            "overall_confidence_score",
            "overall_risk_score",
        )
        if column in recommendations.columns
    ]

    frame = horizons.merge(
        summary[summary_columns],
        on="investment_product_id",
        how="left",
        validate="many_to_one",
    )
    if recommendation_columns:
        frame = frame.merge(
            recommendations[recommendation_columns],
            on="investment_product_id",
            how="left",
            validate="many_to_one",
        )

    frame["forecast_run_id"] = run_id
    frame["forecast_as_of_date"] = (
        as_of.date().isoformat()
    )
    frame["forecast_created_at_utc"] = (
        datetime.now(timezone.utc).isoformat()
    )
    horizon_months = pd.to_numeric(
        frame["horizon_months"],
        errors="coerce",
    )
    frame["target_date"] = [
        (
            as_of
            + pd.DateOffset(months=int(months))
        ).date().isoformat()
        if pd.notna(months)
        else ""
        for months in horizon_months
    ]
    frame["forecast_price"] = pd.to_numeric(
        frame["base_forecast_price"],
        errors="coerce",
    )
    frame["forecast_expected_return"] = pd.to_numeric(
        frame["expected_return"],
        errors="coerce",
    )
    frame["probability_of_loss"] = pd.to_numeric(
        frame["probability_of_loss"],
        errors="coerce",
    )
    frame["forecast_confidence"] = pd.to_numeric(
        frame["forecast_confidence"],
        errors="coerce",
    )
    frame["model_version"] = model_version

    for column in VINTAGE_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame[list(VINTAGE_COLUMNS)].copy()


def _append_vintage_archive(
    current: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    previous = _read_csv(
        VINTAGE_ARCHIVE_PATH,
        VINTAGE_COLUMNS,
    )
    before = len(previous)
    combined = pd.concat(
        [previous, current],
        ignore_index=True,
    )
    if not combined.empty:
        combined = (
            combined.drop_duplicates(
                [
                    "forecast_run_id",
                    "investment_product_id",
                    "horizon_months",
                ],
                keep="first",
            )
            .sort_values(
                [
                    "forecast_as_of_date",
                    "investment_product_id",
                    "horizon_months",
                ]
            )
            .reset_index(drop=True)
        )
    ARCHIVE_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )
    combined.to_csv(
        VINTAGE_ARCHIVE_PATH,
        index=False,
    )
    return combined, len(combined) - before


def _load_historical_prices() -> pd.DataFrame:
    prices = _read_csv(
        _current_path(
            "products",
            "historical_prices",
        )
    )
    if prices.empty:
        return prices
    prices["observation_date"] = pd.to_datetime(
        prices["observation_date"],
        errors="coerce",
    )
    prices["market_price"] = pd.to_numeric(
        prices["market_price"],
        errors="coerce",
    )
    return prices.dropna(
        subset=[
            "investment_product_id",
            "observation_date",
            "market_price",
        ]
    )


def _match_realized_outcomes(
    vintages: pd.DataFrame,
    historical_prices: pd.DataFrame,
    *,
    evaluation_date: str | None = None,
    tolerance_days: int = 45,
) -> pd.DataFrame:
    if vintages.empty:
        return _empty(OUTCOME_COLUMNS)

    evaluation = pd.Timestamp(
        evaluation_date
        or datetime.now(timezone.utc).date().isoformat()
    )
    prices = historical_prices.copy()
    if not prices.empty:
        daily = (
            prices.groupby(
                [
                    "investment_product_id",
                    "observation_date",
                ],
                as_index=False,
            )["market_price"]
            .median()
            .sort_values(
                [
                    "investment_product_id",
                    "observation_date",
                ]
            )
        )
    else:
        daily = pd.DataFrame(
            columns=[
                "investment_product_id",
                "observation_date",
                "market_price",
            ]
        )

    rows = []
    for _, vintage in vintages.iterrows():
        target = pd.to_datetime(
            vintage["target_date"],
            errors="coerce",
        )
        as_of = pd.to_datetime(
            vintage["forecast_as_of_date"],
            errors="coerce",
        )
        status = "pending"
        realized_date = pd.NaT
        realized_price = np.nan
        realized_return = np.nan
        days_from_target = np.nan

        if pd.notna(target) and target <= evaluation:
            candidates = daily[
                (
                    daily["investment_product_id"]
                    .astype(str)
                    == str(
                        vintage[
                            "investment_product_id"
                        ]
                    )
                )
                & (
                    daily["observation_date"]
                    >= target
                )
                & (
                    daily["observation_date"]
                    <= target
                    + pd.Timedelta(
                        days=tolerance_days
                    )
                )
            ]
            if not candidates.empty:
                observation = candidates.iloc[0]
                realized_date = observation[
                    "observation_date"
                ]
                realized_price = float(
                    observation["market_price"]
                )
                current_price = pd.to_numeric(
                    pd.Series(
                        [vintage["current_price"]]
                    ),
                    errors="coerce",
                ).iloc[0]
                if (
                    pd.notna(current_price)
                    and current_price > 0
                ):
                    realized_return = (
                        realized_price
                        / float(current_price)
                        - 1
                    )
                days_from_target = int(
                    (realized_date - target).days
                )
                status = "matured"
            else:
                status = "missing_realized_price"

        rows.append(
            {
                "forecast_run_id": vintage[
                    "forecast_run_id"
                ],
                "forecast_as_of_date": (
                    as_of.date().isoformat()
                    if pd.notna(as_of)
                    else ""
                ),
                "investment_product_id": vintage[
                    "investment_product_id"
                ],
                "box_name": vintage.get("box_name"),
                "product_type": vintage.get(
                    "product_type"
                ),
                "horizon_months": vintage[
                    "horizon_months"
                ],
                "target_date": (
                    target.date().isoformat()
                    if pd.notna(target)
                    else ""
                ),
                "realized_observation_date": (
                    realized_date.date().isoformat()
                    if pd.notna(realized_date)
                    else ""
                ),
                "realized_price": realized_price,
                "realized_return": realized_return,
                "days_from_target": days_from_target,
                "maturity_status": status,
            }
        )

    return pd.DataFrame(
        rows,
        columns=OUTCOME_COLUMNS,
    )


def _forecast_errors(
    vintages: pd.DataFrame,
    outcomes: pd.DataFrame,
) -> pd.DataFrame:
    matured = outcomes[
        outcomes["maturity_status"].eq("matured")
    ]
    if matured.empty:
        return _empty(ERROR_COLUMNS)

    merge_columns = [
        "forecast_run_id",
        "investment_product_id",
        "horizon_months",
    ]
    frame = vintages.merge(
        matured[
            merge_columns
            + [
                "realized_price",
                "realized_return",
            ]
        ],
        on=merge_columns,
        how="inner",
        validate="one_to_one",
    )

    forecast_price = pd.to_numeric(
        frame["forecast_price"],
        errors="coerce",
    )
    realized_price = pd.to_numeric(
        frame["realized_price"],
        errors="coerce",
    )
    forecast_return = pd.to_numeric(
        frame["forecast_expected_return"],
        errors="coerce",
    )
    realized_return = pd.to_numeric(
        frame["realized_return"],
        errors="coerce",
    )

    price_error = forecast_price - realized_price
    frame["absolute_price_error"] = (
        price_error.abs()
    )
    frame["percentage_price_error"] = np.where(
        realized_price > 0,
        price_error / realized_price,
        np.nan,
    )
    frame["absolute_percentage_error"] = (
        pd.Series(
            frame["percentage_price_error"]
        ).abs()
    )
    frame["squared_price_error"] = (
        price_error ** 2
    )
    frame["return_error"] = (
        forecast_return - realized_return
    )
    frame["direction_correct"] = (
        np.sign(forecast_return.fillna(0))
        == np.sign(realized_return.fillna(0))
    )

    for column in ERROR_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame[list(ERROR_COLUMNS)].copy()


def _recommendation_performance(
    vintages: pd.DataFrame,
    outcomes: pd.DataFrame,
) -> pd.DataFrame:
    matured = outcomes[
        outcomes["maturity_status"].eq("matured")
    ]
    if matured.empty:
        return _empty(RECOMMENDATION_COLUMNS)

    keys = [
        "forecast_run_id",
        "investment_product_id",
        "horizon_months",
    ]
    frame = vintages.merge(
        matured[
            keys + ["realized_return"]
        ],
        on=keys,
        how="inner",
        validate="one_to_one",
    )

    realized = pd.to_numeric(
        frame["realized_return"],
        errors="coerce",
    )
    recommendation = frame[
        "recommendation"
    ].fillna("Insufficient Data")

    success = np.select(
        [
            recommendation.eq("Strong Buy"),
            recommendation.eq("Buy"),
            recommendation.eq("Watch"),
            recommendation.eq("Hold"),
            recommendation.eq("Avoid"),
        ],
        [
            realized >= 0.10,
            realized >= 0.05,
            realized >= 0,
            realized >= -0.05,
            realized < 0,
        ],
        default=False,
    )
    frame["recommendation_success"] = success

    for column in RECOMMENDATION_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame[
        list(RECOMMENDATION_COLUMNS)
    ].copy()


def _probability_bucket(
    values: pd.Series,
) -> pd.Series:
    return pd.cut(
        values,
        bins=[
            -0.001,
            0.20,
            0.40,
            0.60,
            0.80,
            1.001,
        ],
        labels=[
            "0-20%",
            "20-40%",
            "40-60%",
            "60-80%",
            "80-100%",
        ],
    ).astype(str)


def _confidence_bucket(
    values: pd.Series,
) -> pd.Series:
    return pd.cut(
        values,
        bins=[-0.001, 40, 60, 75, 90, 100.001],
        labels=[
            "0-40",
            "40-60",
            "60-75",
            "75-90",
            "90-100",
        ],
    ).astype(str)


def _probability_buckets(
    vintages: pd.DataFrame,
    errors: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "horizon_months",
        "probability_bucket",
        "confidence_bucket",
        "forecast_count",
        "average_predicted_loss_probability",
        "observed_loss_frequency",
        "calibration_gap",
        "directional_accuracy",
        "mean_absolute_percentage_error",
    ]
    if errors.empty:
        return pd.DataFrame(columns=columns)

    keys = [
        "forecast_run_id",
        "investment_product_id",
        "horizon_months",
    ]
    frame = errors.merge(
        vintages[
            keys
            + [
                "probability_of_loss",
                "forecast_confidence",
            ]
        ],
        on=keys,
        how="left",
        validate="one_to_one",
    )
    probability = pd.to_numeric(
        frame["probability_of_loss"],
        errors="coerce",
    )
    confidence = pd.to_numeric(
        frame["forecast_confidence"],
        errors="coerce",
    )
    frame["probability_bucket"] = (
        _probability_bucket(probability)
    )
    frame["confidence_bucket"] = (
        _confidence_bucket(confidence)
    )
    frame["observed_loss"] = (
        pd.to_numeric(
            frame["realized_return"],
            errors="coerce",
        )
        < 0
    )

    grouped = (
        frame.groupby(
            [
                "horizon_months",
                "probability_bucket",
                "confidence_bucket",
            ],
            as_index=False,
            observed=True,
        )
        .agg(
            forecast_count=(
                "investment_product_id",
                "count",
            ),
            average_predicted_loss_probability=(
                "probability_of_loss",
                "mean",
            ),
            observed_loss_frequency=(
                "observed_loss",
                "mean",
            ),
            directional_accuracy=(
                "direction_correct",
                "mean",
            ),
            mean_absolute_percentage_error=(
                "absolute_percentage_error",
                "mean",
            ),
        )
    )
    grouped["calibration_gap"] = (
        grouped[
            "average_predicted_loss_probability"
        ]
        - grouped["observed_loss_frequency"]
    ).abs()
    return grouped[columns]


def _segment_performance(
    errors: pd.DataFrame,
    recommendation_performance: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "product_type",
        "horizon_months",
        "model_version",
        "matured_forecast_count",
        "mean_absolute_error",
        "mean_absolute_percentage_error",
        "root_mean_squared_error",
        "directional_accuracy",
        "recommendation_hit_rate",
        "average_realized_return",
    ]
    if errors.empty:
        return pd.DataFrame(columns=columns)

    rec = recommendation_performance[
        [
            "forecast_run_id",
            "investment_product_id",
            "horizon_months",
            "recommendation_success",
        ]
    ] if not recommendation_performance.empty else pd.DataFrame(
        columns=[
            "forecast_run_id",
            "investment_product_id",
            "horizon_months",
            "recommendation_success",
        ]
    )
    keys = [
        "forecast_run_id",
        "investment_product_id",
        "horizon_months",
    ]
    frame = errors.merge(
        rec,
        on=keys,
        how="left",
        validate="one_to_one",
    )
    frame["recommendation_success"] = (
        frame["recommendation_success"]
        .fillna(False)
        .astype(bool)
    )

    grouped = (
        frame.groupby(
            [
                "product_type",
                "horizon_months",
                "model_version",
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            matured_forecast_count=(
                "investment_product_id",
                "count",
            ),
            mean_absolute_error=(
                "absolute_price_error",
                "mean",
            ),
            mean_absolute_percentage_error=(
                "absolute_percentage_error",
                "mean",
            ),
            mean_squared_error=(
                "squared_price_error",
                "mean",
            ),
            directional_accuracy=(
                "direction_correct",
                "mean",
            ),
            recommendation_hit_rate=(
                "recommendation_success",
                "mean",
            ),
            average_realized_return=(
                "realized_return",
                "mean",
            ),
        )
    )
    grouped["root_mean_squared_error"] = np.sqrt(
        grouped.pop("mean_squared_error")
    )
    return grouped[columns]


def _drift_monitor(
    errors: pd.DataFrame,
    recommendation_performance: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "metric_name",
        "horizon_months",
        "recent_value",
        "prior_value",
        "absolute_change",
        "relative_change",
        "drift_status",
        "recent_sample_size",
        "prior_sample_size",
    ]
    if errors.empty:
        return pd.DataFrame(columns=columns)

    frame = errors.copy()
    frame["_date"] = pd.to_datetime(
        frame["forecast_as_of_date"],
        errors="coerce",
    )

    rows = []
    for horizon, group in frame.groupby(
        "horizon_months"
    ):
        group = group.sort_values("_date")
        split = max(1, len(group) // 2)
        prior = group.iloc[:split]
        recent = group.iloc[split:]
        if recent.empty:
            recent = group.iloc[-split:]
            prior = group.iloc[:-split]

        metrics = {
            "mean_absolute_percentage_error": (
                "absolute_percentage_error",
                "lower",
            ),
            "directional_accuracy": (
                "direction_correct",
                "higher",
            ),
        }
        for metric_name, (
            column,
            preferred,
        ) in metrics.items():
            recent_value = (
                float(
                    pd.to_numeric(
                        recent[column],
                        errors="coerce",
                    ).mean()
                )
                if not recent.empty
                else np.nan
            )
            prior_value = (
                float(
                    pd.to_numeric(
                        prior[column],
                        errors="coerce",
                    ).mean()
                )
                if not prior.empty
                else np.nan
            )
            if (
                len(recent) < 5
                or len(prior) < 5
                or pd.isna(recent_value)
                or pd.isna(prior_value)
            ):
                status = "Insufficient History"
            else:
                change = recent_value - prior_value
                threshold = (
                    0.10
                    if metric_name
                    == "directional_accuracy"
                    else 0.15
                )
                adverse = (
                    change < -threshold
                    if preferred == "higher"
                    else change > threshold
                )
                status = (
                    "Drift Alert"
                    if adverse
                    else "Stable"
                )
            absolute_change = (
                recent_value - prior_value
                if pd.notna(recent_value)
                and pd.notna(prior_value)
                else np.nan
            )
            relative_change = (
                absolute_change / abs(prior_value)
                if pd.notna(absolute_change)
                and prior_value not in (0, np.nan)
                else np.nan
            )
            rows.append(
                {
                    "metric_name": metric_name,
                    "horizon_months": horizon,
                    "recent_value": recent_value,
                    "prior_value": prior_value,
                    "absolute_change": absolute_change,
                    "relative_change": relative_change,
                    "drift_status": status,
                    "recent_sample_size": len(recent),
                    "prior_sample_size": len(prior),
                }
            )

    return pd.DataFrame(rows, columns=columns)


def _executive_summary(
    vintages: pd.DataFrame,
    outcomes: pd.DataFrame,
    errors: pd.DataFrame,
    recommendation_performance: pd.DataFrame,
) -> pd.DataFrame:
    matured = outcomes[
        outcomes["maturity_status"].eq("matured")
    ] if not outcomes.empty else outcomes
    pending = outcomes[
        outcomes["maturity_status"].eq("pending")
    ] if not outcomes.empty else outcomes

    if errors.empty:
        mae = mape = rmse = directional = np.nan
    else:
        mae = float(
            pd.to_numeric(
                errors["absolute_price_error"],
                errors="coerce",
            ).mean()
        )
        mape = float(
            pd.to_numeric(
                errors["absolute_percentage_error"],
                errors="coerce",
            ).mean()
        )
        rmse = float(
            np.sqrt(
                pd.to_numeric(
                    errors["squared_price_error"],
                    errors="coerce",
                ).mean()
            )
        )
        directional = float(
            errors["direction_correct"].mean()
        )

    hit_rate = (
        float(
            recommendation_performance[
                "recommendation_success"
            ].mean()
        )
        if not recommendation_performance.empty
        else np.nan
    )

    matured_count = len(matured)
    status = (
        "Insufficient Matured Forecasts"
        if matured_count < 25
        else "Initial Calibration Available"
        if matured_count < 100
        else "Calibration Active"
    )

    return pd.DataFrame(
        [
            {
                "snapshot_date": datetime.now(
                    timezone.utc
                ).date().isoformat(),
                "archived_forecast_count": len(
                    vintages
                ),
                "matured_forecast_count": (
                    matured_count
                ),
                "pending_forecast_count": len(
                    pending
                ),
                "missing_realized_price_count": int(
                    outcomes[
                        "maturity_status"
                    ].eq(
                        "missing_realized_price"
                    ).sum()
                )
                if not outcomes.empty
                else 0,
                "mean_absolute_error": mae,
                "mean_absolute_percentage_error": mape,
                "root_mean_squared_error": rmse,
                "directional_accuracy": directional,
                "recommendation_hit_rate": hit_rate,
                "calibration_status": status,
                "model_version": MODEL_VERSION,
            }
        ]
    )


def build_model_calibration_datasets(
    *,
    as_of_date: str | None = None,
    evaluation_date: str | None = None,
    append_current_vintage: bool = True,
) -> CalibrationBuildResult:
    current = _build_current_vintage(
        as_of_date=as_of_date,
    )
    if append_current_vintage:
        vintages, new_rows = _append_vintage_archive(
            current
        )
    else:
        vintages = _read_csv(
            VINTAGE_ARCHIVE_PATH,
            VINTAGE_COLUMNS,
        )
        new_rows = 0

    historical_prices = _load_historical_prices()
    outcomes = _match_realized_outcomes(
        vintages,
        historical_prices,
        evaluation_date=evaluation_date,
    )
    errors = _forecast_errors(
        vintages,
        outcomes,
    )
    recommendation_performance = (
        _recommendation_performance(
            vintages,
            outcomes,
        )
    )
    probability_buckets = _probability_buckets(
        vintages,
        errors,
    )
    segment_performance = _segment_performance(
        errors,
        recommendation_performance,
    )
    drift = _drift_monitor(
        errors,
        recommendation_performance,
    )
    executive = _executive_summary(
        vintages,
        outcomes,
        errors,
        recommendation_performance,
    )

    return CalibrationBuildResult(
        datasets={
            "calibration_forecast_vintages": vintages,
            "calibration_realized_outcomes": outcomes,
            "calibration_forecast_errors": errors,
            "calibration_recommendation_performance": (
                recommendation_performance
            ),
            "calibration_probability_buckets": (
                probability_buckets
            ),
            "calibration_segment_performance": (
                segment_performance
            ),
            "calibration_drift_monitor": drift,
            "calibration_executive_summary": executive,
        },
        archive_path=str(VINTAGE_ARCHIVE_PATH),
        new_vintage_rows=new_rows,
    )
