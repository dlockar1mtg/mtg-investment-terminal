from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_early_awareness_lorwyn_forecast_contract_v1.json"
PREMODEL = ROOT / "data/governance/permanence/certification/collector_v1_final_premodel_user_exclusion_resolution"
HISTORY = ROOT / "data/governance/permanence/certification/collector_v1_august1_historical_observation_ledger/collector_august1_historical_observation_ledger.csv"
RELEASE = ROOT / "data/governance/permanence/certification/collector_v1_wizards_release_date_authority/collector_wizards_release_date_authority.csv"
CURRENT = PREMODEL / "collector_final_current_price_authority.csv"
COMPARABLES = PREMODEL / "collector_comparable_pool_certification.csv"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_early_awareness_lorwyn_forecast"


def clean(value: Any) -> str:
    return str(value or "").strip()


def num(value: Any) -> float | None:
    text = clean(value).replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        value_f = float(text)
    except ValueError:
        return None
    return value_f if math.isfinite(value_f) else None


def parse_date(value: Any) -> datetime | None:
    text = clean(value)[:10]
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def percentile(values: list[float], q: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=float), q)) if values else 0.0


def deterministic_seed(snapshot_id: str, product_id: str, horizon: int) -> int:
    digest = hashlib.sha256(f"{snapshot_id}|{product_id}|{horizon}|lorwyn".encode()).digest()
    return int.from_bytes(digest[:8], "big") % (2**32 - 1)


def nearest(rows: list[dict[str, Any]], target: datetime, tolerance_days: int) -> dict[str, Any] | None:
    if not rows:
        return None
    chosen = min(rows, key=lambda row: abs((row["date"] - target).days))
    return chosen if abs((chosen["date"] - target).days) <= tolerance_days else None


def log_returns(prices: list[float]) -> np.ndarray:
    values = np.asarray([p for p in prices if p > 0], dtype=float)
    return np.diff(np.log(values)) if values.size >= 2 else np.asarray([], dtype=float)


def winsor(values: np.ndarray, lo: float = 0.05, hi: float = 0.95) -> np.ndarray:
    if values.size == 0:
        return values
    return np.clip(values, np.quantile(values, lo), np.quantile(values, hi))


def early_prediction(prices: list[float], peer_returns: np.ndarray) -> tuple[float, float, float]:
    own = winsor(log_returns(prices))
    peer = winsor(peer_returns)
    own_drift = float(np.median(own)) if own.size else 0.0
    peer_drift = float(np.median(peer)) if peer.size else 0.0
    own_weight = min(0.75, len(own) / 8.0)
    monthly_drift = own_weight * own_drift + (1.0 - own_weight) * peer_drift
    remaining_steps = max(1, 12 - max(1, len(prices) - 1))
    predicted_return = math.exp(monthly_drift * remaining_steps) - 1.0
    volatility = float(np.std(np.concatenate([own, peer]))) if own.size + peer.size > 1 else 0.15
    score = predicted_return / max(volatility, 0.05)
    return predicted_return, score, volatility


