from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
FOUNDATION_DIR = ROOT / "data/governance/permanence/certification/collector_v1_august1_snapshot_bound_current_foundation"
FOUNDATION = FOUNDATION_DIR / "collector_v1_august1_snapshot_bound_current_foundation.csv"
FOUNDATION_CERT = FOUNDATION_DIR / "collector_v1_august1_snapshot_bound_current_foundation_certification.json"
STANDARD = ROOT / "config/mtg/standards/mtg_forecasting_standard_v1.json"
ROUTER = ROOT / "config/mtg/governance/collector_forecast_method_router_v1.json"
COMPARABLE_POLICY = ROOT / "config/mtg/evidence/collector_comparable_selection_v1.json"
COMPARABLE_TARGETS = ROOT / "data/operations/collector_comparable_selection/candidate_v1_0_0/collector_comparable_target_summary.csv"
COMPARABLE_PAIRS = ROOT / "data/operations/collector_comparable_selection/candidate_v1_0_0/collector_comparable_pair_scores.csv"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_forecast_ranking_execution_readiness"
KEY = "tcgplayer_product_id"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")


def first(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    return next((name for name in names if name in frame.columns), None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    generated = datetime.now(timezone.utc).isoformat()
    required_files = [FOUNDATION, FOUNDATION_CERT, STANDARD, ROUTER, COMPARABLE_POLICY]
    missing = [str(path.relative_to(ROOT)) for path in required_files if not path.is_file()]
    if missing:
        summary = {
            "block_name": "Collector V1 Forecast and Ranking Execution Readiness",
            "generated_at_utc": generated,
            "critical_failures": [f"missing_required_files:{'|'.join(missing)}"],
            "status": "FAIL_COLLECTOR_V1_FORECAST_RANKING_READINESS_INPUTS_MISSING",
        }
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "collector_v1_forecast_ranking_execution_readiness_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1 if args.strict else 0

    foundation = read_csv(FOUNDATION)
    cert = read_json(FOUNDATION_CERT)
    standard = read_json(STANDARD)
    router = read_json(ROUTER)
    comparable_policy = read_json(COMPARABLE_POLICY)

    method_col = first(foundation, ("forecast_route", "forecast_method"))
    name_col = first(foundation, ("product_name", "canonical_product_name"))
    if KEY not in foundation.columns or not method_col:
        raise RuntimeError("Certified foundation lacks governed product identity or method route")

    supported = set(standard["lanes"]["COLLECTOR_BOOSTER"]["supported_methods"])
    horizons = list(standard.get("forecast_horizons_years", []))
    scenarios = list(standard.get("scenario_names", []))
    required_outputs = set(standard.get("required_product_output_fields", []))
    required_lineage = {
        "source_snapshot_id", "source_bundle_sha256", "source_price_authority_sha256",
        "source_listing_authority_sha256", "source_feature_authority_sha256", "model_generated_at_utc",
    }

    targets = read_csv(COMPARABLE_TARGETS) if COMPARABLE_TARGETS.is_file() else pd.DataFrame()
    pairs = read_csv(COMPARABLE_PAIRS) if COMPARABLE_PAIRS.is_file() else pd.DataFrame()
    target_id_col = first(targets, ("target_product_id", "tcgplayer_product_id", "investment_product_id")) if not targets.empty else None
    pair_target_col = first(pairs, ("target_product_id", "tcgplayer_product_id", "investment_product_id")) if not pairs.empty else None
    selected_col = first(pairs, ("selected", "is_selected")) if not pairs.empty else None

    target_ids = set(targets[target_id_col].astype(str).str.removeprefix("TCGPLAYER-").str.replace(r"\.0$", "", regex=True)) if target_id_col else set()
    selected_pair_counts: dict[str, int] = {}
    if pair_target_col and selected_col:
        selected = pairs[pairs[selected_col].astype(str).str.lower().isin({"true", "1", "yes"})].copy()
        selected[pair_target_col] = selected[pair_target_col].astype(str).str.removeprefix("TCGPLAYER-").str.replace(r"\.0$", "", regex=True)
        selected_pair_counts = selected.groupby(pair_target_col).size().astype(int).to_dict()

    matrix_rows = []
    for _, row in foundation.iterrows():
        product_id = str(row[KEY]).strip()
        method = str(row[method_col]).strip()
        comparable_route = method in {"COMPARABLE_PRODUCT_ADJUSTED", "FUNDAMENTAL_COMPARABLE_HYBRID"}
        direct_route = method in {"DIRECT_HISTORY_CALIBRATED", "DIRECT_HISTORY_LIMITED"}
        history_count = int(float(str(row.get("history_observation_count", "0") or "0")))
        selected_count = int(selected_pair_counts.get(product_id, 0))
        matrix_rows.append({
            KEY: product_id,
            "product_name": str(row.get(name_col, "")) if name_col else "",
            "forecast_method": method,
            "method_supported": method in supported,
            "direct_history_route": direct_route,
            "direct_history_observations": history_count,
            "direct_history_requirement_satisfied": (not direct_route) or history_count > 0,
            "comparable_route": comparable_route,
            "comparable_target_record_present": (not comparable_route) or product_id in target_ids,
            "selected_comparable_count": selected_count,
            "selected_comparable_evidence_present": (not comparable_route) or selected_count > 0 or method == "FUNDAMENTAL_COMPARABLE_HYBRID",
            "confidence_penalty_required": str(row.get("confidence_penalty_required", "False")),
            "wider_uncertainty_required": str(row.get("wider_uncertainty_required", "False")),
            "forecast_output_required": True,
            "purchase_recommendation_authorized": False,
            "source_snapshot_id": str(row.get("source_snapshot_id", "")),
        })

    matrix = pd.DataFrame(matrix_rows)
    checks = {
        "foundation_certified": cert.get("current_foundation_certified") is True,
        "forecast_ranking_rebuild_authorized": cert.get("forecast_ranking_rebuild_authorized") is True,
        "foundation_has_50_products": len(matrix) == 50,
        "all_product_ids_unique": bool(matrix[KEY].is_unique),
        "all_methods_supported": bool(matrix["method_supported"].all()),
        "all_direct_routes_have_history": bool(matrix["direct_history_requirement_satisfied"].all()),
        "all_comparable_routes_have_target_record": bool(matrix["comparable_target_record_present"].all()),
        "all_comparable_routes_have_selected_evidence_or_hybrid": bool(matrix["selected_comparable_evidence_present"].all()),
        "all_products_remain_forecast_required": bool(matrix["forecast_output_required"].all()),
        "all_snapshot_ids_match": bool(matrix["source_snapshot_id"].eq(SNAPSHOT_ID).all()),
        "standard_horizons_are_1_3_5": horizons == [1, 3, 5],
        "standard_scenarios_are_downside_base_upside": scenarios == ["DOWNSIDE", "BASE", "UPSIDE"],
        "standard_requires_full_forecast_disclosure": {
            "forecast_1y", "forecast_3y", "forecast_5y", "confidence_score", "uncertainty_width",
            "comparable_products_used", "comparable_selection_basis",
        }.issubset(required_outputs),
        "foundation_contains_required_lineage": required_lineage.issubset(set(foundation.columns)),
        "purchase_recommendations_remain_unauthorized": bool(matrix["purchase_recommendation_authorized"].eq(False).all()),
    }

    # Numerical projection weights/rates are governed material parameters. The canonical standard
    # establishes outputs and routes but does not itself approve a Collector execution policy.
    policy_text = json.dumps(comparable_policy).lower() + json.dumps(router).lower() + json.dumps(standard).lower()
    has_execution_policy = all(token in policy_text for token in ("direct_history_weight", "comparable_weight", "fundamental_weight")) and any(
        token in policy_text for token in ("annual_rate", "growth_rate", "scenario_rate", "projection_rate")
    )
    checks["approved_numerical_execution_policy_present"] = has_execution_policy

    integrity_checks = {key: value for key, value in checks.items() if key != "approved_numerical_execution_policy_present"}
    integrity_passed = all(bool(value) for value in integrity_checks.values())
    execution_policy_ready = bool(checks["approved_numerical_execution_policy_present"])
    if integrity_passed and execution_policy_ready:
        status = "PASS_COLLECTOR_V1_FORECAST_RANKING_EXECUTION_READY"
    elif integrity_passed:
        status = "READY_FOR_GOVERNED_NUMERICAL_EXECUTION_POLICY"
    else:
        status = "FAIL_COLLECTOR_V1_FORECAST_RANKING_READINESS"

    OUT.mkdir(parents=True, exist_ok=True)
    matrix_path = OUT / "collector_v1_forecast_ranking_product_readiness.csv"
    matrix.to_csv(matrix_path, index=False)
    summary = {
        "block_name": "Collector V1 Forecast and Ranking Execution Readiness",
        "block_version": "1.0.0",
        "governing_standard": f"{standard.get('standard_name')} v{standard.get('standard_version')}",
        "generated_at_utc": generated,
        "source_snapshot_id": SNAPSHOT_ID,
        "foundation_sha256": sha256(FOUNDATION),
        "readiness_matrix_path": str(matrix_path.relative_to(ROOT)),
        "readiness_matrix_sha256": sha256(matrix_path),
        "governed_product_count": len(matrix),
        "method_distribution": matrix["forecast_method"].value_counts().sort_index().to_dict(),
        "direct_history_route_products": int(matrix["direct_history_route"].sum()),
        "comparable_route_products": int(matrix["comparable_route"].sum()),
        "forecast_horizons_years": horizons,
        "scenario_names": scenarios,
        "required_product_output_field_count": len(required_outputs),
        "checks": {key: bool(value) for key, value in checks.items()},
        "integrity_failures": [key for key, value in integrity_checks.items() if not bool(value)],
        "governed_policy_gap": None if execution_policy_ready else {
            "gap": "APPROVED_COLLECTOR_NUMERICAL_FORECAST_EXECUTION_POLICY_NOT_FOUND",
            "required_scope": [
                "route-specific direct/comparable/fundamental weights",
                "1y/3y/5y downside/base/upside rate construction",
                "confidence score construction",
                "uncertainty width construction",
                "ranking factor weights and tie-breaking",
            ],
            "reason": "The standard requires approval for weight and threshold changes; no values were invented.",
        },
        "forecast_generation_authorized": integrity_passed and execution_policy_ready,
        "ranking_generation_authorized": integrity_passed and execution_policy_ready,
        "purchase_recommendations_authorized": False,
        "status": status,
    }
    (OUT / "collector_v1_forecast_ranking_execution_readiness_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if integrity_passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
