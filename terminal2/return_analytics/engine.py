from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from terminal2.db.schema import get_connection, init_db
from terminal2.history.exports import _clean_prices, _monthly_history
from terminal2.db.loaders import load_price_observations_df
from terminal2.secret_lair.pricing import build_secret_lair_pricing_datasets
from terminal2.secret_lair.registry import load_secret_lair_registry


MIN_ANALYTICS_MONTHS = 6
MIN_ANALYTICS_SPAN_MONTHS = 4
ANNUAL_PERIODS = 12


@dataclass(frozen=True)
class ReturnAnalyticsBuildResult:
    datasets: dict[str, pd.DataFrame]


def _empty(columns) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))


def _load_booster_names() -> pd.DataFrame:
    init_db()
    connection = get_connection()
    try:
        return pd.read_sql_query(
            """
            SELECT investment_product_id, box_name, product_type
            FROM products
            """,
            connection,
        )
    finally:
        connection.close()


def _canonical_booster_monthly() -> pd.DataFrame:
    prices = _clean_prices(load_price_observations_df())
    monthly = _monthly_history(prices)
    columns = [
        "price_month",
        "investment_product_id",
        "asset_class",
        "product_name",
        "market_price",
        "source_count",
        "source_name",
    ]
    if monthly.empty:
        return _empty(columns)

    frame = monthly.copy()
    frame["price_month"] = pd.to_datetime(
        frame["year_month"].astype(str) + "-01",
        errors="coerce",
    )
    frame["market_price"] = pd.to_numeric(
        frame["market_price"],
        errors="coerce",
    )
    frame = frame.dropna(
        subset=["price_month", "investment_product_id", "market_price"]
    )
    frame = frame[frame["market_price"] > 0].copy()
    canonical = (
        frame.groupby(
            ["price_month", "investment_product_id"],
            as_index=False,
        )
        .agg(
            market_price=("market_price", "median"),
            source_count=("price_source", "nunique"),
            source_name=(
                "price_source",
                lambda values: "|".join(
                    sorted(set(values.dropna().astype(str)))
                ),
            ),
        )
    )
    names = _load_booster_names()
    canonical = canonical.merge(
        names[["investment_product_id", "box_name"]],
        on="investment_product_id",
        how="left",
        validate="many_to_one",
    )
    canonical["asset_class"] = "Booster Product"
    canonical["product_name"] = canonical["box_name"].fillna(
        canonical["investment_product_id"]
    )
    return canonical[columns].sort_values(
        ["investment_product_id", "price_month"]
    ).reset_index(drop=True)


def _canonical_secret_lair_monthly() -> pd.DataFrame:
    pricing = build_secret_lair_pricing_datasets().datasets
    monthly = pricing["secret_lair_monthly_prices"]
    registry, _ = load_secret_lair_registry()
    columns = [
        "price_month",
        "investment_product_id",
        "asset_class",
        "product_name",
        "market_price",
        "source_count",
        "source_name",
    ]
    if monthly.empty:
        return _empty(columns)

    frame = monthly.copy()
    frame["price_month"] = pd.to_datetime(
        frame["year_month"].astype(str) + "-01",
        errors="coerce",
    )
    frame["market_price"] = pd.to_numeric(
        frame["market_price"],
        errors="coerce",
    )
    frame = frame.dropna(
        subset=["price_month", "secret_lair_id", "market_price"]
    )
    frame = frame[frame["market_price"] > 0].copy()
    canonical = (
        frame.groupby(
            ["price_month", "secret_lair_id"],
            as_index=False,
        )
        .agg(
            market_price=("market_price", "median"),
            source_count=("source_name", "nunique"),
            source_name=(
                "source_name",
                lambda values: "|".join(
                    sorted(set(values.dropna().astype(str)))
                ),
            ),
        )
    )
    names = registry.copy()
    if "product_name" not in names.columns:
        names["product_name"] = names.get("drop_name", pd.NA)
    canonical = canonical.merge(
        names[["secret_lair_id", "product_name"]].drop_duplicates(
            "secret_lair_id"
        ),
        on="secret_lair_id",
        how="left",
        validate="many_to_one",
    )
    canonical["investment_product_id"] = (
        "SL-" + canonical["secret_lair_id"].astype(str)
    )
    canonical["asset_class"] = "Secret Lair"
    canonical["product_name"] = canonical["product_name"].fillna(
        canonical["secret_lair_id"]
    )
    return canonical[columns].sort_values(
        ["investment_product_id", "price_month"]
    ).reset_index(drop=True)


