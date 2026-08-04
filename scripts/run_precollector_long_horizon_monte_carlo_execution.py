from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_long_horizon_monte_carlo_execution_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/long_horizon_monte_carlo_execution"


def clean(value: Any) -> str:
    return str(value or "").strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_csv_bytes(payload: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def first(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    return next((name for name in candidates if name in columns), None)


def load_package(package: dict[str, str], required: list[str], role: str) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    path = Path(tempfile.gettempdir()) / package["package_name"]
    if not path.is_file():
        raise RuntimeError(f"PACKAGE_MISSING:{path}")
    actual = sha256_file(path)
    if actual != package["sha256"]:
        raise RuntimeError(f"PACKAGE_HASH_DRIFT:{path.name}:expected={package['sha256']}:actual={actual}")
    payloads: dict[str, bytes] = {}
    lineage: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        available = {Path(item.filename).name: item for item in archive.infolist() if not item.is_dir()}
        for name in required:
            member = available.get(name)
            if member is None:
                raise RuntimeError(f"PACKAGE_MEMBER_MISSING:{path.name}:{name}")
            payload = archive.read(member)
            payloads[name] = payload
            lineage.append({
                "artifact_role": role,
                "package_name": path.name,
                "package_sha256": actual,
                "member_name": name,
                "member_sha256": sha256_bytes(payload),
                "row_count": len(read_csv_bytes(payload)) if name.endswith(".csv") else "",
            })
    return payloads, lineage


def stable_seed(snapshot_id: str, product_id: str, horizon: str) -> int:
    raw = hashlib.sha256(f"{snapshot_id}|{product_id}|{horizon}".encode("utf-8")).digest()
    return 1 + int.from_bytes(raw[:8], "big") % 2147483646


def main() -> int:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    architecture_required = [
        "precollector_long_horizon_monte_carlo_route_registry.csv",
        "precollector_long_horizon_monte_carlo_simulation_policy.csv",
        "precollector_long_horizon_monte_carlo_seed_policy.csv",
        "precollector_long_horizon_monte_carlo_output_schema.csv",
        "precollector_long_horizon_monte_carlo_architecture_summary.json",
    ]
    winner_required = [
        "precollector_certified_short_horizon_winner_uncertainty_registry.csv",
        "precollector_winner_uncertainty_unresolved_group_registry.csv",
        "precollector_winner_uncertainty_execution_summary.json",
    ]
    architecture, lineage_a = load_package(contract["required_architecture_package"], architecture_required, "CERTIFIED_MONTE_CARLO_ARCHITECTURE")
    winner, lineage_w = load_package(contract["required_winner_uncertainty_execution_package"], winner_required, "CERTIFIED_WINNER_UNCERTAINTY_EXECUTION")

    routes = read_csv_bytes(architecture["precollector_long_horizon_monte_carlo_route_registry.csv"])
    winners = read_csv_bytes(winner["precollector_certified_short_horizon_winner_uncertainty_registry.csv"])
    unresolved = read_csv_bytes(winner["precollector_winner_uncertainty_unresolved_group_registry.csv"])

    manifest_path = ROOT / contract["input_governance"]["snapshot_manifest_path"]
    foundation_path = ROOT / contract["input_governance"]["current_foundation_path"]
    if not manifest_path.is_file() or not foundation_path.is_file():
        raise RuntimeError("SNAPSHOT_AUTHORITY_INPUT_MISSING")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if manifest.get("snapshot_id") != contract["governing_snapshot_id"]:
        raise RuntimeError("SNAPSHOT_ID_DRIFT")
    by_role = {clean(item.get("role")): item for item in manifest.get("files", []) if isinstance(item, dict)}
    history_item = by_role.get("canonical_history")
    if not history_item:
        raise RuntimeError("CANONICAL_HISTORY_ROLE_MISSING")
    history_path = ROOT / clean(history_item.get("path"))
    if not history_path.is_file() or sha256_file(history_path) != clean(history_item.get("sha256")):
        raise RuntimeError("CANONICAL_HISTORY_HASH_DRIFT")

    foundation = pd.read_csv(foundation_path, dtype=str, encoding="utf-8-sig").fillna("")
    history = pd.read_csv(history_path, dtype=str, encoding="utf-8-sig").fillna("")
    product_col = first(list(foundation.columns), ("tcgplayer_product_id", "product_id", "investment_product_id"))
    price_col = first(list(foundation.columns), ("current_price", "market_price", "price", "governed_current_price"))
    route_col = first(list(foundation.columns), ("forecast_route", "forecast_method"))
    name_col = first(list(foundation.columns), ("product_name", "canonical_product_name"))
    hist_product = first(list(history.columns), ("tcgplayer_product_id", "product_id", "investment_product_id"))
    hist_price = first(list(history.columns), ("price", "market_price", "observed_price", "current_price"))
    hist_date = first(list(history.columns), ("observed_at", "observation_date", "date", "timestamp", "as_of_date"))
    required_columns = [product_col, price_col, route_col, hist_product, hist_price, hist_date]
    if any(value is None for value in required_columns):
        raise RuntimeError(f"AUTHORITY_SCHEMA_UNSUPPORTED:{required_columns}")

    foundation[product_col] = foundation[product_col].astype(str).str.removeprefix("TCGPLAYER-").str.replace(r"\.0$", "", regex=True)
    foundation[price_col] = pd.to_numeric(foundation[price_col], errors="coerce")
    history[hist_product] = history[hist_product].astype(str).str.removeprefix("TCGPLAYER-").str.replace(r"\.0$", "", regex=True)
    history[hist_price] = pd.to_numeric(history[hist_price], errors="coerce")
    history[hist_date] = pd.to_datetime(history[hist_date], errors="coerce", utc=True)
    history = history.dropna(subset=[hist_price, hist_date])
    history = history[history[hist_price] > 0].sort_values([hist_product, hist_date])

    annual_returns: dict[str, list[float]] = {}
    for product_id, group in history.groupby(hist_product):
        values: list[float] = []
        rows = group[[hist_date, hist_price]].drop_duplicates().sort_values(hist_date)
        prior = None
        for _, row in rows.iterrows():
            if prior is not None:
                days = (row[hist_date] - prior[hist_date]).total_seconds() / 86400.0
                if days > 0 and prior[hist_price] > 0 and row[hist_price] > 0:
                    annualized = math.log(row[hist_price] / prior[hist_price]) * 365.25 / days
                    if math.isfinite(annualized):
                        values.append(float(np.clip(annualized, -1.5, 1.5)))
            prior = row
        annual_returns[clean(product_id)] = values

    route_by_product = dict(zip(foundation[product_col].astype(str), foundation[route_col].astype(str)))
    route_pools: dict[str, list[float]] = {}
    for product_id, values in annual_returns.items():
        route_pools.setdefault(route_by_product.get(product_id, ""), []).extend(values)
    global_pool = [value for values in annual_returns.values() for value in values]
    if not global_pool:
        raise RuntimeError("NO_CANONICAL_RETURN_OBSERVATIONS")

    policy = contract["simulation_policy"]
    simulations = int(policy["required_simulations_per_product_horizon"])
    quantiles = list(policy["required_quantiles"])
    scenario_names = list(policy["scenario_uncertainty"]["scenario_probabilities"].keys())
    scenario_probs = np.array(list(policy["scenario_uncertainty"]["scenario_probabilities"].values()), dtype=float)
    scenario_probs = scenario_probs / scenario_probs.sum()
    scenario_adjustments = policy["scenario_uncertainty"]["annual_log_return_adjustments"]
    minimum_obs = int(policy["minimum_product_return_observations"])

    seed_rows: list[dict[str, Any]] = []
    pool_rows: list[dict[str, Any]] = []
    distribution_rows: list[dict[str, Any]] = []
    failures: list[str] = []

    for _, product in foundation.iterrows():
        product_id = clean(product[product_col])
        current_price = float(product[price_col]) if pd.notna(product[price_col]) else 0.0
        route = clean(product[route_col])
        name = clean(product[name_col]) if name_col else ""
        product_pool = annual_returns.get(product_id, [])
        if len(product_pool) >= minimum_obs:
            pool = product_pool
            pool_source = "PRODUCT"
        elif len(route_pools.get(route, [])) >= minimum_obs:
            pool = route_pools[route]
            pool_source = "FORECAST_ROUTE_POOL"
        else:
            pool = global_pool
            pool_source = "GLOBAL_POOL"
        if current_price <= 0 or not pool:
            failures.append(f"PRODUCT_INPUT_INVALID:{product_id}")
            continue
        pool_array = np.array(pool, dtype=float)
        pool_rows.append({
            "tcgplayer_product_id": product_id,
            "product_name": name,
            "forecast_route": route,
            "return_pool_source": pool_source,
            "product_return_observations": len(product_pool),
            "selected_pool_observations": len(pool),
            "current_price": current_price,
        })
        for horizon, years in policy["horizon_years"].items():
            seed = stable_seed(contract["governing_snapshot_id"], product_id, horizon)
            rng = np.random.default_rng(seed)
            scenario = rng.choice(scenario_names, size=simulations, p=scenario_probs)
            scenario_shift = np.array([float(scenario_adjustments[item]) for item in scenario])
            steps = max(1, int(round(float(years) * int(policy["path_uncertainty"]["steps_per_year"]))))
            sampled = rng.choice(pool_array, size=(simulations, steps), replace=True)
            path_annual = sampled.mean(axis=1)
            standard_error = max(float(np.std(pool_array, ddof=1) / math.sqrt(max(len(pool_array), 1))) if len(pool_array) > 1 else 0.0, float(policy["parameter_uncertainty"]["standard_error_floor"]))
            parameter_shift = rng.normal(0.0, standard_error, size=simulations)
            tail_mask = rng.random(simulations) < float(policy["tail_stress"]["probability"])
            tail_shift = tail_mask.astype(float) * float(policy["tail_stress"]["annual_log_return_adjustment"])
            annual_log_return = np.clip(path_annual + parameter_shift + scenario_shift + tail_shift, float(policy["minimum_annualized_log_return"]), float(policy["maximum_annualized_log_return"]))
            terminal = np.maximum(float(policy["minimum_terminal_value"]), current_price * np.exp(annual_log_return * float(years)))
            annualized_return = np.power(terminal / current_price, 1.0 / float(years)) - 1.0
            row: dict[str, Any] = {
                "tcgplayer_product_id": product_id,
                "product_name": name,
                "forecast_route": route,
                "horizon_code": horizon,
                "horizon_years": years,
                "simulations": simulations,
                "seed": seed,
                "return_pool_source": pool_source,
                "return_pool_observations": len(pool),
                "current_price": current_price,
                "terminal_value_mean": float(np.mean(terminal)),
                "terminal_value_median": float(np.median(terminal)),
                "annualized_return_mean": float(np.mean(annualized_return)),
                "annualized_return_median": float(np.median(annualized_return)),
                "probability_of_loss": float(np.mean(terminal < current_price)),
                "probability_of_positive_return": float(np.mean(terminal > current_price)),
                "downside_tail_mean_terminal_value": float(np.mean(terminal[terminal <= np.quantile(terminal, 0.05)])),
                "upside_tail_mean_terminal_value": float(np.mean(terminal[terminal >= np.quantile(terminal, 0.95)])),
                "forecast_generation_authorized": False,
                "ranking_execution_authorized": False,
            }
            for quantile, value in zip(quantiles, np.quantile(terminal, quantiles)):
                row[f"terminal_value_q{int(round(quantile * 100)):02d}"] = float(value)
            distribution_rows.append(row)
            seed_rows.append({
                "tcgplayer_product_id": product_id,
                "horizon_code": horizon,
                "seed": seed,
                "seed_method": policy["deterministic_seed_method"],
                "common_random_numbers_within_product": True,
            })

    expected = contract["expected_counts"]
    observed = {
        "governed_products": len(foundation),
        "long_horizon_routes": len(routes),
        "long_horizon_horizon_codes": len({clean(row.get("horizon_code")) for row in routes}),
        "product_horizon_rows": len(distribution_rows),
        "certified_short_horizon_winners": len(winners),
        "unresolved_short_horizon_groups": len(unresolved),
    }
    for key, value in expected.items():
        if observed.get(key) != value:
            failures.append(f"COUNT_DRIFT:{key}:expected={value}:actual={observed.get(key)}")

    route_summary_rows: list[dict[str, Any]] = []
    frame = pd.DataFrame(distribution_rows)
    if not frame.empty:
        for (route, horizon), group in frame.groupby(["forecast_route", "horizon_code"]):
            route_summary_rows.append({
                "forecast_route": route,
                "horizon_code": horizon,
                "product_rows": len(group),
                "mean_probability_of_loss": float(group["probability_of_loss"].mean()),
                "median_terminal_value_multiple": float((group["terminal_value_median"] / group["current_price"]).median()),
                "simulations_per_product_horizon": simulations,
            })

    diagnostics = [{"severity": "BLOCKING", "code": failure, "detail": ""} for failure in failures]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["required_outputs"]
    lineage = lineage_a + lineage_w + [
        {"artifact_role": "CERTIFIED_SNAPSHOT_MANIFEST", "package_name": "", "package_sha256": "", "member_name": str(manifest_path.relative_to(ROOT)), "member_sha256": sha256_file(manifest_path), "row_count": ""},
        {"artifact_role": "CERTIFIED_CURRENT_FOUNDATION", "package_name": "", "package_sha256": "", "member_name": str(foundation_path.relative_to(ROOT)), "member_sha256": sha256_file(foundation_path), "row_count": len(foundation)},
        {"artifact_role": "CERTIFIED_CANONICAL_HISTORY", "package_name": "", "package_sha256": "", "member_name": str(history_path.relative_to(ROOT)), "member_sha256": sha256_file(history_path), "row_count": len(history)},
    ]
    write_csv(OUTPUT_DIR / outputs["input_lineage_csv"], lineage, list(lineage[0].keys()))
    write_csv(OUTPUT_DIR / outputs["seed_registry_csv"], seed_rows, list(seed_rows[0].keys()) if seed_rows else ["tcgplayer_product_id", "horizon_code", "seed"])
    write_csv(OUTPUT_DIR / outputs["return_pool_registry_csv"], pool_rows, list(pool_rows[0].keys()) if pool_rows else ["tcgplayer_product_id"])
    distribution_fields = list(distribution_rows[0].keys()) if distribution_rows else ["tcgplayer_product_id", "horizon_code"]
    write_csv(OUTPUT_DIR / outputs["product_horizon_distribution_csv"], distribution_rows, distribution_fields)
    write_csv(OUTPUT_DIR / outputs["route_summary_csv"], route_summary_rows, list(route_summary_rows[0].keys()) if route_summary_rows else ["forecast_route", "horizon_code"])
    write_csv(OUTPUT_DIR / outputs["diagnostics_csv"], diagnostics, ["severity", "code", "detail"])

    status = "PASS" if not failures else "FAIL"
    summary = {
        "certification_status": status,
        **observed,
        "required_simulations_per_product_horizon": simulations,
        "total_simulated_terminal_values": len(distribution_rows) * simulations,
        "deterministic_seed_registry_rows": len(seed_rows),
        "return_pool_registry_rows": len(pool_rows),
        "route_summary_rows": len(route_summary_rows),
        "short_horizon_model_selection_reopened": False,
        "short_horizon_certifications_modified": False,
        "new_live_collection_performed": False,
        "model_tuning_performed": False,
        "critical_failures": failures,
        "next_stage": contract["next_stage_if_certified"] if not failures else "REPAIR_PRECOLLECTOR_LONG_HORIZON_MONTE_CARLO_EXECUTION",
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_analysis_authorized": False,
        "purchase_recommendation_authorized": False,
    }
    (OUTPUT_DIR / outputs["summary_json"]).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_out = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "outputs": [
            {"path": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in sorted(OUTPUT_DIR.iterdir())
            if path.is_file() and path.name != outputs["manifest_json"]
        ],
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(json.dumps(manifest_out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_LONG_HORIZON_MONTE_CARLO_EXECUTION" if not failures else "FAIL_PRECOLLECTOR_LONG_HORIZON_MONTE_CARLO_EXECUTION")
    print(f"GOVERNED_PRODUCTS={len(foundation)}")
    print(f"PRODUCT_HORIZON_ROWS={len(distribution_rows)}")
    print(f"SIMULATIONS_PER_PRODUCT_HORIZON={simulations}")
    print(f"TOTAL_SIMULATED_TERMINAL_VALUES={len(distribution_rows) * simulations}")
    print(f"LONG_HORIZON_ROUTES={len(routes)}")
    print("SHORT_HORIZON_MODEL_SELECTION_REOPENED=FALSE")
    print("FORECAST_GENERATION_AUTHORIZED=FALSE")
    print(f"NEXT_STAGE={summary['next_stage']}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
