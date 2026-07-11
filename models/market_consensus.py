from __future__ import annotations

from pathlib import Path
import math
import pandas as pd
import numpy as np

from config import (
    MANUAL_PRICE_SOURCES_FILE,
    CONSENSUS_PRICE_FILE,
    OUTLIER_RATIO_THRESHOLD,
)


def _clean_price(value):
    try:
        if pd.isna(value):
            return None
        value = float(value)
        if value <= 0:
            return None
        return value
    except Exception:
        return None


def load_manual_price_sources():
    path = Path(MANUAL_PRICE_SOURCES_FILE)
    if not path.exists():
        return pd.DataFrame(columns=[
            "box_name",
            "source_name",
            "market_price",
            "low_price",
            "last_price_checked",
            "source_note",
            "source_confidence",
        ])
    return pd.read_csv(path)


def canonical_to_source_rows(canonical_df):
    if canonical_df is None or canonical_df.empty:
        return pd.DataFrame()

    rows = []
    for _, r in canonical_df.iterrows():
        market = _clean_price(r.get("market_price"))
        if market is None:
            continue
        rows.append({
            "box_name": r.get("box_name"),
            "source_name": r.get("price_source") or "tcgcsv",
            "market_price": market,
            "low_price": _clean_price(r.get("low_price")),
            "last_price_checked": r.get("last_price_checked"),
            "source_note": "auto_tcgcsv_discovered",
            "source_confidence": 80,
            "tcgplayer_product_id": r.get("tcgplayer_product_id"),
        })
    return pd.DataFrame(rows)


def combine_price_sources(canonical_df):
    source_frames = []

    tcgcsv_rows = canonical_to_source_rows(canonical_df)
    if not tcgcsv_rows.empty:
        source_frames.append(tcgcsv_rows)

    manual = load_manual_price_sources()
    if not manual.empty:
        for col in ["source_name", "source_note", "source_confidence", "low_price", "last_price_checked"]:
            if col not in manual.columns:
                manual[col] = None
        source_frames.append(manual)

    if not source_frames:
        return pd.DataFrame()

    combined = pd.concat(source_frames, ignore_index=True, sort=False)
    combined["market_price"] = pd.to_numeric(combined["market_price"], errors="coerce")
    combined = combined.dropna(subset=["box_name", "market_price"])
    combined = combined[combined["market_price"] > 0].copy()
    combined["source_confidence"] = pd.to_numeric(combined.get("source_confidence", 70), errors="coerce").fillna(70)
    return combined


def build_consensus_for_box(group):
    prices = group["market_price"].astype(float).tolist()
    sources = group["source_name"].astype(str).tolist()

    if not prices:
        return {}

    median_price = float(np.median(prices))
    mean_price = float(np.mean(prices))

    source_rows = []
    included_prices = []
    outlier_sources = []

    for _, r in group.iterrows():
        price = float(r["market_price"])
        if median_price > 0:
            ratio = max(price / median_price, median_price / price)
        else:
            ratio = 1

        is_outlier = ratio >= OUTLIER_RATIO_THRESHOLD and len(prices) >= 2

        source_rows.append({
            "source_name": r.get("source_name"),
            "market_price": price,
            "ratio_to_median": round(ratio, 3),
            "is_outlier": is_outlier,
            "source_note": r.get("source_note"),
        })

        if is_outlier:
            outlier_sources.append(f"{r.get('source_name')}:{price}")
        else:
            included_prices.append(price)

    if not included_prices:
        included_prices = prices

    consensus = float(np.median(included_prices))
    dispersion = 0.0
    if len(included_prices) >= 2:
        dispersion = float(np.std(included_prices) / consensus) if consensus else 0

    # Confidence: more sources and lower dispersion are better. Outliers reduce confidence.
    source_count = len(prices)
    included_count = len(included_prices)
    confidence = 70
    confidence += min(20, (source_count - 1) * 8)
    confidence -= min(25, dispersion * 100)
    confidence -= len(outlier_sources) * 10
    confidence = max(30, min(100, round(confidence, 1)))

    primary_row = group.iloc[0]

    return {
        "box_name": primary_row["box_name"],
        "consensus_market_price": round(consensus, 2),
        "source_count": source_count,
        "included_source_count": included_count,
        "median_source_price": round(median_price, 2),
        "mean_source_price": round(mean_price, 2),
        "source_price_dispersion": round(dispersion, 4),
        "consensus_confidence": confidence,
        "outlier_sources": "; ".join(outlier_sources),
        "source_detail": str(source_rows),
    }


