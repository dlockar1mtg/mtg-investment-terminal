from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/mtg/governance/collector_early_lifecycle_forecast_engine_v1.json"
OUT = ROOT / "data/operations/collector_early_lifecycle_forecast_engine/candidate_v1_0_0"
NA = "NOT_AVAILABLE"
NAP = "NOT_APPLICABLE"


def read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()
    except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def choose(df: pd.DataFrame, aliases: list[str]) -> str | None:
    cols = {str(c).lower(): str(c) for c in df.columns}
    return next((cols[a.lower()] for a in aliases if a.lower() in cols), None)


def norm(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    text = re.sub(r"\bcollector booster (display|box)\b", "collector booster", text)
    return " ".join(text.split())


def num(value: object) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else np.nan
    except (TypeError, ValueError):
        return np.nan


def first_value(row: pd.Series, aliases: list[str], default: object = np.nan) -> object:
    lower = {str(c).lower(): c for c in row.index}
    for alias in aliases:
        if alias.lower() in lower:
            value = row[lower[alias.lower()]]
            if pd.notna(value) and str(value).strip() not in {"", "nan", "None"}:
                return value
    return default


def age_band(age: float) -> str:
    if not math.isfinite(age):
        return "AGE_UNRESOLVED"
    if age <= 3:
        return "LAUNCH_PRICE_DISCOVERY"
    if age <= 8:
        return "INITIAL_SUPPLY_ABSORPTION"
    if age <= 12:
        return "STABILIZATION"
    if age <= 17:
        return "EARLY_ACCUMULATION"
    if age <= 35:
        return "DEVELOPING"
    return "MATURE"


def price_band(price: float) -> str:
    if not math.isfinite(price):
        return "PRICE_UNRESOLVED"
    if price < 180:
        return "UNDER_180"
    if price < 250:
        return "180_TO_249"
    if price < 350:
        return "250_TO_349"
    if price < 500:
        return "350_TO_499"
    return "500_PLUS"


def release_class(name: str) -> str:
    value = name.lower()
    if "universes beyond" in value or any(x in value for x in ["final fantasy", "doctor who", "fallout", "assassin", "spider-man", "avatar", "turtles"]):
        return "UNIVERSES_BEYOND"
    if "masters" in value or "double masters" in value:
        return "MASTERS_PREMIUM"
    if "remastered" in value:
        return "REMASTERED"
    if "special edition" in value:
        return "SPECIAL_EDITION"
    return "STANDARD_OR_SUPPLEMENTAL"


def available_numeric(row: pd.Series, aliases: list[str]) -> float:
    return num(first_value(row, aliases))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    master = read_csv(ROOT / cfg["inputs"]["product_master"])
    features = read_csv(ROOT / cfg["inputs"]["historical_feature_panel"])
    monthly = read_csv(ROOT / cfg["inputs"]["monthly_price_panel"])
    forecast_parts = [read_csv(ROOT / p) for p in cfg["inputs"].get("forecast_candidates", [])]
    forecasts = pd.concat([x for x in forecast_parts if not x.empty], ignore_index=True) if any(not x.empty for x in forecast_parts) else pd.DataFrame()

    if master.empty:
        failures.append("product_master_missing_or_empty")
    name_col = choose(master, ["product_name", "name", "canonical_product_name"])
    key_col = choose(master, ["product_key", "tcgplayer_product_id", "product_id"])
    release_col = choose(master, ["release_date", "set_release_date"])
    price_col = choose(master, ["market_price", "current_market_price", "price"])
    if name_col is None:
        failures.append("product_name_unmapped")

    universe = pd.DataFrame()
    if name_col:
        collector_mask = master[name_col].astype(str).str.contains("Collector Booster", case=False, na=False)
        universe = master.loc[collector_mask].copy()
        universe["normalized_name"] = universe[name_col].map(norm)
        universe = universe.sort_values(name_col).drop_duplicates("normalized_name")
    if universe.empty:
        failures.append("collector_universe_empty")

    for frame in [features, monthly, forecasts]:
        if not frame.empty:
            ncol = choose(frame, ["product_name", "name", "canonical_product_name"])
            frame["normalized_name"] = frame[ncol].map(norm) if ncol else ""

    output_rows: list[dict[str, object]] = []
    comp_rows: list[dict[str, object]] = []
    as_of = pd.Timestamp.now(tz="UTC").tz_convert(None).normalize()

    for _, product in universe.iterrows():
        pname = str(product[name_col])
        identity = product["normalized_name"]
        pkey = str(product[key_col]) if key_col and pd.notna(product[key_col]) else identity
        release = pd.to_datetime(product[release_col], errors="coerce") if release_col else pd.NaT
        frows = features.loc[features.get("normalized_name", pd.Series(dtype=str)).eq(identity)].copy() if not features.empty else pd.DataFrame()
        mrows = monthly.loc[monthly.get("normalized_name", pd.Series(dtype=str)).eq(identity)].copy() if not monthly.empty else pd.DataFrame()
        prows = forecasts.loc[forecasts.get("normalized_name", pd.Series(dtype=str)).eq(identity)].copy() if not forecasts.empty else pd.DataFrame()

        if pd.isna(release) and not frows.empty and "release_date" in frows:
            release_values = pd.to_datetime(frows["release_date"], errors="coerce").dropna()
            release = release_values.iloc[-1] if not release_values.empty else pd.NaT
        age = ((as_of.year - release.year) * 12 + as_of.month - release.month) if pd.notna(release) else np.nan
        band = age_band(float(age) if pd.notna(age) else np.nan)

        latest_feature = frows.sort_values("decision_cutoff").iloc[-1] if not frows.empty and "decision_cutoff" in frows else (frows.iloc[-1] if not frows.empty else pd.Series(dtype=object))
        current_price = num(product[price_col]) if price_col else np.nan
        if not math.isfinite(current_price) and not mrows.empty and "market_price" in mrows:
            current_price = num(pd.to_numeric(mrows["market_price"], errors="coerce").dropna().iloc[-1]) if pd.to_numeric(mrows["market_price"], errors="coerce").notna().any() else np.nan
        history_count = int(len(mrows)) if not mrows.empty else int(num(first_value(latest_feature, ["history_observation_count"], 0)) or 0)

        signal90 = np.nan
        signal180 = np.nan
        if not prows.empty:
            horizon_col = choose(prows, ["horizon_days", "forecast_horizon_days"])
            forecast_col = choose(prows, ["forecast_return", "point_forecast_return", "forecast_return_365_equivalent", "predicted_return", "shadow_forecast_return"])
            if horizon_col and forecast_col:
                h = pd.to_numeric(prows[horizon_col], errors="coerce")
                vals = pd.to_numeric(prows[forecast_col], errors="coerce")
                if (h == 90).any():
                    signal90 = num(vals[h == 90].dropna().iloc[-1]) if vals[h == 90].notna().any() else np.nan
                if (h == 180).any():
                    signal180 = num(vals[h == 180].dropna().iloc[-1]) if vals[h == 180].notna().any() else np.nan

        own3 = available_numeric(latest_feature, ["return_3_month"])
        own6 = available_numeric(latest_feature, ["return_6_month"])
        own12 = available_numeric(latest_feature, ["return_12_month"])
        vol = available_numeric(latest_feature, ["trailing_12_month_volatility"])
        drawdown = available_numeric(latest_feature, ["maximum_12_month_drawdown"])

        candidates = features.copy() if not features.empty else pd.DataFrame()
        if not candidates.empty:
            candidates = candidates[candidates["normalized_name"] != identity].copy()
            candidates["candidate_age"] = pd.to_numeric(candidates.get("product_age_months"), errors="coerce")
            candidates["candidate_price"] = pd.to_numeric(candidates.get("market_price_at_cutoff"), errors="coerce")
            if math.isfinite(age):
                candidates = candidates[(candidates["candidate_age"] - age).abs() <= 6]
            if math.isfinite(current_price):
                candidates = candidates[(candidates["candidate_price"] / current_price).between(0.5, 2.0, inclusive="both")]
            candidates["peer_signal"] = pd.to_numeric(candidates.get("return_12_month"), errors="coerce")
            candidates = candidates.dropna(subset=["peer_signal"]).sort_values("decision_cutoff").drop_duplicates("normalized_name", keep="last")
            candidates["peer_release_class"] = candidates["product_name"].astype(str).map(release_class)
            same_class = candidates[candidates["peer_release_class"] == release_class(pname)]
            if len(same_class) >= 3:
                candidates = same_class
            candidates = candidates.head(8)
        comp_count = int(len(candidates))
        peer_signal = float(candidates["peer_signal"].median()) if comp_count else np.nan
        comp_names = "|".join(candidates["product_name"].astype(str).tolist()) if comp_count else NA
        for rank, (_, peer) in enumerate(candidates.iterrows(), start=1):
            comp_rows.append({"target_product": pname, "comparable_rank": rank, "comparable_product": peer["product_name"], "age_difference_months": abs(num(peer.get("candidate_age")) - num(age)), "price_ratio": num(peer.get("candidate_price")) / current_price if math.isfinite(current_price) and current_price > 0 else NA, "peer_signal_at_cutoff": num(peer.get("peer_signal")), "future_information_used": False})

        bridge_values = [x for x in [signal90, signal180, own3, own6, own12, peer_signal] if math.isfinite(x)]
        bridge = float(np.median(bridge_values)) if bridge_values else np.nan
        supply_fields = ["listing_count", "active_listing_count", "sales_count", "sold_count", "inventory_score", "supply_score"]
        demand_fields = ["demand_score", "demand_durability_score", "franchise_strength", "franchise_score"]
        supply_available = any(str(first_value(product, [x], "")).strip() not in {"", "nan", "None"} for x in supply_fields)
        demand_available = any(str(first_value(product, [x], "")).strip() not in {"", "nan", "None"} for x in demand_fields)

        validated_bridge = math.isfinite(signal90) or math.isfinite(signal180)
        if history_count >= 9 and comp_count >= 3 and validated_bridge and math.isfinite(bridge):
            status = "PROVISIONAL_365"
            route = "EARLY_LIFECYCLE_COMPARABLE_BRIDGE"
            uncertainty = 1.75 if band in {"LAUNCH_PRICE_DISCOVERY", "INITIAL_SUPPLY_ABSORPTION"} else 1.5
            base = bridge
            width = max(0.30, abs(base) * uncertainty, (vol if math.isfinite(vol) else 0.20) * uncertainty)
            confidence = "LOW"
            evidence = "C_PROXY_PRIOR"
            blocked = NAP
            next_req = "MATURE_ANOTHER_365_DAY_OUTCOME_AND_REVALIDATE_RANKING"
        elif history_count >= 3 and (comp_count >= 1 or len(bridge_values) >= 2):
            status = "SCENARIO_ELIGIBLE"
            route = "EARLY_LIFECYCLE_SCENARIO"
            uncertainty = 2.0 if band in {"LAUNCH_PRICE_DISCOVERY", "INITIAL_SUPPLY_ABSORPTION"} else 1.75
            base = bridge if math.isfinite(bridge) else 0.0
            width = max(0.40, abs(base) * uncertainty, (vol if math.isfinite(vol) else 0.25) * uncertainty)
            confidence = "VERY_LOW"
            evidence = "D_EXPERIMENTAL"
            blocked = "POINT_FORECAST_NOT_QUALIFIED"
            next_req = "ADD_VALIDATED_90_OR_180_SIGNAL_AND_AT_LEAST_THREE_AGE_ALIGNED_COMPARABLES"
        else:
            status = "BLOCKED"
            route = "NO_RELIABLE_EARLY_LIFECYCLE_EVIDENCE"
            uncertainty = 2.5
            base = bridge if math.isfinite(bridge) else 0.0
            width = max(0.50, abs(base) * uncertainty)
            confidence = "UNRATED"
            evidence = "BLOCKED"
            blocked = "INSUFFICIENT_HISTORY_COMPARABLES_OR_BRIDGE_SIGNAL"
            next_req = "COLLECT_AT_LEAST_THREE_MONTHLY_OBSERVATIONS_OR_ONE_VALIDATED_NEAR_TERM_FORECAST"

        bear = base - width
        bull = base + width
        point = base if status == "PROVISIONAL_365" else NA
        next_trigger = "NEXT_MONTHLY_OBSERVATION_OR_LIFECYCLE_BAND_CHANGE"
        lineage = sorted(set(([str(x) for x in mrows.get("source_lineage", pd.Series(dtype=str)).dropna().unique()] if not mrows.empty else []) + ([str(x) for x in frows.get("source_lineage", pd.Series(dtype=str)).dropna().unique()] if not frows.empty else [])))

        output_rows.append({
            "product_key": pkey, "product_name": pname, "release_date": release.date().isoformat() if pd.notna(release) else NA,
            "product_age_months": int(age) if pd.notna(age) else NA, "early_lifecycle_band": band,
            "forecast_status": status, "forecast_route": route, "forecast_center_365": point,
            "bear_return_365": bear, "base_return_365": base, "bull_return_365": bull,
            "forecast_lower_365": bear, "forecast_upper_365": bull,
            "forecast_90_signal": signal90 if math.isfinite(signal90) else NA,
            "forecast_180_signal": signal180 if math.isfinite(signal180) else NA,
            "age_aligned_comparable_count": comp_count, "age_aligned_comparable_group": comp_names,
            "release_class": release_class(pname), "price_band": price_band(current_price),
            "supply_inventory_evidence": "AVAILABLE" if supply_available else NA,
            "franchise_demand_evidence": "AVAILABLE" if demand_available else NA,
            "evidence_grade": evidence, "confidence_tier": confidence, "uncertainty_multiplier": uncertainty,
            "blocked_reason": blocked, "next_evidence_requirement": next_req, "next_review_trigger": next_trigger,
            "source_lineage": "|".join(lineage) if lineage else "PRODUCT_MASTER_ONLY",
            "future_information_used": False,
        })

    output = pd.DataFrame(output_rows)
    comparables = pd.DataFrame(comp_rows)
    required = cfg["required_output_fields"]
    output = output.reindex(columns=required)
    output = output.replace([np.inf, -np.inf], np.nan).fillna(NA)
    output = output.applymap(lambda x: NA if isinstance(x, str) and not x.strip() else x)
    output.to_csv(OUT / "collector_early_lifecycle_complete_universe.csv", index=False)
    comparables.to_csv(OUT / "collector_early_lifecycle_age_aligned_comparables.csv", index=False)

    if len(output) != len(universe):
        failures.append("complete_universe_row_count_mismatch")
    if output["product_name"].duplicated().any():
        failures.append("duplicate_products_in_output")
    if output.isna().any().any() or output.astype(str).apply(lambda s: s.str.strip().eq("").any()).any():
        failures.append("missing_output_values_detected")
    if not set(output["forecast_status"]).issubset({"PROVISIONAL_365", "SCENARIO_ELIGIBLE", "BLOCKED"}):
        failures.append("invalid_status")
    if ((output["forecast_status"] != "PROVISIONAL_365") & (output["forecast_center_365"].astype(str) != NA)).any():
        failures.append("point_forecast_exposed_without_provisional_status")
    if output["future_information_used"].astype(str).str.lower().eq("true").any():
        failures.append("future_information_detected")

    result = {
        "audit_name": cfg["program_name"], "audit_version": cfg["program_version"],
        "status": "PASS" if not failures else "FAIL", "complete_universe_product_count": int(len(universe)),
        "output_product_count": int(len(output)), "missing_product_count": int(max(0, len(universe) - len(output))),
        "provisional_365_count": int((output["forecast_status"] == "PROVISIONAL_365").sum()) if not output.empty else 0,
        "scenario_eligible_count": int((output["forecast_status"] == "SCENARIO_ELIGIBLE").sum()) if not output.empty else 0,
        "blocked_count": int((output["forecast_status"] == "BLOCKED").sum()) if not output.empty else 0,
        "all_products_have_status": bool(not output.empty and output["forecast_status"].notna().all()),
        "all_required_fields_populated": bool(not output.empty and not output.isna().any().any()),
        "future_information_used": False, "shadow_only": True,
        "early_lifecycle_shadow_implementation_authorized": False, "provisional_365_authorized": False,
        "scenario_output_authorized": False, "production_projection_authorized": False,
        "purchase_recommendation_authorized": False, "automatic_model_update_allowed": False,
        "technical_freeze_authorized": False, "uip_acceptance_authorized": False,
        "failure_count": len(failures), "failures": failures,
    }
    (OUT / "collector_early_lifecycle_forecast_engine_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
