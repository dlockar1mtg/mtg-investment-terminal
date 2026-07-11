import pandas as pd
from config import (
    MIN_PORTFOLIO_RISK_ADJUSTED_SCORE,
    MIN_PORTFOLIO_EXPECTED_CAGR,
    ALLOW_SPECULATIVE_IN_PORTFOLIO,
    MAX_QUANTITY_PER_BOX,
    MAX_ALLOCATION_PER_BOX,
)

def optimize_portfolio(df, budget):
    candidates = df.copy()

    candidates = candidates[
        (candidates["risk_adjusted_score"] >= MIN_PORTFOLIO_RISK_ADJUSTED_SCORE) &
        (candidates["expected_cagr"] >= MIN_PORTFOLIO_EXPECTED_CAGR)
    ]

    if not ALLOW_SPECULATIVE_IN_PORTFOLIO:
        candidates = candidates[~candidates["rating"].isin(["Speculative", "Avoid", "Watch"])]

    candidates = candidates.sort_values(
        by=["risk_adjusted_score", "expected_cagr", "projection_confidence"],
        ascending=False
    )

    remaining = float(budget)
    picks = []
    spent_by_box = {}

    # Greedy quality-first allocation.
    while True:
        affordable = candidates[candidates["current_price"] <= remaining].copy()
        if affordable.empty:
            break

        selected = None
        for _, row in affordable.iterrows():
            name = row["box_name"]
            current_qty = spent_by_box.get(name, 0)
            max_spend_for_box = budget * MAX_ALLOCATION_PER_BOX
            if current_qty >= MAX_QUANTITY_PER_BOX:
                continue
            if (current_qty + 1) * row["current_price"] > max_spend_for_box and current_qty > 0:
                continue
            selected = row
            break

        if selected is None:
            break

        picks.append(selected.to_dict())
        spent_by_box[selected["box_name"]] = spent_by_box.get(selected["box_name"], 0) + 1
        remaining -= float(selected["current_price"])

    if not picks:
        return pd.DataFrame()

    picks_df = pd.DataFrame(picks)
    grouped = (
        picks_df
        .groupby(["box_name", "set_type"], as_index=False)
        .agg(
            quantity=("box_name", "size"),
            unit_price=("current_price", "first"),
            investment_score=("investment_score", "first"),
            risk_adjusted_score=("risk_adjusted_score", "first"),
            expected_cagr=("expected_cagr", "first"),
            projection_confidence=("projection_confidence", "first"),
            bear_cagr=("bear_cagr", "first"),
            base_cagr=("base_cagr", "first"),
            bull_cagr=("bull_cagr", "first"),
            base_5yr=("base_5yr", "first"),
            bear_5yr=("bear_5yr", "first"),
            bull_5yr=("bull_5yr", "first"),
        )
    )

    grouped["total_cost"] = grouped["quantity"] * grouped["unit_price"]
    grouped["projected_5yr_value"] = grouped["quantity"] * grouped["base_5yr"]
    grouped["bear_5yr_value"] = grouped["quantity"] * grouped["bear_5yr"]
    grouped["bull_5yr_value"] = grouped["quantity"] * grouped["bull_5yr"]

    ordered_cols = [
        "box_name",
        "set_type",
        "quantity",
        "unit_price",
        "total_cost",
        "investment_score",
        "risk_adjusted_score",
        "expected_cagr",
        "projection_confidence",
        "bear_cagr",
        "base_cagr",
        "bull_cagr",
        "projected_5yr_value",
        "bear_5yr_value",
        "bull_5yr_value",
    ]
    return grouped[ordered_cols].sort_values(
        by=["risk_adjusted_score", "expected_cagr"],
        ascending=False
    ).round(2)
