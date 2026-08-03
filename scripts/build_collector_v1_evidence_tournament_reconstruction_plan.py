from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_evidence_tournament_contract_v1.json"
FOUNDATION_DIR = ROOT / "data/governance/permanence/certification/collector_v1_august1_snapshot_bound_current_foundation"
FOUNDATION = FOUNDATION_DIR / "collector_v1_august1_snapshot_bound_current_foundation.csv"
FOUNDATION_CERT = FOUNDATION_DIR / "collector_v1_august1_snapshot_bound_current_foundation_certification.json"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_evidence_tournament_reconstruction_plan"
SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    generated_at = datetime.now(timezone.utc).isoformat()
    required = [CONTRACT, FOUNDATION, FOUNDATION_CERT]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    OUT.mkdir(parents=True, exist_ok=True)

    if missing:
        summary = {
            "block_name": "Collector V1 Evidence Tournament Reconstruction Plan",
            "generated_at_utc": generated_at,
            "critical_failures": [f"missing_required_files:{'|'.join(missing)}"],
            "status": "FAIL_COLLECTOR_V1_EVIDENCE_TOURNAMENT_RECONSTRUCTION_INPUTS_MISSING",
        }
        (OUT / "collector_v1_evidence_tournament_reconstruction_plan_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, indent=2))
        return 1 if args.strict else 0

    contract = read_json(CONTRACT)
    certification = read_json(FOUNDATION_CERT)
    foundation = pd.read_csv(FOUNDATION, dtype=str, encoding="utf-8-sig").fillna("")

    horizons = contract["required_forecast_horizons"]
    horizon_ids = [item["horizon_id"] for item in horizons]
    required_outputs = set(contract["required_product_outputs"])
    required_lineage = set(contract["required_lineage"])
    mtg_owns = set(contract["domain_boundary"]["mtg_owns"])
    uip_owns = set(contract["domain_boundary"]["uip_owns"])

    rows = []
    for _, product in foundation.iterrows():
        product_id = str(product.get("tcgplayer_product_id", "")).strip()
        product_name = str(product.get("product_name", "")).strip()
        route = str(product.get("forecast_route", "")).strip()
        limited_history = str(product.get("comparable_only_forecast_required", "False")).lower() == "true"
        for horizon in horizons:
            rows.append({
                "tcgplayer_product_id": product_id,
                "product_name": product_name,
                "forecast_route": route,
                "horizon_id": horizon["horizon_id"],
                "horizon_days": horizon["days"],
                "selection_method": horizon["selection_method"],
                "point_in_time_backtest_required": True,
                "model_tournament_required": True,
                "comparable_selection_required": limited_history,
                "breakout_validation_required": limited_history,
                "supply_demand_ablation_required": True,
                "monte_carlo_required": horizon["horizon_id"] in {"3_year", "5_year"},
                "mtg_owned_output": True,
                "uip_may_rewrite_output": False,
                "purchase_recommendation_authorized": False,
                "source_snapshot_id": str(product.get("source_snapshot_id", "")),
            })

    matrix = pd.DataFrame(rows)
    matrix_path = OUT / "collector_v1_evidence_tournament_reconstruction_matrix.csv"
    matrix.to_csv(matrix_path, index=False)

    checks = {
        "foundation_certified": certification.get("current_foundation_certified") is True,
        "forecast_ranking_rebuild_authorized": certification.get("forecast_ranking_rebuild_authorized") is True,
        "foundation_has_50_products": len(foundation) == 50,
        "foundation_product_ids_unique": bool(foundation["tcgplayer_product_id"].is_unique),
        "five_required_horizons_present": horizon_ids == ["90_day", "180_day", "365_day", "3_year", "5_year"],
        "all_250_product_horizon_rows_present": len(matrix) == 250,
        "all_products_receive_all_horizons": bool(matrix.groupby("tcgplayer_product_id")["horizon_id"].nunique().eq(5).all()),
        "all_horizons_use_tournament_selection": bool(matrix["model_tournament_required"].all()),
        "long_horizons_require_monte_carlo": bool(matrix.loc[matrix["horizon_id"].isin(["3_year", "5_year"]), "monte_carlo_required"].all()),
        "short_horizons_do_not_require_monte_carlo": bool((~matrix.loc[matrix["horizon_id"].isin(["90_day", "180_day", "365_day"]), "monte_carlo_required"]).all()),
        "all_rows_require_supply_demand_ablation": bool(matrix["supply_demand_ablation_required"].all()),
        "all_outputs_owned_by_mtg": bool(matrix["mtg_owned_output"].all()),
        "uip_cannot_rewrite_mtg_outputs": bool((~matrix["uip_may_rewrite_output"]).all()),
        "purchase_recommendations_remain_unauthorized": bool((~matrix["purchase_recommendation_authorized"]).all()),
        "all_snapshot_ids_match": bool(matrix["source_snapshot_id"].eq(SNAPSHOT_ID).all()),
        "contract_has_required_outputs": len(required_outputs) >= 30,
        "contract_has_required_lineage": {
            "source_snapshot_id",
            "source_bundle_sha256",
            "source_price_authority_sha256",
            "source_listing_authority_sha256",
            "source_feature_authority_sha256",
            "model_generated_at_utc",
            "code_commit_sha",
            "tournament_run_id",
            "training_cutoff",
        }.issubset(required_lineage),
        "domain_ownership_is_separated": bool(mtg_owns) and bool(uip_owns) and mtg_owns.isdisjoint(uip_owns),
        "fixed_weights_not_required": all(
            token not in json.dumps(contract).lower()
            for token in ["direct_history_weight", "comparable_weight", "fundamental_weight"]
        ),
    }

    critical_failures = [name for name, passed in checks.items() if not bool(passed)]
    ready = not critical_failures
    summary = {
        "block_name": "Collector V1 Evidence Tournament Reconstruction Plan",
        "block_version": "1.0.0",
        "governing_contract": f"{contract['contract_name']} v{contract['contract_version']}",
        "generated_at_utc": generated_at,
        "source_snapshot_id": SNAPSHOT_ID,
        "foundation_sha256": sha256(FOUNDATION),
        "contract_sha256": sha256(CONTRACT),
        "matrix_path": str(matrix_path.relative_to(ROOT)),
        "matrix_sha256": sha256(matrix_path),
        "governed_product_count": int(foundation["tcgplayer_product_id"].nunique()),
        "required_horizons": horizon_ids,
        "product_horizon_rows": len(matrix),
        "mtg_owned_measurement_count": len(mtg_owns),
        "uip_owned_decision_count": len(uip_owns),
        "required_product_output_count": len(required_outputs),
        "required_lineage_field_count": len(required_lineage),
        "checks": {name: bool(value) for name, value in checks.items()},
        "critical_failures": critical_failures,
        "reconstruction_execution_authorized": ready,
        "forecast_generation_authorized": False,
        "ranking_generation_authorized": False,
        "purchase_recommendations_authorized": False,
        "status": (
            "PASS_COLLECTOR_V1_EVIDENCE_TOURNAMENT_RECONSTRUCTION_PLAN"
            if ready
            else "FAIL_COLLECTOR_V1_EVIDENCE_TOURNAMENT_RECONSTRUCTION_PLAN"
        ),
    }
    (OUT / "collector_v1_evidence_tournament_reconstruction_plan_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if ready else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
