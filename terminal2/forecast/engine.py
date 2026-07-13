from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import erf, exp, log, sqrt

import numpy as np
import pandas as pd


HORIZONS = (6, 12, 36, 60)


@dataclass(frozen=True)
class ForecastBuildResult:
    datasets: dict[str, pd.DataFrame]


def _num(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(default)


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + erf(value / sqrt(2.0)))


def _loss_probability(mu: float, sigma: float, years: float) -> float:
    if sigma <= 0 or years <= 0:
        return float(mu < 0)
    z = (-mu * years) / (sigma * sqrt(years))
    return float(np.clip(_normal_cdf(z), 0.01, 0.99))


def _trend_persistence(frame: pd.DataFrame) -> pd.Series:
    components = []
    for column in ("return_30d", "return_90d", "return_180d", "return_365d"):
        values = _num(frame, column, np.nan)
        components.append(np.sign(values))
    direction = pd.concat(components, axis=1)
    agreement = direction.abs().sum(axis=1)
    signed = direction.sum(axis=1).abs()
    persistence = np.where(
        agreement > 0,
        signed / agreement * 100,
        0,
    )
    trend_score = _num(frame, "trend_score", 50)
    return (pd.Series(persistence, index=frame.index) * 0.65 + trend_score * 0.35).clip(0, 100).round(2)


def _regime(frame: pd.DataFrame) -> pd.DataFrame:
    momentum = (
        _num(frame, "trend_score", 50) * 0.40
        + ((_num(frame, "return_90d", 0).clip(-0.50, 0.50) + 0.50) * 100) * 0.25
        + ((_num(frame, "return_180d", 0).clip(-0.75, 0.75) + 0.75) / 1.50 * 100) * 0.20
        + _trend_persistence(frame) * 0.15
    ).clip(0, 100)

    market_support = (
        _num(frame, "market_intelligence_score", 50) * 0.50
        + _num(frame, "supply_signal_score", 50) * 0.20
        + _num(frame, "sales_velocity_score", 50) * 0.15
        + _num(frame, "liquidity_score", 50) * 0.15
    ).clip(0, 100)

    regime_score = (momentum * 0.60 + market_support * 0.40).round(2)
    regime = np.select(
        [
            regime_score >= 68,
            regime_score >= 55,
            regime_score >= 43,
            regime_score >= 30,
        ],
        ["Bull", "Positive", "Sideways", "Weak"],
        default="Bear",
    )
    return pd.DataFrame({
        "momentum_score": momentum.round(2),
        "market_support_score": market_support.round(2),
        "regime_score": regime_score,
        "forecast_regime": regime,
    }, index=frame.index)


def _expected_cagr(frame: pd.DataFrame, regimes: pd.DataFrame) -> pd.Series:
    base = _num(frame, "expected_cagr", 0.08)
    score_adj = (_num(frame, "risk_adjusted_score", 50) - 50) / 100 * 0.06
    market_adj = (_num(frame, "market_intelligence_score", 50) - 50) / 100 * 0.04
    persistence_adj = (_trend_persistence(frame) - 50) / 100 * 0.03
    regime_adj = regimes["forecast_regime"].map({
        "Bull": 0.035,
        "Positive": 0.015,
        "Sideways": 0.0,
        "Weak": -0.025,
        "Bear": -0.050,
    }).fillna(0.0)
    return (base * 0.55 + score_adj + market_adj + persistence_adj + regime_adj).clip(-0.10, 0.30).round(4)


def _confidence(frame: pd.DataFrame) -> pd.Series:
    return (
        _num(frame, "projection_confidence", 0) * 0.30
        + _num(frame, "history_confidence", 0) * 0.25
        + _num(frame, "market_intelligence_confidence", 0) * 0.20
        + np.minimum(_num(frame, "observation_count", 0) / 24 * 100, 100) * 0.15
        + (100 - np.minimum(_num(frame, "annualized_volatility", 0.50) * 100, 100)) * 0.10
    ).clip(0, 95).round(2)


def _conviction(
    frame: pd.DataFrame,
    regimes: pd.DataFrame,
    expected_cagr: pd.Series,
    confidence: pd.Series,
) -> pd.Series:
    return (
        _num(frame, "risk_adjusted_score", 50) * 0.25
        + _num(frame, "investment_score", 50) * 0.15
        + _num(frame, "market_intelligence_score", 50) * 0.15
        + regimes["regime_score"] * 0.15
        + confidence * 0.15
        + ((expected_cagr + 0.10) / 0.40 * 100).clip(0, 100) * 0.15
    ).clip(0, 100).round(2)


