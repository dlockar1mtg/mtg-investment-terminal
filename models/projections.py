import numpy as np
import pandas as pd
from config import MIN_EXPECTED_CAGR

def age_adjustment(months_since_release):
    if months_since_release < 6:
        return -0.05
    if months_since_release < 12:
        return -0.025
    if months_since_release < 24:
        return 0.00
    if months_since_release < 48:
        return 0.015
    return 0.025

def get_tiered_cagr_caps(investment_score, projection_confidence, set_type):
    if investment_score >= 90:
        base_cap, bull_cap = 0.28, 0.36
    elif investment_score >= 85:
        base_cap, bull_cap = 0.25, 0.33
    elif investment_score >= 80:
        base_cap, bull_cap = 0.22, 0.30
    elif investment_score >= 75:
        base_cap, bull_cap = 0.18, 0.25
    else:
        base_cap, bull_cap = 0.14, 0.20

    if projection_confidence < 70:
        base_cap -= 0.02
        bull_cap -= 0.03

    st = str(set_type).lower()
    if "universes" in st or "masters" in st:
        base_cap += 0.01
        bull_cap += 0.01

    return max(0.02, base_cap), max(0.05, bull_cap)

def cohort_base_cagr(row):
    set_type = str(row.get("set_type", "")).lower()
    ip = row.get("ip_score", 50)
    demand = row.get("demand_score", 50)
    chase = row.get("chase_score", 50)
    supply = row.get("supply_score", 50)
    historical = row.get("historical_score", 50)
    value = row.get("value_score", 50)
    months = row.get("months_since_release", 18)

    type_anchor = 0.06
    if "universes" in set_type:
        type_anchor = 0.105
    elif "masters" in set_type:
        type_anchor = 0.095
    elif "modern horizons" in set_type:
        type_anchor = 0.09
    elif "standard" in set_type:
        type_anchor = 0.055

    quality = (
        (demand - 50) * 0.0014 +
        (chase - 50) * 0.0012 +
        (supply - 50) * 0.0010 +
        (ip - 50) * 0.0010 +
        (historical - 50) * 0.0011 +
        (value - 50) * 0.0008
    )

    risk_drag = (
        row.get("reprint_risk", 50) * 0.00035 +
        row.get("supply_dump_risk", 50) * 0.00045 +
        row.get("chase_concentration_risk", 50) * 0.00025
    )

    # v10: small empirical feature adjustment.
    # This is intentionally modest until the project accumulates enough history.
    investment_feature = row.get("investment_feature_score", 50)
    history_conf = row.get("history_confidence", 0)
    try:
        empirical_adj = ((float(investment_feature) - 50) / 50) * 0.025 * (float(history_conf) / 100)
    except Exception:
        empirical_adj = 0

    raw = type_anchor + quality + age_adjustment(months) - risk_drag + empirical_adj
    return float(max(raw, MIN_EXPECTED_CAGR))

def scenario_cagrs(raw_base_cagr, row):
    confidence = row.get("projection_confidence", 65)
    investment_score = row.get("investment_score", 70)
    set_type = row.get("set_type", "")

    base_cap, bull_cap = get_tiered_cagr_caps(investment_score, confidence, set_type)
    base = min(raw_base_cagr, base_cap)

    spread_bonus = max(0, (75 - confidence) / 100)
    bear_spread = 0.055 + spread_bonus * 0.035
    bull_spread = 0.075 + spread_bonus * 0.045

    bear = max(base - bear_spread, MIN_EXPECTED_CAGR)
    bull = min(base + bull_spread, bull_cap)
    return bear, base, bull, base_cap, bull_cap

def calculate_projection_confidence(row):
    months = row.get("months_since_release", 0)
    data_quality = row.get("data_quality_score", 60)
    price_quality = row.get("price_data_quality", 70)
    liquidity = row.get("liquidity_score", 60)
    volatility = row.get("volatility_score", 50)
    supply_dump = row.get("supply_dump_risk", 50)

    age_component = min(100, 45 + months * 1.6)
    conf = (
        age_component * 0.25 +
        data_quality * 0.22 +
        price_quality * 0.16 +
        row.get("history_confidence", 0) * 0.07 +
        liquidity * 0.10 +
        (100 - volatility) * 0.10 +
        (100 - supply_dump) * 0.10
    )
    return round(float(np.clip(conf, 30, 95)), 1)

def add_projections(df):
    df = df.copy()
    df["projection_confidence"] = df.apply(calculate_projection_confidence, axis=1)
    df["raw_base_cagr"] = df.apply(cohort_base_cagr, axis=1)
    scenario_values = df.apply(lambda r: scenario_cagrs(r["raw_base_cagr"], r), axis=1)

    df["bear_cagr"] = [x[0] for x in scenario_values]
    df["base_cagr"] = [x[1] for x in scenario_values]
    df["expected_cagr"] = df["base_cagr"]
    df["bull_cagr"] = [x[2] for x in scenario_values]
    df["base_cagr_cap"] = [x[3] for x in scenario_values]
    df["bull_cagr_cap"] = [x[4] for x in scenario_values]

    for scenario in ["bear", "base", "bull"]:
        cagr_col = f"{scenario}_cagr"
        out_col = f"{scenario}_5yr"
        df[out_col] = (df["current_price"] * ((1 + df[cagr_col]) ** 5)).round(2)

    for col in ["raw_base_cagr", "bear_cagr", "base_cagr", "expected_cagr", "bull_cagr", "base_cagr_cap", "bull_cagr_cap"]:
        df[col] = df[col].round(4)

    return df