def simulate_lorwyn(
    current_price: float,
    distribution: np.ndarray,
    horizon_days: int,
    method_id: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    simulations = int(contract["lorwyn"]["simulation_count"])
    steps = max(1, int(math.ceil(horizon_days / 30.4375)))
    rng = np.random.default_rng(deterministic_seed(contract["snapshot_id"], contract["lorwyn"]["canonical_product_id"], horizon_days))
    draws = rng.choice(distribution, size=(simulations, steps), replace=True)
    drift = float(np.median(distribution))
    decay_scale = {90: 18.0, 180: 15.0, 365: 12.0, 730: 10.0, 1095: 8.0, 1825: 6.0}[horizon_days]
    decay = np.exp(-np.arange(steps, dtype=float) / decay_scale)
    regime_scale = {90: 1.00, 180: 0.95, 365: 0.90, 730: 0.78, 1095: 0.67, 1825: 0.55}[horizon_days]
    centered = draws - drift
    terminal = current_price * np.exp((centered + drift * decay * regime_scale).sum(axis=1))
    q10, q25, q50, q75, q90 = np.quantile(terminal, [0.10, 0.25, 0.50, 0.75, 0.90])
    return {
        "canonical_product_id": contract["lorwyn"]["canonical_product_id"],
        "product_name": contract["lorwyn"]["product_name"],
        "horizon_days": horizon_days,
        "explicit_method_id": method_id,
        "current_price": round(current_price, 4),
        "p10_price": round(float(q10), 6),
        "p25_price": round(float(q25), 6),
        "median_price": round(float(q50), 6),
        "p75_price": round(float(q75), 6),
        "p90_price": round(float(q90), 6),
        "mean_price": round(float(np.mean(terminal)), 6),
        "median_expected_return": round(float(q50 / current_price - 1.0), 6),
        "probability_of_loss": round(float(np.mean(terminal < current_price)), 6),
        "probability_of_50pct_gain": round(float(np.mean(terminal >= current_price * 1.5)), 6),
        "probability_of_doubling": round(float(np.mean(terminal >= current_price * 2.0)), 6),
        "simulation_count": simulations,
        "supply_status": contract["lorwyn"]["supply_status"],
        "supply_overlay_status": contract["lorwyn"]["supply_overlay_status"],
        "forecast_status": contract["lorwyn"]["forecast_status"],
        "current_ebay_data_used": False,
        "production_forecast_authorized": False,
        "ranking_authorized": False,
        "purchase_recommendation_authorized": False,
    }


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    required = [HISTORY, RELEASE, CURRENT, COMPARABLES]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("MISSING_REQUIRED_INPUTS:" + ";".join(missing))

    history_rows = read_csv(HISTORY)
    release_rows = read_csv(RELEASE)
    current_rows = read_csv(CURRENT)
    comparable_rows = read_csv(COMPARABLES)
    failures: list[str] = []

    release_by_id = {
        clean(row.get("canonical_product_id")): parse_date(row.get("official_release_date") or row.get("release_date"))
        for row in release_rows
    }
    name_by_id = {clean(row.get("canonical_product_id")): clean(row.get("product_name")) for row in current_rows}
    current_by_id = {clean(row.get("canonical_product_id")): num(row.get("current_price")) for row in current_rows}

    series: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in history_rows:
        cid = clean(row.get("canonical_product_id"))
        date = parse_date(row.get("observation_date"))
        price = num(row.get("market_price") or row.get("selected_price") or row.get("price"))
        if cid and date and price and price > 0:
            series[cid].append({"date": date, "price": price})
    for rows in series.values():
        rows.sort(key=lambda row: row["date"])

    truth_rows: list[dict[str, Any]] = []
    cfg = contract["early_awareness"]
    for cid, rows in series.items():
        release = release_by_id.get(cid)
        if not release:
            continue
        start = nearest(rows, release, cfg["future_match_tolerance_days"])
        end = nearest(rows, release + timedelta(days=365), cfg["future_match_tolerance_days"])
        if not start or not end or end["date"] <= start["date"]:
            continue
        realized = end["price"] / start["price"] - 1.0
        truth_rows.append({
            "canonical_product_id": cid,
            "product_name": name_by_id.get(cid, ""),
            "release_date": release.date().isoformat(),
            "start_observation_date": start["date"].date().isoformat(),
            "day365_observation_date": end["date"].date().isoformat(),
            "start_price": round(start["price"], 4),
            "day365_price": round(end["price"], 4),
            "realized_365_return": round(realized, 6),
        })

    threshold = max(
        float(cfg["absolute_breakout_return_floor"]),
        percentile([float(row["realized_365_return"]) for row in truth_rows], float(cfg["cross_product_breakout_quantile"])),
    )
    for row in truth_rows:
        row["breakout_threshold"] = round(threshold, 6)
        row["actual_first_year_breakout"] = float(row["realized_365_return"]) >= threshold

    prediction_rows: list[dict[str, Any]] = []
    for checkpoint in cfg["checkpoint_days"]:
        candidates: list[dict[str, Any]] = []
        all_peer_returns: list[float] = []
        for cid, rows in series.items():
            release = release_by_id.get(cid)
            if not release:
                continue
            cutoff = release + timedelta(days=int(checkpoint))
            observed = [row for row in rows if release <= row["date"] <= cutoff]
            if len(observed) >= 2:
                all_peer_returns.extend(log_returns([row["price"] for row in observed]).tolist())
        peer_distribution = np.asarray(all_peer_returns, dtype=float)

        truth_by_id = {row["canonical_product_id"]: row for row in truth_rows}
        for cid, truth in truth_by_id.items():
            release = release_by_id[cid]
            cutoff = release + timedelta(days=int(checkpoint))
            observed = [row for row in series[cid] if release <= row["date"] <= cutoff]
            if not observed:
                continue
            predicted_return, score, volatility = early_prediction([row["price"] for row in observed], peer_distribution)
            candidates.append({
                "canonical_product_id": cid,
                "product_name": truth["product_name"],
                "checkpoint_day": checkpoint,
                "checkpoint_date": cutoff.date().isoformat(),
                "observations_available": len(observed),
                "checkpoint_price": round(observed[-1]["price"], 4),
                "predicted_day365_return": round(predicted_return, 6),
                "awareness_score": round(score, 6),
                "estimated_volatility": round(volatility, 6),
                "actual_day365_return": truth["realized_365_return"],
                "actual_first_year_breakout": truth["actual_first_year_breakout"],
                "days_of_advance_warning": 365 - checkpoint,
                "remaining_unrealized_appreciation": round(float(truth["day365_price"]) / observed[-1]["price"] - 1.0, 6),
                "future_observations_used": False,
                "current_ebay_data_used": False,
            })
        candidates.sort(key=lambda row: (float(row["awareness_score"]), float(row["predicted_day365_return"])), reverse=True)
        for rank, row in enumerate(candidates, start=1):
            row["checkpoint_rank"] = rank
            prediction_rows.append(row)

    metric_rows: list[dict[str, Any]] = []
    best_gate = False
    breakout_count = sum(bool(row["actual_first_year_breakout"]) for row in truth_rows)
    random_rate = breakout_count / len(truth_rows) if truth_rows else 0.0
    for checkpoint in cfg["checkpoint_days"]:
        rows = [row for row in prediction_rows if int(row["checkpoint_day"]) == int(checkpoint)]
        for cutoff in cfg["selection_cutoffs"]:
            selected = rows[: min(int(cutoff), len(rows))]
            tp = sum(bool(row["actual_first_year_breakout"]) for row in selected)
            precision = tp / len(selected) if selected else 0.0
            recall = tp / breakout_count if breakout_count else 0.0
            lift = precision - random_rate
            gate = (
                int(cutoff) == 5
                and recall >= float(cfg["minimum_recall_at_top5"])
                and lift >= float(cfg["minimum_precision_lift_over_random"])
                and (365 - int(checkpoint)) >= int(cfg["minimum_median_lead_days"])
            )
            best_gate = best_gate or gate
            metric_rows.append({
                "checkpoint_day": checkpoint,
                "selection_cutoff": cutoff,
                "eligible_products": len(rows),
                "actual_breakouts": breakout_count,
                "true_positives": tp,
                "precision": round(precision, 6),
                "recall": round(recall, 6),
                "random_precision_baseline": round(random_rate, 6),
                "precision_lift_over_random": round(lift, 6),
                "lead_days": 365 - int(checkpoint),
                "early_awareness_gate_passed": gate,
            })

    selected_top5 = [row for row in prediction_rows if int(row["checkpoint_rank"]) <= 5]
    false_positives = [row for row in selected_top5 if not bool(row["actual_first_year_breakout"])]
    false_negatives: list[dict[str, Any]] = []
    for checkpoint in cfg["checkpoint_days"]:
        top_ids = {row["canonical_product_id"] for row in prediction_rows if int(row["checkpoint_day"]) == int(checkpoint) and int(row["checkpoint_rank"]) <= 5}
        for truth in truth_rows:
            if bool(truth["actual_first_year_breakout"]) and truth["canonical_product_id"] not in top_ids:
                false_negatives.append({**truth, "checkpoint_day": checkpoint})

    lorwyn_id = contract["lorwyn"]["canonical_product_id"]
    lorwyn_price = current_by_id.get(lorwyn_id)
    if not lorwyn_price:
        failures.append("LORWYN_CURRENT_PRICE_NOT_FOUND")

    explicit_comps = [
        clean(row.get("comparable_canonical_product_id"))
        for row in comparable_rows
        if clean(row.get("target_canonical_product_id")) == lorwyn_id
    ]
    if not explicit_comps:
        candidates = []
        for cid, rows in series.items():
            if cid == lorwyn_id or len(rows) < 3:
                continue
            first_price = rows[0]["price"]
            distance = abs(math.log(max(first_price, 0.01) / max(lorwyn_price or first_price, 0.01)))
            candidates.append((distance, cid))
        candidates.sort()
        explicit_comps = [cid for _, cid in candidates[: int(contract["lorwyn"]["maximum_comparable_products"])]]

    peer_parts: list[np.ndarray] = []
    used_comps: list[str] = []
    for cid in explicit_comps:
        returns = winsor(log_returns([row["price"] for row in series.get(cid, [])]))
        if returns.size:
            peer_parts.append(returns)
            used_comps.append(cid)
    distribution = np.concatenate(peer_parts) if peer_parts else np.asarray([], dtype=float)
    if distribution.size == 0 or len(used_comps) < int(contract["lorwyn"]["minimum_comparable_products"]):
        failures.append("LORWYN_COMPARABLE_DISTRIBUTION_INSUFFICIENT")

    lorwyn_rows: list[dict[str, Any]] = []
    if lorwyn_price and distribution.size:
        for horizon in contract["lorwyn"]["horizons_days"]:
            method = contract["lorwyn"]["method_ids"][str(horizon)]
            row = simulate_lorwyn(float(lorwyn_price), distribution, int(horizon), method, contract)
            row["comparable_products_used"] = len(used_comps)
            row["comparable_product_ids"] = "|".join(used_comps)
            lorwyn_rows.append(row)

    if len(truth_rows) < int(cfg["minimum_truth_products"]):
        failures.append("EARLY_AWARENESS_TRUTH_SAMPLE_TOO_SMALL")
    if breakout_count < int(cfg["minimum_breakout_products"]):
        failures.append("EARLY_AWARENESS_BREAKOUT_SAMPLE_TOO_SMALL")
    if not best_gate:
        failures.append("EARLY_AWARENESS_SELECTION_GATE_NOT_MET")
    if len(lorwyn_rows) != 6:
        failures.append("LORWYN_SIX_HORIZON_FORECAST_COUNT_MISMATCH")
    if len({row["explicit_method_id"] for row in lorwyn_rows}) != len(lorwyn_rows):
        failures.append("LORWYN_METHODS_NOT_DISTINCT_BY_HORIZON")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_first_year_breakout_truth_registry.csv", truth_rows, [
        "canonical_product_id", "product_name", "release_date", "start_observation_date", "day365_observation_date",
        "start_price", "day365_price", "realized_365_return", "breakout_threshold", "actual_first_year_breakout",
    ])
    write_csv(OUTPUT / "collector_early_awareness_checkpoint_predictions.csv", prediction_rows, [
        "canonical_product_id", "product_name", "checkpoint_day", "checkpoint_date", "observations_available",
        "checkpoint_price", "predicted_day365_return", "awareness_score", "estimated_volatility", "checkpoint_rank",
        "actual_day365_return", "actual_first_year_breakout", "days_of_advance_warning", "remaining_unrealized_appreciation",
        "future_observations_used", "current_ebay_data_used",
    ])
    write_csv(OUTPUT / "collector_early_awareness_metric_summary.csv", metric_rows, [
        "checkpoint_day", "selection_cutoff", "eligible_products", "actual_breakouts", "true_positives", "precision",
        "recall", "random_precision_baseline", "precision_lift_over_random", "lead_days", "early_awareness_gate_passed",
    ])
    write_csv(OUTPUT / "collector_early_awareness_false_positives.csv", false_positives, list(prediction_rows[0].keys()) if prediction_rows else ["canonical_product_id"])
    write_csv(OUTPUT / "collector_early_awareness_false_negatives.csv", false_negatives, list(false_negatives[0].keys()) if false_negatives else ["canonical_product_id", "checkpoint_day"])
    write_csv(OUTPUT / "collector_lorwyn_standalone_probabilistic_forecasts.csv", lorwyn_rows, [
        "canonical_product_id", "product_name", "horizon_days", "explicit_method_id", "current_price", "p10_price",
        "p25_price", "median_price", "p75_price", "p90_price", "mean_price", "median_expected_return",
        "probability_of_loss", "probability_of_50pct_gain", "probability_of_doubling", "simulation_count",
        "comparable_products_used", "comparable_product_ids", "supply_status", "supply_overlay_status", "forecast_status",
        "current_ebay_data_used", "production_forecast_authorized", "ranking_authorized", "purchase_recommendation_authorized",
    ])

    summary = {
        "block_name": "Collector Early-Awareness Backtest and Lorwyn Standalone Forecast Authorization",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "truth_products": len(truth_rows),
        "actual_breakouts": breakout_count,
        "breakout_threshold": round(threshold, 6),
        "checkpoint_prediction_rows": len(prediction_rows),
        "metric_rows": len(metric_rows),
        "early_awareness_selection_gate_passed": best_gate,
        "lorwyn_forecast_rows": len(lorwyn_rows),
        "lorwyn_distinct_methods": len({row["explicit_method_id"] for row in lorwyn_rows}),
        "lorwyn_comparable_products_used": len(used_comps),
        "lorwyn_forecast_authorized_with_elevated_uncertainty": len(lorwyn_rows) == 6,
        "lorwyn_supply_status": contract["lorwyn"]["supply_status"],
        "lorwyn_supply_overlay_status": contract["lorwyn"]["supply_overlay_status"],
        "current_ebay_data_used": False,
        "production_forecast_authorized": False,
        "ranking_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": contract["expected_status"] if not failures else "FAIL_COLLECTOR_EARLY_AWARENESS_AND_LORWYN_FORECAST_AUTHORIZATION",
    }
    (OUTPUT / "collector_early_awareness_lorwyn_forecast_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
