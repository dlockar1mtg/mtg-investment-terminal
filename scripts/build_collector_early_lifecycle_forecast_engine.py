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
    columns = {str(column).lower(): str(column) for column in df.columns}
    return next((columns[alias.lower()] for alias in aliases if alias.lower() in columns), None)


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
    columns = {str(column).lower(): column for column in row.index}
    for alias in aliases:
        column = columns.get(alias.lower())
        if column is None:
            continue
        value = row[column]
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
    crossover_tokens = ["final fantasy", "doctor who", "fallout", "assassin", "spider-man", "avatar", "turtles"]
    if "universes beyond" in value or any(token in value for token in crossover_tokens):
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


def prepare_peer_pool(features: pd.DataFrame) -> pd.DataFrame:
    if features.empty:
        return pd.DataFrame()
    pool = features.copy()
    pool["candidate_age"] = pd.to_numeric(pool.get("product_age_months"), errors="coerce")
    pool["candidate_price"] = pd.to_numeric(pool.get("market_price_at_cutoff"), errors="coerce")
    pool["peer_signal"] = pd.to_numeric(pool.get("return_12_month"), errors="coerce")
    pool = pool.dropna(subset=["peer_signal"])
    if "decision_cutoff" in pool.columns:
        pool = pool.sort_values("decision_cutoff")
    pool = pool.drop_duplicates("normalized_name", keep="last")
    pool["peer_release_class"] = pool["product_name"].astype(str).map(release_class)
    pool["peer_price_band"] = pool["candidate_price"].map(price_band)
    return pool


