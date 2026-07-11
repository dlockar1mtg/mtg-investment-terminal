from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np

from config import (
    INVENTORY_SIGNALS_FILE,
    SALES_VELOCITY_FILE,
    DEMAND_SIGNALS_FILE,
    SCARCITY_SIGNALS_FILE,
    REAL_SIGNAL_OUTPUT_FILE,
)


def _load_optional(path, required_cols):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=required_cols)
    df = pd.read_csv(path, dtype={"investment_product_id": str})
    for col in required_cols:
        if col not in df.columns:
            df[col] = np.nan
    return df


def load_external_signal_inputs():
    inventory = _load_optional(INVENTORY_SIGNALS_FILE, [
        "investment_product_id",
        "listing_count",
        "seller_count",
        "inventory_units",
        "inventory_change_7d",
        "inventory_change_30d",
        "inventory_confidence",
    ])
    sales = _load_optional(SALES_VELOCITY_FILE, [
        "investment_product_id",
        "sales_7d",
        "sales_30d",
        "median_sold_price_30d",
        "sell_through_rate_30d",
        "sales_confidence",
    ])
    demand = _load_optional(DEMAND_SIGNALS_FILE, [
        "investment_product_id",
        "commander_demand_score",
        "modern_demand_score",
        "legacy_demand_score",
        "cube_demand_score",
        "collector_demand_score",
        "demand_confidence",
    ])
    scarcity = _load_optional(SCARCITY_SIGNALS_FILE, [
        "investment_product_id",
        "months_out_of_print",
        "estimated_print_window_months",
        "serialized_chase_score",
        "reprint_risk_override",
        "scarcity_confidence",
    ])
    return inventory, sales, demand, scarcity


def merge_signal_inputs(model_df):
    model = model_df.copy()
    model["investment_product_id"] = model["investment_product_id"].astype(str)

    for extra in load_external_signal_inputs():
        if extra.empty:
            continue
        extra["investment_product_id"] = extra["investment_product_id"].astype(str)
        model = model.merge(extra, on="investment_product_id", how="left")

    return model


def score_inventory_signal(row):
    listing_count = row.get("listing_count")
    inventory_change_30d = row.get("inventory_change_30d")
    inventory_conf = row.get("inventory_confidence")

    # No input yet: neutral-low confidence.
    if pd.isna(listing_count) and pd.isna(inventory_change_30d):
        return 50, 0

    score = 50
    try:
        lc = float(listing_count)
        if lc < 25:
            score += 20
        elif lc < 75:
            score += 10
        elif lc > 250:
            score -= 15
    except Exception:
        pass

    try:
        change = float(inventory_change_30d)
        # falling inventory is bullish
        if change < -0.20:
            score += 20
        elif change < -0.05:
            score += 10
        elif change > 0.20:
            score -= 15
    except Exception:
        pass

    conf = 50 if pd.isna(inventory_conf) else float(inventory_conf)
    return round(max(0, min(100, score)), 2), round(max(0, min(100, conf)), 2)


def score_sales_signal(row):
    sell_through = row.get("sell_through_rate_30d")
    sales_30d = row.get("sales_30d")
    sales_conf = row.get("sales_confidence")

    if pd.isna(sell_through) and pd.isna(sales_30d):
        return 50, 0

    score = 50
    try:
        st = float(sell_through)
        if st > 0.35:
            score += 25
        elif st > 0.15:
            score += 12
        elif st < 0.03:
            score -= 15
    except Exception:
        pass

    try:
        s30 = float(sales_30d)
        if s30 >= 20:
            score += 15
        elif s30 >= 8:
            score += 8
        elif s30 <= 1:
            score -= 10
    except Exception:
        pass

    conf = 50 if pd.isna(sales_conf) else float(sales_conf)
    return round(max(0, min(100, score)), 2), round(max(0, min(100, conf)), 2)


def score_demand_signal(row):
    demand_cols = [
        "commander_demand_score",
        "modern_demand_score",
        "legacy_demand_score",
        "cube_demand_score",
        "collector_demand_score",
    ]
    vals = []
    for c in demand_cols:
        v = row.get(c)
        if not pd.isna(v):
            vals.append(float(v))

    if not vals:
        # fallback to built-in demand/ip/chase scores
        vals = [
            float(row.get("demand_score", 50) or 50),
            float(row.get("ip_score", 50) or 50),
            float(row.get("chase_score", 50) or 50),
        ]
        conf = 25
    else:
        conf = row.get("demand_confidence")
        conf = 50 if pd.isna(conf) else float(conf)

    return round(max(0, min(100, np.mean(vals))), 2), round(max(0, min(100, conf)), 2)


