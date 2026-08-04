from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_forecast_input_assembly_method_certification_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/forecast_input_assembly_method_certification"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str]) -> None:
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"SUBPROCESS_FAILED:{completed.returncode}:{' '.join(command)}")


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    artifacts_root = ROOT / "artifacts/precollector"
    if artifacts_root.exists():
        shutil.rmtree(artifacts_root)
    run([sys.executable, str(ROOT / contract["upstream_builder_path"])])

    routing_dir = ROOT / contract["routing_output_directory"]
    ledger_dir = ROOT / contract["ledger_output_directory"]
    tournament_dir = ROOT / contract["tournament_output_directory"]

    selected_path = routing_dir / "precollector_79_product_selected_universe.csv"
    routes_path = routing_dir / "precollector_79_product_forecast_method_routes.csv"
    exclusions_path = routing_dir / "precollector_15_product_exclusion_reconciliation.csv"
    ledger_path = ledger_dir / "precollector_owner_approved_comparable_ledger.csv"
    tournament_summary_path = tournament_dir / "precollector_comparable_model_tournament_calibration_summary.json"
    tournament_winner_path = tournament_dir / "precollector_comparable_model_tournament_winner.csv"

    required_paths = [selected_path, routes_path, exclusions_path, ledger_path, tournament_summary_path, tournament_winner_path]
    for path in required_paths:
        if not path.is_file():
            raise RuntimeError(f"UPSTREAM_OUTPUT_MISSING:{path}")

    selected = pd.read_csv(selected_path, dtype=str).fillna("")
    routes = pd.read_csv(routes_path, dtype=str).fillna("")
    exclusions = pd.read_csv(exclusions_path, dtype=str).fillna("")
    ledger = pd.read_csv(ledger_path, dtype=str).fillna("")
    tournament_summary = load_json(tournament_summary_path)
    winner = pd.read_csv(tournament_winner_path, dtype=str).fillna("")

    diagnostics: list[dict] = []
    expected_products = int(contract["expected_active_product_count"])
    expected_exclusions = int(contract["expected_excluded_product_count"])
    horizons = contract["forecast_horizons"]

    if len(selected) != expected_products:
        diagnostics.append({"severity": "BLOCKING", "code": "ACTIVE_PRODUCT_COUNT_DRIFT", "detail": str(len(selected))})
    if len(routes) != expected_products:
        diagnostics.append({"severity": "BLOCKING", "code": "METHOD_ROUTE_COUNT_DRIFT", "detail": str(len(routes))})
    if len(exclusions) != expected_exclusions:
        diagnostics.append({"severity": "BLOCKING", "code": "EXCLUSION_COUNT_DRIFT", "detail": str(len(exclusions))})
    if len(horizons) != int(contract["expected_horizon_count"]):
        diagnostics.append({"severity": "BLOCKING", "code": "HORIZON_COUNT_DRIFT", "detail": str(len(horizons))})

    selected_model = str(tournament_summary.get("selected_model", ""))
    if selected_model != contract["required_selected_comparable_model"]:
        diagnostics.append({"severity": "BLOCKING", "code": "COMPARABLE_MODEL_WINNER_DRIFT", "detail": selected_model})
    if winner.empty or str(winner.iloc[0].get("model_name", "")) != selected_model:
        diagnostics.append({"severity": "BLOCKING", "code": "WINNER_ARTIFACT_MISMATCH", "detail": selected_model})

    selected_ids = set(selected["canonical_product_id"])
    route_ids = set(routes["canonical_product_id"])
    excluded_ids = set(exclusions["canonical_product_id"])
    if selected_ids != route_ids:
        diagnostics.append({"severity": "BLOCKING", "code": "PRODUCT_ROUTE_ID_MISMATCH", "detail": str(len(selected_ids ^ route_ids))})
    if selected_ids & excluded_ids:
        diagnostics.append({"severity": "BLOCKING", "code": "EXCLUDED_PRODUCT_LEAKAGE", "detail": str(sorted(selected_ids & excluded_ids))})

    route_subset = routes[[
        "canonical_product_id", "forecast_method", "historical_rows", "history_span_days",
        "accepted_listing_count", "accepted_seller_count", "coverage_state",
        "confidence_penalty_required", "route_version"
    ]].copy()
    product_input = selected.merge(route_subset, on="canonical_product_id", how="left", validate="one_to_one")

    comparable_counts = ledger.groupby("target_canonical_product_id").agg(
        approved_comparable_count=("candidate_canonical_product_id", "count"),
        primary_comparable_count=("comparable_designation", lambda s: int((s == "PRIMARY").sum())),
        secondary_comparable_count=("comparable_designation", lambda s: int((s == "SECONDARY").sum())),
        approved_weight_sum=("normalized_target_weight", lambda s: round(pd.to_numeric(s, errors="coerce").fillna(0).sum(), 8)),
    ).reset_index().rename(columns={"target_canonical_product_id": "canonical_product_id"})
    product_input = product_input.merge(comparable_counts, on="canonical_product_id", how="left")
    for col in ["approved_comparable_count", "primary_comparable_count", "secondary_comparable_count", "approved_weight_sum"]:
        product_input[col] = product_input[col].fillna(0)

    product_input["certified_comparable_model"] = selected_model
    product_input["model_input_status"] = "CERTIFIED_FOR_HORIZON_TOURNAMENT_INPUT"
    product_input["forecast_generation_authorized"] = False

    allowed_methods = set(contract["allowed_forecast_methods"])
    invalid_methods = sorted(set(product_input["forecast_method"]) - allowed_methods)
    if invalid_methods:
        diagnostics.append({"severity": "BLOCKING", "code": "UNSUPPORTED_FORECAST_METHOD", "detail": str(invalid_methods)})
    if product_input["forecast_method"].eq("").any():
        diagnostics.append({"severity": "BLOCKING", "code": "MISSING_FORECAST_METHOD", "detail": str(int(product_input["forecast_method"].eq("").sum()))})
    if product_input["governed_current_price"].eq("").any():
        diagnostics.append({"severity": "BLOCKING", "code": "MISSING_GOVERNED_CURRENT_PRICE", "detail": str(int(product_input["governed_current_price"].eq("").sum()))})

    comparable_required = product_input["forecast_method"].isin(["DIRECT_HISTORY_LIMITED", "COMPARABLE_PRODUCT_ADJUSTED"])
    missing_comparables = product_input[comparable_required & (pd.to_numeric(product_input["approved_comparable_count"], errors="coerce").fillna(0) <= 0)]
    if not missing_comparables.empty:
        diagnostics.append({"severity": "BLOCKING", "code": "REQUIRED_COMPARABLE_SUPPORT_MISSING", "detail": str(len(missing_comparables))})

    horizon_rows: list[dict] = []
    for _, product in product_input.iterrows():
        for horizon in horizons:
            horizon_rows.append({
                "canonical_product_id": product["canonical_product_id"],
                "product_name": product["product_name"],
                "product_family": product["product_family"],
                "forecast_method": product["forecast_method"],
                "certified_comparable_model": selected_model,
                "horizon_code": horizon["horizon_code"],
                "horizon_days": int(horizon["horizon_days"]),
                "horizon_display_name": horizon["display_name"],
                "independent_horizon_tournament_required": True,
                "horizon_winner_selected": False,
                "forecast_generation_authorized": False,
            })
    horizon_matrix = pd.DataFrame(horizon_rows)
    expected_matrix_rows = expected_products * len(horizons)
    if len(horizon_matrix) != expected_matrix_rows:
        diagnostics.append({"severity": "BLOCKING", "code": "HORIZON_MATRIX_ROW_COUNT_DRIFT", "detail": str(len(horizon_matrix))})
    horizon_counts = horizon_matrix.groupby("canonical_product_id")["horizon_code"].nunique()
    if not horizon_counts.eq(len(horizons)).all():
        diagnostics.append({"severity": "BLOCKING", "code": "INCOMPLETE_PRODUCT_HORIZON_COVERAGE", "detail": str(int((~horizon_counts.eq(len(horizons))).sum()))})

    method_certification = product_input.groupby("forecast_method").agg(
        product_count=("canonical_product_id", "count"),
        total_historical_rows=("historical_rows", lambda s: int(pd.to_numeric(s, errors="coerce").fillna(0).sum())),
        comparable_supported_products=("approved_comparable_count", lambda s: int((pd.to_numeric(s, errors="coerce").fillna(0) > 0).sum())),
    ).reset_index()
    method_certification["method_input_certification_status"] = "PASS"
    method_certification["forecast_generation_authorized"] = False

    lineage_rows = [
        {"artifact_role": "PRODUCT_UNIVERSE_AND_CURRENT_EVIDENCE", "path": str(selected_path.relative_to(ROOT)), "sha256": sha256_file(selected_path)},
        {"artifact_role": "FORECAST_METHOD_ROUTES", "path": str(routes_path.relative_to(ROOT)), "sha256": sha256_file(routes_path)},
        {"artifact_role": "EXCLUSION_RECONCILIATION", "path": str(exclusions_path.relative_to(ROOT)), "sha256": sha256_file(exclusions_path)},
        {"artifact_role": "OWNER_APPROVED_COMPARABLE_LEDGER", "path": str(ledger_path.relative_to(ROOT)), "sha256": sha256_file(ledger_path)},
        {"artifact_role": "COMPARABLE_MODEL_TOURNAMENT_SUMMARY", "path": str(tournament_summary_path.relative_to(ROOT)), "sha256": sha256_file(tournament_summary_path)},
        {"artifact_role": "COMPARABLE_MODEL_WINNER", "path": str(tournament_winner_path.relative_to(ROOT)), "sha256": sha256_file(tournament_winner_path)},
    ]
    lineage = pd.DataFrame(lineage_rows)

    diagnostics_frame = pd.DataFrame(diagnostics, columns=["severity", "code", "detail"])
    blocking = int(diagnostics_frame["severity"].eq("BLOCKING").sum()) if not diagnostics_frame.empty else 0
    status = "PASS" if blocking == 0 else "REVIEW_REQUIRED"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    frames = {
        outputs["product_input_csv"]: product_input.sort_values("product_name"),
        outputs["horizon_matrix_csv"]: horizon_matrix.sort_values(["product_name", "horizon_days"]),
        outputs["method_certification_csv"]: method_certification.sort_values("forecast_method"),
        outputs["lineage_csv"]: lineage,
        outputs["diagnostics_csv"]: diagnostics_frame,
    }
    output_paths: dict[str, Path] = {}
    for filename, frame in frames.items():
        path = OUTPUT_DIR / filename
        frame.to_csv(path, index=False)
        output_paths[filename] = path

    summary = {
        "certification_status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "active_product_rows": len(product_input),
        "excluded_product_rows": len(exclusions),
        "forecast_horizon_count": len(horizons),
        "product_horizon_matrix_rows": len(horizon_matrix),
        "forecast_method_rows": len(method_certification),
        "selected_comparable_model": selected_model,
        "blocking_diagnostic_rows": blocking,
        "all_products_method_certified": blocking == 0,
        "all_five_horizons_declared": len(horizons) == 5,
        "independent_horizon_tournaments_required": True,
        "next_stage": contract["next_stage_if_certified"],
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_analysis_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
        "uip_delivery_authorized": False,
    }
    summary_path = OUTPUT_DIR / outputs["summary_json"]
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "input_lineage_sha256": {row["artifact_role"]: row["sha256"] for row in lineage_rows},
        "output_sha256": {name: sha256_file(path) for name, path in sorted(output_paths.items())},
        "active_product_count_mutation_detected": len(product_input) != expected_products,
        "excluded_product_leakage_detected": bool(selected_ids & excluded_ids),
        "horizon_matrix_incomplete": len(horizon_matrix) != expected_matrix_rows,
        "forecast_generation_authorized": False,
    }
    manifest_path = OUTPUT_DIR / outputs["manifest_json"]
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_FORECAST_INPUT_ASSEMBLY_METHOD_CERTIFICATION_BUILD" if status == "PASS" else "REVIEW_PRECOLLECTOR_FORECAST_INPUT_ASSEMBLY_METHOD_CERTIFICATION_BUILD")
    print(f"ACTIVE_PRODUCT_ROWS={len(product_input)}")
    print(f"EXCLUDED_PRODUCT_ROWS={len(exclusions)}")
    print(f"FORECAST_HORIZON_COUNT={len(horizons)}")
    print(f"PRODUCT_HORIZON_MATRIX_ROWS={len(horizon_matrix)}")
    print(f"FORECAST_METHOD_ROWS={len(method_certification)}")
    print(f"SELECTED_COMPARABLE_MODEL={selected_model}")
    print(f"BLOCKING_DIAGNOSTIC_ROWS={blocking}")
    print(f"NEXT_STAGE={contract['next_stage_if_certified']}")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    print("UIP_DELIVERY_AUTHORIZED=FALSE")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
