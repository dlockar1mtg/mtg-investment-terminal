from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_complete_horizon_probabilistic_forecast_contract_v1.json"
PREMODEL = ROOT / "data/governance/permanence/certification/collector_v1_final_premodel_user_exclusion_resolution"
HISTORY = ROOT / "data/governance/permanence/certification/collector_v1_august1_historical_observation_ledger/collector_august1_historical_observation_ledger.csv"
CURRENT = PREMODEL / "collector_final_current_price_authority.csv"
ROUTING = PREMODEL / "collector_final_method_routing.csv"
COMPARABLES = PREMODEL / "collector_comparable_pool_certification.csv"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_complete_horizon_probabilistic_forecast"


def clean(value: Any) -> str:
    return str(value or "").strip()


def num(value: Any) -> float | None:
    text = clean(value).replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        result = float(text)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def deterministic_seed(snapshot_id: str, product_id: str, horizon: int) -> int:
    digest = hashlib.sha256(f"{snapshot_id}|{product_id}|{horizon}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False) % (2**32 - 1)


def monthly_log_returns(prices: list[float]) -> np.ndarray:
    values = np.asarray([p for p in prices if p and p > 0], dtype=float)
    if values.size < 2:
        return np.asarray([], dtype=float)
    return np.diff(np.log(values))


def winsorized(values: np.ndarray, lower_q: float, upper_q: float, floor: float, ceiling: float) -> np.ndarray:
    if values.size == 0:
        return values
    lo = float(np.quantile(values, lower_q))
    hi = float(np.quantile(values, upper_q))
    return np.clip(values, max(lo, floor), min(hi, ceiling))


def build_distribution(
    route: str,
    target_id: str,
    series: dict[str, list[float]],
    comparable_ids: list[str],
    contract: dict[str, Any],
) -> tuple[np.ndarray, str, int, int]:
    mc = contract["monte_carlo"]
    own = winsorized(
        monthly_log_returns(series.get(target_id, [])),
        mc["winsor_lower_quantile"],
        mc["winsor_upper_quantile"],
        mc["minimum_monthly_log_return"],
        mc["maximum_monthly_log_return"],
    )

    comparable_parts: list[np.ndarray] = []
    comparable_used = 0
    for comp_id in comparable_ids:
        comp = winsorized(
            monthly_log_returns(series.get(comp_id, [])),
            mc["winsor_lower_quantile"],
            mc["winsor_upper_quantile"],
            mc["minimum_monthly_log_return"],
            mc["maximum_monthly_log_return"],
        )
        if comp.size:
            comparable_parts.append(comp)
            comparable_used += 1
    comparable = np.concatenate(comparable_parts) if comparable_parts else np.asarray([], dtype=float)

    if route == "DIRECT_HISTORY_CALIBRATED":
        if own.size < 2:
            raise RuntimeError("INSUFFICIENT_OWN_HISTORY_FOR_DIRECT_CALIBRATED")
        distribution = own
        method = contract["method_families"][route]
    elif route == "DIRECT_HISTORY_LIMITED":
        if own.size == 0 and comparable.size == 0:
            raise RuntimeError("NO_PRODUCT_OR_TARGET_SPECIFIC_COMPARABLE_RETURNS")
        if own.size and comparable.size:
            own_weight = max(1, min(4, own.size))
            comp_weight = max(1, min(4, comparable.size // max(comparable_used, 1)))
            distribution = np.concatenate([
                np.repeat(own, own_weight),
                np.repeat(comparable, comp_weight),
            ])
        else:
            distribution = own if own.size else comparable
        method = contract["method_families"][route]
    elif route == "COMPARABLE_PRODUCT_ADJUSTED":
        if comparable.size == 0:
            raise RuntimeError("NO_TARGET_SPECIFIC_COMPARABLE_RETURN_DISTRIBUTION")
        distribution = comparable
        method = contract["method_families"][route]
    else:
        raise RuntimeError(f"UNSUPPORTED_ROUTE:{route}")

    distribution = winsorized(
        distribution,
        mc["winsor_lower_quantile"],
        mc["winsor_upper_quantile"],
        mc["minimum_monthly_log_return"],
        mc["maximum_monthly_log_return"],
    )
    if distribution.size == 0:
        raise RuntimeError("EMPTY_PRODUCT_SPECIFIC_RETURN_DISTRIBUTION")
    return distribution, method, int(own.size), comparable_used


def simulate(
    current_price: float,
    distribution: np.ndarray,
    horizon_days: int,
    product_id: str,
    contract: dict[str, Any],
) -> dict[str, float | int]:
    mc = contract["monte_carlo"]
    simulations = int(mc["simulations_per_product_horizon"])
    steps = max(1, int(math.ceil(horizon_days / float(mc["time_step_days"]))))
    rng = np.random.default_rng(deterministic_seed(contract["snapshot_id"], product_id, horizon_days))
    draws = rng.choice(distribution, size=(simulations, steps), replace=True)

    decay_months = float(mc["long_horizon_drift_decay_months"])
    step_index = np.arange(steps, dtype=float)
    decay = np.exp(-step_index / max(decay_months, 1.0))
    centered = draws - float(np.median(distribution))
    simulated_logs = centered + float(np.median(distribution)) * decay
    terminal = current_price * np.exp(simulated_logs.sum(axis=1))

    q10, q25, q50, q75, q90 = np.quantile(terminal, [0.10, 0.25, 0.50, 0.75, 0.90])
    expected = float(np.mean(terminal))
    return {
        "simulation_count": simulations,
        "monthly_steps": steps,
        "p10_price": float(q10),
        "p25_price": float(q25),
        "median_price": float(q50),
        "p75_price": float(q75),
        "p90_price": float(q90),
        "mean_price": expected,
        "median_expected_return": float(q50 / current_price - 1.0),
        "mean_expected_return": float(expected / current_price - 1.0),
        "probability_of_loss": float(np.mean(terminal < current_price)),
        "probability_of_50pct_gain": float(np.mean(terminal >= current_price * 1.5)),
        "probability_of_doubling": float(np.mean(terminal >= current_price * 2.0)),
    }


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    required = [CURRENT, ROUTING, HISTORY, COMPARABLES]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("MISSING_REQUIRED_INPUTS:" + ";".join(missing))

    current_rows = read_csv(CURRENT)
    routing_rows = read_csv(ROUTING)
    history_rows = read_csv(HISTORY)
    comparable_rows = read_csv(COMPARABLES)
    failures: list[str] = []

    current_by_id = {
        clean(row.get("canonical_product_id")): {
            "product_name": clean(row.get("product_name")),
            "current_price": num(row.get("current_price")),
        }
        for row in current_rows
    }
    route_by_id: dict[str, dict[str, str]] = {}
    for row in routing_rows:
        cid = clean(row.get("canonical_product_id"))
        route_by_id[cid] = {
            "route": clean(row.get("final_forecast_method")),
            "allowed": clean(row.get("forecast_output_allowed")).lower(),
            "reason": clean(row.get("final_reason_code") or row.get("blocked_reason") or row.get("final_forecast_method")),
        }

    series: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in history_rows:
        cid = clean(row.get("canonical_product_id"))
        date = clean(row.get("observation_date"))
        price = num(row.get("market_price") or row.get("selected_price") or row.get("price"))
        if cid and date and price and price > 0:
            series[cid].append((date, price))
    price_series: dict[str, list[float]] = {}
    for cid, values in series.items():
        values.sort(key=lambda item: item[0])
        price_series[cid] = [price for _, price in values]

    comparables_by_target: dict[str, list[str]] = defaultdict(list)
    for row in comparable_rows:
        target = clean(row.get("target_canonical_product_id"))
        comp = clean(row.get("comparable_canonical_product_id"))
        if target and comp and comp not in comparables_by_target[target]:
            comparables_by_target[target].append(comp)

    forecast_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    method_rows: list[dict[str, Any]] = []

    for cid, current in sorted(current_by_id.items(), key=lambda item: item[1]["product_name"].lower()):
        route_info = route_by_id.get(cid, {"route": "", "allowed": "false", "reason": "ROUTING_NOT_FOUND"})
        allowed = route_info["allowed"] == "true"
        route = route_info["route"]
        price = current["current_price"]
        for horizon in contract["horizons_days"]:
            if not allowed or not price or price <= 0:
                coverage_rows.append({
                    "canonical_product_id": cid,
                    "product_name": current["product_name"],
                    "horizon_days": horizon,
                    "coverage_status": "GOVERNED_BLOCKED_NO_FORECAST",
                    "explicit_method_id": "",
                    "blocked_reason": route_info["reason"] or "ROUTING_OR_PRICE_NOT_AUTHORIZED",
                })
                continue
            try:
                distribution, method, own_count, comparable_count = build_distribution(
                    route, cid, price_series, comparables_by_target.get(cid, []), contract
                )
                result = simulate(float(price), distribution, int(horizon), cid, contract)
            except RuntimeError as exc:
                failures.append(f"FORECAST_BUILD_FAILED:{cid}:{horizon}:{exc}")
                coverage_rows.append({
                    "canonical_product_id": cid,
                    "product_name": current["product_name"],
                    "horizon_days": horizon,
                    "coverage_status": "FORECAST_BUILD_FAILED",
                    "explicit_method_id": "",
                    "blocked_reason": str(exc),
                })
                continue

            row = {
                "snapshot_id": contract["snapshot_id"],
                "canonical_product_id": cid,
                "product_name": current["product_name"],
                "route": route,
                "horizon_days": horizon,
                "explicit_method_id": method,
                "current_price": round(float(price), 4),
                "history_observations_used": len(price_series.get(cid, [])),
                "own_monthly_returns_used": own_count,
                "target_specific_comparable_members_used": comparable_count,
                "return_distribution_size": int(distribution.size),
                "random_seed": deterministic_seed(contract["snapshot_id"], cid, int(horizon)),
                **{key: round(value, 6) if isinstance(value, float) else value for key, value in result.items()},
                "current_supply_demand_used": False,
                "production_forecast_authorized": False,
                "ranking_authorized": False,
                "purchase_recommendation_authorized": False,
            }
            forecast_rows.append(row)
            coverage_rows.append({
                "canonical_product_id": cid,
                "product_name": current["product_name"],
                "horizon_days": horizon,
                "coverage_status": "FORECAST_CREATED",
                "explicit_method_id": method,
                "blocked_reason": "",
            })
            method_rows.append({
                "canonical_product_id": cid,
                "product_name": current["product_name"],
                "route": route,
                "horizon_days": horizon,
                "explicit_method_id": method,
                "history_observations_used": len(price_series.get(cid, [])),
                "own_monthly_returns_used": own_count,
                "target_specific_comparable_members_used": comparable_count,
                "return_distribution_size": int(distribution.size),
                "random_seed": deterministic_seed(contract["snapshot_id"], cid, int(horizon)),
            })

    authorized_products = {
        row["canonical_product_id"] for row in forecast_rows
    }
    blocked_products = {
        row["canonical_product_id"] for row in coverage_rows if row["coverage_status"] == "GOVERNED_BLOCKED_NO_FORECAST"
    }
    horizon_counts = {
        str(h): sum(1 for row in forecast_rows if int(row["horizon_days"]) == h)
        for h in contract["horizons_days"]
    }

    if len(current_rows) != contract["required_product_rows"]:
        failures.append("CURRENT_PRODUCT_ROW_COUNT_MISMATCH")
    if len(forecast_rows) != contract["required_forecast_rows"]:
        failures.append("FORECAST_ROW_COUNT_MISMATCH")
    if len(coverage_rows) != contract["required_coverage_rows"]:
        failures.append("COVERAGE_ROW_COUNT_MISMATCH")
    if len(authorized_products) != contract["required_authorized_products"]:
        failures.append("AUTHORIZED_PRODUCT_COUNT_MISMATCH")
    if len(blocked_products) != contract["required_blocked_products"]:
        failures.append("BLOCKED_PRODUCT_COUNT_MISMATCH")
    if any(count != contract["required_authorized_products"] for count in horizon_counts.values()):
        failures.append("INCOMPLETE_HORIZON_COVERAGE")
    if any(not clean(row.get("explicit_method_id")) for row in forecast_rows):
        failures.append("MISSING_EXPLICIT_METHOD_ID")
    if any(int(row.get("simulation_count") or 0) != contract["monte_carlo"]["simulations_per_product_horizon"] for row in forecast_rows):
        failures.append("MONTE_CARLO_SIMULATION_COUNT_MISMATCH")
    if any(bool(row.get("current_supply_demand_used")) for row in forecast_rows):
        failures.append("CURRENT_SUPPLY_DEMAND_LEAKAGE")

    fields = [
        "snapshot_id", "canonical_product_id", "product_name", "route", "horizon_days",
        "explicit_method_id", "current_price", "history_observations_used", "own_monthly_returns_used",
        "target_specific_comparable_members_used", "return_distribution_size", "random_seed",
        "simulation_count", "monthly_steps", "p10_price", "p25_price", "median_price", "p75_price",
        "p90_price", "mean_price", "median_expected_return", "mean_expected_return",
        "probability_of_loss", "probability_of_50pct_gain", "probability_of_doubling",
        "current_supply_demand_used", "production_forecast_authorized", "ranking_authorized",
        "purchase_recommendation_authorized",
    ]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_complete_horizon_probabilistic_forecasts.csv", forecast_rows, fields)
    write_csv(OUTPUT / "collector_complete_horizon_method_provenance.csv", method_rows, [
        "canonical_product_id", "product_name", "route", "horizon_days", "explicit_method_id",
        "history_observations_used", "own_monthly_returns_used", "target_specific_comparable_members_used",
        "return_distribution_size", "random_seed",
    ])
    write_csv(OUTPUT / "collector_complete_horizon_coverage_registry.csv", coverage_rows, [
        "canonical_product_id", "product_name", "horizon_days", "coverage_status", "explicit_method_id", "blocked_reason",
    ])

    summary = {
        "block_name": "Collector Complete-Horizon Product-Specific Probabilistic Forecast",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "product_rows": len(current_rows),
        "authorized_products": len(authorized_products),
        "blocked_products": len(blocked_products),
        "forecast_rows": len(forecast_rows),
        "coverage_rows": len(coverage_rows),
        "horizons_days": contract["horizons_days"],
        "horizon_forecast_counts": horizon_counts,
        "monte_carlo_simulations_per_product_horizon": contract["monte_carlo"]["simulations_per_product_horizon"],
        "all_authorized_product_horizons_have_explicit_methods": not any(not clean(row.get("explicit_method_id")) for row in forecast_rows),
        "all_authorized_product_horizons_have_monte_carlo": not any(int(row.get("simulation_count") or 0) != contract["monte_carlo"]["simulations_per_product_horizon"] for row in forecast_rows),
        "current_supply_demand_used": False,
        "production_forecast_authorized": False,
        "ranking_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": contract["expected_status"] if not failures else "FAIL_COLLECTOR_COMPLETE_HORIZON_PROBABILISTIC_FORECAST",
    }
    (OUTPUT / "collector_complete_horizon_probabilistic_forecast_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