def build_forecast_datasets(universe: pd.DataFrame) -> ForecastBuildResult:
    frame = universe.copy()
    if frame.empty:
        raise ValueError("Forecast universe is empty.")

    frame["current_price"] = _num(frame, "current_price")
    frame = frame[frame["current_price"] > 0].copy()
    if frame.empty:
        raise ValueError("Forecast universe has no valid current prices.")

    regimes = _regime(frame)
    persistence = _trend_persistence(frame)
    expected_cagr = _expected_cagr(frame, regimes)
    confidence = _confidence(frame)
    conviction = _conviction(frame, regimes, expected_cagr, confidence)

    volatility = _num(frame, "annualized_volatility", 0.45).clip(0.05, 1.50)
    uncertainty = (
        volatility * 45
        + (100 - confidence) * 0.55
    ).clip(0, 100).round(2)
    expected_drawdown = (
        volatility * 0.65
        + _num(frame, "prob_loss", 0.30) * 0.35
    ).clip(0.05, 0.90).round(4)
    prob_loss_12m = [
        round(_loss_probability(float(mu), float(sig), 1.0), 4)
        for mu, sig in zip(expected_cagr, volatility)
    ]

    product_summary = frame[[
        column for column in (
            "investment_product_id",
            "box_name",
            "set_name",
            "product_type",
            "current_price",
            "investment_score",
            "risk_adjusted_score",
            "market_intelligence_score",
            "projection_confidence",
            "history_confidence",
        ) if column in frame.columns
    ]].copy()
    product_summary["forecast_regime"] = regimes["forecast_regime"].values
    product_summary["regime_score"] = regimes["regime_score"].values
    product_summary["trend_persistence_score"] = persistence.values
    product_summary["forecast_expected_cagr"] = expected_cagr.values
    product_summary["forecast_confidence"] = confidence.values
    product_summary["conviction_score"] = conviction.values
    product_summary["conviction_tier"] = pd.cut(
        conviction,
        bins=[-1, 50, 65, 75, 85, 101],
        labels=["Low", "Speculative", "Watch", "High", "Highest"],
    ).astype(str)

    horizon_rows = []
    for index, row in frame.iterrows():
        current = float(row["current_price"])
        mu = float(expected_cagr.loc[index])
        sigma = float(volatility.loc[index])
        conf = float(confidence.loc[index])
        for months in HORIZONS:
            years = months / 12
            spread = sigma * sqrt(years) * (0.85 + (100 - conf) / 200)
            base_price = current * exp(mu * years)
            bear_price = current * exp((mu * years) - 1.15 * spread)
            bull_price = current * exp((mu * years) + 1.15 * spread)
            horizon_rows.append({
                "investment_product_id": row["investment_product_id"],
                "box_name": row.get("box_name"),
                "horizon_months": months,
                "current_price": round(current, 2),
                "base_forecast_price": round(base_price, 2),
                "bear_forecast_price": round(max(0.01, bear_price), 2),
                "bull_forecast_price": round(bull_price, 2),
                "expected_return": round(base_price / current - 1, 4),
                "bear_return": round(bear_price / current - 1, 4),
                "bull_return": round(bull_price / current - 1, 4),
                "probability_of_loss": round(
                    _loss_probability(mu, sigma, years), 4
                ),
                "forecast_confidence": round(conf, 2),
            })
    horizons = pd.DataFrame(horizon_rows)

    risk = frame[[
        column for column in (
            "investment_product_id",
            "box_name",
            "current_price",
        ) if column in frame.columns
    ]].copy()
    risk["forecast_volatility"] = volatility.values.round(4)
    risk["expected_max_drawdown"] = expected_drawdown.values
    risk["probability_loss_12m"] = prob_loss_12m
    risk["uncertainty_score"] = uncertainty.values
    risk["risk_tier"] = pd.cut(
        uncertainty,
        bins=[-1, 30, 50, 70, 101],
        labels=["Low", "Moderate", "High", "Very High"],
    ).astype(str)

    regime_data = frame[[
        column for column in (
            "investment_product_id",
            "box_name",
        ) if column in frame.columns
    ]].copy()
    for column in regimes.columns:
        regime_data[column] = regimes[column].values
    regime_data["trend_persistence_score"] = persistence.values

    ranking = product_summary.copy()
    ranking["probability_loss_12m"] = prob_loss_12m
    ranking["risk_adjusted_expected_return"] = (
        expected_cagr.values
        - np.array(prob_loss_12m) * 0.10
        - volatility.values * 0.05
    ).round(4)
    ranking = ranking.sort_values(
        ["conviction_score", "risk_adjusted_expected_return"],
        ascending=False,
    ).reset_index(drop=True)
    ranking["forecast_rank"] = range(1, len(ranking) + 1)

    counts = product_summary["forecast_regime"].value_counts()
    market_summary = pd.DataFrame([{
        "snapshot_date": datetime.now(timezone.utc).date().isoformat(),
        "product_count": int(len(product_summary)),
        "bullish_product_count": int(
            counts.get("Bull", 0) + counts.get("Positive", 0)
        ),
        "neutral_product_count": int(counts.get("Sideways", 0)),
        "bearish_product_count": int(
            counts.get("Weak", 0) + counts.get("Bear", 0)
        ),
        "average_conviction_score": round(
            float(product_summary["conviction_score"].mean()), 2
        ),
        "average_forecast_confidence": round(
            float(product_summary["forecast_confidence"].mean()), 2
        ),
        "average_expected_cagr": round(float(expected_cagr.mean()), 4),
        "highest_conviction_product": (
            ranking.iloc[0]["box_name"] if len(ranking) else ""
        ),
    }])

    return ForecastBuildResult(datasets={
        "forecast_product_summary": product_summary,
        "forecast_horizons": horizons,
        "forecast_risk": risk,
        "forecast_regimes": regime_data,
        "forecast_rankings": ranking,
        "forecast_market_summary": market_summary,
    })
