from __future__ import annotations

from pathlib import Path
import re
import pandas as pd
import numpy as np

from config import (
    PRODUCT_MASTER_FILE,
    PRODUCT_CANDIDATES_FILE,
    PRODUCT_SELECTION_REVIEW_FILE,
    PRODUCT_MASTER_MODEL_INPUT_FILE,
    PRODUCT_MASTER_MIN_SELECTION_SCORE,
    AUTO_APPROVE_HIGH_CONFIDENCE_PRODUCTS,
)


def _norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def ensure_product_master_exists():
    path = Path(PRODUCT_MASTER_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        cols = [
            "investment_product_id",
            "set_name",
            "box_name",
            "approved_tcgplayer_product_id",
            "approved_product_name",
            "tcgcsv_category_id",
            "tcgcsv_group_id",
            "investment_product_type",
            "approval_status",
            "approval_method",
            "notes",
        ]
        pd.DataFrame(columns=cols).to_csv(path, index=False)


def load_product_master():
    ensure_product_master_exists()
    return pd.read_csv(PRODUCT_MASTER_FILE, dtype=str)


def save_product_master(df):
    Path(PRODUCT_MASTER_FILE).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(PRODUCT_MASTER_FILE, index=False)


def product_candidate_score(row):
    """
    Score candidates for individual Collector Booster Display.

    This does NOT automatically prove correctness. It ranks candidates and
    writes review files. Only approved rows become trusted investment products.
    """
    name = _norm(row.get("official_product_name", "") or row.get("source_product_name", ""))
    score = 0

    # Desired phrase
    if "collector booster display" in name:
        score += 200
    elif "collector booster box" in name:
        score += 160

    # Bad product forms
    hard_bad = [
        "display case",
        "collector booster case",
        "case",
        "collector booster pack",
        "sample",
        "sample pack",
        "blister",
        "bundle",
        "commander deck",
        "starter kit",
        "prerelease",
        "draft booster",
        "set booster",
        "play booster",
        "jumpstart",
    ]
    for term in hard_bad:
        if term in name:
            score -= 400

    # Language variants are not preferred as canonical default.
    language_terms = ["japanese", "german", "french", "spanish", "italian", "portuguese", "korean", "chinese", "russian"]
    for term in language_terms:
        if term in name:
            score -= 75

    # Has price
    try:
        market = float(row.get("market_price") or 0)
    except Exception:
        market = 0
    if market > 0:
        score += 40

    # Sanity heuristic: extreme display prices are suspicious unless known high-end.
    set_name = _norm(row.get("set_name", ""))
    if market > 2500 and "lord of the rings" not in set_name:
        score -= 125
    if market > 3000:
        score -= 125

    return score


def build_candidate_review(discovered_df):
    if discovered_df is None or discovered_df.empty:
        return pd.DataFrame()

    df = discovered_df.copy()

    # Only products with collector booster in the name enter candidate review.
    name_text = (
        df.get("official_product_name", pd.Series("", index=df.index)).fillna("").astype(str) + " " +
        df.get("source_product_name", pd.Series("", index=df.index)).fillna("").astype(str)
    ).map(_norm)
    df = df[name_text.str.contains("collector booster", regex=False)].copy()

    if df.empty:
        return df

    df["candidate_score"] = df.apply(product_candidate_score, axis=1)
    df["candidate_rank"] = (
        df.sort_values(["tcgcsv_group_id", "candidate_score", "market_price"], ascending=[True, False, True])
          .groupby("tcgcsv_group_id")
          .cumcount() + 1
    )

    # Flag suspicious likely case rows.
    product_name = df.get("official_product_name", pd.Series("", index=df.index)).fillna("").map(_norm)
    df["case_or_pack_flag"] = product_name.str.contains("case", regex=False) | product_name.str.contains(" pack", regex=False)
    df["high_price_flag"] = pd.to_numeric(df.get("market_price"), errors="coerce").fillna(0) > 2500

    review_cols = [
        "set_name",
        "tcgcsv_group_id",
        "tcgplayer_product_id",
        "official_product_name",
        "market_price",
        "low_price",
        "candidate_score",
        "candidate_rank",
        "case_or_pack_flag",
        "high_price_flag",
        "price_source",
        "last_price_checked",
    ]
    review = df[[c for c in review_cols if c in df.columns]].copy()
    Path(PRODUCT_CANDIDATES_FILE).parent.mkdir(parents=True, exist_ok=True)
    review.to_csv(PRODUCT_CANDIDATES_FILE, index=False)

    # One best candidate per set for human review.
    best = (
        df.sort_values(["candidate_score", "market_price"], ascending=[False, True])
          .groupby("tcgcsv_group_id", as_index=False)
          .head(1)
          .copy()
    )
    best["recommended_action"] = np.where(
        (best["candidate_score"] >= PRODUCT_MASTER_MIN_SELECTION_SCORE) &
        (~best.get("case_or_pack_flag", False)) &
        (~best.get("high_price_flag", False)),
        "auto_approve_candidate",
        "needs_manual_review"
    )
    best.to_csv(PRODUCT_SELECTION_REVIEW_FILE, index=False)

    return df


def update_product_master_from_candidates(discovered_df):
    """
    Creates/updates investment product master.

    Existing approved mappings win. Auto-approval is conservative and can be
    disabled in config. Rows needing review are written out, but not scored.
    """
    master = load_product_master()
    candidates = build_candidate_review(discovered_df)

    if candidates.empty:
        return master, candidates

    existing_keys = set(master.get("tcgcsv_group_id", pd.Series(dtype=str)).dropna().astype(str).tolist())

    best = (
        candidates.sort_values(["candidate_score", "market_price"], ascending=[False, True])
          .groupby("tcgcsv_group_id", as_index=False)
          .head(1)
          .copy()
    )

    new_rows = []
    for _, row in best.iterrows():
        group_id = str(row.get("tcgcsv_group_id"))
        if group_id in existing_keys:
            continue

        product_name = _norm(row.get("official_product_name", ""))
        has_bad = any(term in product_name for term in ["case", " pack", "sample", "bundle"])
        high_price = float(row.get("market_price") or 0) > 2500
        score = float(row.get("candidate_score") or 0)

        if AUTO_APPROVE_HIGH_CONFIDENCE_PRODUCTS and score >= PRODUCT_MASTER_MIN_SELECTION_SCORE and not has_bad and not high_price:
            status = "approved"
            method = "auto_high_confidence_v9"
        else:
            status = "review_required"
            method = "needs_manual_review_v9"

        new_rows.append({
            "investment_product_id": f"TCGCSV-{group_id}-{row.get('tcgplayer_product_id')}",
            "set_name": row.get("set_name"),
            "box_name": f"{row.get('set_name')} Collector Booster Display",
            "approved_tcgplayer_product_id": row.get("tcgplayer_product_id"),
            "approved_product_name": row.get("official_product_name"),
            "tcgcsv_category_id": row.get("tcgcsv_category_id"),
            "tcgcsv_group_id": group_id,
            "investment_product_type": "Collector Booster Display",
            "approval_status": status,
            "approval_method": method,
            "notes": f"candidate_score={score}; market_price={row.get('market_price')}",
        })

    if new_rows:
        master = pd.concat([master, pd.DataFrame(new_rows)], ignore_index=True)

    save_product_master(master)
    return master, candidates


def apply_product_master(discovered_df):
    """
    Converts raw discovered product rows into the model universe using only
    approved investment products from product master.
    """
    master, candidates = update_product_master_from_candidates(discovered_df)

    approved = master[master["approval_status"].astype(str).str.lower() == "approved"].copy()
    if approved.empty:
        return pd.DataFrame(), master, candidates

    df = discovered_df.copy()
    df["tcgplayer_product_id_str"] = df["tcgplayer_product_id"].astype(str)
    approved["approved_tcgplayer_product_id_str"] = approved["approved_tcgplayer_product_id"].astype(str)

    model = df.merge(
        approved,
        left_on="tcgplayer_product_id_str",
        right_on="approved_tcgplayer_product_id_str",
        how="inner",
        suffixes=("", "_master")
    )

    if model.empty:
        return model, master, candidates

    # Canonical output fields from master.
    model["investment_product_id"] = model["investment_product_id"]
    model["box_name"] = model["box_name_master"].fillna(model["set_name"].astype(str) + " Collector Booster Display")
    model["source_product_name"] = model["approved_product_name"].fillna(model.get("source_product_name"))
    model["price_source"] = model.get("price_source", "tcgcsv")

    # Recalculate safer price bands around the chosen product.
    current = pd.to_numeric(model["market_price"], errors="coerce").fillna(pd.to_numeric(model["current_price"], errors="coerce"))
    model["current_price"] = current
    model["fair_value_estimate"] = current
    model["estimated_floor_price"] = np.minimum(
        pd.to_numeric(model.get("low_price"), errors="coerce").fillna(current * 0.82),
        current * 0.95
    ).round(2)
    model["estimated_ceiling_price"] = np.maximum(
        pd.to_numeric(model.get("high_price"), errors="coerce").fillna(current * 1.35),
        current * 1.10
    ).round(2)

    model.to_csv(PRODUCT_MASTER_MODEL_INPUT_FILE, index=False)
    return model, master, candidates


def approved_rows_to_latest_cache(model_df):
    if model_df is None or model_df.empty:
        return pd.DataFrame()

    return pd.DataFrame({
        "box_name": model_df["box_name"],
        "tcgplayer_product_id": model_df["approved_tcgplayer_product_id"],
        "price_source": "product_master_tcgcsv",
        "market_price": model_df["current_price"],
        "low_price": model_df["estimated_floor_price"],
        "last_price_checked": model_df.get("last_price_checked"),
        "price_data_quality": 95,
    })