def select_peers(
    pool: pd.DataFrame,
    identity: str,
    target_age: float,
    target_price: float,
    target_class: str,
    target_price_band: str,
) -> tuple[pd.DataFrame, str, str]:
    eligible = pool[pool["normalized_name"] != identity].copy()
    if eligible.empty:
        return eligible, "UNIVERSAL_COLLECTOR_PRIOR", "PRIOR_ONLY"

    age_diff = (eligible["candidate_age"] - target_age).abs() if math.isfinite(target_age) else pd.Series(np.inf, index=eligible.index)
    price_ratio = eligible["candidate_price"] / target_price if math.isfinite(target_price) and target_price > 0 else pd.Series(np.nan, index=eligible.index)
    same_class = eligible["peer_release_class"].eq(target_class)
    same_band = eligible["peer_price_band"].eq(target_price_band)
    price_near = price_ratio.between(0.5, 2.0, inclusive="both")

    tiers: list[tuple[str, pd.Series, str]] = [
        ("AGE_CLASS_PRICE", age_diff.le(6) & same_class & price_near, "STRONG"),
        ("AGE_CLASS", age_diff.le(9) & same_class, "GOOD"),
        ("AGE_PRICE", age_diff.le(9) & price_near, "GOOD"),
        ("RELEASE_CLASS", same_class, "MODERATE"),
        ("PRICE_BAND", same_band, "MODERATE"),
        ("AGE_ALIGNED_ANY_CLASS", age_diff.le(18), "WEAK"),
        ("UNIVERSAL_COLLECTOR_COHORT", pd.Series(True, index=eligible.index), "VERY_WEAK"),
    ]

    for tier, mask, quality in tiers:
        selected = eligible.loc[mask].copy()
        if selected.empty:
            continue
        selected["age_difference_months"] = age_diff.loc[selected.index]
        selected["price_ratio"] = price_ratio.loc[selected.index]
        selected["match_distance"] = (
            selected["age_difference_months"].fillna(24.0) / 12.0
            + (selected["price_ratio"].fillna(1.0) - 1.0).abs()
            + (~selected["peer_release_class"].eq(target_class)).astype(float) * 0.5
        )
        return selected.sort_values(["match_distance", "product_name"]).head(8), tier, quality

    return eligible.head(8), "UNIVERSAL_COLLECTOR_COHORT", "VERY_WEAK"


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
    forecast_parts = [read_csv(ROOT / path) for path in cfg["inputs"].get("forecast_candidates", [])]
    nonempty_forecasts = [frame for frame in forecast_parts if not frame.empty]
    forecasts = pd.concat(nonempty_forecasts, ignore_index=True) if nonempty_forecasts else pd.DataFrame()

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
        if frame.empty:
            continue
        frame_name_col = choose(frame, ["product_name", "name", "canonical_product_name"])
        frame["normalized_name"] = frame[frame_name_col].map(norm) if frame_name_col else ""

    peer_pool = prepare_peer_pool(features)
    universal_prior = float(peer_pool["peer_signal"].median()) if not peer_pool.empty else np.nan
    if not math.isfinite(universal_prior):
        failures.append("universal_collector_prior_unavailable")
        universal_prior = 0.0

    output_rows: list[dict[str, object]] = []
    comparable_rows: list[dict[str, object]] = []
    as_of = pd.Timestamp.now(tz="UTC").tz_convert(None).normalize()

    for _, product in universe.iterrows():
        product_name = str(product[name_col])
        identity = product["normalized_name"]
        product_key = str(product[key_col]) if key_col and pd.notna(product[key_col]) else identity
        release = pd.to_datetime(product[release_col], errors="coerce") if release_col else pd.NaT

        feature_rows = features.loc[features.get("normalized_name", pd.Series(dtype=str)).eq(identity)].copy() if not features.empty else pd.DataFrame()
        monthly_rows = monthly.loc[monthly.get("normalized_name", pd.Series(dtype=str)).eq(identity)].copy() if not monthly.empty else pd.DataFrame()
        forecast_rows = forecasts.loc[forecasts.get("normalized_name", pd.Series(dtype=str)).eq(identity)].copy() if not forecasts.empty else pd.DataFrame()

        if pd.isna(release) and not feature_rows.empty and "release_date" in feature_rows.columns:
            release_values = pd.to_datetime(feature_rows["release_date"], errors="coerce").dropna()
            release = release_values.iloc[-1] if not release_values.empty else pd.NaT

        age = ((as_of.year - release.year) * 12 + as_of.month - release.month) if pd.notna(release) else np.nan
        band = age_band(float(age) if pd.notna(age) else np.nan)
        current_class = release_class(product_name)

        if not feature_rows.empty and "decision_cutoff" in feature_rows.columns:
            latest_feature = feature_rows.sort_values("decision_cutoff").iloc[-1]
        elif not feature_rows.empty:
            latest_feature = feature_rows.iloc[-1]
        else:
            latest_feature = pd.Series(dtype=object)

        current_price = num(product[price_col]) if price_col else np.nan
        if not math.isfinite(current_price) and not monthly_rows.empty and "market_price" in monthly_rows.columns:
            prices = pd.to_numeric(monthly_rows["market_price"], errors="coerce").dropna()
            current_price = num(prices.iloc[-1]) if not prices.empty else np.nan
        current_price_band = price_band(current_price)
        history_count = len(monthly_rows) if not monthly_rows.empty else int(num(first_value(latest_feature, ["history_observation_count"], 0)) or 0)

        signal90 = np.nan
        signal180 = np.nan
        if not forecast_rows.empty:
            horizon_col = choose(forecast_rows, ["horizon_days", "forecast_horizon_days"])
            forecast_col = choose(forecast_rows, ["forecast_return", "point_forecast_return", "forecast_return_365_equivalent", "predicted_return", "shadow_forecast_return"])
            if horizon_col and forecast_col:
                horizons = pd.to_numeric(forecast_rows[horizon_col], errors="coerce")
                values = pd.to_numeric(forecast_rows[forecast_col], errors="coerce")
                values90 = values[horizons.eq(90)].dropna()
                values180 = values[horizons.eq(180)].dropna()
                signal90 = num(values90.iloc[-1]) if not values90.empty else np.nan
                signal180 = num(values180.iloc[-1]) if not values180.empty else np.nan

        own3 = available_numeric(latest_feature, ["return_3_month"])
        own6 = available_numeric(latest_feature, ["return_6_month"])
        own12 = available_numeric(latest_feature, ["return_12_month"])
        volatility = available_numeric(latest_feature, ["trailing_12_month_volatility"])

        peers, match_tier, match_quality = select_peers(
            peer_pool,
            identity,
            float(age) if pd.notna(age) else np.nan,
            current_price,
            current_class,
            current_price_band,
        )
        comparable_count = len(peers)
        peer_signal = float(peers["peer_signal"].median()) if comparable_count else universal_prior
        comparable_group = "|".join(peers["product_name"].astype(str).tolist()) if comparable_count else "UNIVERSAL_COLLECTOR_PRIOR"

        if comparable_count:
            inverse_distance = 1.0 / (1.0 + peers["match_distance"].fillna(1.0))
            weights = inverse_distance / inverse_distance.sum()
            for rank, ((_, peer), weight) in enumerate(zip(peers.iterrows(), weights), start=1):
                comparable_rows.append({
                    "target_product": product_name,
                    "comparable_rank": rank,
                    "comparable_product": peer["product_name"],
                    "match_tier": match_tier,
                    "match_quality": match_quality,
                    "age_difference_months": num(peer.get("age_difference_months")),
                    "price_ratio": num(peer.get("price_ratio")),
                    "comparable_weight": float(weight),
                    "peer_signal_at_cutoff": num(peer.get("peer_signal")),
                    "future_information_used": False,
                })
        else:
            comparable_rows.append({
                "target_product": product_name,
                "comparable_rank": 1,
                "comparable_product": "UNIVERSAL_COLLECTOR_PRIOR",
                "match_tier": "UNIVERSAL_COLLECTOR_PRIOR",
                "match_quality": "PRIOR_ONLY",
                "age_difference_months": NA,
                "price_ratio": NA,
                "comparable_weight": 1.0,
                "peer_signal_at_cutoff": universal_prior,
                "future_information_used": False,
            })

        available_signals = [value for value in [signal90, signal180, own3, own6, own12, peer_signal] if math.isfinite(value)]
        base = float(np.median(available_signals)) if available_signals else universal_prior
        validated_bridge = math.isfinite(signal90) or math.isfinite(signal180)

        if history_count >= 9 and comparable_count >= 3 and validated_bridge:
            status = "PROVISIONAL_365"
            route = "EARLY_LIFECYCLE_COMPARABLE_BRIDGE"
            uncertainty = 1.75 if band in {"LAUNCH_PRICE_DISCOVERY", "INITIAL_SUPPLY_ABSORPTION"} else 1.5
            confidence = "LOW"
            evidence = "C_PROXY_PRIOR"
            forecast_basis = "OWN_HISTORY_PLUS_VALIDATED_NEAR_TERM_PLUS_MATCHED_PEERS"
            next_requirement = "MATURE_ANOTHER_365_DAY_OUTCOME_AND_REVALIDATE_RANKING"
        elif history_count >= 3 and (comparable_count >= 1 or len(available_signals) >= 2):
            status = "SCENARIO_ELIGIBLE"
            route = "COMPARABLE_SUPPORTED_SCENARIO_AND_POINT"
            uncertainty = 2.0 if band in {"LAUNCH_PRICE_DISCOVERY", "INITIAL_SUPPLY_ABSORPTION"} else 1.75
            confidence = "VERY_LOW"
            evidence = "D_EXPERIMENTAL"
            forecast_basis = "AVAILABLE_PRODUCT_SIGNALS_PLUS_MATCHED_PEERS"
            next_requirement = "ADD_VALIDATED_90_OR_180_SIGNAL_AND_AT_LEAST_THREE_STRONGER_COMPARABLES"
        else:
            status = "UNIVERSAL_MATCHED_365"
            route = match_tier
            uncertainty = 3.0 if match_quality in {"VERY_WEAK", "PRIOR_ONLY"} else 2.5
            confidence = "VERY_LOW"
            evidence = "D_EXPERIMENTAL"
            forecast_basis = "BROAD_MATCHED_COHORT" if comparable_count else "UNIVERSAL_COLLECTOR_PRIOR"
            next_requirement = "REPLACE_BROAD_PRIOR_WITH_PRODUCT_HISTORY_NEAR_TERM_SIGNAL_OR_STRONGER_MATCH"

        width = max(0.40, abs(base) * uncertainty, (volatility if math.isfinite(volatility) else 0.25) * uncertainty)
        bear = base - width
        bull = base + width

        supply_fields = ["listing_count", "active_listing_count", "sales_count", "sold_count", "inventory_score", "supply_score"]
        demand_fields = ["demand_score", "demand_durability_score", "franchise_strength", "franchise_score"]
        supply_available = any(str(first_value(product, [field], "")).strip() not in {"", "nan", "None"} for field in supply_fields)
        demand_available = any(str(first_value(product, [field], "")).strip() not in {"", "nan", "None"} for field in demand_fields)

        lineage_values = []
        if not monthly_rows.empty and "source_lineage" in monthly_rows.columns:
            lineage_values.extend(str(value) for value in monthly_rows["source_lineage"].dropna().unique())
        if not feature_rows.empty and "source_lineage" in feature_rows.columns:
            lineage_values.extend(str(value) for value in feature_rows["source_lineage"].dropna().unique())
        lineage = "|".join(sorted(set(lineage_values))) if lineage_values else "PRODUCT_MASTER_PLUS_MATCHED_COHORT"

        output_rows.append({
            "product_key": product_key,
            "product_name": product_name,
            "release_date": release.date().isoformat() if pd.notna(release) else NA,
            "product_age_months": int(age) if pd.notna(age) else NA,
            "early_lifecycle_band": band,
            "forecast_status": status,
            "forecast_route": route,
            "forecast_center_365": base,
            "bear_return_365": bear,
            "base_return_365": base,
            "bull_return_365": bull,
            "forecast_lower_365": bear,
            "forecast_upper_365": bull,
            "forecast_90_signal": signal90 if math.isfinite(signal90) else NA,
            "forecast_180_signal": signal180 if math.isfinite(signal180) else NA,
            "age_aligned_comparable_count": comparable_count,
            "age_aligned_comparable_group": comparable_group,
            "match_tier": match_tier,
            "match_quality": match_quality,
            "forecast_basis": forecast_basis,
            "release_class": current_class,
            "price_band": current_price_band,
            "supply_inventory_evidence": "AVAILABLE" if supply_available else NA,
            "franchise_demand_evidence": "AVAILABLE" if demand_available else NA,
            "evidence_grade": evidence,
            "confidence_tier": confidence,
            "uncertainty_multiplier": uncertainty,
            "blocked_reason": NAP,
            "next_evidence_requirement": next_requirement,
            "next_review_trigger": "NEXT_MONTHLY_OBSERVATION_OR_LIFECYCLE_BAND_CHANGE",
            "source_lineage": lineage,
            "future_information_used": False,
        })

    output = pd.DataFrame(output_rows).reindex(columns=cfg["required_output_fields"])
    comparables = pd.DataFrame(comparable_rows)
    output = output.replace([np.inf, -np.inf], np.nan).fillna(NA)
    output = output.apply(lambda column: column.map(lambda value: NA if isinstance(value, str) and not value.strip() else value))

    output.to_csv(OUT / "collector_early_lifecycle_complete_universe.csv", index=False)
    comparables.to_csv(OUT / "collector_early_lifecycle_age_aligned_comparables.csv", index=False)

    blank_values = output.astype(str).apply(lambda column: column.str.strip().eq("")).to_numpy().any()
    if len(output) != len(universe):
        failures.append("complete_universe_row_count_mismatch")
    if output["product_name"].duplicated().any():
        failures.append("duplicate_products_in_output")
    if output.isna().to_numpy().any() or blank_values:
        failures.append("missing_output_values_detected")
    allowed_statuses = {"PROVISIONAL_365", "SCENARIO_ELIGIBLE", "UNIVERSAL_MATCHED_365"}
    if not set(output["forecast_status"]).issubset(allowed_statuses):
        failures.append("invalid_status")
    if output["forecast_status"].eq("BLOCKED").any():
        failures.append("blocked_status_detected")
    if output["forecast_center_365"].astype(str).isin(["", NA]).any():
        failures.append("point_forecast_missing")
    if output["age_aligned_comparable_group"].astype(str).isin(["", NA]).any():
        failures.append("match_or_prior_missing")
    if output["future_information_used"].astype(str).str.lower().eq("true").any():
        failures.append("future_information_detected")

    result = {
        "audit_name": cfg["program_name"],
        "audit_version": cfg["program_version"],
        "status": "PASS" if not failures else "FAIL",
        "complete_universe_product_count": int(len(universe)),
        "output_product_count": int(len(output)),
        "missing_product_count": int(max(0, len(universe) - len(output))),
        "provisional_365_count": int(output["forecast_status"].eq("PROVISIONAL_365").sum()) if not output.empty else 0,
        "scenario_eligible_count": int(output["forecast_status"].eq("SCENARIO_ELIGIBLE").sum()) if not output.empty else 0,
        "universal_matched_365_count": int(output["forecast_status"].eq("UNIVERSAL_MATCHED_365").sum()) if not output.empty else 0,
        "blocked_count": 0,
        "all_products_have_status": bool(not output.empty and output["forecast_status"].notna().all()),
        "all_products_have_point_forecast": bool(not output.empty and not output["forecast_center_365"].astype(str).isin(["", NA]).any()),
        "all_products_have_match_or_prior": bool(not output.empty and not output["age_aligned_comparable_group"].astype(str).isin(["", NA]).any()),
        "all_required_fields_populated": bool(not output.empty and not output.isna().to_numpy().any() and not blank_values),
        "future_information_used": False,
        "shadow_only": True,
        "early_lifecycle_shadow_implementation_authorized": False,
        "provisional_365_authorized": False,
        "scenario_output_authorized": False,
        "universal_matched_365_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "technical_freeze_authorized": False,
        "uip_acceptance_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
    }
    (OUT / "collector_early_lifecycle_forecast_engine_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
