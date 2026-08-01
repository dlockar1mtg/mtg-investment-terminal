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

FEATURE_COLUMNS = [
    "product_key", "product_name", "decision_cutoff", "market_price_at_cutoff", "release_date",
    "release_identity_source", "product_age_months", "product_age_route", "return_3_month",
    "return_6_month", "return_12_month", "cagr_2_year", "cagr_3_year",
    "since_history_start_cagr", "since_release_cagr", "collector_category_cagr",
    "trailing_12_month_volatility", "maximum_12_month_drawdown", "positive_month_rate",
    "return_persistence", "forecast_extremeness", "history_observation_count", "data_quality_grade",
    "predictor_information_available_at_cutoff", "future_information_used", "source_lineage",
]


def norm_name(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    return " ".join(text.split())


def release_identity(value: object) -> str:
    text = norm_name(value)
    for suffix in (
        "collector booster display", "collector booster box", "collector booster",
        "booster display", "booster box",
    ):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return text


def choose(df: pd.DataFrame, aliases: list[str]) -> str | None:
    lower = {str(c).lower(): str(c) for c in df.columns}
    return next((lower[a.lower()] for a in aliases if a.lower() in lower), None)


def load_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()
    except (pd.errors.EmptyDataError, UnicodeDecodeError, OSError):
        return pd.DataFrame()


def parse_dates(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce", utc=True)
    return parsed.dt.tz_convert(None)


def standardize_history(raw: pd.DataFrame, aliases: dict[str, list[str]], source: str) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()
    key = choose(raw, aliases["product_key"])
    name = choose(raw, aliases["product_name"])
    date = choose(raw, aliases["observation_date"])
    price = choose(raw, aliases["market_price"])
    if date is None or price is None or (key is None and name is None):
        return pd.DataFrame()
    frame = pd.DataFrame({
        "product_key": raw[key].astype(str) if key else "",
        "product_name": raw[name].astype(str) if name else "",
        "observation_date": parse_dates(raw[date]),
        "market_price": pd.to_numeric(raw[price], errors="coerce"),
        "source_lineage": source,
    })
    frame["normalized_name"] = frame["product_name"].map(norm_name)
    frame["release_identity"] = frame["product_name"].map(release_identity)
    frame = frame.dropna(subset=["observation_date", "market_price"])
    frame = frame[frame["market_price"] > 0]
    collector = frame["product_name"].str.contains("Collector Booster", case=False, na=False)
    if collector.any():
        frame = frame[collector]
    return frame


def collect_release_candidates(
    raw: pd.DataFrame,
    aliases: dict[str, list[str]],
    source: str,
) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()
    key = choose(raw, aliases["product_key"])
    name = choose(raw, aliases["product_name"])
    date = choose(raw, aliases["release_date"])
    if date is None or (key is None and name is None):
        return pd.DataFrame()
    frame = pd.DataFrame({
        "product_key": raw[key].astype(str) if key else "",
        "product_name": raw[name].astype(str) if name else "",
        "release_date": parse_dates(raw[date]),
        "release_identity_source": source,
    }).dropna(subset=["release_date"])
    frame["release_identity"] = frame["product_name"].map(release_identity)
    return frame


def prior_value(group: pd.DataFrame, cutoff: pd.Timestamp, months: int) -> float:
    eligible = group[group["observation_date"] <= cutoff - pd.DateOffset(months=months)]
    return float(eligible.iloc[-1]["market_price"]) if not eligible.empty else np.nan


def safe_return(current: float, prior: float) -> float:
    return current / prior - 1.0 if np.isfinite(current) and np.isfinite(prior) and prior > 0 else np.nan


def cagr(current: float, prior: float, years: float) -> float:
    if not all([np.isfinite(current), np.isfinite(prior), current > 0, prior > 0, years > 0]):
        return np.nan
    return (current / prior) ** (1.0 / years) - 1.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    aliases = cfg["field_aliases"]
    OUT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    canonical = {k: ROOT / v for k, v in cfg["canonical_sources"].items()}
    source_paths = [ROOT / p for p in cfg.get("price_history_sources", [cfg["canonical_sources"]["price_history"]])]
    lineage_rows: list[dict[str, object]] = []
    history_parts: list[pd.DataFrame] = []
    release_parts: list[pd.DataFrame] = []

    for i, path in enumerate(source_paths):
        role = "price_history" if i == 0 else "price_history_supplement"
        raw = load_csv(path)
        part = standardize_history(raw, aliases, str(path.relative_to(ROOT)))
        releases = collect_release_candidates(raw, aliases, str(path.relative_to(ROOT)))
        lineage_rows.append({
            "source_role": role,
            "source_path": str(path.relative_to(ROOT)),
            "exists": path.exists(),
            "historical_predictor_eligible": not part.empty,
            "current_only": False,
            "mapped_row_count": int(len(part)),
            "release_candidate_count": int(len(releases)),
        })
        if not part.empty:
            history_parts.append(part)
        if not releases.empty:
            release_parts.append(releases)

    registry_raw = load_csv(canonical["release_registry"])
    replay_raw = load_csv(canonical["walk_forward_outcomes"])
    registry_releases = collect_release_candidates(
        registry_raw, aliases, str(canonical["release_registry"].relative_to(ROOT))
    )
    if not registry_releases.empty:
        release_parts.insert(0, registry_releases)

    for role in ["release_registry", "walk_forward_outcomes", "current_fundamentals"]:
        path = canonical[role]
        lineage_rows.append({
            "source_role": role,
            "source_path": str(path.relative_to(ROOT)),
            "exists": path.exists(),
            "historical_predictor_eligible": role in {"release_registry", "walk_forward_outcomes"},
            "current_only": role == "current_fundamentals",
            "mapped_row_count": None,
            "release_candidate_count": int(len(registry_releases)) if role == "release_registry" else None,
        })

    history = pd.concat(history_parts, ignore_index=True) if history_parts else pd.DataFrame()
    if history.empty:
        failures.append("canonical_price_history_stack_missing_or_empty")
    else:
        history["month"] = history["observation_date"].dt.to_period("M").dt.to_timestamp("M")
        history["identity"] = np.where(
            history["product_key"].astype(str).str.strip().isin(["", "nan", "None"]),
            history["release_identity"],
            history["product_key"].astype(str),
        )
        history = history.sort_values(["identity", "month", "observation_date", "source_lineage"])
        history = history.groupby(["identity", "month"], as_index=False).tail(1)
        history["observation_date"] = history["month"]

    release_table = pd.concat(release_parts, ignore_index=True) if release_parts else pd.DataFrame()
    release_by_key: dict[str, pd.Timestamp] = {}
    release_by_name: dict[str, pd.Timestamp] = {}
    release_source_by_key: dict[str, str] = {}
    release_source_by_name: dict[str, str] = {}
    if not release_table.empty:
        release_table = release_table.sort_values(["release_date", "release_identity_source"])
        valid_key = ~release_table["product_key"].astype(str).str.strip().isin(["", "nan", "None"])
        keyed = release_table[valid_key].drop_duplicates("product_key", keep="first")
        named = release_table[release_table["release_identity"] != ""].drop_duplicates("release_identity", keep="first")
        release_by_key = keyed.set_index("product_key")["release_date"].to_dict()
        release_by_name = named.set_index("release_identity")["release_date"].to_dict()
        release_source_by_key = keyed.set_index("product_key")["release_identity_source"].to_dict()
        release_source_by_name = named.set_index("release_identity")["release_identity_source"].to_dict()

    if not history.empty:
        history["release_date"] = history["product_key"].astype(str).map(release_by_key)
        missing_release = history["release_date"].isna()
        history.loc[missing_release, "release_date"] = history.loc[missing_release, "release_identity"].map(release_by_name)
        history["release_identity_source"] = history["product_key"].astype(str).map(release_source_by_key)
        missing_source = history["release_identity_source"].isna()
        history.loc[missing_source, "release_identity_source"] = history.loc[missing_source, "release_identity"].map(release_source_by_name)
        history["monthly_return"] = history.groupby("identity")["market_price"].pct_change()
        history.to_csv(OUT / "collector_long_horizon_monthly_price_panel.csv", index=False)
    else:
        pd.DataFrame(columns=[
            "product_key", "product_name", "observation_date", "market_price", "source_lineage",
            "normalized_name", "release_identity", "release_date", "release_identity_source", "monthly_return",
        ]).to_csv(OUT / "collector_long_horizon_monthly_price_panel.csv", index=False)

    decision_rows: list[dict[str, object]] = []
    if replay_raw.empty:
        failures.append("walk_forward_outcomes_missing_or_empty")
    elif not history.empty:
        d_key = choose(replay_raw, aliases["product_key"])
        d_name = choose(replay_raw, aliases["product_name"])
        d_cutoff = choose(replay_raw, aliases["decision_cutoff"])
        if not d_cutoff or (not d_key and not d_name):
            failures.append("decision_mapping_missing")
        else:
            decisions = pd.DataFrame({
                "product_key": replay_raw[d_key].astype(str) if d_key else "",
                "product_name": replay_raw[d_name].astype(str) if d_name else "",
                "decision_cutoff": parse_dates(replay_raw[d_cutoff]),
            }).dropna(subset=["decision_cutoff"]).drop_duplicates()
            decisions["release_identity"] = decisions["product_name"].map(release_identity)

            for row in decisions.itertuples(index=False):
                key = str(row.product_key)
                matched = history[history["product_key"].astype(str) == key] if key not in {"", "nan", "None"} else pd.DataFrame()
                if matched.empty:
                    matched = history[history["release_identity"] == row.release_identity]
                matched = matched[matched["observation_date"] <= row.decision_cutoff].sort_values("observation_date")
                if matched.empty:
                    continue

                current = float(matched.iloc[-1]["market_price"])
                release = matched["release_date"].dropna().iloc[-1] if matched["release_date"].notna().any() else pd.NaT
                release_source = matched["release_identity_source"].dropna().iloc[-1] if matched["release_identity_source"].notna().any() else ""
                age = ((row.decision_cutoff.year - release.year) * 12 + row.decision_cutoff.month - release.month) if pd.notna(release) else np.nan
                route = "MATURE" if pd.notna(age) and age >= 36 else "DEVELOPING" if pd.notna(age) and age >= 18 else "LIMITED"

                monthly_returns = matched["monthly_return"].dropna().tail(12)
                rolling = matched.tail(13)["market_price"]
                drawdown = float((rolling / rolling.cummax() - 1.0).min()) if len(rolling) >= 2 else np.nan
                first_observation = matched.iloc[0]["observation_date"]
                first_price = float(matched.iloc[0]["market_price"])
                history_years = max((row.decision_cutoff - first_observation).days / 365.25, 0.0)
                near_release = pd.notna(release) and abs((first_observation - release).days) <= 120

                decision_rows.append({
                    "product_key": key,
                    "product_name": row.product_name,
                    "decision_cutoff": row.decision_cutoff.date().isoformat(),
                    "market_price_at_cutoff": current,
                    "release_date": release.date().isoformat() if pd.notna(release) else "",
                    "release_identity_source": release_source,
                    "product_age_months": age,
                    "product_age_route": route,
                    "return_3_month": safe_return(current, prior_value(matched, row.decision_cutoff, 3)),
                    "return_6_month": safe_return(current, prior_value(matched, row.decision_cutoff, 6)),
                    "return_12_month": safe_return(current, prior_value(matched, row.decision_cutoff, 12)),
                    "cagr_2_year": cagr(current, prior_value(matched, row.decision_cutoff, 24), 2.0),
                    "cagr_3_year": cagr(current, prior_value(matched, row.decision_cutoff, 36), 3.0),
                    "since_history_start_cagr": cagr(current, first_price, history_years),
                    "since_release_cagr": cagr(current, first_price, history_years) if near_release else np.nan,
                    "trailing_12_month_volatility": float(monthly_returns.std(ddof=1) * math.sqrt(12)) if len(monthly_returns) >= 6 else np.nan,
                    "maximum_12_month_drawdown": drawdown,
                    "positive_month_rate": float((monthly_returns > 0).mean()) if len(monthly_returns) >= 6 else np.nan,
                    "return_persistence": float(monthly_returns.autocorr(lag=1)) if len(monthly_returns) >= 6 else np.nan,
                    "history_observation_count": int(len(matched)),
                    "predictor_information_available_at_cutoff": True,
                    "future_information_used": False,
                    "source_lineage": "|".join(sorted(set(matched["source_lineage"].astype(str)))),
                })

    base_columns = [c for c in FEATURE_COLUMNS if c not in {"collector_category_cagr", "forecast_extremeness", "data_quality_grade"}]
    features = pd.DataFrame(decision_rows, columns=base_columns)
    if not features.empty:
        for _, idx in features.groupby("decision_cutoff").groups.items():
            values = pd.to_numeric(features.loc[idx, "return_12_month"], errors="coerce")
            if values.notna().any():
                median = values.median(skipna=True)
                scale = values.std(skipna=True)
                features.loc[idx, "collector_category_cagr"] = median
                features.loc[idx, "forecast_extremeness"] = (values - median).abs() / scale if pd.notna(scale) and scale > 0 else np.nan
        features["data_quality_grade"] = np.select(
            [features["history_observation_count"] >= 36, features["history_observation_count"] >= 18, features["history_observation_count"] >= 6],
            ["A", "B", "C"],
            default="D",
        )
        features = features.reindex(columns=FEATURE_COLUMNS)
    else:
        features = pd.DataFrame(columns=FEATURE_COLUMNS)
    features.to_csv(OUT / "collector_long_horizon_decision_feature_panel.csv", index=False)

    feature_names = [
        "product_age_months", "product_age_route", "return_3_month", "return_6_month", "return_12_month",
        "cagr_2_year", "cagr_3_year", "since_history_start_cagr", "since_release_cagr",
        "collector_category_cagr", "trailing_12_month_volatility", "maximum_12_month_drawdown",
        "positive_month_rate", "return_persistence", "forecast_extremeness", "data_quality_grade",
    ]
    coverage_rows = [{
        "derived_feature": name,
        "implemented": name in features.columns,
        "non_null_count": int(features[name].notna().sum()) if name in features else 0,
        "row_count": int(len(features)),
        "coverage_rate": float(features[name].notna().mean()) if len(features) and name in features else 0.0,
        "certified": False,
    } for name in feature_names]
    pd.DataFrame(coverage_rows).to_csv(OUT / "collector_long_horizon_feature_coverage.csv", index=False)
    pd.DataFrame(lineage_rows).to_csv(OUT / "collector_long_horizon_source_lineage.csv", index=False)

    if features.empty:
        failures.append("decision_feature_panel_empty")
    if not features.empty and features["future_information_used"].astype(str).str.lower().eq("true").any():
        failures.append("future_information_detected")

    release_coverage = float(features["release_date"].astype(str).ne("").mean()) if not features.empty else 0.0
    result = {
        "audit_name": "Collector Long-Horizon Historical Feature Panel",
        "audit_version": "1.0.2",
        "status": "PASS" if not failures else "FAIL",
        "history_source_count": len(source_paths),
        "mapped_history_source_count": len(history_parts),
        "release_candidate_count": int(len(release_table)),
        "release_date_coverage_rate": release_coverage,
        "monthly_price_row_count": int(len(history)),
        "monthly_price_product_count": int(history["identity"].nunique()) if not history.empty else 0,
        "decision_feature_row_count": int(len(features)),
        "decision_cutoff_count": int(features["decision_cutoff"].nunique()) if not features.empty else 0,
        "implemented_feature_count": int(sum(bool(r["implemented"]) for r in coverage_rows)),
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
    (OUT / "collector_long_horizon_historical_feature_panel_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
