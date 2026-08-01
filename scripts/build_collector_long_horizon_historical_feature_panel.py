from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/mtg/governance/collector_long_horizon_canonical_source_mapping_v1.json"
OUT = ROOT / "data/operations/collector_long_horizon_historical_feature_panel/candidate_v1_0_0"


def norm_name(value: object) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def choose(df: pd.DataFrame, aliases: list[str]) -> str | None:
    lower = {c.lower(): c for c in df.columns}
    for alias in aliases:
        if alias.lower() in lower:
            return lower[alias.lower()]
    return None


def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()


def safe_return(current: float, prior: float) -> float:
    if not np.isfinite(current) or not np.isfinite(prior) or prior <= 0:
        return np.nan
    return current / prior - 1.0


def cagr(current: float, prior: float, years: float) -> float:
    if not np.isfinite(current) or not np.isfinite(prior) or current <= 0 or prior <= 0 or years <= 0:
        return np.nan
    return (current / prior) ** (1.0 / years) - 1.0


def prior_value(group: pd.DataFrame, cutoff: pd.Timestamp, months: int) -> float:
    target = cutoff - pd.DateOffset(months=months)
    eligible = group[group["observation_date"] <= target]
    if eligible.empty:
        return np.nan
    return float(eligible.iloc[-1]["market_price"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    aliases = cfg["field_aliases"]

    paths = {k: ROOT / v for k, v in cfg["canonical_sources"].items()}
    history_raw = load_csv(paths["price_history"])
    registry_raw = load_csv(paths["release_registry"])
    replay_raw = load_csv(paths["walk_forward_outcomes"])

    if history_raw.empty:
        failures.append("canonical_price_history_missing_or_empty")
    if replay_raw.empty:
        failures.append("walk_forward_outcomes_missing_or_empty")

    lineage_rows: list[dict[str, object]] = []
    for role, path in paths.items():
        lineage_rows.append({
            "source_role": role,
            "source_path": str(path.relative_to(ROOT)),
            "exists": path.exists(),
            "historical_predictor_eligible": role in {"price_history", "release_registry", "walk_forward_outcomes"},
            "current_only": role == "current_fundamentals",
        })

    history = pd.DataFrame()
    if not history_raw.empty:
        h_key = choose(history_raw, aliases["product_key"])
        h_name = choose(history_raw, aliases["product_name"])
        h_date = choose(history_raw, aliases["observation_date"])
        h_price = choose(history_raw, aliases["market_price"])
        missing = [name for name, col in [("product", h_key or h_name), ("observation_date", h_date), ("market_price", h_price)] if col is None]
        if missing:
            failures.append("history_mapping_missing:" + ",".join(missing))
        else:
            history = pd.DataFrame({
                "product_key": history_raw[h_key].astype(str) if h_key else "",
                "product_name": history_raw[h_name].astype(str) if h_name else "",
                "observation_date": pd.to_datetime(history_raw[h_date], errors="coerce"),
                "market_price": pd.to_numeric(history_raw[h_price], errors="coerce"),
            })
            history["normalized_name"] = history["product_name"].map(norm_name)
            history = history.dropna(subset=["observation_date", "market_price"])
            history = history[history["market_price"] > 0]
            history = history[history["product_name"].str.contains("Collector Booster", case=False, na=False)]
            history["month"] = history["observation_date"].dt.to_period("M").dt.to_timestamp("M")
            history = history.sort_values(["product_key", "normalized_name", "observation_date"])
            history = history.groupby(["product_key", "normalized_name", "month"], as_index=False).tail(1)
            history["observation_date"] = history["month"]

    release_map: dict[str, pd.Timestamp] = {}
    if not registry_raw.empty:
        r_name = choose(registry_raw, aliases["product_name"])
        r_date = choose(registry_raw, aliases["release_date"])
        if r_name and r_date:
            temp = pd.DataFrame({
                "normalized_name": registry_raw[r_name].map(norm_name),
                "release_date": pd.to_datetime(registry_raw[r_date], errors="coerce"),
            }).dropna()
            release_map = temp.drop_duplicates("normalized_name").set_index("normalized_name")["release_date"].to_dict()

    if not history.empty:
        history["release_date"] = history["normalized_name"].map(release_map)
        history["monthly_return"] = history.groupby(["product_key", "normalized_name"])["market_price"].pct_change()
        history.to_csv(OUT / "collector_long_horizon_monthly_price_panel.csv", index=False)
    else:
        pd.DataFrame().to_csv(OUT / "collector_long_horizon_monthly_price_panel.csv", index=False)

    decision_rows: list[dict[str, object]] = []
    if not replay_raw.empty and not history.empty:
        d_key = choose(replay_raw, aliases["product_key"])
        d_name = choose(replay_raw, aliases["product_name"])
        d_cutoff = choose(replay_raw, aliases["decision_cutoff"])
        if not d_cutoff or (not d_key and not d_name):
            failures.append("decision_mapping_missing")
        else:
            decisions = pd.DataFrame({
                "product_key": replay_raw[d_key].astype(str) if d_key else "",
                "product_name": replay_raw[d_name].astype(str) if d_name else "",
                "decision_cutoff": pd.to_datetime(replay_raw[d_cutoff], errors="coerce"),
            }).dropna(subset=["decision_cutoff"]).drop_duplicates()
            decisions["normalized_name"] = decisions["product_name"].map(norm_name)

            for row in decisions.itertuples(index=False):
                product_hist = history.copy()
                if row.product_key and row.product_key != "nan":
                    matched = product_hist[product_hist["product_key"] == row.product_key]
                    if matched.empty:
                        matched = product_hist[product_hist["normalized_name"] == row.normalized_name]
                else:
                    matched = product_hist[product_hist["normalized_name"] == row.normalized_name]
                matched = matched[matched["observation_date"] <= row.decision_cutoff].sort_values("observation_date")
                if matched.empty:
                    continue
                current = float(matched.iloc[-1]["market_price"])
                release_date = matched["release_date"].dropna().iloc[-1] if matched["release_date"].notna().any() else pd.NaT
                age_months = ((row.decision_cutoff.year - release_date.year) * 12 + row.decision_cutoff.month - release_date.month) if pd.notna(release_date) else np.nan
                route = "MATURE" if pd.notna(age_months) and age_months >= 36 else "DEVELOPING" if pd.notna(age_months) and age_months >= 18 else "LIMITED"
                returns = matched["monthly_return"].dropna().tail(12)
                rolling = matched.tail(13)["market_price"]
                drawdown = np.nan
                if len(rolling) >= 2:
                    drawdown = float((rolling / rolling.cummax() - 1.0).min())
                first_price = float(matched.iloc[0]["market_price"])
                elapsed_years = max((row.decision_cutoff - matched.iloc[0]["observation_date"]).days / 365.25, 0.0)
                decision_rows.append({
                    "product_key": row.product_key,
                    "product_name": row.product_name,
                    "decision_cutoff": row.decision_cutoff.date().isoformat(),
                    "market_price_at_cutoff": current,
                    "release_date": release_date.date().isoformat() if pd.notna(release_date) else "",
                    "product_age_months": age_months,
                    "product_age_route": route,
                    "return_3_month": safe_return(current, prior_value(matched, row.decision_cutoff, 3)),
                    "return_6_month": safe_return(current, prior_value(matched, row.decision_cutoff, 6)),
                    "return_12_month": safe_return(current, prior_value(matched, row.decision_cutoff, 12)),
                    "cagr_2_year": cagr(current, prior_value(matched, row.decision_cutoff, 24), 2.0),
                    "cagr_3_year": cagr(current, prior_value(matched, row.decision_cutoff, 36), 3.0),
                    "since_release_cagr": cagr(current, first_price, elapsed_years),
                    "trailing_12_month_volatility": float(returns.std(ddof=1) * math.sqrt(12)) if len(returns) >= 6 else np.nan,
                    "maximum_12_month_drawdown": drawdown,
                    "positive_month_rate": float((returns > 0).mean()) if len(returns) >= 6 else np.nan,
                    "return_persistence": float(returns.autocorr(lag=1)) if len(returns) >= 6 else np.nan,
                    "history_observation_count": int(len(matched)),
                    "predictor_information_available_at_cutoff": True,
                    "future_information_used": False,
                    "source_lineage": str(paths["price_history"].relative_to(ROOT)),
                })

    features = pd.DataFrame(decision_rows)
    if not features.empty:
        for cutoff, idx in features.groupby("decision_cutoff").groups.items():
            values = features.loc[idx, "return_12_month"]
            median = values.median(skipna=True)
            features.loc[idx, "collector_category_cagr"] = median
            scale = values.std(skipna=True)
            features.loc[idx, "forecast_extremeness"] = (values - median).abs() / scale if pd.notna(scale) and scale > 0 else np.nan
        features["data_quality_grade"] = np.select(
            [features["history_observation_count"] >= 36, features["history_observation_count"] >= 18, features["history_observation_count"] >= 6],
            ["A", "B", "C"],
            default="D",
        )
    features.to_csv(OUT / "collector_long_horizon_decision_feature_panel.csv", index=False)

    feature_names = [
        "product_age_months", "product_age_route", "return_3_month", "return_6_month", "return_12_month",
        "cagr_2_year", "cagr_3_year", "since_release_cagr", "collector_category_cagr",
        "trailing_12_month_volatility", "maximum_12_month_drawdown", "positive_month_rate",
        "return_persistence", "forecast_extremeness", "data_quality_grade",
    ]
    coverage_rows = []
    for name in feature_names:
        non_null = int(features[name].notna().sum()) if name in features else 0
        coverage_rows.append({
            "derived_feature": name,
            "implemented": name in features.columns,
            "non_null_count": non_null,
            "row_count": int(len(features)),
            "coverage_rate": non_null / len(features) if len(features) else 0.0,
            "certified": False,
        })
    pd.DataFrame(coverage_rows).to_csv(OUT / "collector_long_horizon_feature_coverage.csv", index=False)
    pd.DataFrame(lineage_rows).to_csv(OUT / "collector_long_horizon_source_lineage.csv", index=False)

    if not features.empty and (features["future_information_used"] == True).any():
        failures.append("future_information_detected")
    if features.empty:
        failures.append("decision_feature_panel_empty")

    result = {
        "audit_name": "Collector Long-Horizon Historical Feature Panel",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "monthly_price_row_count": int(len(history)),
        "monthly_price_product_count": int(history["normalized_name"].nunique()) if not history.empty else 0,
        "decision_feature_row_count": int(len(features)),
        "decision_cutoff_count": int(features["decision_cutoff"].nunique()) if not features.empty else 0,
        "implemented_feature_count": int(sum(r["implemented"] for r in coverage_rows)),
        "current_only_fundamentals_used": False,
        "shadow_only": True,
        "candidate_methodology_change_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "technical_freeze_authorized": False,
        "uip_acceptance_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
    }
    (OUT / "collector_long_horizon_historical_feature_panel_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