def _canonical_universe() -> pd.DataFrame:
    frames = [
        frame
        for frame in (
            _canonical_booster_monthly(),
            _canonical_secret_lair_monthly(),
        )
        if not frame.empty
    ]
    if not frames:
        return _empty(
            (
                "price_month",
                "investment_product_id",
                "asset_class",
                "product_name",
                "market_price",
                "source_count",
                "source_name",
            )
        )
    return pd.concat(frames, ignore_index=True).sort_values(
        ["investment_product_id", "price_month"]
    ).reset_index(drop=True)


def _rolling_return(series: pd.Series, periods: int) -> pd.Series:
    return series / series.shift(periods) - 1.0


def _rolling_and_drawdowns(canonical: pd.DataFrame):
    rolling_columns = [
        "price_month",
        "investment_product_id",
        "asset_class",
        "product_name",
        "market_price",
        "monthly_return",
        "rolling_3m_return",
        "rolling_6m_return",
        "rolling_12m_return",
        "rolling_24m_return",
    ]
    drawdown_columns = [
        "price_month",
        "investment_product_id",
        "asset_class",
        "market_price",
        "running_peak_price",
        "drawdown",
        "underwater_months",
        "recovery_state",
    ]
    if canonical.empty:
        return _empty(rolling_columns), _empty(drawdown_columns)

    rolling_frames = []
    drawdown_frames = []
    for product_id, group in canonical.groupby("investment_product_id"):
        group = group.sort_values("price_month").copy()
        prices = group["market_price"].astype(float)
        group["monthly_return"] = prices.pct_change()
        for periods, column in (
            (3, "rolling_3m_return"),
            (6, "rolling_6m_return"),
            (12, "rolling_12m_return"),
            (24, "rolling_24m_return"),
        ):
            group[column] = _rolling_return(prices, periods)
        rolling_frames.append(group[rolling_columns])

        peak = prices.cummax()
        drawdown = prices / peak - 1.0
        underwater = []
        duration = 0
        for value in drawdown:
            if pd.isna(value) or value >= -1e-12:
                duration = 0
            else:
                duration += 1
            underwater.append(duration)
        drawdown_frames.append(
            pd.DataFrame(
                {
                    "price_month": group["price_month"],
                    "investment_product_id": product_id,
                    "asset_class": group["asset_class"].iloc[0],
                    "market_price": prices,
                    "running_peak_price": peak,
                    "drawdown": drawdown,
                    "underwater_months": underwater,
                    "recovery_state": np.select(
                        [
                            drawdown >= -1e-12,
                            drawdown >= -0.10,
                            drawdown >= -0.25,
                        ],
                        ["At Peak", "Mild Drawdown", "Drawdown"],
                        default="Deep Drawdown",
                    ),
                }
            )
        )

    return (
        pd.concat(rolling_frames, ignore_index=True),
        pd.concat(drawdown_frames, ignore_index=True),
    )


