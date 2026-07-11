from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from config import (
    MARKET_INTELLIGENCE_FILE,
    MONTE_CARLO_OUTPUT_FILE,
    MONTE_CARLO_SIMULATIONS,
    MONTE_CARLO_YEARS,
    MONTE_CARLO_RANDOM_SEED,
)


def _safe_num(series, default=0):
    return pd.to_numeric(series, errors="coerce").fillna(default)


def calculate_liquidity_proxy(row):
    """
    v11 placeholder/proxy until direct listing/sales velocity sources are added.

    Higher price usually means thinner liquidity; older iconic products may offset that.
    """
    price = float(row.get("current_price", 0) or 0)
    set_type = str(row.get("set_type", "")).lower()
    demand = float(row.get("demand_score", 50) or 50)
    ip = float(row.get("ip_score", 50) or 50)

    score = 70
    if price > 1500:
        score -= 20
    elif price > 800:
        score -= 10
    elif price < 350:
        score += 8

    if "universes" in set_type:
        score += 5
    if demand >= 85:
        score += 8
    if ip >= 90:
        score += 5

    return round(max(0, min(100, score)), 2)


def calculate_inventory_risk_proxy(row):
    """
    v11 placeholder/proxy until listing count and inventory trend are collected.
    Higher score = more supply/inventory risk.
    """
    months = float(row.get("months_since_release", 24) or 24)
    supply = float(row.get("supply_score", 50) or 50)
    price = float(row.get("current_price", 0) or 0)

    risk = 55

    if months < 6:
        risk += 20
    elif months < 12:
        risk += 10
    elif months > 36:
        risk -= 12

    if supply >= 80:
        risk -= 8
    elif supply <= 45:
        risk += 8

    if price > 1500:
        risk -= 5

    return round(max(0, min(100, risk)), 2)


def calculate_market_regime_score(row):
    """
    Combines price trend, drawdown, volatility, and history confidence.
    With limited history this stays neutral.
    """
    hist_conf = float(row.get("history_confidence", 0) or 0)
    momentum = float(row.get("momentum_score", 50) or 50)
    stability = float(row.get("price_stability_score", 50) or 50)
    drawdown = float(row.get("drawdown_score", 50) or 50)

    raw = momentum * 0.40 + stability * 0.25 + drawdown * 0.25 + hist_conf * 0.10
    return round(max(0, min(100, raw)), 2)


def calculate_market_intelligence_score(row):
    liquidity = float(row.get("liquidity_proxy_score", 50) or 50)
    inventory_risk = float(row.get("inventory_risk_proxy", 50) or 50)
    regime = float(row.get("market_regime_score", 50) or 50)
    investment_feature = float(row.get("investment_feature_score", 50) or 50)

    score = (
        regime * 0.35 +
        liquidity * 0.25 +
        (100 - inventory_risk) * 0.20 +
        investment_feature * 0.20
    )
    return round(max(0, min(100, score)), 2)


def add_market_intelligence_features(df):
    model = df.copy()

    model["liquidity_proxy_score"] = model.apply(calculate_liquidity_proxy, axis=1)
    model["inventory_risk_proxy"] = model.apply(calculate_inventory_risk_proxy, axis=1)
    model["market_regime_score"] = model.apply(calculate_market_regime_score, axis=1)
    model["market_intelligence_score"] = model.apply(calculate_market_intelligence_score, axis=1)

    Path(MARKET_INTELLIGENCE_FILE).parent.mkdir(parents=True, exist_ok=True)
    model.to_csv(MARKET_INTELLIGENCE_FILE, index=False)
    return model


def monte_carlo_for_row(row, rng):
    current = float(row.get("current_price", 0) or 0)
    base_cagr = float(row.get("expected_cagr", row.get("base_cagr", 0.08)) or 0.08)

    # Use observed volatility when available; otherwise use a conservative proxy.
    vol = row.get("annualized_volatility")
    try:
        vol = float(vol)
    except Exception:
        vol = np.nan

    if np.isnan(vol) or vol <= 0:
        price = current
        if price > 1500:
            vol = 0.28
        elif price > 700:
            vol = 0.34
        else:
            vol = 0.40

    hist_conf = float(row.get("history_confidence", 0) or 0)
    intelligence = float(row.get("market_intelligence_score", 50) or 50)

    # Confidence narrows volatility slightly; weak intelligence reduces drift.
    confidence_multiplier = 1 - min(0.25, hist_conf / 400)
    sim_vol = vol * confidence_multiplier
    drift_adj = ((intelligence - 50) / 50) * 0.015
    drift = base_cagr + drift_adj

    sims = int(MONTE_CARLO_SIMULATIONS)
    years = int(MONTE_CARLO_YEARS)

    # lognormal terminal value approximation
    shocks = rng.normal(
        loc=(drift - 0.5 * sim_vol ** 2) * years,
        scale=sim_vol * np.sqrt(years),
        size=sims,
    )
    terminal = current * np.exp(shocks)

    return {
        "box_name": row.get("box_name"),
        "current_price": round(current, 2),
        "mc_expected_value": round(float(np.mean(terminal)), 2),
        "mc_median": round(float(np.percentile(terminal, 50)), 2),
        "mc_p05": round(float(np.percentile(terminal, 5)), 2),
        "mc_p25": round(float(np.percentile(terminal, 25)), 2),
        "mc_p75": round(float(np.percentile(terminal, 75)), 2),
        "mc_p95": round(float(np.percentile(terminal, 95)), 2),
        "prob_double": round(float(np.mean(terminal >= current * 2)), 4),
        "prob_triple": round(float(np.mean(terminal >= current * 3)), 4),
        "prob_loss": round(float(np.mean(terminal < current)), 4),
        "simulated_cagr_base": round(drift, 4),
        "simulated_volatility": round(sim_vol, 4),
    }


def run_monte_carlo(df):
    if df is None or df.empty:
        return pd.DataFrame()

    rng = np.random.default_rng(MONTE_CARLO_RANDOM_SEED)
    rows = [monte_carlo_for_row(row, rng) for _, row in df.iterrows()]
    out = pd.DataFrame(rows)

    Path(MONTE_CARLO_OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(MONTE_CARLO_OUTPUT_FILE, index=False)
    return out


def apply_market_intelligence(df):
    model = add_market_intelligence_features(df)
    mc = run_monte_carlo(model)

    if not mc.empty:
        merge_cols = [
            "box_name",
            "mc_expected_value",
            "mc_median",
            "mc_p05",
            "mc_p25",
            "mc_p75",
            "mc_p95",
            "prob_double",
            "prob_triple",
            "prob_loss",
        ]
        model = model.merge(mc[merge_cols], on="box_name", how="left")

    return model
