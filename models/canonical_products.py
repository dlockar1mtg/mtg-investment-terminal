from __future__ import annotations

import re
import pandas as pd


def _norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def is_bad_non_display_product(text):
    """
    Hard exclude products that are not the individual collector booster display.
    """
    bad_terms = [
        "case",
        "display case",
        "collector booster case",
        "pack",
        "sample",
        "sample pack",
        "blister",
        "bundle",
        "commander deck",
        "starter",
        "prerelease",
        "draft booster",
        "set booster",
        "play booster",
        "jumpstart",
    ]
    return any(term in text for term in bad_terms)


def canonical_display_score(row):
    name = _norm(row.get("official_product_name", ""))
    source = _norm(row.get("source_product_name", ""))
    combined = f"{name} {source}"

    score = 0

    # Desired investment unit.
    if "collector booster display" in combined:
        score += 200
    if "collector booster box" in combined:
        score += 120

    # Hard penalty for anything that is likely not the single display box.
    if is_bad_non_display_product(combined):
        score -= 1000

    # Prefer English/default version.
    language_penalties = [
        "japanese",
        "jp ",
        "german",
        "french",
        "spanish",
        "italian",
        "portuguese",
        "korean",
        "chinese",
        "russian",
    ]
    for term in language_penalties:
        if term in combined:
            score -= 75

    try:
        market = float(row.get("market_price", 0) or 0)
    except Exception:
        market = 0
    if market > 0:
        score += 50

    try:
        low = float(row.get("low_price", 0) or 0)
    except Exception:
        low = 0
    if low > 0:
        score += 10

    return score


def select_canonical_collector_displays(discovered_df):
    """
    Returns one canonical individual Collector Booster Display per TCGCSV group/set.

    v7.1 hard-excludes cases and packs before grouping. This prevents a case price
    from being saved under the set-level display row.
    """
    if discovered_df is None or discovered_df.empty:
        return discovered_df

    df = discovered_df.copy()

    text = (
        df.get("official_product_name", pd.Series("", index=df.index)).fillna("").astype(str) + " " +
        df.get("source_product_name", pd.Series("", index=df.index)).fillna("").astype(str)
    ).map(_norm)

    display_mask = text.str.contains("collector booster display", regex=False) | text.str.contains("collector booster box", regex=False)
    bad_mask = text.apply(is_bad_non_display_product)

    df = df[display_mask & ~bad_mask].copy()

    if df.empty:
        return df

    df["canonical_score"] = df.apply(canonical_display_score, axis=1)

    if "tcgplayer_product_id" in df.columns:
        df = df.sort_values("canonical_score", ascending=False).drop_duplicates(
            subset=["tcgplayer_product_id"], keep="first"
        )

    group_key = "tcgcsv_group_id" if "tcgcsv_group_id" in df.columns else "set_name"

    df = (
        df.sort_values(["canonical_score", "market_price"], ascending=[False, False])
          .groupby(group_key, as_index=False)
          .head(1)
          .copy()
    )

    if "set_name" in df.columns:
        df["box_name"] = df["set_name"].astype(str) + " Collector Booster Display"

    return df.reset_index(drop=True)


def canonical_rows_to_price_snapshots(canonical_df):
    """
    Builds clean price snapshot rows only from canonical displays.
    """
    if canonical_df is None or canonical_df.empty:
        return pd.DataFrame()

    rows = []
    for _, r in canonical_df.iterrows():
        rows.append({
            "box_name": r.get("box_name"),
            "tcgplayer_product_id": r.get("tcgplayer_product_id"),
            "source_name": "tcgcsv",
            "market_price": r.get("market_price"),
            "low_price": r.get("low_price"),
            "mid_price": r.get("mid_price"),
            "high_price": r.get("high_price"),
            "direct_low_price": r.get("direct_low_price"),
            "sub_type_name": r.get("sub_type_name"),
            "source_timestamp": r.get("last_price_checked"),
            "collected_at": r.get("last_price_checked"),
            "price_data_quality": 100 if pd.notna(r.get("market_price")) and float(r.get("market_price") or 0) > 0 else 50,
            "raw_payload": "{}",
        })
    return pd.DataFrame(rows)
