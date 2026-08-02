from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config/mtg/governance/collector_v1_authoritative_data_registry.json"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_authoritative_feature_foundation"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def first_column(df: pd.DataFrame, names: Iterable[str], required: bool = True) -> str | None:
    lookup = {str(c).strip().lower(): str(c) for c in df.columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    if required:
        raise ValueError(f"None of the required columns exist: {list(names)}; available={list(df.columns)}")
    return None


def clean_id(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)


def bool_value(value) -> bool:
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y", "pass", "eligible"}


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def read_authorities() -> tuple[dict, dict[str, Path], dict[str, pd.DataFrame]]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    paths: dict[str, Path] = {}
    frames: dict[str, pd.DataFrame] = {}
    for key, spec in registry["authorities"].items():
        if key == "current_feature_matrix":
            continue
        path = ROOT / spec["path"]
        if not path.exists():
            raise FileNotFoundError(f"Registered authority is missing: {key} -> {path}")
        paths[key] = path
        frames[key] = pd.read_csv(path, low_memory=False)
    return registry, paths, frames


def monthly_features(history: pd.DataFrame, active_ids: set[str]) -> tuple[pd.DataFrame, dict]:
    id_col = first_column(history, ["tcgplayer_product_id", "product_id", "tcgplayer_id"])
    date_col = first_column(history, ["month", "observation_month", "observation_date", "date", "period", "snapshot_date"])
    price_col = first_column(history, ["market_price", "price", "monthly_market_price", "tcg_market_price", "value"])

    h = history.copy()
    h["tcgplayer_product_id"] = clean_id(h[id_col])
    h["observation_date"] = pd.to_datetime(h[date_col], errors="coerce", utc=True)
    h["market_price"] = numeric(h[price_col])
    h = h[h["tcgplayer_product_id"].isin(active_ids)]
    h = h[h["observation_date"].notna() & h["market_price"].gt(0)]
    h["observation_month"] = h["observation_date"].dt.to_period("M").dt.to_timestamp().dt.tz_localize("UTC")

    # Fail closed on ambiguous product-month grain by using median and retaining diagnostics.
    grouped = h.groupby(["tcgplayer_product_id", "observation_month"], as_index=False).agg(
        market_price=("market_price", "median"),
        source_row_count=("market_price", "size"),
        price_min=("market_price", "min"),
        price_max=("market_price", "max"),
    )

    rows = []
    for pid, g in grouped.groupby("tcgplayer_product_id"):
        g = g.sort_values("observation_month").reset_index(drop=True)
        prices = g["market_price"].astype(float)
        dates = g["observation_month"]
        returns = prices.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        latest_date = dates.iloc[-1]
        latest_price = float(prices.iloc[-1])

        def trailing_return(days: int):
            target = latest_date - pd.Timedelta(days=int(days))
            prior = g[g["observation_month"] <= target]
            if prior.empty:
                return np.nan
            base = float(prior.iloc[-1]["market_price"])
            return latest_price / base - 1.0 if base > 0 else np.nan

        running_max = prices.cummax()
        drawdowns = prices / running_max - 1.0
        span_days = int((dates.iloc[-1] - dates.iloc[0]).days) if len(g) > 1 else 0
        rows.append({
            "tcgplayer_product_id": pid,
            "history_months": int(len(g)),
            "history_start_date": dates.iloc[0].date().isoformat(),
            "history_end_date": dates.iloc[-1].date().isoformat(),
            "history_span_days": span_days,
            "latest_history_price": latest_price,
            "return_30d": trailing_return(30),
            "return_90d": trailing_return(90),
            "return_180d": trailing_return(180),
            "return_365d": trailing_return(365),
            "annualized_volatility": float(returns.std(ddof=1) * np.sqrt(12)) if len(returns) >= 2 else np.nan,
            "maximum_drawdown": float(drawdowns.min()) if len(drawdowns) else np.nan,
            "trend_slope_monthly": float(np.polyfit(np.arange(len(prices)), np.log(prices), 1)[0]) if len(prices) >= 3 and prices.gt(0).all() else np.nan,
            "duplicate_product_month_source_rows": int((g["source_row_count"] - 1).clip(lower=0).sum()),
        })
    return pd.DataFrame(rows), {
        "id_column": id_col,
        "date_column": date_col,
        "price_column": price_col,
        "eligible_source_rows": int(len(h)),
        "canonical_product_month_rows": int(len(grouped)),
        "covered_active_products": int(grouped["tcgplayer_product_id"].nunique()),
    }


def comparable_features(comps: pd.DataFrame, active_ids: set[str]) -> tuple[pd.DataFrame, dict]:
    target_col = first_column(comps, [
        "target_tcgplayer_product_id", "target_product_id", "tcgplayer_product_id",
        "target_investment_product_id", "investment_product_id"
    ])
    peer_col = first_column(comps, [
        "peer_tcgplayer_product_id", "comparable_tcgplayer_product_id", "peer_product_id",
        "comparable_product_id", "selected_peer_product_id"
    ], required=False)
    score_col = first_column(comps, ["similarity_score", "comparable_score", "pair_score", "score"], required=False)
    weight_col = first_column(comps, ["peer_weight", "weight", "normalized_weight"], required=False)

    c = comps.copy()
    target_raw = clean_id(c[target_col])
    if "investment" in target_col.lower():
        target_raw = target_raw.str.extract(r"(\d+)$", expand=False)
    c["tcgplayer_product_id"] = target_raw
    c = c[c["tcgplayer_product_id"].isin(active_ids)]
    if peer_col:
        peer = clean_id(c[peer_col])
        if "investment" in peer_col.lower():
            peer = peer.str.extract(r"(\d+)$", expand=False)
        c["peer_id"] = peer
    else:
        c["peer_id"] = pd.NA
    c["score_value"] = numeric(c[score_col]) if score_col else np.nan
    c["weight_value"] = numeric(c[weight_col]) if weight_col else np.nan

    out = c.groupby("tcgplayer_product_id", as_index=False).agg(
        selected_comparable_rows=("tcgplayer_product_id", "size"),
        selected_comparable_unique_peers=("peer_id", lambda s: int(s.dropna().nunique())),
        comparable_mean_score=("score_value", "mean"),
        comparable_weight_sum=("weight_value", "sum"),
    )
    return out, {
        "target_column": target_col,
        "peer_column": peer_col,
        "score_column": score_col,
        "weight_column": weight_col,
        "matched_rows": int(len(c)),
        "covered_active_products": int(out["tcgplayer_product_id"].nunique()),
    }


def structural_features(structure: pd.DataFrame, active_ids: set[str]) -> tuple[pd.DataFrame, dict]:
    id_col = first_column(structure, ["tcgplayer_product_id", "product_id", "tcgplayer_id", "investment_product_id"])
    s = structure.copy()
    ids = clean_id(s[id_col])
    if "investment" in id_col.lower():
        ids = ids.str.extract(r"(\d+)$", expand=False)
    s["tcgplayer_product_id"] = ids
    s = s[s["tcgplayer_product_id"].isin(active_ids)]

    aliases = {
        "pack_count": ["pack_count", "packs_per_box", "booster_pack_count", "display_pack_count"],
        "box_topper": ["box_topper", "has_box_topper", "box_topper_status", "topper_included"],
        "licensed_ip": ["licensed_ip", "is_licensed_ip", "universes_beyond", "licensed_property"],
        "product_family": ["product_family", "family", "set_family", "product_line"],
        "edition_classification": ["edition_classification", "edition_type", "product_edition", "classification"],
        "product_configuration": ["product_configuration", "configuration", "sealed_configuration", "display_configuration"],
    }
    chosen: dict[str, str | None] = {}
    out = s[["tcgplayer_product_id"]].copy()
    for feature, candidates in aliases.items():
        col = first_column(s, candidates, required=False)
        chosen[feature] = col
        out[feature] = s[col] if col else pd.NA
    out = out.groupby("tcgplayer_product_id", as_index=False).first()
    return out, {"id_column": id_col, "chosen_columns": chosen, "covered_active_products": int(out["tcgplayer_product_id"].nunique())}


def simple_by_id(df: pd.DataFrame, aliases: list[str]) -> tuple[pd.DataFrame, str]:
    id_col = first_column(df, aliases)
    x = df.copy()
    ids = clean_id(x[id_col])
    if "investment" in id_col.lower():
        ids = ids.str.extract(r"(\d+)$", expand=False)
    x["tcgplayer_product_id"] = ids
    return x, id_col


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    registry, paths, frames = read_authorities()
    routes, route_id_col = simple_by_id(frames["active_universe"], ["tcgplayer_product_id", "product_id"])
    routes = routes.drop_duplicates("tcgplayer_product_id").copy()
    active_ids = set(routes["tcgplayer_product_id"].dropna().astype(str))

    history_features, history_diag = monthly_features(frames["safe_monthly_history"], active_ids)
    comparable_features_df, comparable_diag = comparable_features(frames["comparables"], active_ids)
    structural_features_df, structural_diag = structural_features(frames["structural_authority"], active_ids)

    hist_cert, hist_cert_id_col = simple_by_id(frames["historical_product_certification"], ["tcgplayer_product_id", "product_id", "investment_product_id"])
    hist_eligible, hist_eligible_id_col = simple_by_id(frames["historical_forecast_eligible"], ["tcgplayer_product_id", "product_id", "investment_product_id"])
    release, release_id_col = simple_by_id(frames["release_authority"], ["tcgplayer_product_id", "product_id", "investment_product_id"])
    scarcity, scarcity_id_col = simple_by_id(frames["scarcity_v1"], ["tcgplayer_product_id", "product_id", "investment_product_id"])
    prices, price_id_col = simple_by_id(frames["current_price"], ["tcgplayer_product_id", "product_id", "investment_product_id"])

    current_price_col = first_column(prices, ["current_price", "market_price", "price", "latest_price"])
    release_date_col = first_column(release, ["release_date", "official_release_date", "released_at", "date"])
    scarcity_score_col = first_column(scarcity, ["supply_scarcity_index_v1", "scarcity_score", "ssi_v1", "score"])
    history_status_col = first_column(hist_cert, ["history_certification_status", "certification_status", "forecast_status", "status"], required=False)

    matrix = routes.copy()
    keep_price = prices[["tcgplayer_product_id", current_price_col]].drop_duplicates("tcgplayer_product_id").rename(columns={current_price_col: "current_price_authoritative"})
    keep_release = release[["tcgplayer_product_id", release_date_col]].drop_duplicates("tcgplayer_product_id").rename(columns={release_date_col: "release_date_authoritative"})
    keep_scarcity = scarcity[["tcgplayer_product_id", scarcity_score_col]].drop_duplicates("tcgplayer_product_id").rename(columns={scarcity_score_col: "supply_scarcity_index_v1"})
    matrix = matrix.merge(keep_price, on="tcgplayer_product_id", how="left")
    matrix = matrix.merge(keep_release, on="tcgplayer_product_id", how="left")
    matrix = matrix.merge(keep_scarcity, on="tcgplayer_product_id", how="left")
    matrix = matrix.merge(history_features, on="tcgplayer_product_id", how="left")
    matrix = matrix.merge(comparable_features_df, on="tcgplayer_product_id", how="left")
    matrix = matrix.merge(structural_features_df, on="tcgplayer_product_id", how="left")

    eligible_set = set(hist_eligible["tcgplayer_product_id"].dropna().astype(str))
    matrix["historical_forecast_eligible_authority"] = matrix["tcgplayer_product_id"].isin(eligible_set)
    if history_status_col:
        status_map = hist_cert.drop_duplicates("tcgplayer_product_id").set_index("tcgplayer_product_id")[history_status_col]
        matrix["history_certification_status_authority"] = matrix["tcgplayer_product_id"].map(status_map)
    else:
        matrix["history_certification_status_authority"] = pd.NA

    matrix["selected_comparable_rows"] = numeric(matrix.get("selected_comparable_rows", pd.Series(index=matrix.index, dtype=float))).fillna(0).astype(int)
    matrix["history_months"] = numeric(matrix.get("history_months", pd.Series(index=matrix.index, dtype=float))).fillna(0).astype(int)
    matrix["direct_history_eligible_v1"] = matrix["historical_forecast_eligible_authority"] & matrix["history_months"].ge(3)
    matrix["comparable_eligible_v1"] = matrix["selected_comparable_rows"].gt(0)
    matrix["forecast_experiment_eligible_v1"] = matrix["direct_history_eligible_v1"] | matrix["comparable_eligible_v1"]

    # Persist explicit source-to-feature lineage.
    lineage_rows = []
    lineage_map = {
        "current_price_authoritative": ("current_price", current_price_col, "DIRECT_JOIN"),
        "release_date_authoritative": ("release_authority", release_date_col, "DIRECT_JOIN"),
        "supply_scarcity_index_v1": ("scarcity_v1", scarcity_score_col, "DIRECT_JOIN"),
        "history_months": ("safe_monthly_history", history_diag["date_column"], "COUNT_UNIQUE_CANONICAL_MONTHS"),
        "return_30d": ("safe_monthly_history", history_diag["price_column"], "TRAILING_RETURN"),
        "return_90d": ("safe_monthly_history", history_diag["price_column"], "TRAILING_RETURN"),
        "return_180d": ("safe_monthly_history", history_diag["price_column"], "TRAILING_RETURN"),
        "return_365d": ("safe_monthly_history", history_diag["price_column"], "TRAILING_RETURN"),
        "annualized_volatility": ("safe_monthly_history", history_diag["price_column"], "MONTHLY_RETURN_STD_X_SQRT12"),
        "maximum_drawdown": ("safe_monthly_history", history_diag["price_column"], "RUNNING_PEAK_DRAWDOWN"),
        "selected_comparable_rows": ("comparables", comparable_diag["target_column"], "COUNT_ROWS_BY_TARGET"),
        "historical_forecast_eligible_authority": ("historical_forecast_eligible", hist_eligible_id_col, "AUTHORITY_MEMBERSHIP"),
    }
    for feature, col in structural_diag["chosen_columns"].items():
        lineage_map[feature] = ("structural_authority", col or "UNRESOLVED", "DIRECT_JOIN" if col else "BLOCKED_UNRESOLVED_COLUMN")
    for feature, (authority, source_column, transform) in lineage_map.items():
        lineage_rows.append({
            "feature": feature,
            "authority_key": authority,
            "authority_path": registry["authorities"][authority]["path"],
            "source_column": source_column,
            "transformation": transform,
            "join_key": "tcgplayer_product_id",
        })
    lineage = pd.DataFrame(lineage_rows)

    coverage_rows = []
    key_features = [
        "current_price_authoritative", "release_date_authoritative", "supply_scarcity_index_v1",
        "history_months", "return_90d", "return_180d", "return_365d", "annualized_volatility",
        "maximum_drawdown", "selected_comparable_rows", "pack_count", "box_topper", "licensed_ip",
        "product_family", "edition_classification"
    ]
    for feature in key_features:
        if feature not in matrix.columns:
            nonmissing = 0
        elif feature == "selected_comparable_rows":
            nonmissing = int(numeric(matrix[feature]).fillna(0).gt(0).sum())
        else:
            nonmissing = int(matrix[feature].notna().sum())
        coverage_rows.append({"feature": feature, "nonmissing_rows": nonmissing, "total_rows": len(matrix), "coverage_rate": nonmissing / len(matrix) if len(matrix) else 0})
    coverage = pd.DataFrame(coverage_rows)

    blockers = []
    if len(matrix) != 50 or matrix["tcgplayer_product_id"].nunique() != 50:
        blockers.append("Active universe is not exactly 50 unique products.")
    if matrix["current_price_authoritative"].isna().any():
        blockers.append("One or more active products lack authoritative current price.")
    if history_diag["covered_active_products"] == 0:
        blockers.append("Safe monthly history did not join to any active product.")
    if comparable_diag["covered_active_products"] == 0:
        blockers.append("Comparable authority did not join to any active product.")
    unresolved_structural = [k for k, v in structural_diag["chosen_columns"].items() if v is None]
    if unresolved_structural:
        blockers.append(f"Structural authority columns unresolved: {unresolved_structural}")
    if int(matrix["forecast_experiment_eligible_v1"].sum()) == 0:
        blockers.append("No active product is forecast-experiment eligible after authoritative joins.")

    matrix.to_csv(OUT / "collector_v1_authoritative_feature_matrix.csv", index=False)
    lineage.to_csv(OUT / "collector_v1_source_to_feature_lineage.csv", index=False)
    coverage.to_csv(OUT / "collector_v1_authoritative_feature_coverage.csv", index=False)
    pd.DataFrame([
        {"authority_key": k, "path": str(paths[k].relative_to(ROOT)), "sha256": sha256(paths[k]), "rows": len(frames[k]), "columns": "|".join(map(str, frames[k].columns))}
        for k in paths
    ]).to_csv(OUT / "collector_v1_authority_input_manifest.csv", index=False)

    summary = {
        "block_name": "Collector V1 Authoritative Feature Foundation",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "active_product_rows": int(len(matrix)),
        "unique_product_ids": int(matrix["tcgplayer_product_id"].nunique()),
        "history_diagnostics": history_diag,
        "comparable_diagnostics": comparable_diag,
        "structural_diagnostics": structural_diag,
        "direct_history_eligible_rows": int(matrix["direct_history_eligible_v1"].sum()),
        "comparable_eligible_rows": int(matrix["comparable_eligible_v1"].sum()),
        "forecast_experiment_eligible_rows": int(matrix["forecast_experiment_eligible_v1"].sum()),
        "blockers": blockers,
        "authoritative_feature_foundation_ready": not blockers,
        "forecast_experiments_authorized": not blockers,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_AUTHORITATIVE_FEATURE_FOUNDATION_READY" if not blockers else "BLOCKED_COLLECTOR_V1_AUTHORITATIVE_FEATURE_FOUNDATION",
    }
    (OUT / "collector_v1_authoritative_feature_foundation_summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return 1 if args.strict and blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
