from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from terminal2.config import (
    PORTFOLIO_HOLDINGS_FILE,
    PORTFOLIO_HOLDINGS_TEMPLATE_FILE,
)
from terminal2.db.module2_migration import migrate_module2
from terminal2.db.schema import get_connection


HOLDINGS_COLUMNS = (
    "investment_product_id",
    "quantity",
    "acquisition_cost_total",
    "acquisition_date",
    "notes",
)


@dataclass(frozen=True)
class PortfolioBuildResult:
    datasets: dict[str, pd.DataFrame]
    holdings_file_found: bool
    model_capital: float


def _asset_group(value: object) -> str:
    text = str(value or "").lower()
    if "collector" in text:
        return "Collector Booster Displays"
    if "secret lair" in text:
        return "Secret Lair"
    if "draft" in text or "traditional" in text or "booster box" in text:
        return "Draft / Traditional Booster Boxes"
    if "jumpstart" in text:
        return "Jumpstart"
    if "theme" in text:
        return "Theme Booster"
    return "Other Sealed"


def create_holdings_template(path: Path = PORTFOLIO_HOLDINGS_TEMPLATE_FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        pd.DataFrame(columns=HOLDINGS_COLUMNS).to_csv(path, index=False)
    return path


def load_portfolio_holdings(
    path: Path = PORTFOLIO_HOLDINGS_FILE,
) -> tuple[pd.DataFrame, bool]:
    create_holdings_template()
    if not path.exists():
        return pd.DataFrame(columns=HOLDINGS_COLUMNS), False

    holdings = pd.read_csv(path)
    missing = sorted(set(HOLDINGS_COLUMNS) - set(holdings.columns))
    if missing:
        raise ValueError(
            f"Portfolio holdings file is missing columns: {missing}"
        )

    holdings = holdings[list(HOLDINGS_COLUMNS)].copy()
    holdings["investment_product_id"] = (
        holdings["investment_product_id"].astype(str).str.strip()
    )
    holdings["quantity"] = pd.to_numeric(
        holdings["quantity"], errors="coerce"
    )
    holdings["acquisition_cost_total"] = pd.to_numeric(
        holdings["acquisition_cost_total"], errors="coerce"
    )
    holdings = holdings.dropna(
        subset=["investment_product_id", "quantity"]
    )
    holdings = holdings[
        (holdings["investment_product_id"] != "")
        & (holdings["quantity"] > 0)
    ].copy()

    if holdings["investment_product_id"].duplicated().any():
        holdings = (
            holdings.groupby("investment_product_id", as_index=False)
            .agg(
                quantity=("quantity", "sum"),
                acquisition_cost_total=(
                    "acquisition_cost_total",
                    "sum",
                ),
                acquisition_date=("acquisition_date", "min"),
                notes=("notes", lambda values: " | ".join(
                    sorted({
                        str(value)
                        for value in values
                        if pd.notna(value) and str(value).strip()
                    })
                )),
            )
        )
    return holdings, True


def load_portfolio_universe() -> pd.DataFrame:
    migrate_module2()
    connection = get_connection()
    try:
        return pd.read_sql_query(
            """
            SELECT
                p.investment_product_id,
                p.box_name,
                p.set_name,
                p.product_type,
                p.approval_status,
                s.current_price,
                s.investment_score,
                s.risk_adjusted_score,
                s.rating,
                s.buy_signal,
                s.target_buy_price,
                s.expected_cagr,
                s.projection_confidence,
                s.mc_median_5yr,
                s.mc_p05_5yr,
                s.mc_p95_5yr,
                s.prob_double,
                s.prob_loss,
                f.annualized_volatility,
                f.drawdown_from_ath,
                f.history_confidence,
                f.observation_count,
                mi.market_intelligence_score,
                mi.market_intelligence_confidence,
                mi.liquidity_score,
                mi.supply_signal_score,
                mi.sales_velocity_score
            FROM products p
            LEFT JOIN investment_scores s
              ON s.investment_product_id = p.investment_product_id
            LEFT JOIN product_features f
              ON f.investment_product_id = p.investment_product_id
            LEFT JOIN market_intelligence mi
              ON mi.investment_product_id = p.investment_product_id
            WHERE LOWER(COALESCE(p.approval_status, '')) = 'approved'
            """,
            connection,
        )
    finally:
        connection.close()


def _number(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(default)


def _conviction(universe: pd.DataFrame) -> pd.Series:
    risk = _number(universe, "risk_adjusted_score", 50).clip(0, 100)
    market = _number(universe, "market_intelligence_score", 50).clip(0, 100)
    confidence = (
        _number(universe, "projection_confidence", 0) * 0.6
        + _number(universe, "market_intelligence_confidence", 0) * 0.4
    ).clip(0, 100)
    cagr_score = ((_number(universe, "expected_cagr", 0.06) - 0.02) / 0.20 * 100).clip(0, 100)
    downside_score = (100 - _number(universe, "prob_loss", 0.40) * 100).clip(0, 100)
    return (
        risk * 0.35
        + market * 0.20
        + confidence * 0.15
        + cagr_score * 0.15
        + downside_score * 0.15
    ).round(2)


def _bounded_weights(scores: pd.Series, maximum: float = 0.15) -> pd.Series:
    scores = scores.clip(lower=0).astype(float)
    if scores.sum() <= 0:
        return pd.Series(0.0, index=scores.index)

    weights = scores / scores.sum()
    for _ in range(20):
        over = weights > maximum
        if not over.any():
            break
        excess = float((weights[over] - maximum).sum())
        weights.loc[over] = maximum
        under = ~over
        denominator = float(weights.loc[under].sum())
        if denominator <= 0:
            break
        weights.loc[under] += weights.loc[under] / denominator * excess

    return (weights / weights.sum()).round(6)


def _candidate_allocation(
    universe: pd.DataFrame,
    model_capital: float,
    maximum_positions: int,
) -> pd.DataFrame:
    df = universe.copy()
    df["current_price"] = _number(df, "current_price")
    df["conviction_score"] = _conviction(df)
    df["asset_group"] = df["product_type"].apply(_asset_group)

    eligible = df[
        (df["current_price"] > 0)
        & (_number(df, "risk_adjusted_score", 0) >= 55)
        & (_number(df, "projection_confidence", 0) >= 20)
    ].copy()
    eligible = eligible.sort_values(
        ["conviction_score", "risk_adjusted_score"],
        ascending=False,
    ).head(maximum_positions)

    columns = [
        "investment_product_id",
        "box_name",
        "asset_group",
        "allocation_rank",
        "target_weight",
        "recommended_dollar_amount",
        "recommended_units",
        "current_price",
        "conviction_score",
        "risk_adjusted_score",
        "market_intelligence_score",
        "expected_cagr",
        "projection_confidence",
        "prob_loss",
        "buy_signal",
    ]
    if eligible.empty:
        return pd.DataFrame(columns=columns)

    raw_scores = eligible["conviction_score"].clip(lower=1) ** 1.5
    eligible["target_weight"] = _bounded_weights(raw_scores, maximum=0.15)
    eligible["recommended_dollar_amount"] = (
        eligible["target_weight"] * float(model_capital)
    ).round(2)
    eligible["recommended_units"] = np.floor(
        eligible["recommended_dollar_amount"]
        / eligible["current_price"]
    ).astype(int)
    eligible["allocation_rank"] = range(1, len(eligible) + 1)
    return eligible[[column for column in columns if column in eligible.columns]]


def _positions(
    universe: pd.DataFrame,
    holdings: pd.DataFrame,
) -> pd.DataFrame:
    required = [
        "investment_product_id",
        "quantity",
        "acquisition_cost_total",
        "acquisition_date",
        "notes",
        "box_name",
        "set_name",
        "product_type",
        "asset_group",
        "current_price",
        "current_value",
        "portfolio_weight",
        "cost_basis_per_unit",
        "unrealized_gain",
        "unrealized_gain_pct",
        "investment_score",
        "risk_adjusted_score",
        "market_intelligence_score",
        "expected_cagr",
        "projection_confidence",
        "annualized_volatility",
        "prob_loss",
        "mc_median_5yr",
    ]
    if holdings.empty:
        return pd.DataFrame(columns=required)

    positions = holdings.merge(
        universe,
        on="investment_product_id",
        how="left",
        validate="one_to_one",
    )
    missing_products = positions["box_name"].isna()
    if missing_products.any():
        missing = positions.loc[
            missing_products, "investment_product_id"
        ].tolist()
        raise ValueError(
            f"Holdings contain unknown product IDs: {missing}"
        )

    positions["current_price"] = _number(positions, "current_price")
    positions["current_value"] = (
        positions["quantity"] * positions["current_price"]
    ).round(2)
    total_value = float(positions["current_value"].sum())
    positions["portfolio_weight"] = np.where(
        total_value > 0,
        positions["current_value"] / total_value,
        0,
    )
    positions["cost_basis_per_unit"] = np.where(
        positions["quantity"] > 0,
        positions["acquisition_cost_total"] / positions["quantity"],
        np.nan,
    )
    positions["unrealized_gain"] = (
        positions["current_value"]
        - positions["acquisition_cost_total"].fillna(0)
    ).round(2)
    positions["unrealized_gain_pct"] = np.where(
        positions["acquisition_cost_total"] > 0,
        positions["unrealized_gain"]
        / positions["acquisition_cost_total"],
        np.nan,
    )
    positions["asset_group"] = positions["product_type"].apply(_asset_group)
    return positions[[column for column in required if column in positions.columns]]


def _allocation(positions: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "asset_group",
        "position_count",
        "current_value",
        "portfolio_weight",
        "average_risk_adjusted_score",
        "average_projection_confidence",
    ]
    if positions.empty:
        return pd.DataFrame(columns=columns)

    allocation = (
        positions.groupby("asset_group", as_index=False)
        .agg(
            position_count=("investment_product_id", "nunique"),
            current_value=("current_value", "sum"),
            average_risk_adjusted_score=(
                "risk_adjusted_score",
                "mean",
            ),
            average_projection_confidence=(
                "projection_confidence",
                "mean",
            ),
        )
    )
    total = float(allocation["current_value"].sum())
    allocation["portfolio_weight"] = np.where(
        total > 0, allocation["current_value"] / total, 0
    )
    return allocation[columns]


def _risk_exposure(positions: pd.DataFrame) -> pd.DataFrame:
    columns = ["risk_metric", "metric_value", "risk_level", "description"]
    if positions.empty:
        rows = [
            {
                "risk_metric": "Position Count",
                "metric_value": 0.0,
                "risk_level": "No Holdings",
                "description": "No actual portfolio holdings file was found.",
            }
        ]
        return pd.DataFrame(rows, columns=columns)

    weights = _number(positions, "portfolio_weight")
    max_weight = float(weights.max())
    top3 = float(weights.nlargest(3).sum())
    hhi = float((weights ** 2).sum())
    weighted_vol = float(
        (
            weights
            * _number(positions, "annualized_volatility", 0)
        ).sum()
    )
    weighted_loss = float(
        (weights * _number(positions, "prob_loss", 0.4)).sum()
    )
    weighted_confidence = float(
        (
            weights
            * _number(positions, "projection_confidence", 0)
        ).sum()
    )

    def level(value: float, low: float, high: float) -> str:
        if value >= high:
            return "High"
        if value >= low:
            return "Moderate"
        return "Low"

    rows = [
        {
            "risk_metric": "Largest Position Weight",
            "metric_value": round(max_weight, 4),
            "risk_level": level(max_weight, 0.15, 0.25),
            "description": "Share of portfolio held in the largest single position.",
        },
        {
            "risk_metric": "Top 3 Concentration",
            "metric_value": round(top3, 4),
            "risk_level": level(top3, 0.45, 0.65),
            "description": "Combined weight of the three largest positions.",
        },
        {
            "risk_metric": "Herfindahl Concentration",
            "metric_value": round(hhi, 4),
            "risk_level": level(hhi, 0.12, 0.20),
            "description": "Squared-weight concentration index.",
        },
        {
            "risk_metric": "Weighted Annualized Volatility",
            "metric_value": round(weighted_vol, 4),
            "risk_level": level(weighted_vol, 0.25, 0.45),
            "description": "Weighted average of position volatility estimates.",
        },
        {
            "risk_metric": "Weighted Probability of Loss",
            "metric_value": round(weighted_loss, 4),
            "risk_level": level(weighted_loss, 0.25, 0.35),
            "description": "Weighted modeled probability of loss.",
        },
        {
            "risk_metric": "Weighted Projection Confidence",
            "metric_value": round(weighted_confidence, 2),
            "risk_level": (
                "Low" if weighted_confidence >= 65
                else "Moderate" if weighted_confidence >= 40
                else "High"
            ),
            "description": "Low confidence is treated as higher portfolio risk.",
        },
    ]
    return pd.DataFrame(rows, columns=columns)


def _recommendations(
    universe: pd.DataFrame,
    positions: pd.DataFrame,
    candidates: pd.DataFrame,
    model_capital: float,
) -> pd.DataFrame:
    candidate_targets = candidates[
        [
            "investment_product_id",
            "target_weight",
            "recommended_dollar_amount",
            "conviction_score",
        ]
    ].copy() if not candidates.empty else pd.DataFrame(
        columns=[
            "investment_product_id",
            "target_weight",
            "recommended_dollar_amount",
            "conviction_score",
        ]
    )

    base = universe.merge(
        candidate_targets,
        on="investment_product_id",
        how="left",
    )
    owned = set(
        positions["investment_product_id"].tolist()
        if not positions.empty else []
    )
    actual_weights = (
        positions.set_index("investment_product_id")["portfolio_weight"]
        if not positions.empty else pd.Series(dtype=float)
    )
    base["current_portfolio_weight"] = (
        base["investment_product_id"].map(actual_weights).fillna(0)
    )
    base["target_weight"] = _number(base, "target_weight")
    base["recommended_dollar_amount"] = _number(
        base, "recommended_dollar_amount"
    )
    base["recommendation_score"] = _number(
        base, "conviction_score", 0
    )

    def action(row) -> str:
        product_id = row["investment_product_id"]
        current_weight = float(row["current_portfolio_weight"])
        target_weight = float(row["target_weight"])
        risk_score = float(row.get("risk_adjusted_score") or 0)
        buy_signal = str(row.get("buy_signal") or "")

        if product_id in owned:
            if risk_score < 55 or buy_signal == "Wait":
                return "Review / Reduce"
            if target_weight > 0 and current_weight > target_weight * 1.35:
                return "Trim"
            if target_weight > current_weight * 1.20:
                return "Add"
            return "Hold"
        if target_weight > 0:
            return "Candidate Buy"
        if risk_score < 55:
            return "Avoid"
        return "Watch"

    base["recommendation"] = base.apply(action, axis=1)
    base["weight_gap"] = (
        base["target_weight"] - base["current_portfolio_weight"]
    ).round(6)
    base["recommended_incremental_amount"] = (
        base["weight_gap"].clip(lower=0) * float(model_capital)
    ).round(2)

    columns = [
        "investment_product_id",
        "box_name",
        "product_type",
        "recommendation",
        "recommendation_score",
        "current_portfolio_weight",
        "target_weight",
        "weight_gap",
        "recommended_dollar_amount",
        "recommended_incremental_amount",
        "current_price",
        "risk_adjusted_score",
        "market_intelligence_score",
        "expected_cagr",
        "projection_confidence",
        "prob_loss",
        "buy_signal",
    ]
    return (
        base[[column for column in columns if column in base.columns]]
        .sort_values(
            ["recommendation_score", "risk_adjusted_score"],
            ascending=False,
        )
        .reset_index(drop=True)
    )


def _scenarios(positions: pd.DataFrame) -> pd.DataFrame:
    current_value = float(
        positions["current_value"].sum()
        if not positions.empty else 0
    )
    if positions.empty:
        modeled_5yr = 0.0
        downside_model = 0.0
        upside_model = 0.0
    else:
        modeled_5yr = float(
            (
                positions["quantity"]
                * _number(positions, "mc_median_5yr")
            ).sum()
        )
        downside_model = float(
            (
                positions["quantity"]
                * _number(positions, "current_price")
                * (1 - _number(positions, "prob_loss", 0.4))
                * 0.70
            ).sum()
        )
        upside_model = float(
            (
                positions["quantity"]
                * _number(positions, "mc_median_5yr")
                * 1.25
            ).sum()
        )

    scenarios = [
        ("Immediate -20% Shock", current_value * 0.80),
        ("Current Market Value", current_value),
        ("Immediate +20% Move", current_value * 1.20),
        ("Risk-Adjusted Downside", downside_model),
        ("Five-Year Median Model", modeled_5yr),
        ("Five-Year Upside Model", upside_model),
    ]
    rows = []
    for name, value in scenarios:
        change = value - current_value
        pct = change / current_value if current_value > 0 else 0.0
        rows.append(
            {
                "scenario_name": name,
                "scenario_value": round(value, 2),
                "change_amount": round(change, 2),
                "change_pct": round(pct, 4),
            }
        )
    return pd.DataFrame(rows)


def _summary(
    positions: pd.DataFrame,
    candidates: pd.DataFrame,
    model_capital: float,
    holdings_file_found: bool,
) -> pd.DataFrame:
    current_value = float(
        positions["current_value"].sum()
        if not positions.empty else 0
    )
    total_cost = float(
        positions["acquisition_cost_total"].fillna(0).sum()
        if not positions.empty else 0
    )
    unrealized = current_value - total_cost
    weights = _number(positions, "portfolio_weight")
    concentration = float((weights ** 2).sum()) if len(weights) else 0
    weighted_score = float(
        (
            weights
            * _number(positions, "risk_adjusted_score", 0)
        ).sum()
    ) if len(weights) else 0
    weighted_confidence = float(
        (
            weights
            * _number(positions, "projection_confidence", 0)
        ).sum()
    ) if len(weights) else 0
    diversification_score = max(0.0, min(100.0, (1 - concentration) * 100))
    health = (
        weighted_score * 0.50
        + weighted_confidence * 0.25
        + diversification_score * 0.25
    ) if len(weights) else 0.0

    return pd.DataFrame(
        [
            {
                "snapshot_date": datetime.now(
                    timezone.utc
                ).date().isoformat(),
                "holdings_file_found": holdings_file_found,
                "position_count": int(len(positions)),
                "current_value": round(current_value, 2),
                "total_cost_basis": round(total_cost, 2),
                "unrealized_gain": round(unrealized, 2),
                "unrealized_gain_pct": round(
                    unrealized / total_cost, 4
                ) if total_cost > 0 else 0.0,
                "portfolio_health_score": round(health, 2),
                "weighted_risk_adjusted_score": round(
                    weighted_score, 2
                ),
                "weighted_projection_confidence": round(
                    weighted_confidence, 2
                ),
                "concentration_score": round(
                    concentration * 100, 2
                ),
                "model_portfolio_capital": round(
                    float(model_capital), 2
                ),
                "model_candidate_count": int(len(candidates)),
            }
        ]
    )


def build_portfolio_datasets(
    universe: pd.DataFrame,
    holdings: pd.DataFrame,
    *,
    model_capital: float = 10000.0,
    maximum_positions: int = 12,
    holdings_file_found: bool = True,
) -> PortfolioBuildResult:
    universe = universe.copy()
    universe["asset_group"] = universe["product_type"].apply(_asset_group)
    candidates = _candidate_allocation(
        universe,
        model_capital=float(model_capital),
        maximum_positions=int(maximum_positions),
    )
    positions = _positions(universe, holdings)
    allocation = _allocation(positions)
    risk = _risk_exposure(positions)
    recommendations = _recommendations(
        universe,
        positions,
        candidates,
        model_capital=float(model_capital),
    )
    scenarios = _scenarios(positions)
    summary = _summary(
        positions,
        candidates,
        model_capital=float(model_capital),
        holdings_file_found=holdings_file_found,
    )

    return PortfolioBuildResult(
        datasets={
            "portfolio_positions": positions,
            "portfolio_allocation": allocation,
            "portfolio_risk_exposure": risk,
            "portfolio_recommendations": recommendations,
            "portfolio_candidate_allocation": candidates,
            "portfolio_scenarios": scenarios,
            "portfolio_summary": summary,
        },
        holdings_file_found=holdings_file_found,
        model_capital=float(model_capital),
    )