def _product_metrics(canonical, rolling, drawdowns):
    summary_rows = []
    risk_rows = []
    momentum_rows = []
    coverage_rows = []

    for product_id, group in canonical.groupby("investment_product_id"):
        group = group.sort_values("price_month").copy()
        asset_class = str(group["asset_class"].iloc[-1])
        product_name = str(group["product_name"].iloc[-1])
        first_month = group["price_month"].iloc[0]
        latest_month = group["price_month"].iloc[-1]
        observation_months = int(len(group))
        span_months = int(
            (latest_month.year - first_month.year) * 12
            + latest_month.month
            - first_month.month
        )
        first_price = float(group["market_price"].iloc[0])
        latest_price = float(group["market_price"].iloc[-1])
        total_return = latest_price / first_price - 1.0
        years = span_months / 12.0
        cagr = (
            (latest_price / first_price) ** (1.0 / years) - 1.0
            if years >= MIN_ANALYTICS_SPAN_MONTHS / 12.0
            else np.nan
        )

        rolling_group = rolling[
            rolling["investment_product_id"].eq(product_id)
        ].sort_values("price_month")
        monthly_returns = pd.to_numeric(
            rolling_group["monthly_return"],
            errors="coerce",
        ).dropna()
        volatility = (
            float(monthly_returns.std(ddof=1) * np.sqrt(ANNUAL_PERIODS))
            if len(monthly_returns) >= 5
            else np.nan
        )
        downside = monthly_returns[monthly_returns < 0]
        downside_deviation = (
            float(
                np.sqrt(np.mean(np.square(downside)))
                * np.sqrt(ANNUAL_PERIODS)
            )
            if len(downside) >= 2
            else np.nan
        )
        sharpe = (
            cagr / volatility
            if pd.notna(cagr) and pd.notna(volatility) and volatility > 0
            else np.nan
        )
        sortino = (
            cagr / downside_deviation
            if pd.notna(cagr)
            and pd.notna(downside_deviation)
            and downside_deviation > 0
            else np.nan
        )

        dd_group = drawdowns[
            drawdowns["investment_product_id"].eq(product_id)
        ].sort_values("price_month")
        maximum_drawdown = float(dd_group["drawdown"].min())
        latest_drawdown = float(dd_group["drawdown"].iloc[-1])
        maximum_recovery_months = int(dd_group["underwater_months"].max())
        return_to_drawdown = (
            cagr / abs(maximum_drawdown)
            if pd.notna(cagr) and maximum_drawdown < 0
            else np.nan
        )

        latest_rolling = rolling_group.iloc[-1]
        r3 = latest_rolling["rolling_3m_return"]
        r6 = latest_rolling["rolling_6m_return"]
        r12 = latest_rolling["rolling_12m_return"]
        r24 = latest_rolling["rolling_24m_return"]
        positive_ratio = (
            float((monthly_returns > 0).mean())
            if len(monthly_returns)
            else np.nan
        )
        recent = monthly_returns.tail(6)
        persistence = (
            float((recent > 0).mean())
            if len(recent) >= 3
            else np.nan
        )
        if pd.notna(r6) and r6 >= 0.20 and pd.notna(persistence) and persistence >= 0.67:
            momentum_state = "Strong Positive"
        elif pd.notna(r6) and r6 > 0:
            momentum_state = "Positive"
        elif pd.notna(r6) and r6 <= -0.20:
            momentum_state = "Strong Negative"
        elif pd.notna(r6):
            momentum_state = "Negative"
        else:
            momentum_state = "Insufficient History"

        ready = (
            observation_months >= MIN_ANALYTICS_MONTHS
            and span_months >= MIN_ANALYTICS_SPAN_MONTHS
        )
        if observation_months >= 25 and span_months >= 24:
            coverage_tier = "Advanced"
        elif observation_months >= 13 and span_months >= 12:
            coverage_tier = "Established"
        elif ready:
            coverage_tier = "Analytics Ready"
        elif observation_months >= 2:
            coverage_tier = "Emerging"
        else:
            coverage_tier = "Insufficient"

        base = {
            "investment_product_id": product_id,
            "asset_class": asset_class,
            "product_name": product_name,
        }
        summary_rows.append(
            {
                **base,
                "first_observation_month": first_month.date().isoformat(),
                "latest_observation_month": latest_month.date().isoformat(),
                "observation_months": observation_months,
                "history_span_months": span_months,
                "first_price": round(first_price, 2),
                "latest_price": round(latest_price, 2),
                "total_return": total_return,
                "cagr": cagr,
                "annualized_volatility": volatility,
                "downside_deviation": downside_deviation,
                "maximum_drawdown": maximum_drawdown,
                "maximum_recovery_months": maximum_recovery_months,
                "latest_drawdown": latest_drawdown,
                "analytics_status": "Ready" if ready else "Insufficient History",
            }
        )
        risk_rows.append(
            {
                **base,
                "annualized_return": cagr,
                "annualized_volatility": volatility,
                "downside_deviation": downside_deviation,
                "sharpe_like_ratio": sharpe,
                "sortino_like_ratio": sortino,
                "return_to_drawdown_ratio": return_to_drawdown,
                "maximum_drawdown": maximum_drawdown,
                "maximum_recovery_months": maximum_recovery_months,
            }
        )
        momentum_rows.append(
            {
                **base,
                "return_3m": r3,
                "return_6m": r6,
                "return_12m": r12,
                "return_24m": r24,
                "positive_month_ratio": positive_ratio,
                "momentum_persistence": persistence,
                "momentum_state": momentum_state,
            }
        )
        coverage_rows.append(
            {
                **base,
                "observation_months": observation_months,
                "history_span_months": span_months,
                "cagr_available": pd.notna(cagr),
                "volatility_available": pd.notna(volatility),
                "rolling_12m_available": pd.notna(r12),
                "rolling_24m_available": pd.notna(r24),
                "coverage_tier": coverage_tier,
            }
        )

    return (
        pd.DataFrame(summary_rows),
        pd.DataFrame(risk_rows),
        pd.DataFrame(momentum_rows),
        pd.DataFrame(coverage_rows),
    )


