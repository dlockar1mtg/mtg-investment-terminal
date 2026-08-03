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
FOUNDATION = ROOT / "data/governance/permanence/certification/collector_v1_authoritative_feature_foundation"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_experiment_foundation"
HORIZONS = ROOT / "config/mtg/governance/collector_v1_forecast_horizons.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def first_column(df: pd.DataFrame, aliases: list[str], required: bool = True) -> str | None:
    lookup = {str(c).strip().lower(): str(c) for c in df.columns}
    for alias in aliases:
        if alias.lower() in lookup:
            return lookup[alias.lower()]
    if required:
        raise ValueError(f"Required column unresolved. aliases={aliases}; available={list(df.columns)}")
    return None


def normalize_id(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    extracted = text.str.extract(r"(\d+)$", expand=False)
    return extracted.fillna(text)


def minmax_inverse(series: pd.Series) -> pd.Series:
    x = pd.to_numeric(series, errors="coerce")
    if x.notna().sum() == 0:
        return pd.Series(np.nan, index=series.index)
    lo, hi = float(x.min()), float(x.max())
    if hi == lo:
        return pd.Series(50.0, index=series.index)
    return 100.0 * (hi - x) / (hi - lo)


def build_ssi_v1a(matrix: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    accepted_col = first_column(matrix, ["accepted_listing_count", "observable_listing_count", "listing_count"], required=False)
    review_col = first_column(matrix, ["review_listing_count", "review_count"], required=False)
    ambiguity_col = first_column(matrix, ["ambiguity_exclusion_count", "ambiguous_listing_count", "cross_product_ambiguity_count"], required=False)
    confidence_col = first_column(matrix, ["scarcity_confidence", "confidence_score", "scarcity_confidence_score"], required=False)

    out = matrix[["tcgplayer_product_id"]].copy()
    accepted = pd.to_numeric(matrix[accepted_col], errors="coerce") if accepted_col else pd.Series(np.nan, index=matrix.index)
    review = pd.to_numeric(matrix[review_col], errors="coerce").fillna(0) if review_col else pd.Series(0.0, index=matrix.index)
    ambiguity = pd.to_numeric(matrix[ambiguity_col], errors="coerce").fillna(0) if ambiguity_col else pd.Series(0.0, index=matrix.index)
    confidence = pd.to_numeric(matrix[confidence_col], errors="coerce") if confidence_col else pd.Series(np.nan, index=matrix.index)

    listing_component = minmax_inverse(accepted)
    uncertainty_raw = review + ambiguity
    uncertainty_penalty = 100.0 - minmax_inverse(uncertainty_raw)
    if confidence.notna().any():
        conf = confidence.copy()
        if conf.max(skipna=True) <= 1.0:
            conf = conf * 100.0
        confidence_component = conf.clip(0, 100)
    else:
        confidence_component = (100.0 - uncertainty_penalty).clip(0, 100)

    zero_observed = accepted.fillna(0).eq(0)
    raw = 0.75 * listing_component + 0.25 * confidence_component
    adjusted = raw.where(~zero_observed, raw * 0.80)

    out["accepted_listing_count"] = accepted
    out["review_listing_count"] = review
    out["ambiguity_exclusion_count"] = ambiguity
    out["listing_scarcity_component"] = listing_component
    out["confidence_component"] = confidence_component
    out["zero_observed_listing_flag"] = zero_observed
    out["supply_scarcity_index_v1a"] = adjusted.clip(0, 100)
    out["seller_component_used"] = False
    out["formula_version"] = "SSI_V1A_LISTINGS_75_CONFIDENCE_25_ZERO_OBSERVED_PENALTY"

    diagnostics = {
        "accepted_listing_column": accepted_col,
        "review_listing_column": review_col,
        "ambiguity_column": ambiguity_col,
        "confidence_column": confidence_col,
        "seller_component_used": False,
        "scored_products": int(out["supply_scarcity_index_v1a"].notna().sum()),
        "zero_observed_products": int(zero_observed.sum()),
    }
    return out, diagnostics


def load_monthly_history(registry: dict) -> tuple[pd.DataFrame, dict]:
    path = ROOT / registry["authorities"]["safe_monthly_history"]["path"]
    history = pd.read_csv(path, low_memory=False)
    id_col = first_column(history, ["tcgplayer_product_id", "product_id", "investment_product_id"])
    date_col = first_column(history, ["observation_month", "parsed_date", "source_observation_date", "month", "date"])
    price_col = first_column(history, ["source_market_price", "market_price", "monthly_market_price", "price"])
    h = history.copy()
    h["tcgplayer_product_id"] = normalize_id(h[id_col])
    h["observation_date"] = pd.to_datetime(h[date_col], errors="coerce", utc=True).dt.tz_convert(None)
    h["market_price"] = pd.to_numeric(h[price_col], errors="coerce")
    h = h[h["observation_date"].notna() & h["market_price"].gt(0)]
    h["observation_month"] = h["observation_date"].dt.to_period("M").dt.to_timestamp()
    h = h.groupby(["tcgplayer_product_id", "observation_month"], as_index=False).agg(market_price=("market_price", "median"))
    return h, {"path": str(path.relative_to(ROOT)), "id_column": id_col, "date_column": date_col, "price_column": price_col, "sha256": sha256(path)}


def build_experiments(matrix: pd.DataFrame, history: pd.DataFrame, horizons: list[int]) -> tuple[pd.DataFrame, dict]:
    matrix = matrix.copy()
    matrix["tcgplayer_product_id"] = normalize_id(matrix["tcgplayer_product_id"])
    route_col = first_column(matrix, ["forecast_method", "forecast_route", "method"])
    product_name_col = first_column(matrix, ["product_name", "governed_box_name", "set_name"], required=False)
    history_groups = {pid: g.sort_values("observation_month").reset_index(drop=True) for pid, g in history.groupby("tcgplayer_product_id")}
    rows: list[dict] = []

    horizon_months = {days: max(1, round(days / 30.4375)) for days in horizons}
    for _, product in matrix.iterrows():
        pid = str(product["tcgplayer_product_id"])
        if pid not in history_groups:
            continue
        g = history_groups[pid]
        prices = g["market_price"].astype(float)
        dates = g["observation_month"]
        for i in range(2, len(g)):
            cutoff = dates.iloc[i]
            known = g.iloc[: i + 1]
            cutoff_price = float(prices.iloc[i])
            monthly_returns = known["market_price"].pct_change().replace([np.inf, -np.inf], np.nan).dropna()
            momentum_3m = cutoff_price / float(known.iloc[max(0, i - 3)]["market_price"]) - 1.0 if i >= 1 else np.nan
            momentum_12m = cutoff_price / float(known.iloc[max(0, i - 12)]["market_price"]) - 1.0 if i >= 1 else np.nan
            vol = float(monthly_returns.std(ddof=1) * np.sqrt(12)) if len(monthly_returns) >= 2 else np.nan
            trend = float(np.polyfit(np.arange(len(known)), np.log(known["market_price"].astype(float)), 1)[0]) if len(known) >= 3 else np.nan

            for days, months in horizon_months.items():
                target_idx = i + months
                if target_idx >= len(g):
                    continue
                actual_price = float(prices.iloc[target_idx])
                rows.append({
                    "tcgplayer_product_id": pid,
                    "product_name": product.get(product_name_col, pd.NA) if product_name_col else pd.NA,
                    "forecast_method": product[route_col],
                    "cutoff_month": cutoff.date().isoformat(),
                    "horizon_days": int(days),
                    "horizon_months": int(months),
                    "price_at_cutoff": cutoff_price,
                    "actual_future_price": actual_price,
                    "actual_return": actual_price / cutoff_price - 1.0,
                    "history_months_at_cutoff": int(len(known)),
                    "momentum_3m": momentum_3m,
                    "momentum_12m": momentum_12m,
                    "annualized_volatility_at_cutoff": vol,
                    "trend_slope_monthly_at_cutoff": trend,
                    "feature_cutoff_enforced": True,
                    "target_after_cutoff": bool(dates.iloc[target_idx] > cutoff),
                })
    experiments = pd.DataFrame(rows)
    diagnostics = {
        "experiment_rows": int(len(experiments)),
        "products": int(experiments["tcgplayer_product_id"].nunique()) if not experiments.empty else 0,
        "cutoffs": int(experiments["cutoff_month"].nunique()) if not experiments.empty else 0,
        "rows_by_horizon": {str(k): int(v) for k, v in experiments.groupby("horizon_days").size().to_dict().items()} if not experiments.empty else {},
        "anti_leakage_pass": bool(experiments["target_after_cutoff"].all()) if not experiments.empty else False,
    }
    return experiments, diagnostics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    matrix_path = FOUNDATION / "collector_v1_authoritative_feature_matrix.csv"
    cert_path = FOUNDATION / "collector_v1_authoritative_feature_foundation_certification.json"
    if not matrix_path.exists() or not cert_path.exists():
        raise FileNotFoundError("Certified authoritative feature foundation is missing.")
    cert = json.loads(cert_path.read_text(encoding="utf-8"))
    if not cert.get("authoritative_feature_foundation_certified"):
        raise RuntimeError("Authoritative feature foundation is not certified.")

    matrix = pd.read_csv(matrix_path, low_memory=False)
    matrix["tcgplayer_product_id"] = normalize_id(matrix["tcgplayer_product_id"])
    ssi, ssi_diag = build_ssi_v1a(matrix)
    history, history_diag = load_monthly_history(registry)
    horizon_data = json.loads(HORIZONS.read_text(encoding="utf-8"))
    raw_horizons = horizon_data.get("horizons", horizon_data)
    horizons: list[int] = []
    if isinstance(raw_horizons, list):
        for item in raw_horizons:
            if isinstance(item, dict):
                days = item.get("days") or item.get("horizon_days")
            else:
                days = item
            if days is not None:
                horizons.append(int(days))
    if not horizons:
        horizons = [30, 90, 180, 365, 1095, 1825]

    experiments, exp_diag = build_experiments(matrix, history, horizons)
    blockers = []
    if len(ssi) != 50 or ssi["tcgplayer_product_id"].nunique() != 50:
        blockers.append("SSI V1A does not cover exactly 50 products.")
    if ssi["supply_scarcity_index_v1a"].notna().sum() == 0:
        blockers.append("SSI V1A produced no valid scores.")
    if experiments.empty:
        blockers.append("Historical cutoff dataset is empty.")
    if not exp_diag.get("anti_leakage_pass"):
        blockers.append("Historical cutoff anti-leakage check failed.")

    ssi.to_csv(OUT / "collector_supply_scarcity_index_v1a.csv", index=False)
    experiments.to_csv(OUT / "collector_v1_historical_cutoff_experiments.csv", index=False)
    lineage = pd.DataFrame([
        {"output": "collector_supply_scarcity_index_v1a.csv", "source": "authoritative_feature_matrix", "transformation": "LISTING_SCARCITY_75_PLUS_CONFIDENCE_25_NO_SELLER_COMPONENT"},
        {"output": "collector_v1_historical_cutoff_experiments.csv", "source": registry["authorities"]["safe_monthly_history"]["path"], "transformation": "ROLLING_MONTHLY_CUTOFFS_WITH_FUTURE_TARGETS"},
    ])
    lineage.to_csv(OUT / "collector_v1_experiment_lineage.csv", index=False)

    summary = {
        "block_name": "Collector V1 SSI V1A and Historical Experiment Foundation",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ssi_v1a_diagnostics": ssi_diag,
        "history_authority": history_diag,
        "experiment_diagnostics": exp_diag,
        "horizons_days": horizons,
        "blockers": blockers,
        "experiment_foundation_ready": not blockers,
        "baseline_backtesting_authorized": not blockers,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_EXPERIMENT_FOUNDATION_READY" if not blockers else "BLOCKED_COLLECTOR_V1_EXPERIMENT_FOUNDATION",
    }
    (OUT / "collector_v1_experiment_foundation_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if args.strict and blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
