from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_horizon_specific_tournament_architecture_contract_v1.json"
PREMODEL = ROOT / "data/governance/permanence/certification/collector_v1_final_premodel_user_exclusion_resolution"
ROUTING = PREMODEL / "collector_final_method_routing.csv"
LIFECYCLE = ROOT / "data/governance/permanence/certification/collector_v1_wizards_release_date_authority/collector_lifecycle_panel_final_candidate.csv"
RELEASES = ROOT / "data/governance/permanence/certification/collector_v1_wizards_release_date_authority/collector_wizards_release_date_authority.csv"
PRICES = PREMODEL / "collector_final_current_price_authority.csv"
SUMMARY_IN = PREMODEL / "collector_final_premodel_user_exclusion_resolution_summary.json"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_horizon_specific_tournament_architecture"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def clean(value: Any) -> str:
    return str(value or "").strip()


def truth(value: Any) -> bool:
    return clean(value).lower() in {"true", "1", "yes"}


def number(value: Any) -> float | None:
    try:
        return float(clean(value).replace("$", "").replace(",", ""))
    except ValueError:
        return None


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    upstream = json.loads(SUMMARY_IN.read_text(encoding="utf-8"))
    failures: list[str] = []
    if upstream.get("status") != "PASS_COLLECTOR_FINAL_PREMODEL_USER_EXCLUSION_RESOLUTION":
        failures.append("FINAL_PREMODEL_NOT_CERTIFIED")

    routing = read_csv(ROUTING)
    releases = {clean(r.get("canonical_product_id")): r for r in read_csv(RELEASES)}
    prices = {clean(r.get("canonical_product_id")): r for r in read_csv(PRICES)}
    lifecycle = read_csv(LIFECYCLE)
    latest_band: dict[str, str] = {}
    for row in sorted(lifecycle, key=lambda r: clean(r.get("observation_date"))):
        latest_band[clean(row.get("canonical_product_id"))] = clean(row.get("lifecycle_band"))

    authorized = [r for r in routing if truth(r.get("forecast_output_allowed"))]
    if len(routing) != contract["required_total_products"]:
        failures.append("TOTAL_PRODUCT_COUNT_MISMATCH")
    if len(authorized) != contract["required_authorized_products"]:
        failures.append("AUTHORIZED_PRODUCT_COUNT_MISMATCH")

    tournaments: list[dict[str, Any]] = []
    models: list[dict[str, Any]] = []
    early_life: list[dict[str, Any]] = []
    overlays: list[dict[str, Any]] = []
    today = date(2026, 8, 1)
    early = contract["early_life_policy"]

    for horizon in contract["forecast_horizons"]:
        hid = horizon["horizon_id"]
        for route, families in contract["route_model_families"].items():
            route_products = [r for r in authorized if clean(r.get("final_forecast_method")) == route]
            tournaments.append({
                "tournament_id": f"COLLECTOR-{hid}-{route}",
                "horizon_id": hid,
                "horizon_days": horizon["days"],
                "horizon_label": horizon["label"],
                "route": route,
                "eligible_products": len(route_products),
                "independent_winner_required": True,
                "rolling_origin_required": True,
                "production_forecast_authorized": False,
                "purchase_authorized": False,
            })
            for family in families:
                models.append({
                    "tournament_id": f"COLLECTOR-{hid}-{route}",
                    "horizon_id": hid,
                    "route": route,
                    "model_family": family,
                    "must_compete_at_this_horizon": True,
                    "baseline_model": family in contract["required_baselines"],
                    "current_supply_demand_allowed_in_fit": False,
                    "uncertainty_required": True,
                })

    for row in routing:
        cid = clean(row.get("canonical_product_id"))
        price = number(prices.get(cid, {}).get("current_price"))
        release_text = clean(releases.get(cid, {}).get("official_release_date")) or clean(releases.get(cid, {}).get("release_date"))
        try:
            age_days = (today - date.fromisoformat(release_text[:10])).days
        except ValueError:
            age_days = None
        band = latest_band.get(cid, "")
        is_early = band in early["eligible_lifecycle_bands"] or (age_days is not None and age_days <= early["early_life_max_age_days"])
        in_target = price is not None and early["entry_price_target_low"] <= price <= early["entry_price_target_high"]
        late_warning = price is not None and price >= early["late_recognition_warning_price"]
        early_life.append({
            "canonical_product_id": cid,
            "product_name": clean(row.get("product_name")),
            "release_date": release_text,
            "age_days_at_snapshot": age_days if age_days is not None else "",
            "current_lifecycle_band": band,
            "current_price": price if price is not None else "",
            "early_life_identified": is_early,
            "price_in_350_400_target_zone": in_target,
            "late_recognition_warning": late_warning,
            "early_entry_model_required": is_early and truth(row.get("forecast_output_allowed")),
            "must_score_before_600": is_early and truth(row.get("forecast_output_allowed")),
            "forecast_output_allowed": truth(row.get("forecast_output_allowed")),
        })

    for feature in contract["current_overlay_policy"]["allowed_overlays"]:
        overlays.append({
            "overlay_feature": feature,
            "historical_backtest_allowed": False,
            "historical_model_fit_allowed": False,
            "production_post_forecast_allowed": True,
            "may_change_point_forecast": contract["current_overlay_policy"]["may_change_point_forecast"],
            "may_change_ranking_and_confidence": contract["current_overlay_policy"]["may_change_ranking_and_confidence"],
            "purchase_authorization_separate": True,
        })

    expected_tournaments = len(contract["forecast_horizons"]) * len(contract["route_model_families"])
    if len(tournaments) != expected_tournaments:
        failures.append("TOURNAMENT_COUNT_MISMATCH")
    if any(r["current_supply_demand_allowed_in_fit"] for r in models):
        failures.append("CURRENT_OVERLAY_LEAKAGE")
    if any(not r["independent_winner_required"] for r in tournaments):
        failures.append("HORIZON_INDEPENDENCE_VIOLATION")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_horizon_tournament_registry.csv", tournaments)
    write_csv(OUTPUT / "collector_horizon_model_family_registry.csv", models)
    write_csv(OUTPUT / "collector_early_life_entry_registry.csv", early_life)
    write_csv(OUTPUT / "collector_current_supply_demand_overlay_registry.csv", overlays)

    summary = {
        "block_name": contract["contract_name"],
        "block_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "forecast_horizons": len(contract["forecast_horizons"]),
        "route_specific_tournaments": len(tournaments),
        "authorized_products": len(authorized),
        "early_life_products_identified": sum(bool(r["early_life_identified"]) for r in early_life),
        "early_entry_models_required": sum(bool(r["early_entry_model_required"]) for r in early_life),
        "current_overlay_features_registered": len(overlays),
        "independent_tournament_per_horizon": True,
        "current_supply_demand_backtest_prohibited": True,
        "current_supply_demand_post_forecast_overlay_authorized": True,
        "model_tournament_execution_authorized": not failures,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": contract["expected_status"] if not failures else "FAIL_COLLECTOR_HORIZON_SPECIFIC_TOURNAMENT_ARCHITECTURE",
    }
    (OUTPUT / "collector_horizon_specific_tournament_architecture_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
