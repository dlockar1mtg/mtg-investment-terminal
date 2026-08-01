from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_methodology_sensitivity_review_v1.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def num(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def weighted_mean(values: pd.Series, weights: pd.Series) -> float | None:
    v = pd.to_numeric(values, errors="coerce")
    w = pd.to_numeric(weights, errors="coerce")
    mask = v.notna() & w.notna() & (w > 0)
    if not mask.any():
        return None
    return float(np.average(v[mask], weights=w[mask]))


def trimmed_mean(values: pd.Series, proportion: float = 0.10) -> float | None:
    vals = sorted(pd.to_numeric(values, errors="coerce").dropna().tolist())
    if not vals:
        return None
    trim = int(len(vals) * proportion)
    if trim > 0 and len(vals) > trim * 2:
        vals = vals[trim:-trim]
    return float(np.mean(vals))


def blend(history: float | None, comparable: float | None, fundamental: float | None, route: str) -> float | None:
    if route == "DIRECT_HISTORY_CALIBRATED":
        return history
    if route == "COMPARABLE_PRODUCT_ADJUSTED":
        return comparable
    if route == "DIRECT_HISTORY_LIMITED":
        if history is None or comparable is None:
            return None
        return 0.25 * history + 0.75 * comparable + (fundamental or 0.0)
    if route == "FUNDAMENTAL_COMPARABLE_HYBRID":
        if comparable is None:
            return None
        return 0.75 * comparable + 0.25 * (fundamental or 0.0)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = load_json(CONFIG)
    reconciliation_root = ROOT / cfg["inputs"]["reconciliation_root"]
    evidence_root = ROOT / cfg["inputs"]["evidence_root"]
    out_dir = ROOT / cfg["output_directory"]
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "forecasts": reconciliation_root / "collector_reconciled_candidate_forecasts.csv",
        "peers": reconciliation_root / "collector_reconciled_peer_contributions.csv",
        "review": evidence_root / "collector_methodology_product_review.csv",
        "outcomes": evidence_root / "collector_retrospective_outcome_diagnostics.csv",
    }
    failures = [f"missing_input:{name}:{path}" for name, path in paths.items() if not path.exists()]
    if failures:
        result = {"status": "FAIL", "failure_count": len(failures), "failures": failures}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    forecasts = pd.read_csv(paths["forecasts"], low_memory=False)
    peers = pd.read_csv(paths["peers"], low_memory=False)
    review = pd.read_csv(paths["review"], low_memory=False)
    outcomes = pd.read_csv(paths["outcomes"], low_memory=False)

    pid_col = "canonical_tcgplayer_product_id"
    for frame in [forecasts, review, outcomes]:
        if pid_col in frame.columns:
            frame[pid_col] = frame[pid_col].astype(str).str.replace(r"\.0$", "", regex=True)
    peers["target_tcgplayer_product_id"] = peers["target_tcgplayer_product_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    peers["peer_tcgplayer_product_id"] = peers["peer_tcgplayer_product_id"].astype(str).str.replace(r"\.0$", "", regex=True)

    review_flags = review.set_index(pid_col).to_dict("index")
    outcome_map = outcomes.set_index(pid_col).to_dict("index") if pid_col in outcomes.columns else {}

    rows: list[dict[str, Any]] = []
    peer_rows: list[dict[str, Any]] = []
    for _, forecast in forecasts.iterrows():
        pid = str(forecast[pid_col])
        route = str(forecast.get("forecast_method_route", ""))
        base = num(forecast.get("base_annual_rate"))
        history = num(forecast.get("history_component_annual_rate"))
        comparable = num(forecast.get("comparable_component_annual_rate"))
        fundamental = num(forecast.get("fundamental_adjustment_annual_rate")) or 0.0
        target_peers = peers[peers["target_tcgplayer_product_id"] == pid].copy()
        target_peers["peer_return"] = pd.to_numeric(target_peers.get("peer_annualized_retrospective_return"), errors="coerce")
        target_peers["score"] = pd.to_numeric(target_peers.get("similarity_score"), errors="coerce")
        target_peers = target_peers.dropna(subset=["peer_return", "score"])
        target_peers = target_peers[target_peers["score"] > 0]

        baseline_peer = weighted_mean(target_peers["peer_return"], target_peers["score"]) if not target_peers.empty else comparable
        median_peer = float(target_peers["peer_return"].median()) if not target_peers.empty else None
        trimmed_peer = trimmed_mean(target_peers["peer_return"]) if not target_peers.empty else None
        top5 = target_peers.nlargest(5, "score") if not target_peers.empty else target_peers
        top5_peer = weighted_mean(top5["peer_return"], top5["score"]) if not top5.empty else None
        without_dominant = target_peers.drop(target_peers["score"].idxmax()) if len(target_peers) > 1 else target_peers.iloc[0:0]
        no_dominant_peer = weighted_mean(without_dominant["peer_return"], without_dominant["score"]) if not without_dominant.empty else None

        outcome = outcome_map.get(pid, {})
        simple_history = num(outcome.get("simple_return"))
        annual_history = history

        variants = {
            "BASELINE_WEIGHTED_MEAN": blend(history, baseline_peer, fundamental, route),
            "PEER_MEDIAN": blend(history, median_peer, fundamental, route),
            "PEER_TRIMMED_MEAN_10_PERCENT": blend(history, trimmed_peer, fundamental, route),
            "TOP_5_SIMILARITY_WEIGHTED": blend(history, top5_peer, fundamental, route),
            "EXCLUDE_DOMINANT_PEER": blend(history, no_dominant_peer, fundamental, route),
            "SHORT_HISTORY_SIMPLE_RETURN": blend(simple_history if route == "DIRECT_HISTORY_LIMITED" else history, baseline_peer, fundamental, route),
            "SHORT_HISTORY_ANNUALIZED_RETURN": blend(annual_history, baseline_peer, fundamental, route),
        }
        flag = review_flags.get(pid, {})
        valid = [value for value in variants.values() if value is not None and np.isfinite(value)]
        spread = (max(valid) - min(valid)) if valid else None
        row = {
            pid_col: pid,
            "product_name": forecast.get("product_name", ""),
            "forecast_method_route": route,
            "baseline_base_annual_rate": base,
            "variant_min_annual_rate": min(valid) if valid else None,
            "variant_max_annual_rate": max(valid) if valid else None,
            "variant_spread": spread,
            "variant_count": len(valid),
            "sensitivity_review_required": truthy(flag.get("methodology_review_required")) or (spread is not None and spread >= 0.25),
            "short_history_flag": truthy(flag.get("short_history_flag")),
            "extreme_base_rate_flag": truthy(flag.get("extreme_base_rate_flag")),
            "negative_base_rate_flag": truthy(flag.get("negative_base_rate_flag")),
            "high_peer_concentration_flag": truthy(flag.get("high_peer_concentration_flag")),
            "reverse_pair_candidate_used": truthy(flag.get("reverse_pair_candidate_used")),
            "candidate_projection_authorized": False,
            "production_projection_authorized": False,
            "purchase_recommendation_authorized": False,
        }
        row.update({f"variant_{key.lower()}": value for key, value in variants.items()})
        rows.append(row)

        for variant, value in variants.items():
            peer_rows.append({
                pid_col: pid,
                "product_name": forecast.get("product_name", ""),
                "forecast_method_route": route,
                "variant_name": variant,
                "variant_base_annual_rate": value,
                "difference_from_baseline": None if value is None or base is None else value - base,
                "retrospective_diagnostic_only": True,
            })

    product = pd.DataFrame(rows)
    variants = pd.DataFrame(peer_rows)
    product.to_csv(out_dir / "collector_methodology_sensitivity_product_review.csv", index=False)
    variants.to_csv(out_dir / "collector_methodology_sensitivity_variants.csv", index=False)

    route_summary = product.groupby("forecast_method_route", dropna=False).agg(
        product_count=(pid_col, "count"),
        mean_baseline_rate=("baseline_base_annual_rate", "mean"),
        median_variant_spread=("variant_spread", "median"),
        max_variant_spread=("variant_spread", "max"),
        sensitivity_review_required_count=("sensitivity_review_required", "sum"),
        short_history_count=("short_history_flag", "sum"),
        extreme_rate_count=("extreme_base_rate_flag", "sum"),
        negative_rate_count=("negative_base_rate_flag", "sum"),
        high_concentration_count=("high_peer_concentration_flag", "sum"),
    ).reset_index()
    route_summary.to_csv(out_dir / "collector_methodology_sensitivity_route_summary.csv", index=False)

    decisions = pd.DataFrame([
        {"decision_id": "COL-METH-001", "topic": "Symmetric comparable-score reuse", "current_status": "PENDING_OWNER_DECISION", "evidence_output": "collector_methodology_sensitivity_product_review.csv"},
        {"decision_id": "COL-METH-002", "topic": "Short-history annualization", "current_status": "PENDING_OWNER_DECISION", "evidence_output": "collector_methodology_sensitivity_variants.csv"},
        {"decision_id": "COL-METH-003", "topic": "Peer aggregation method", "current_status": "PENDING_OWNER_DECISION", "evidence_output": "collector_methodology_sensitivity_variants.csv"},
        {"decision_id": "COL-METH-004", "topic": "Dominant-peer treatment", "current_status": "PENDING_OWNER_DECISION", "evidence_output": "collector_methodology_sensitivity_variants.csv"},
        {"decision_id": "COL-METH-005", "topic": "Extreme annual-rate treatment", "current_status": "PENDING_OWNER_DECISION", "evidence_output": "collector_methodology_sensitivity_product_review.csv"},
        {"decision_id": "COL-METH-006", "topic": "Japanese FINAL FANTASY hybrid numeric methodology", "current_status": "COMPARABLE_APPROVED_FORMULA_PENDING", "evidence_output": "collector_methodology_sensitivity_product_review.csv"},
    ])
    decisions.to_csv(out_dir / "collector_methodology_sensitivity_owner_decisions.csv", index=False)

    summary = {
        "audit_name": "Collector Methodology Sensitivity Review",
        "audit_version": "1.0.0",
        "status": "PASS",
        "product_count": int(len(product)),
        "variant_row_count": int(len(variants)),
        "route_count": int(product["forecast_method_route"].nunique()),
        "sensitivity_review_required_product_count": int(product["sensitivity_review_required"].sum()),
        "short_history_product_count": int(product["short_history_flag"].sum()),
        "extreme_base_rate_product_count": int(product["extreme_base_rate_flag"].sum()),
        "negative_base_rate_product_count": int(product["negative_base_rate_flag"].sum()),
        "high_peer_concentration_product_count": int(product["high_peer_concentration_flag"].sum()),
        "owner_decision_count": int(len(decisions)),
        "future_information_prohibited": True,
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "failure_count": 0,
        "failures": [],
        "governing_note": "This batch compares inactive diagnostic alternatives without replacing the 51-product baseline or authorizing forecasts, parameters, purchases, or automatic updates."
    }
    (out_dir / "collector_methodology_sensitivity_review_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
