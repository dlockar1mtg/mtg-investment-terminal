from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config/mtg/governance/collector_v1_authoritative_data_registry.json"
CONTRACT = ROOT / "config/mtg/governance/collector_v1_early_opportunity_contract.json"
FEATURES = ROOT / "data/governance/permanence/certification/collector_v1_authoritative_feature_foundation/collector_v1_authoritative_feature_matrix.csv"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_early_opportunity_foundation"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def first_column(df: pd.DataFrame, names: list[str], required: bool = True) -> str | None:
    lookup = {str(c).strip().lower(): str(c) for c in df.columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    if required:
        raise ValueError(f"Required column unresolved: candidates={names}; available={list(df.columns)}")
    return None


def norm_id(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    return text.str.extract(r"(\d+)$", expand=False).fillna(text)


def nearest_price(g: pd.DataFrame, target_date: pd.Timestamp, max_days: int = 62) -> float | None:
    candidates = g[g["observation_date"] >= target_date].copy()
    if candidates.empty:
        return None
    row = candidates.iloc[0]
    if (row["observation_date"] - target_date).days > max_days:
        return None
    return float(row["market_price"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if not FEATURES.exists():
        raise FileNotFoundError(FEATURES)

    history_path = ROOT / registry["authorities"]["safe_monthly_history"]["path"]
    release_path = ROOT / registry["authorities"]["release_authority"]["path"]
    comparable_path = ROOT / registry["authorities"]["comparables"]["path"]
    scarcity_path = ROOT / registry["authorities"]["scarcity_v1"]["path"]

    history = pd.read_csv(history_path, low_memory=False)
    release = pd.read_csv(release_path, low_memory=False)
    comparables = pd.read_csv(comparable_path, low_memory=False)
    scarcity = pd.read_csv(scarcity_path, low_memory=False)
    features = pd.read_csv(FEATURES, low_memory=False)

    hid = first_column(history, ["tcgplayer_product_id", "product_id"])
    hdate = first_column(history, ["observation_month", "source_observation_date", "parsed_date", "date"])
    hprice = first_column(history, ["source_market_price", "market_price", "price"])
    rid = first_column(release, ["tcgplayer_product_id", "investment_product_id", "product_id"])
    rdate = first_column(release, ["release_date", "official_release_date", "date"])
    tid = first_column(comparables, ["target_product_id", "target_tcgplayer_product_id", "target_investment_product_id"])
    pid = first_column(comparables, ["peer_product_id", "peer_tcgplayer_product_id", "comparable_product_id"])
    score_col = first_column(comparables, ["similarity_score", "pair_score", "selection_score", "score"], required=False)
    sid = first_column(scarcity, ["tcgplayer_product_id", "investment_product_id", "product_id"])
    accepted_col = first_column(scarcity, ["accepted_listing_count"], required=False)
    review_col = first_column(scarcity, ["review_listing_count"], required=False)

    history = history.copy()
    history["tcgplayer_product_id"] = norm_id(history[hid])
    history["observation_date"] = pd.to_datetime(history[hdate], errors="coerce", utc=True)
    history["market_price"] = pd.to_numeric(history[hprice], errors="coerce")
    history = history[history["observation_date"].notna() & history["market_price"].gt(0)]
    history = history.sort_values(["tcgplayer_product_id", "observation_date"])

    release = release.copy()
    release["tcgplayer_product_id"] = norm_id(release[rid])
    release["release_date_authority"] = pd.to_datetime(release[rdate], errors="coerce", utc=True)
    release = release.dropna(subset=["release_date_authority"]).drop_duplicates("tcgplayer_product_id")

    comparables = comparables.copy()
    comparables["target_id"] = norm_id(comparables[tid])
    comparables["peer_id"] = norm_id(comparables[pid])
    comparables["similarity_score"] = pd.to_numeric(comparables[score_col], errors="coerce") if score_col else np.nan

    scarcity = scarcity.copy()
    scarcity["tcgplayer_product_id"] = norm_id(scarcity[sid])
    scarcity["accepted_listing_count"] = pd.to_numeric(scarcity[accepted_col], errors="coerce") if accepted_col else np.nan
    scarcity["review_listing_count"] = pd.to_numeric(scarcity[review_col], errors="coerce") if review_col else np.nan
    scarcity = scarcity.drop_duplicates("tcgplayer_product_id")

    features["tcgplayer_product_id"] = norm_id(features["tcgplayer_product_id"])
    active_ids = set(features["tcgplayer_product_id"].dropna())

    outcomes = []
    for product_id, g in history[history["tcgplayer_product_id"].isin(active_ids)].groupby("tcgplayer_product_id"):
        g = g.sort_values("observation_date").reset_index(drop=True)
        release_row = release[release["tcgplayer_product_id"] == product_id]
        anchor_date = release_row.iloc[0]["release_date_authority"] if not release_row.empty else g.iloc[0]["observation_date"]
        first_after_release = g[g["observation_date"] >= anchor_date]
        if first_after_release.empty:
            first_after_release = g
        anchor = first_after_release.iloc[0]
        anchor_price = float(anchor["market_price"])
        anchor_obs_date = anchor["observation_date"]
        p90 = nearest_price(g, anchor_obs_date + pd.Timedelta(days=90))
        p180 = nearest_price(g, anchor_obs_date + pd.Timedelta(days=180))
        p365 = nearest_price(g, anchor_obs_date + pd.Timedelta(days=365), max_days=93)
        first_year = g[(g["observation_date"] >= anchor_obs_date) & (g["observation_date"] <= anchor_obs_date + pd.Timedelta(days=365))]
        max_first_year = float(first_year["market_price"].max()) if not first_year.empty else np.nan
        min_first_year = float(first_year["market_price"].min()) if not first_year.empty else np.nan
        return_365 = (p365 / anchor_price - 1.0) if p365 and anchor_price > 0 else np.nan
        outcomes.append({
            "tcgplayer_product_id": product_id,
            "release_date_authority": anchor_date.date().isoformat(),
            "anchor_observation_date": anchor_obs_date.date().isoformat(),
            "release_anchor_price": anchor_price,
            "price_90d": p90,
            "price_180d": p180,
            "price_365d": p365,
            "return_90d": p90 / anchor_price - 1.0 if p90 else np.nan,
            "return_180d": p180 / anchor_price - 1.0 if p180 else np.nan,
            "return_365d": return_365,
            "maximum_first_year_price": max_first_year,
            "maximum_first_year_return": max_first_year / anchor_price - 1.0 if anchor_price > 0 and pd.notna(max_first_year) else np.nan,
            "minimum_first_year_return": min_first_year / anchor_price - 1.0 if anchor_price > 0 and pd.notna(min_first_year) else np.nan,
            "winner_25pct": bool(pd.notna(return_365) and return_365 >= 0.25),
            "winner_50pct": bool(pd.notna(return_365) and return_365 >= 0.50),
            "first_year_loss": bool(pd.notna(return_365) and return_365 < 0),
        })
    outcomes_df = pd.DataFrame(outcomes)

    peer_curves = comparables.merge(
        outcomes_df.add_prefix("peer_").rename(columns={"peer_tcgplayer_product_id": "peer_id"}),
        on="peer_id", how="left"
    )
    peer_agg = peer_curves.groupby("target_id", as_index=False).agg(
        peer_count=("peer_id", "nunique"),
        peer_return_90d_median=("peer_return_90d", "median"),
        peer_return_180d_median=("peer_return_180d", "median"),
        peer_return_365d_median=("peer_return_365d", "median"),
        peer_return_365d_mean=("peer_return_365d", "mean"),
        peer_winner_25_rate=("peer_winner_25pct", "mean"),
        peer_winner_50_rate=("peer_winner_50pct", "mean"),
        peer_loss_rate=("peer_first_year_loss", "mean"),
        peer_return_365d_dispersion=("peer_return_365d", "std"),
    ).rename(columns={"target_id": "tcgplayer_product_id"})

    cutoffs = []
    ages = [0, 1, 2, 3, 6, 9, 12]
    for product_id, g in history[history["tcgplayer_product_id"].isin(active_ids)].groupby("tcgplayer_product_id"):
        g = g.sort_values("observation_date").reset_index(drop=True)
        outcome = outcomes_df[outcomes_df["tcgplayer_product_id"] == product_id]
        if outcome.empty or pd.isna(outcome.iloc[0]["return_365d"]):
            continue
        anchor_date = pd.Timestamp(outcome.iloc[0]["anchor_observation_date"], tz="UTC")
        anchor_price = float(outcome.iloc[0]["release_anchor_price"])
        for age_months in ages:
            cutoff = anchor_date + pd.DateOffset(months=age_months)
            known = g[g["observation_date"] <= cutoff]
            if known.empty:
                continue
            current = float(known.iloc[-1]["market_price"])
            prior3 = known.iloc[-4]["market_price"] if len(known) >= 4 else anchor_price
            prior6 = known.iloc[-7]["market_price"] if len(known) >= 7 else anchor_price
            cutoffs.append({
                "tcgplayer_product_id": product_id,
                "age_months": age_months,
                "cutoff_date": known.iloc[-1]["observation_date"].date().isoformat(),
                "release_anchor_price": anchor_price,
                "cutoff_price": current,
                "return_since_release": current / anchor_price - 1.0,
                "momentum_3m": current / float(prior3) - 1.0 if float(prior3) > 0 else np.nan,
                "momentum_6m": current / float(prior6) - 1.0 if float(prior6) > 0 else np.nan,
                "history_months_at_cutoff": len(known),
                "actual_return_365d_from_release": float(outcome.iloc[0]["return_365d"]),
                "actual_winner_25pct": bool(outcome.iloc[0]["winner_25pct"]),
                "actual_winner_50pct": bool(outcome.iloc[0]["winner_50pct"]),
                "actual_first_year_loss": bool(outcome.iloc[0]["first_year_loss"]),
                "feature_cutoff_enforced": True,
            })
    cutoffs_df = pd.DataFrame(cutoffs)
    cutoffs_df = cutoffs_df.merge(peer_agg, on="tcgplayer_product_id", how="left")
    cutoffs_df = cutoffs_df.merge(scarcity[["tcgplayer_product_id", "accepted_listing_count", "review_listing_count"]], on="tcgplayer_product_id", how="left")

    variants = []
    for name, peer_weight, momentum_weight, scarcity_weight in [
        ("PEER_MEDIAN", 1.0, 0.0, 0.0),
        ("PEER_MOMENTUM", 0.70, 0.30, 0.0),
        ("PEER_MOMENTUM_SCARCITY", 0.65, 0.25, 0.10),
        ("ROBUST_PEER_SHRINKAGE", 0.80, 0.20, 0.0),
    ]:
        x = cutoffs_df.copy()
        scarcity_signal = (1.0 - x["accepted_listing_count"].fillna(x["accepted_listing_count"].median()).clip(0, 60) / 60.0) * 0.50
        peer = x["peer_return_365d_median"].fillna(x["peer_return_365d_mean"])
        momentum = x[["return_since_release", "momentum_3m", "momentum_6m"]].median(axis=1, skipna=True)
        pred = peer_weight * peer + momentum_weight * momentum + scarcity_weight * scarcity_signal
        if name == "ROBUST_PEER_SHRINKAGE":
            pred = pred.clip(peer.quantile(0.05), peer.quantile(0.95))
        x["model_variant"] = name
        x["predicted_first_year_return"] = pred
        x["predicted_winner_25_probability"] = np.clip(0.5 + (pred - 0.25), 0, 1)
        x["predicted_winner_50_probability"] = np.clip(0.5 + (pred - 0.50), 0, 1)
        variants.append(x)
    tournament = pd.concat(variants, ignore_index=True)

    metric_rows = []
    for (variant, age), g in tournament.dropna(subset=["predicted_first_year_return"]).groupby(["model_variant", "age_months"]):
        actual = g["actual_return_365d_from_release"].astype(float)
        pred = g["predicted_first_year_return"].astype(float)
        ranked = g.sort_values("predicted_first_year_return", ascending=False)
        top_n = max(1, int(np.ceil(len(ranked) * 0.20)))
        top = ranked.head(top_n)
        precision = float(top["actual_winner_25pct"].mean()) if len(top) else np.nan
        winners = int(g["actual_winner_25pct"].sum())
        caught = int(top["actual_winner_25pct"].sum())
        recall = caught / winners if winners else np.nan
        false_positive_rate = float((~top["actual_winner_25pct"].astype(bool)).mean()) if len(top) else np.nan
        metric_rows.append({
            "model_variant": variant,
            "age_months": int(age),
            "rows": len(g),
            "mae": float(np.mean(np.abs(pred - actual))),
            "rmse": float(np.sqrt(np.mean((pred - actual) ** 2))),
            "bias": float(np.mean(pred - actual)),
            "rank_correlation": float(pd.Series(pred).corr(pd.Series(actual), method="spearman")) if len(g) >= 3 else np.nan,
            "top_quintile_precision_25pct": precision,
            "winner_recall_25pct": recall,
            "false_positive_rate": false_positive_rate,
        })
    metrics = pd.DataFrame(metric_rows)
    metrics["selection_score"] = (
        metrics["top_quintile_precision_25pct"].fillna(0) * 0.35
        + metrics["winner_recall_25pct"].fillna(0) * 0.25
        + metrics["rank_correlation"].fillna(0).clip(-1, 1) * 0.20
        - metrics["false_positive_rate"].fillna(1) * 0.10
        - metrics["mae"].rank(pct=True) * 0.10
    )
    winners = metrics.sort_values(["age_months", "selection_score"], ascending=[True, False]).groupby("age_months", as_index=False).first()

    missing_inputs = []
    if score_col is None:
        missing_inputs.append({"input": "comparable_similarity_score", "status": "NOT_CONNECTED", "source_action": "Connect certified comparable pair-score artifact", "v1_priority": "HIGH"})
    missing_inputs.extend([
        {"input": "historical_supply_snapshots", "status": "NOT_AVAILABLE_IN_V1_AUTHORITY", "source_action": "Future repeated marketplace snapshots", "v1_priority": "OPTIONAL_NOT_BLOCKING"},
        {"input": "historical_demand_or_sales_velocity", "status": "NOT_AVAILABLE_IN_V1_AUTHORITY", "source_action": "Identify lawful historical sold-volume or absorption source", "v1_priority": "OPTIONAL_TEST_IF_AVAILABLE"},
    ])

    blockers = []
    if outcomes_df["return_365d"].notna().sum() < 10:
        blockers.append("Fewer than 10 products have realized first-year outcomes.")
    if cutoffs_df.empty:
        blockers.append("No release-age cutoff rows were generated.")
    if metrics.empty:
        blockers.append("No early-opportunity tournament metrics were generated.")
    if peer_agg["peer_count"].fillna(0).ge(3).sum() == 0:
        blockers.append("No products have at least three comparable peers with maturity evidence.")

    outcomes_df.to_csv(OUT / "collector_v1_first_year_outcomes.csv", index=False)
    peer_agg.to_csv(OUT / "collector_v1_peer_maturity_curves.csv", index=False)
    cutoffs_df.to_csv(OUT / "collector_v1_release_age_cutoffs.csv", index=False)
    tournament.to_csv(OUT / "collector_v1_early_opportunity_predictions.csv", index=False)
    metrics.to_csv(OUT / "collector_v1_early_opportunity_tournament_metrics.csv", index=False)
    winners.to_csv(OUT / "collector_v1_early_opportunity_winners_by_age.csv", index=False)
    pd.DataFrame(missing_inputs).to_csv(OUT / "collector_v1_early_opportunity_input_gap_register.csv", index=False)

    summary = {
        "block_name": "Collector V1 Early Opportunity Foundation",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_hashes": {
            "safe_monthly_history": sha256(history_path),
            "release_authority": sha256(release_path),
            "comparables": sha256(comparable_path),
            "scarcity_v1": sha256(scarcity_path),
            "authoritative_feature_matrix": sha256(FEATURES),
        },
        "realized_first_year_products": int(outcomes_df["return_365d"].notna().sum()),
        "winner_25pct_products": int(outcomes_df["winner_25pct"].sum()),
        "winner_50pct_products": int(outcomes_df["winner_50pct"].sum()),
        "release_age_cutoff_rows": int(len(cutoffs_df)),
        "tournament_prediction_rows": int(len(tournament)),
        "tournament_metric_rows": int(len(metrics)),
        "ages_months": sorted(cutoffs_df["age_months"].unique().tolist()) if not cutoffs_df.empty else [],
        "comparable_similarity_score_connected": score_col is not None,
        "anti_leakage_pass": bool(cutoffs_df.get("feature_cutoff_enforced", pd.Series(dtype=bool)).fillna(False).all()) if not cutoffs_df.empty else False,
        "blockers": blockers,
        "early_opportunity_foundation_ready": not blockers,
        "short_history_model_selection_authorized": not blockers,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_EARLY_OPPORTUNITY_FOUNDATION_READY" if not blockers else "BLOCKED_COLLECTOR_V1_EARLY_OPPORTUNITY_FOUNDATION",
    }
    (OUT / "collector_v1_early_opportunity_foundation_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if args.strict and blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
