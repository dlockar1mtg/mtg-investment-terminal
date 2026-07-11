import numpy as np
import pandas as pd

WEIGHTS = {
    "value_score": 0.13,
    "supply_score": 0.12,
    "demand_score": 0.16,
    "chase_score": 0.12,
    "ip_score": 0.07,
    "historical_score": 0.06,
    "liquidity_score": 0.05,
    "investment_feature_score": 0.08,
    "market_intelligence_score": 0.09,
    "real_signal_score": 0.12,
}

RISK_WEIGHTS = {
    "reprint_risk": 0.22,
    "supply_dump_risk": 0.25,
    "liquidity_risk": 0.18,
    "chase_concentration_risk": 0.20,
    "new_set_uncertainty": 0.15,
}


def clamp(series, low=0, high=100):
    return series.clip(lower=low, upper=high)


def normalize_price_position(df):
    low = pd.to_numeric(df["estimated_floor_price"], errors="coerce").replace(0, np.nan)
    high = pd.to_numeric(df["estimated_ceiling_price"], errors="coerce").replace(0, np.nan)
    price = pd.to_numeric(df["current_price"], errors="coerce")
    position = (price - low) / (high - low)
    return position.replace([np.inf, -np.inf], np.nan).fillna(0.5).clip(0, 1)


def calculate_value_score(df):
    position = normalize_price_position(df)

    fair = pd.to_numeric(df["fair_value_estimate"], errors="coerce").replace(0, np.nan)
    price = pd.to_numeric(df["current_price"], errors="coerce")

    discount_to_target = (fair - price) / fair
    discount_component = (50 + discount_to_target.fillna(0) * 120).clip(0, 100)
    floor_component = (100 - position * 100).clip(0, 100)

    return (floor_component * 0.55 + discount_component * 0.45).round(2)


def calculate_investment_score(df):
    df = df.copy()
    df["value_score"] = calculate_value_score(df)

    for col in WEIGHTS:
        if col not in df.columns:
            df[col] = 50
        df[col] = clamp(pd.to_numeric(df[col], errors="coerce").fillna(50), 0, 100)

    score = sum(df[col] * weight for col, weight in WEIGHTS.items())
    df["investment_score"] = score.round(2)

    for risk_col in RISK_WEIGHTS:
        if risk_col not in df.columns:
            df[risk_col] = 50
        df[risk_col] = clamp(pd.to_numeric(df[risk_col], errors="coerce").fillna(50), 0, 100)

    risk_penalty = sum(df[col] * weight for col, weight in RISK_WEIGHTS.items()) / 100
    df["risk_penalty"] = (risk_penalty * 12).round(2)
    df["risk_adjusted_score"] = (df["investment_score"] - df["risk_penalty"]).round(2)

    return df


def assign_rating(score):
    if score >= 95:
        return "Generational Buy"
    if score >= 90:
        return "Strong Buy"
    if score >= 85:
        return "Buy"
    if score >= 80:
        return "Accumulate"
    if score >= 75:
        return "Fair Value"
    if score >= 70:
        return "Watch"
    if score >= 60:
        return "Speculative"
    return "Avoid"


def assign_buy_signal(row):
    try:
        price = float(row.get("current_price", 0))
        target = float(row.get("target_buy_price", 0))
        score = float(row.get("risk_adjusted_score", 0))
    except Exception:
        return "Data Check"

    if price <= 0 or target <= 0:
        return "Data Check"
    if score < 60:
        return "Avoid"
    if price <= target * 0.95 and score >= 85:
        return "Strong Buy"
    if price <= target and score >= 80:
        return "Buy"
    if price <= target * 1.08 and score >= 78:
        return "Accumulate"
    if score >= 70:
        return "Watch"
    return "Speculative / Wait"


def add_ratings_and_signals(df):
    df = df.copy()
    df["rating"] = df["investment_score"].apply(assign_rating)

    # v8.1 fix:
    # Do not use Series.replace(0, another_series); pandas raises:
    # ValueError: Series.replace cannot use dict-value and non-None to_replace.
    current = pd.to_numeric(df["current_price"], errors="coerce").fillna(0)
    fair = pd.to_numeric(df["fair_value_estimate"], errors="coerce").fillna(0)

    # If fair value is missing/zero, use current market price.
    fair = fair.mask(fair <= 0, current)

    quality = pd.to_numeric(df["risk_adjusted_score"], errors="coerce").fillna(50)

    # Better assets can use a smaller margin of safety; weaker assets need a larger one.
    discount = 0.22 - ((quality - 70).clip(lower=0, upper=25) / 25 * 0.10)

    raw_target = fair * (1 - discount)

    # Target buy should not exceed 95% of current market price.
    cap = current * 0.95
    guarded_target = np.minimum(raw_target, cap)
    guarded_target = pd.Series(guarded_target, index=df.index).clip(lower=0)

    df["target_buy_price"] = guarded_target.round(2)
    df["buy_signal"] = df.apply(assign_buy_signal, axis=1)

    return df