def _percentile(series, higher_is_better=True):
    values = pd.to_numeric(series, errors="coerce")
    result = pd.Series(np.nan, index=values.index, dtype=float)
    valid = values.notna()
    if valid.sum() >= 2:
        result.loc[valid] = values.loc[valid].rank(
            pct=True,
            method="average",
            ascending=higher_is_better,
        ) * 100
    elif valid.sum() == 1:
        result.loc[valid] = 50.0
    return result


def _rankings(summary, risk, momentum):
    columns = [
        "investment_product_id",
        "asset_class",
        "product_name",
        "return_percentile",
        "risk_adjusted_percentile",
        "drawdown_percentile",
        "momentum_percentile",
        "return_rank",
        "risk_adjusted_rank",
        "drawdown_rank",
        "momentum_rank",
        "asset_class_rank",
        "composite_return_score",
        "composite_rank",
    ]
    if summary.empty:
        return _empty(columns)

    frame = summary[
        [
            "investment_product_id",
            "asset_class",
            "product_name",
            "cagr",
            "maximum_drawdown",
            "analytics_status",
        ]
    ].merge(
        risk[["investment_product_id", "sharpe_like_ratio"]],
        on="investment_product_id",
        how="left",
    ).merge(
        momentum[
            [
                "investment_product_id",
                "return_6m",
                "momentum_persistence",
            ]
        ],
        on="investment_product_id",
        how="left",
    )
    ready = frame["analytics_status"].eq("Ready")
    frame["return_percentile"] = _percentile(frame["cagr"], True)
    frame["risk_adjusted_percentile"] = _percentile(
        frame["sharpe_like_ratio"], True
    )
    frame["drawdown_percentile"] = _percentile(
        frame["maximum_drawdown"], True
    )
    momentum_signal = (
        pd.to_numeric(frame["return_6m"], errors="coerce").fillna(0) * 0.70
        + pd.to_numeric(
            frame["momentum_persistence"],
            errors="coerce",
        ).fillna(0.5) * 0.30
    )
    frame["momentum_percentile"] = _percentile(
        momentum_signal, True
    )
    metric_columns = [
        "return_percentile",
        "risk_adjusted_percentile",
        "drawdown_percentile",
        "momentum_percentile",
    ]
    frame.loc[~ready, metric_columns] = np.nan
    frame["composite_return_score"] = (
        frame["return_percentile"] * 0.35
        + frame["risk_adjusted_percentile"] * 0.30
        + frame["drawdown_percentile"] * 0.20
        + frame["momentum_percentile"] * 0.15
    ).round(2)

    for metric, rank_name in (
        ("return_percentile", "return_rank"),
        ("risk_adjusted_percentile", "risk_adjusted_rank"),
        ("drawdown_percentile", "drawdown_rank"),
        ("momentum_percentile", "momentum_rank"),
        ("composite_return_score", "composite_rank"),
    ):
        frame[rank_name] = frame[metric].rank(
            ascending=False,
            method="min",
        ).astype("Int64")
    frame["asset_class_rank"] = (
        frame.groupby("asset_class")["composite_return_score"]
        .rank(ascending=False, method="min")
        .astype("Int64")
    )
    return frame[columns].sort_values(
        ["composite_rank", "asset_class", "investment_product_id"],
        na_position="last",
    ).reset_index(drop=True)


