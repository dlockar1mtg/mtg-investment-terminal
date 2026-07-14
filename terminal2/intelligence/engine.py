from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from terminal2.forecast.engine import build_forecast_datasets


@dataclass(frozen=True)
class IntelligenceBuildResult:
    datasets: dict[str, pd.DataFrame]


def _num(
    frame: pd.DataFrame,
    column: str,
    default: float = 0.0,
) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(
            default,
            index=frame.index,
            dtype=float,
        )
    return pd.to_numeric(
        frame[column],
        errors="coerce",
    ).fillna(default)


def _clip_score(values) -> pd.Series:
    return pd.Series(values).clip(0, 100).round(2)


def _risk_rating(score: pd.Series) -> pd.Series:
    return pd.cut(
        score,
        bins=[-1, 25, 45, 65, 80, 101],
        labels=[
            "Low",
            "Moderate",
            "Elevated",
            "High",
            "Very High",
        ],
    ).astype(str)


def _confidence_rating(score: pd.Series) -> pd.Series:
    return pd.cut(
        score,
        bins=[-1, 35, 55, 70, 85, 101],
        labels=[
            "Very Low",
            "Low",
            "Moderate",
            "High",
            "Very High",
        ],
    ).astype(str)


def _coverage(
    universe: pd.DataFrame,
) -> pd.DataFrame:
    frame = universe.copy()

    historical = (
        _num(frame, "observation_count", 0).gt(0)
        & frame.get(
            "history_confidence",
            pd.Series(index=frame.index, dtype=float),
        ).notna()
    )
    market = (
        frame.get(
            "market_intelligence_score",
            pd.Series(index=frame.index, dtype=float),
        ).notna()
    )
    forecast = frame.get(
        "current_price",
        pd.Series(index=frame.index, dtype=float),
    ).notna()
    pricing = _num(frame, "current_price", 0).gt(0)

    available_count = (
        historical.astype(int)
        + market.astype(int)
        + forecast.astype(int)
        + pricing.astype(int)
    )
    coverage_score = available_count / 4 * 100
    coverage_status = np.select(
        [
            coverage_score >= 100,
            coverage_score >= 75,
            coverage_score >= 50,
        ],
        ["Complete", "Strong", "Partial"],
        default="Insufficient",
    )

    result = frame[
        [
            column
            for column in (
                "investment_product_id",
                "box_name",
                "set_name",
                "product_type",
            )
            if column in frame.columns
        ]
    ].copy()
    result["historical_model_available"] = historical.values
    result["market_model_available"] = market.values
    result["forecast_model_available"] = forecast.values
    result["pricing_available"] = pricing.values
    result["available_model_count"] = available_count.values
    result["model_coverage_score"] = (
        coverage_score.round(2).values
    )
    result["coverage_status"] = coverage_status
    return result