def score_scarcity_signal(row):
    months_oop = row.get("months_out_of_print")
    print_window = row.get("estimated_print_window_months")
    serialized = row.get("serialized_chase_score")
    scarcity_conf = row.get("scarcity_confidence")

    score = float(row.get("supply_score", 50) or 50)

    if not pd.isna(months_oop):
        m = float(months_oop)
        if m > 36:
            score += 20
        elif m > 18:
            score += 12
        elif m < 3:
            score -= 10

    if not pd.isna(print_window):
        pw = float(print_window)
        if pw <= 6:
            score += 12
        elif pw >= 18:
            score -= 8

    if not pd.isna(serialized):
        score += (float(serialized) - 50) * 0.20

    conf = 25 if pd.isna(scarcity_conf) else float(scarcity_conf)
    return round(max(0, min(100, score)), 2), round(max(0, min(100, conf)), 2)


def score_price_signal(row):
    # Use rolling metrics if available.
    r30 = row.get("return_30d_db", row.get("return_30d"))
    r90 = row.get("return_90d_db", row.get("return_90d"))
    dd = row.get("drawdown_from_ath", row.get("drawdown_from_high"))
    obs = row.get("observations", row.get("history_observations"))

    score = 50
    for r, w in [(r30, 25), (r90, 35)]:
        if not pd.isna(r):
            score += float(r) * w

    # mild drawdown can be attractive, extreme drawdown is concerning
    if not pd.isna(dd):
        dd = float(dd)
        if -0.25 <= dd <= -0.05:
            score += 8
        elif dd < -0.45:
            score -= 12

    conf = 0 if pd.isna(obs) else min(100, float(obs) / 30 * 100)
    return round(max(0, min(100, score)), 2), round(conf, 2)


def apply_real_signal_engine(model_df):
    if model_df is None or model_df.empty:
        return model_df

    model = merge_signal_inputs(model_df)

    inventory_scores = model.apply(score_inventory_signal, axis=1)
    sales_scores = model.apply(score_sales_signal, axis=1)
    demand_scores = model.apply(score_demand_signal, axis=1)
    scarcity_scores = model.apply(score_scarcity_signal, axis=1)
    price_scores = model.apply(score_price_signal, axis=1)

    model["inventory_signal_score"] = [x[0] for x in inventory_scores]
    model["inventory_signal_confidence"] = [x[1] for x in inventory_scores]
    model["sales_velocity_score"] = [x[0] for x in sales_scores]
    model["sales_signal_confidence"] = [x[1] for x in sales_scores]
    model["real_demand_score"] = [x[0] for x in demand_scores]
    model["demand_signal_confidence"] = [x[1] for x in demand_scores]
    model["scarcity_signal_score"] = [x[0] for x in scarcity_scores]
    model["scarcity_signal_confidence"] = [x[1] for x in scarcity_scores]
    model["price_trend_signal_score"] = [x[0] for x in price_scores]
    model["price_signal_confidence"] = [x[1] for x in price_scores]

    # Confidence-weighted blend. Missing external signals stay neutral and low confidence.
    components = [
        ("inventory_signal_score", "inventory_signal_confidence", 0.18),
        ("sales_velocity_score", "sales_signal_confidence", 0.20),
        ("real_demand_score", "demand_signal_confidence", 0.22),
        ("scarcity_signal_score", "scarcity_signal_confidence", 0.20),
        ("price_trend_signal_score", "price_signal_confidence", 0.20),
    ]

    weighted_score = 0
    total_weight = 0
    for score_col, conf_col, base_weight in components:
        conf_factor = pd.to_numeric(model[conf_col], errors="coerce").fillna(0) / 100
        effective_weight = base_weight * (0.35 + 0.65 * conf_factor)
        weighted_score += pd.to_numeric(model[score_col], errors="coerce").fillna(50) * effective_weight
        total_weight += effective_weight

    model["real_signal_score"] = (weighted_score / total_weight).round(2)
    model["real_signal_confidence"] = (
        model[[c for _, c, _ in components]].mean(axis=1)
    ).round(2)

    Path(REAL_SIGNAL_OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    model.to_csv(REAL_SIGNAL_OUTPUT_FILE, index=False)
    return model