def calculate_consensus_prices(canonical_df):
    sources = combine_price_sources(canonical_df)
    if sources.empty:
        return pd.DataFrame(), sources

    consensus_rows = []
    for box_name, group in sources.groupby("box_name"):
        consensus_rows.append(build_consensus_for_box(group))

    consensus = pd.DataFrame(consensus_rows)
    Path(CONSENSUS_PRICE_FILE).parent.mkdir(parents=True, exist_ok=True)
    consensus.to_csv(CONSENSUS_PRICE_FILE, index=False)

    source_detail_file = Path(CONSENSUS_PRICE_FILE).parent / "all_price_sources.csv"
    sources.to_csv(source_detail_file, index=False)

    return consensus, sources


def apply_consensus_to_model_input(canonical_df):
    if canonical_df is None or canonical_df.empty:
        return canonical_df, pd.DataFrame(), pd.DataFrame()

    model_df = canonical_df.copy()
    consensus, sources = calculate_consensus_prices(model_df)

    if consensus.empty:
        model_df["consensus_market_price"] = model_df.get("market_price")
        model_df["consensus_confidence"] = 50
        model_df["price_source"] = model_df.get("price_source", "unknown")
        return model_df, consensus, sources

    model_df = model_df.merge(
        consensus[[
            "box_name",
            "consensus_market_price",
            "source_count",
            "included_source_count",
            "source_price_dispersion",
            "consensus_confidence",
            "outlier_sources",
        ]],
        on="box_name",
        how="left",
    )

    # Use consensus price as current scoring price.
    model_df["raw_tcgcsv_market_price"] = model_df.get("market_price")
    model_df["current_price"] = model_df["consensus_market_price"].fillna(model_df["current_price"])
    model_df["market_price"] = model_df["current_price"]
    model_df["price_source"] = "market_consensus"

    # Adjust fair value and price range around consensus unless existing values are more conservative.
    consensus_price = pd.to_numeric(model_df["consensus_market_price"], errors="coerce")
    model_df["fair_value_estimate"] = consensus_price.fillna(model_df["fair_value_estimate"])

    # Use low source price as floor where present, but prevent bizarre low > market case from source data.
    current = pd.to_numeric(model_df["current_price"], errors="coerce")
    low = pd.to_numeric(model_df.get("low_price"), errors="coerce")
    model_df["estimated_floor_price"] = np.minimum(
        low.fillna(current * 0.82),
        current * 0.95
    ).round(2)

    model_df["estimated_ceiling_price"] = np.maximum(
        pd.to_numeric(model_df.get("high_price"), errors="coerce").fillna(current * 1.35),
        current * 1.10
    ).round(2)

    return model_df, consensus, sources


def consensus_to_latest_cache(model_df):
    if model_df is None or model_df.empty:
        return pd.DataFrame()

    latest = pd.DataFrame({
        "box_name": model_df["box_name"],
        "tcgplayer_product_id": model_df.get("tcgplayer_product_id"),
        "price_source": "market_consensus",
        "market_price": model_df["current_price"],
        "low_price": model_df.get("estimated_floor_price"),
        "last_price_checked": model_df.get("last_price_checked"),
        "price_data_quality": model_df.get("consensus_confidence", 70),
    })
    return latest