def _risk(
    universe: pd.DataFrame,
    forecast_datasets: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    summary = forecast_datasets[
        "forecast_product_summary"
    ].copy()
    forecast_risk = forecast_datasets[
        "forecast_risk"
    ][
        [
            "investment_product_id",
            "forecast_volatility",
            "expected_max_drawdown",
            "probability_loss_12m",
            "uncertainty_score",
        ]
    ].copy()

    frame = summary.merge(
        forecast_risk,
        on="investment_product_id",
        how="left",
        validate="one_to_one",
    )
    source = universe[
        [
            column
            for column in (
                "investment_product_id",
                "liquidity_score",
                "observation_count",
                "history_confidence",
                "market_intelligence_confidence",
            )
            if column in universe.columns
        ]
    ].copy()
    frame = frame.merge(
        source,
        on="investment_product_id",
        how="left",
        validate="one_to_one",
    )

    volatility_risk = _clip_score(
        _num(frame, "forecast_volatility", 0.50)
        / 1.20
        * 100
    )
    liquidity_risk = _clip_score(
        100 - _num(frame, "liquidity_score", 50)
    )
    drawdown_risk = _clip_score(
        _num(frame, "expected_max_drawdown", 0.40)
        * 100
    )
    observation_component = np.minimum(
        _num(frame, "observation_count", 0) / 24 * 100,
        100,
    )
    history_component = _num(
        frame,
        "history_confidence",
        0,
    )
    data_risk = _clip_score(
        100
        - (
            observation_component * 0.55
            + history_component * 0.45
        )
    )
    forecast_risk_score = _clip_score(
        _num(frame, "uncertainty_score", 50) * 0.60
        + _num(
            frame,
            "probability_loss_12m",
            0.30,
        )
        * 100
        * 0.40
    )

    overall = _clip_score(
        volatility_risk * 0.22
        + liquidity_risk * 0.18
        + drawdown_risk * 0.22
        + data_risk * 0.16
        + forecast_risk_score * 0.22
    )

    result = frame[
        [
            column
            for column in (
                "investment_product_id",
                "box_name",
                "set_name",
                "product_type",
                "current_price",
            )
            if column in frame.columns
        ]
    ].copy()
    result["overall_risk_score"] = overall.values
    result["risk_rating"] = _risk_rating(overall).values
    result["volatility_risk"] = volatility_risk.values
    result["liquidity_risk"] = liquidity_risk.values
    result["drawdown_risk"] = drawdown_risk.values
    result["data_risk"] = data_risk.values
    result["forecast_risk"] = (
        forecast_risk_score.values
    )
    result["probability_loss_12m"] = _num(
        frame,
        "probability_loss_12m",
        0.30,
    ).values
    result["expected_max_drawdown"] = _num(
        frame,
        "expected_max_drawdown",
        0.40,
    ).values
    return result


def _confidence(
    universe: pd.DataFrame,
    forecast_datasets: dict[str, pd.DataFrame],
    coverage: pd.DataFrame,
) -> pd.DataFrame:
    summary = forecast_datasets[
        "forecast_product_summary"
    ].copy()
    source = universe[
        [
            column
            for column in (
                "investment_product_id",
                "observation_count",
                "history_confidence",
                "market_intelligence_confidence",
                "projection_confidence",
            )
            if column in universe.columns
        ]
    ].copy()
    frame = summary.merge(
        source,
        on="investment_product_id",
        how="left",
        validate="one_to_one",
        suffixes=("", "_source"),
    ).merge(
        coverage[
            [
                "investment_product_id",
                "model_coverage_score",
            ]
        ],
        on="investment_product_id",
        how="left",
        validate="one_to_one",
    )

    observation_score = _clip_score(
        np.minimum(
            _num(frame, "observation_count", 0)
            / 24
            * 100,
            100,
        )
    )
    history_depth = _clip_score(
        _num(frame, "history_confidence", 0)
        * 0.65
        + observation_score * 0.35
    )
    forecast_confidence = _clip_score(
        _num(frame, "forecast_confidence", 0)
    )
    market_confidence = _clip_score(
        _num(
            frame,
            "market_intelligence_confidence",
            0,
        )
    )
    model_coverage = _clip_score(
        _num(frame, "model_coverage_score", 0)
    )

    overall = _clip_score(
        history_depth * 0.25
        + observation_score * 0.15
        + forecast_confidence * 0.30
        + market_confidence * 0.15
        + model_coverage * 0.15
    )

    result = frame[
        [
            column
            for column in (
                "investment_product_id",
                "box_name",
                "set_name",
                "product_type",
            )
            if column in frame.columns
        ]
    ].copy()
    result["overall_confidence_score"] = overall.values
    result["confidence_rating"] = (
        _confidence_rating(overall).values
    )
    result["history_depth_score"] = (
        history_depth.values
    )
    result["observation_score"] = (
        observation_score.values
    )
    result["forecast_confidence_score"] = (
        forecast_confidence.values
    )
    result["market_confidence_score"] = (
        market_confidence.values
    )
    result["model_coverage_score"] = (
        model_coverage.values
    )
    return result


def _recommendation_label(
    score: pd.Series,
    confidence: pd.Series,
    coverage_score: pd.Series,
) -> np.ndarray:
    insufficient = (
        confidence < 35
    ) | (coverage_score < 50)
    return np.select(
        [
            insufficient,
            score >= 78,
            score >= 66,
            score >= 54,
            score >= 42,
        ],
        [
            "Insufficient Data",
            "Strong Buy",
            "Buy",
            "Watch",
            "Hold",
        ],
        default="Avoid",
    )


def _recommendations(
    forecast_datasets: dict[str, pd.DataFrame],
    risk: pd.DataFrame,
    confidence: pd.DataFrame,
    coverage: pd.DataFrame,
) -> pd.DataFrame:
    summary = forecast_datasets[
        "forecast_product_summary"
    ].copy()
    frame = (
        summary.merge(
            risk[
                [
                    "investment_product_id",
                    "overall_risk_score",
                    "risk_rating",
                ]
            ],
            on="investment_product_id",
            how="left",
            validate="one_to_one",
        )
        .merge(
            confidence[
                [
                    "investment_product_id",
                    "overall_confidence_score",
                    "confidence_rating",
                ]
            ],
            on="investment_product_id",
            how="left",
            validate="one_to_one",
        )
        .merge(
            coverage[
                [
                    "investment_product_id",
                    "model_coverage_score",
                    "coverage_status",
                ]
            ],
            on="investment_product_id",
            how="left",
            validate="one_to_one",
        )
    )

    return_score = _clip_score(
        (
            _num(
                frame,
                "forecast_expected_cagr",
                0,
            )
            + 0.10
        )
        / 0.40
        * 100
    )
    conviction = _clip_score(
        _num(frame, "conviction_score", 0)
    )
    regime = _clip_score(
        _num(frame, "regime_score", 50)
    )
    risk_quality = _clip_score(
        100 - _num(frame, "overall_risk_score", 50)
    )
    confidence_score = _clip_score(
        _num(
            frame,
            "overall_confidence_score",
            0,
        )
    )

    recommendation_score = _clip_score(
        return_score * 0.30
        + conviction * 0.25
        + regime * 0.15
        + risk_quality * 0.20
        + confidence_score * 0.10
    )
    recommendation = _recommendation_label(
        recommendation_score,
        confidence_score,
        _num(frame, "model_coverage_score", 0),
    )

    result = frame.copy()
    result["recommendation"] = recommendation
    result["recommendation_score"] = (
        recommendation_score.values
    )
    result["expected_return_score"] = (
        return_score.values
    )
    result["risk_quality_score"] = (
        risk_quality.values
    )
    return result


def _factor_rows(
    recommendations: pd.DataFrame,
    risk: pd.DataFrame,
    confidence: pd.DataFrame,
) -> pd.DataFrame:
    merged = recommendations.merge(
        risk[
            [
                "investment_product_id",
                "volatility_risk",
                "liquidity_risk",
                "drawdown_risk",
                "data_risk",
                "forecast_risk",
            ]
        ],
        on="investment_product_id",
        how="left",
        validate="one_to_one",
    ).merge(
        confidence[
            [
                "investment_product_id",
                "history_depth_score",
                "observation_score",
                "forecast_confidence_score",
                "market_confidence_score",
                "model_coverage_score",
            ]
        ],
        on="investment_product_id",
        how="left",
        validate="one_to_one",
        suffixes=("", "_confidence"),
    )

    specs = (
        (
            "expected_cagr",
            "return",
            "Expected CAGR",
            "forecast_expected_cagr",
            "positive",
        ),
        (
            "conviction",
            "forecast",
            "Forecast conviction",
            "conviction_score",
            "positive",
        ),
        (
            "regime",
            "market",
            "Market regime support",
            "regime_score",
            "positive",
        ),
        (
            "confidence",
            "evidence",
            "Recommendation confidence",
            "overall_confidence_score",
            "positive",
        ),
        (
            "volatility_risk",
            "risk",
            "Volatility risk",
            "volatility_risk",
            "negative",
        ),
        (
            "liquidity_risk",
            "risk",
            "Liquidity risk",
            "liquidity_risk",
            "negative",
        ),
        (
            "drawdown_risk",
            "risk",
            "Drawdown risk",
            "drawdown_risk",
            "negative",
        ),
        (
            "data_risk",
            "risk",
            "Data-quality risk",
            "data_risk",
            "negative",
        ),
        (
            "forecast_risk",
            "risk",
            "Forecast uncertainty",
            "forecast_risk",
            "negative",
        ),
    )

    rows = []
    for _, row in merged.iterrows():
        for (
            code,
            group,
            label,
            column,
            direction,
        ) in specs:
            value = row.get(column)
            if pd.isna(value):
                continue
            if code == "expected_cagr":
                score = float(
                    np.clip(
                        (float(value) + 0.10)
                        / 0.40
                        * 100,
                        0,
                        100,
                    )
                )
            else:
                score = float(value)
            rows.append(
                {
                    "investment_product_id": row[
                        "investment_product_id"
                    ],
                    "box_name": row.get("box_name"),
                    "factor_code": code,
                    "factor_group": group,
                    "factor_label": label,
                    "factor_value": round(
                        float(value),
                        4,
                    ),
                    "factor_score": round(score, 2),
                    "factor_direction": direction,
                }
            )
    return pd.DataFrame(rows)


def _explanations(
    recommendations: pd.DataFrame,
    risk: pd.DataFrame,
    confidence: pd.DataFrame,
) -> pd.DataFrame:
    frame = recommendations.merge(
        risk,
        on=[
            column
            for column in (
                "investment_product_id",
                "box_name",
                "set_name",
                "product_type",
                "current_price",
            )
            if column in recommendations.columns
            and column in risk.columns
        ],
        how="left",
        suffixes=("", "_risk"),
    ).merge(
        confidence[
            [
                "investment_product_id",
                "history_depth_score",
                "observation_score",
                "forecast_confidence_score",
                "market_confidence_score",
                "model_coverage_score",
            ]
        ],
        on="investment_product_id",
        how="left",
        validate="one_to_one",
    )

    rows = []
    for _, row in frame.iterrows():
        positives = []
        risks = []
        evidence = []

        cagr = float(
            row.get("forecast_expected_cagr") or 0
        )
        if cagr >= 0.15:
            positives.append(
                "Expected CAGR is materially above the target return."
            )
        elif cagr >= 0.10:
            positives.append(
                "Expected CAGR is above the long-term target."
            )
        elif cagr < 0.04:
            risks.append(
                "Expected CAGR is below the minimum return target."
            )

        conviction = float(
            row.get("conviction_score") or 0
        )
        if conviction >= 75:
            positives.append(
                "Forecast conviction is high."
            )
        elif conviction < 50:
            risks.append(
                "Forecast conviction is weak."
            )

        regime = str(row.get("forecast_regime") or "")
        if regime in {"Bull", "Positive"}:
            positives.append(
                f"Current forecast regime is {regime.lower()}."
            )
        elif regime in {"Weak", "Bear"}:
            risks.append(
                f"Current forecast regime is {regime.lower()}."
            )

        overall_risk = float(
            row.get("overall_risk_score") or 0
        )
        if overall_risk <= 35:
            positives.append(
                "Composite downside risk is low."
            )
        elif overall_risk >= 65:
            risks.append(
                "Composite downside risk is elevated."
            )

        if float(row.get("liquidity_risk") or 0) >= 65:
            risks.append(
                "Liquidity is below the preferred threshold."
            )
        if float(row.get("data_risk") or 0) >= 60:
            risks.append(
                "Historical evidence is limited or incomplete."
            )
        if float(row.get("forecast_risk") or 0) >= 65:
            risks.append(
                "Forecast uncertainty is elevated."
            )

        confidence_score = float(
            row.get("overall_confidence_score") or 0
        )
        evidence.append(
            f"Recommendation confidence is "
            f"{confidence_score:.0f}%."
        )
        evidence.append(
            f"Model coverage is "
            f"{float(row.get('model_coverage_score') or 0):.0f}%."
        )
        evidence.append(
            f"Historical depth score is "
            f"{float(row.get('history_depth_score') or 0):.0f}%."
        )

        summary = (
            f"{row['recommendation']} with "
            f"{confidence_score:.0f}% confidence, "
            f"{overall_risk:.0f}/100 risk, and "
            f"{cagr:.1%} expected CAGR."
        )
        rows.append(
            {
                "investment_product_id": row[
                    "investment_product_id"
                ],
                "box_name": row.get("box_name"),
                "recommendation": row[
                    "recommendation"
                ],
                "recommendation_summary": summary,
                "positive_drivers": " | ".join(
                    positives
                )
                or "No major positive driver cleared the threshold.",
                "risk_factors": " | ".join(risks)
                or "No major risk factor cleared the threshold.",
                "evidence_summary": " | ".join(
                    evidence
                ),
            }
        )
    return pd.DataFrame(rows)


def _buy_list(
    recommendations: pd.DataFrame,
) -> pd.DataFrame:
    eligible = recommendations[
        recommendations["recommendation"].isin(
            ["Strong Buy", "Buy", "Watch"]
        )
    ].copy()
    if eligible.empty:
        columns = list(recommendations.columns) + [
            "buy_list_rank"
        ]
        return pd.DataFrame(columns=columns)

    recommendation_priority = {
        "Strong Buy": 3,
        "Buy": 2,
        "Watch": 1,
    }
    eligible["_recommendation_priority"] = (
        eligible["recommendation"]
        .map(recommendation_priority)
        .fillna(0)
    )
    eligible = eligible.sort_values(
        [
            "_recommendation_priority",
            "recommendation_score",
            "overall_confidence_score",
            "overall_risk_score",
        ],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    eligible["buy_list_rank"] = (
        eligible.index + 1
    )
    return eligible.drop(
        columns=["_recommendation_priority"]
    ).head(50)


def build_core_intelligence_datasets(
    universe: pd.DataFrame,
) -> IntelligenceBuildResult:
    if universe.empty:
        raise ValueError(
            "Core intelligence universe is empty."
        )

    eligible = universe.copy()
    eligible["current_price"] = _num(
        eligible,
        "current_price",
        0,
    )
    eligible = eligible[
        eligible["current_price"] > 0
    ].copy()
    if eligible.empty:
        raise ValueError(
            "Core intelligence universe has no valid prices."
        )

    forecast = build_forecast_datasets(eligible)
    coverage = _coverage(eligible)
    risk = _risk(
        eligible,
        forecast.datasets,
    )
    confidence = _confidence(
        eligible,
        forecast.datasets,
        coverage,
    )
    recommendations = _recommendations(
        forecast.datasets,
        risk,
        confidence,
        coverage,
    )
    factors = _factor_rows(
        recommendations,
        risk,
        confidence,
    )
    explanations = _explanations(
        recommendations,
        risk,
        confidence,
    )
    buy_list = _buy_list(recommendations)

    recommendation_columns = [
        column
        for column in (
            "investment_product_id",
            "box_name",
            "set_name",
            "product_type",
            "current_price",
            "recommendation",
            "recommendation_score",
            "overall_confidence_score",
            "confidence_rating",
            "overall_risk_score",
            "risk_rating",
            "forecast_expected_cagr",
            "forecast_confidence",
            "conviction_score",
            "conviction_tier",
            "forecast_regime",
            "regime_score",
            "model_coverage_score",
            "coverage_status",
            "expected_return_score",
            "risk_quality_score",
        )
        if column in recommendations.columns
    ]
    recommendations = recommendations[
        recommendation_columns
    ].copy()

    return IntelligenceBuildResult(
        datasets={
            "intelligence_risk_assessment": risk,
            "intelligence_confidence_assessment": confidence,
            "intelligence_recommendations": recommendations,
            "intelligence_recommendation_factors": factors,
            "intelligence_recommendation_explanations": explanations,
            "intelligence_model_coverage": coverage,
            "intelligence_executive_buy_list": buy_list,
        }
    )