def _asset_class_summary(summary, coverage):
    columns = [
        "asset_class",
        "product_count",
        "analytics_ready_count",
        "rolling_12m_ready_count",
        "rolling_24m_ready_count",
        "positive_cagr_count",
        "median_cagr",
        "median_volatility",
        "median_maximum_drawdown",
    ]
    if summary.empty:
        return _empty(columns)
    joined = summary.merge(
        coverage[
            [
                "investment_product_id",
                "rolling_12m_available",
                "rolling_24m_available",
            ]
        ],
        on="investment_product_id",
        how="left",
    )
    rows = []
    for asset_class, group in joined.groupby("asset_class"):
        cagr = pd.to_numeric(group["cagr"], errors="coerce")
        volatility = pd.to_numeric(
            group["annualized_volatility"],
            errors="coerce",
        )
        drawdown = pd.to_numeric(
            group["maximum_drawdown"],
            errors="coerce",
        )
        rows.append(
            {
                "asset_class": asset_class,
                "product_count": len(group),
                "analytics_ready_count": int(
                    group["analytics_status"].eq("Ready").sum()
                ),
                "rolling_12m_ready_count": int(
                    group["rolling_12m_available"].fillna(False).sum()
                ),
                "rolling_24m_ready_count": int(
                    group["rolling_24m_available"].fillna(False).sum()
                ),
                "positive_cagr_count": int((cagr > 0).sum()),
                "median_cagr": cagr.median(),
                "median_volatility": volatility.median(),
                "median_maximum_drawdown": drawdown.median(),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _executive_summary(summary, coverage):
    cagr = pd.to_numeric(summary.get("cagr"), errors="coerce")
    volatility = pd.to_numeric(
        summary.get("annualized_volatility"),
        errors="coerce",
    )
    drawdown = pd.to_numeric(
        summary.get("maximum_drawdown"),
        errors="coerce",
    )
    ready = summary["analytics_status"].eq("Ready")
    return pd.DataFrame(
        [
            {
                "snapshot_date": datetime.now(
                    timezone.utc
                ).date().isoformat(),
                "product_count": len(summary),
                "asset_class_count": int(
                    summary["asset_class"].nunique()
                ),
                "analytics_ready_count": int(ready.sum()),
                "rolling_12m_ready_count": int(
                    coverage["rolling_12m_available"].sum()
                ),
                "rolling_24m_ready_count": int(
                    coverage["rolling_24m_available"].sum()
                ),
                "positive_cagr_count": int((cagr > 0).sum()),
                "negative_cagr_count": int((cagr < 0).sum()),
                "median_cagr": cagr.median(),
                "median_volatility": volatility.median(),
                "median_maximum_drawdown": drawdown.median(),
                "analytics_status": (
                    "READY" if int(ready.sum()) > 0
                    else "INSUFFICIENT_HISTORY"
                ),
            }
        ]
    )


def build_universal_return_analytics() -> ReturnAnalyticsBuildResult:
    canonical = _canonical_universe()
    rolling, drawdowns = _rolling_and_drawdowns(canonical)
    summary, risk, momentum, coverage = _product_metrics(
        canonical,
        rolling,
        drawdowns,
    )
    rankings = _rankings(summary, risk, momentum)
    asset_classes = _asset_class_summary(summary, coverage)
    executive = _executive_summary(summary, coverage)

    if not rolling.empty:
        rolling["price_month"] = rolling[
            "price_month"
        ].dt.date.astype(str)
    if not drawdowns.empty:
        drawdowns["price_month"] = drawdowns[
            "price_month"
        ].dt.date.astype(str)

    return ReturnAnalyticsBuildResult(
        datasets={
            "universal_return_summary": summary,
            "universal_rolling_returns": rolling,
            "universal_drawdown_series": drawdowns,
            "universal_risk_adjusted_returns": risk,
            "universal_momentum_analytics": momentum,
            "universal_return_rankings": rankings,
            "universal_return_coverage": coverage,
            "return_asset_class_summary": asset_classes,
            "universal_return_analytics_summary": executive,
        }
    )
