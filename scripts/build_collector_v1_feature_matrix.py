"""Build the governed 50-product English-only Collector V1 feature matrix."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "data/governance/permanence/certification/collector_v1_active_english_universe"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_feature_matrix"
HORIZONS = ROOT / "config/mtg/governance/collector_v1_forecast_horizons.json"

PATHS = {
    "routes": ACTIVE / "collector_v1_active_canonical_routes.csv",
    "history": ACTIVE / "collector_v1_active_canonical_history.csv",
    "scarcity": ACTIVE / "collector_v1_active_scarcity.csv",
    "release": ACTIVE / "collector_v1_active_release.csv",
    "normalized": ACTIVE / "collector_v1_active_normalized.csv",
    "comparables": ACTIVE / "collector_v1_active_comparables.csv",
}

ID_ALIASES = ["tcgplayer_product_id", "product_id", "canonical_product_id", "resolved_tcgplayer_product_id"]
DATE_ALIASES = ["observation_date_utc", "observation_date", "date", "price_date", "snapshot_date", "as_of_date"]
PRICE_ALIASES = ["market_price", "current_price", "price", "value", "market", "median_price"]
RELEASE_ALIASES = ["official_release_date", "release_date", "released_at", "street_date"]


def load(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")


def pick(frame: pd.DataFrame, aliases: list[str]) -> str | None:
    return next((c for c in aliases if c in frame.columns), None)


def norm_id(value: object) -> str:
    text = str(value or "").strip().removeprefix("TCGPLAYER-")
    return text[:-2] if text.endswith(".0") else text


def truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def first_present(row: pd.Series, names: list[str], default: object = "") -> object:
    for name in names:
        if name in row.index and str(row.get(name, "")).strip() != "":
            return row.get(name)
    return default


def pct_return(series: pd.Series, dates: pd.Series, days: int) -> float | None:
    if len(series) < 2:
        return None
    latest_date = dates.max()
    target = latest_date - pd.Timedelta(days=days)
    eligible = pd.DataFrame({"d": dates, "p": series}).dropna().sort_values("d")
    eligible = eligible[eligible["d"] <= target]
    if eligible.empty:
        return None
    start = float(eligible.iloc[-1]["p"])
    end = float(series.iloc[-1])
    if start <= 0:
        return None
    return end / start - 1.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    missing = [name for name, path in PATHS.items() if not path.is_file()]
    if not HORIZONS.is_file():
        missing.append("horizons")
    if missing:
        print(json.dumps({"status": "FAIL_REQUIRED_INPUTS_MISSING", "missing": missing}, indent=2))
        return 1 if args.strict else 0

    frames = {name: load(path) for name, path in PATHS.items()}
    routes = frames["routes"].copy()
    route_id = pick(routes, ID_ALIASES)
    if route_id is None:
        print(json.dumps({"status": "FAIL_ROUTE_ID_MISSING"}, indent=2))
        return 1 if args.strict else 0
    routes["__pid"] = routes[route_id].map(norm_id)

    history = frames["history"].copy()
    hid = pick(history, ID_ALIASES)
    hdate = pick(history, DATE_ALIASES)
    hprice = pick(history, PRICE_ALIASES)
    if hid:
        history["__pid"] = history[hid].map(norm_id)
    if hdate:
        history["__date"] = pd.to_datetime(history[hdate], errors="coerce", utc=True)
    if hprice:
        history["__price"] = pd.to_numeric(history[hprice], errors="coerce")

    scarcity = frames["scarcity"].copy()
    sid = pick(scarcity, ID_ALIASES)
    scarcity["__pid"] = scarcity[sid].map(norm_id) if sid else ""

    release = frames["release"].copy()
    rid = pick(release, ID_ALIASES)
    release["__pid"] = release[rid].map(norm_id) if rid else ""
    rdate = pick(release, RELEASE_ALIASES)

    normalized = frames["normalized"].copy()
    nid = pick(normalized, ID_ALIASES)
    normalized["__pid"] = normalized[nid].map(norm_id) if nid else ""

    comparables = frames["comparables"].copy()
    cid = pick(comparables, ID_ALIASES)
    comparables["__pid"] = comparables[cid].map(norm_id) if cid else ""

    now = pd.Timestamp.now(tz="UTC")
    rows: list[dict] = []
    horizon_rows: list[dict] = []

    for _, route in routes.sort_values("__pid").iterrows():
        pid = route["__pid"]
        hg = history[history.get("__pid", pd.Series(dtype=str)) == pid].sort_values("__date") if hid and hdate and hprice else pd.DataFrame()
        sg = scarcity[scarcity["__pid"] == pid]
        rg = release[release["__pid"] == pid]
        ng = normalized[normalized["__pid"] == pid]
        cg = comparables[comparables["__pid"] == pid]

        prices = hg["__price"].dropna() if not hg.empty else pd.Series(dtype=float)
        dates = hg.loc[prices.index, "__date"] if not prices.empty else pd.Series(dtype="datetime64[ns, UTC]")
        latest_price = float(prices.iloc[-1]) if not prices.empty else None
        latest_date = dates.iloc[-1] if not dates.empty else pd.NaT
        first_date = dates.iloc[0] if not dates.empty else pd.NaT
        span_days = int((latest_date - first_date).days) if pd.notna(latest_date) and pd.notna(first_date) else 0
        returns = prices.pct_change().dropna() if len(prices) >= 2 else pd.Series(dtype=float)
        volatility = float(returns.std(ddof=1) * np.sqrt(365)) if len(returns) >= 2 else None
        drawdown = None
        if len(prices) >= 2:
            running_max = prices.cummax()
            drawdown = float((prices / running_max - 1.0).min())

        scarcity_row = sg.iloc[0] if not sg.empty else pd.Series(dtype=object)
        release_row = rg.iloc[0] if not rg.empty else pd.Series(dtype=object)
        normalized_row = ng.iloc[0] if not ng.empty else pd.Series(dtype=object)

        release_value = release_row.get(rdate, "") if rdate else ""
        release_ts = pd.to_datetime(release_value, errors="coerce", utc=True)
        presale = bool(pd.notna(release_ts) and release_ts > now)
        age_days = int((now - release_ts).days) if pd.notna(release_ts) and release_ts <= now else None

        seller_count = pd.to_numeric(pd.Series([scarcity_row.get("observable_seller_count", "")]), errors="coerce").iloc[0]
        seller_feature_available = bool(pd.notna(seller_count) and seller_count > 0)

        method = str(first_present(route, ["forecast_method", "method", "selected_method"]))
        history_days = int(dates.dt.normalize().nunique()) if not dates.empty else 0
        direct_history_eligible = bool(history_days >= 30 and not presale and method.startswith("DIRECT_HISTORY"))
        comparable_eligible = bool((method in {"COMPARABLE_PRODUCT_ADJUSTED", "FUNDAMENTAL_COMPARABLE_HYBRID"}) and len(cg) > 0)

        row = {
            "investment_product_id": first_present(route, ["investment_product_id"]),
            "tcgplayer_product_id": pid,
            "product_name": first_present(route, ["product_name", "canonical_product_name"]),
            "forecast_method": method,
            "current_price": first_present(route, ["current_price", "market_price"]),
            "latest_history_price": latest_price,
            "latest_price_date": "" if pd.isna(latest_date) else latest_date.isoformat(),
            "history_observation_days": history_days,
            "history_start_date": "" if pd.isna(first_date) else first_date.isoformat(),
            "history_end_date": "" if pd.isna(latest_date) else latest_date.isoformat(),
            "history_span_days": span_days,
            "return_30d": pct_return(prices.reset_index(drop=True), dates.reset_index(drop=True), 30) if not prices.empty else None,
            "return_90d": pct_return(prices.reset_index(drop=True), dates.reset_index(drop=True), 90) if not prices.empty else None,
            "return_180d": pct_return(prices.reset_index(drop=True), dates.reset_index(drop=True), 180) if not prices.empty else None,
            "return_365d": pct_return(prices.reset_index(drop=True), dates.reset_index(drop=True), 365) if not prices.empty else None,
            "annualized_volatility": volatility,
            "maximum_drawdown": drawdown,
            "release_date": release_value,
            "product_age_days": age_days,
            "presale": presale,
            "accepted_listing_count": scarcity_row.get("accepted_listing_count", ""),
            "review_listing_count": scarcity_row.get("review_listing_count", ""),
            "cross_product_ambiguity_excluded_count": scarcity_row.get("cross_product_ambiguity_excluded_count", ""),
            "supply_scarcity_index_v1": scarcity_row.get("supply_scarcity_index_v1", ""),
            "scarcity_confidence": scarcity_row.get("scarcity_confidence", ""),
            "scarcity_adjusted_score": scarcity_row.get("scarcity_adjusted_score", ""),
            "scarcity_tier": scarcity_row.get("scarcity_tier", ""),
            "observable_seller_count": scarcity_row.get("observable_seller_count", ""),
            "seller_feature_available": seller_feature_available,
            "selected_comparable_rows": int(len(cg)),
            "history_certification_status": first_present(route, ["history_certification_status"]),
            "direct_history_eligible_v1": direct_history_eligible,
            "comparable_eligible_v1": comparable_eligible,
            "forecast_experiment_eligible_v1": bool(direct_history_eligible or comparable_eligible or presale),
            "purchase_recommendation_authorized": False,
            "uip_export_authorized": False,
        }
        for candidate in ["pack_count", "box_topper", "licensed_ip", "product_family", "edition_classification"]:
            row[candidate] = first_present(normalized_row, [candidate], "")
        rows.append(row)

        for days in [30, 90, 180, 365, 1095, 1825]:
            enough_history = history_days >= max(2, min(days, 365) // 30)
            horizon_rows.append({
                "tcgplayer_product_id": pid,
                "product_name": row["product_name"],
                "horizon_days": days,
                "history_observation_days": history_days,
                "presale": presale,
                "direct_history_horizon_eligible": bool(direct_history_eligible and enough_history),
                "comparable_horizon_eligible": bool(comparable_eligible or presale),
                "forecast_experiment_horizon_eligible": bool((direct_history_eligible and enough_history) or comparable_eligible or presale),
                "uncertainty_band": "VERY_WIDE" if presale or days >= 1095 else ("WIDE" if days >= 365 or history_days < 30 else "STANDARD"),
            })

    matrix = pd.DataFrame(rows)
    coverage = []
    for column in matrix.columns:
        nonblank = matrix[column].astype(str).str.strip().ne("") & matrix[column].notna()
        coverage.append({"feature": column, "nonmissing_rows": int(nonblank.sum()), "total_rows": int(len(matrix)), "coverage_rate": round(float(nonblank.mean()), 6)})

    dictionary = pd.DataFrame([
        {"feature": c, "description": c.replace("_", " "), "source_layer": "derived_or_governed_input", "production_role": "EXPERIMENTAL_V1"}
        for c in matrix.columns
    ])
    missing_policy = pd.DataFrame([
        {"feature": "observable_seller_count", "policy": "DO_NOT_USE_AS_DIFFERENTIATING_FEATURE_WHILE_ALL_ZERO", "reason": "Current snapshot has no usable seller differentiation."},
        {"feature": "supply_scarcity_index_v1", "policy": "EXPERIMENTAL_ABLATION_REQUIRED", "reason": "V1 contains an inactive seller component and must be compared with an adjusted variant."},
        {"feature": "historical_returns", "policy": "LEAVE_MISSING_AND_ROUTE_TO_COMPARABLE_METHOD", "reason": "Do not fabricate time-series depth."},
        {"feature": "presale_realized_history", "policy": "NOT_APPLICABLE", "reason": "Presales use comparable logic and wider uncertainty."},
    ])

    matrix.to_csv(OUT / "collector_v1_feature_matrix.csv", index=False)
    dictionary.to_csv(OUT / "collector_v1_feature_dictionary.csv", index=False)
    pd.DataFrame(coverage).to_csv(OUT / "collector_v1_feature_coverage.csv", index=False)
    pd.DataFrame(horizon_rows).to_csv(OUT / "collector_v1_horizon_eligibility.csv", index=False)
    missing_policy.to_csv(OUT / "collector_v1_missing_feature_policy.csv", index=False)

    summary = {
        "block_name": "Collector V1 Governed Feature Matrix",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "active_product_rows": int(len(matrix)),
        "unique_product_ids": int(matrix["tcgplayer_product_id"].nunique()),
        "foreign_language_rows": int(matrix["tcgplayer_product_id"].eq("628315").sum()),
        "presale_rows": int(matrix["presale"].astype(bool).sum()),
        "seller_feature_usable_rows": int(matrix["seller_feature_available"].astype(bool).sum()),
        "direct_history_eligible_rows": int(matrix["direct_history_eligible_v1"].astype(bool).sum()),
        "comparable_eligible_rows": int(matrix["comparable_eligible_v1"].astype(bool).sum()),
        "forecast_experiment_eligible_rows": int(matrix["forecast_experiment_eligible_v1"].astype(bool).sum()),
        "feature_matrix_authorized": bool(len(matrix) == 50 and matrix["tcgplayer_product_id"].nunique() == 50 and not matrix["tcgplayer_product_id"].eq("628315").any()),
        "forecast_experiments_authorized": True,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "seller_feature_policy": "DISABLED_FOR_DIFFERENTIATION_IN_V1",
        "scarcity_v1_policy": "EXPERIMENTAL_FEATURE_REQUIRES_ABLATION_AND_ADJUSTED_VARIANT",
        "artifact_hashes": {name: sha256(path) for name, path in PATHS.items()} | {
            "feature_matrix": sha256(OUT / "collector_v1_feature_matrix.csv"),
            "horizon_eligibility": sha256(OUT / "collector_v1_horizon_eligibility.csv"),
        },
        "status": "PASS_COLLECTOR_V1_FEATURE_MATRIX_READY" if len(matrix) == 50 else "FAIL_COLLECTOR_V1_FEATURE_MATRIX",
    }
    (OUT / "collector_v1_feature_matrix_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (OUT / "collector_v1_feature_matrix_manifest.json").write_text(json.dumps({"inputs": {k: str(v.relative_to(ROOT)) for k, v in PATHS.items()}, "outputs": [p.name for p in OUT.glob("collector_v1_*")]}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    passed = summary["status"].startswith("PASS")
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
