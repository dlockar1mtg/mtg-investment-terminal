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
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_horizon_specific_tournament_architecture_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/horizon_specific_tournament_architecture"


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

    upstream = ROOT / contract["upstream_output_directory"]
    product_path = upstream / "precollector_79_product_forecast_input_certification.csv"
    horizon_input_path = upstream / "precollector_79_product_horizon_tournament_input_matrix.csv"
    summary_path = upstream / "precollector_forecast_input_assembly_method_certification_summary.json"
    for path in [product_path, horizon_input_path, summary_path]:
        if not path.is_file():
            raise RuntimeError(f"UPSTREAM_OUTPUT_MISSING:{path.name}")

    products = pd.read_csv(product_path, dtype=str).fillna("")
    horizon_input = pd.read_csv(horizon_input_path, dtype=str).fillna("")
    upstream_summary = load_json(summary_path)
    diagnostics: list[dict] = []

    horizons = contract["forecast_horizons"]
    if len(products) != int(contract["expected_active_product_count"]):
        diagnostics.append({"severity": "BLOCKING", "code": "ACTIVE_PRODUCT_COUNT_DRIFT", "detail": str(len(products))})
    if len(horizons) != int(contract["expected_horizon_count"]):
        diagnostics.append({"severity": "BLOCKING", "code": "HORIZON_COUNT_DRIFT", "detail": str(len(horizons))})
    if upstream_summary.get("certification_status") != "PASS":
        diagnostics.append({"severity": "BLOCKING", "code": "UPSTREAM_NOT_CERTIFIED", "detail": str(upstream_summary.get("certification_status"))})

    architecture_rows: list[dict] = []
    eligibility_rows: list[dict] = []
    policy = contract["validation_policy"]
    for horizon in horizons:
        architecture_rows.append({
            "horizon_code": horizon["horizon_code"],
            "horizon_days": horizon["horizon_days"],
            "horizon_display_name": horizon["display_name"],
            "independent_tournament_required": True,
            "rolling_origin_required": policy["rolling_origin_required"],
            "minimum_test_origins_when_available": policy["minimum_test_origins_when_available"],
            "promotion_requires_baseline_improvement": policy["promotion_requires_baseline_improvement"],
            "promotion_requires_stability": policy["promotion_requires_stability"],
            "promotion_requires_uncertainty_output": policy["promotion_requires_uncertainty_output"],
            "cross_horizon_winner_reuse_prohibited_without_competing": policy["no_cross_horizon_winner_reuse_without_competing"],
            "horizon_winner_selected": False,
            "forecast_generation_authorized": False,
        })
        for route, models in contract["route_model_families"].items():
            for model in models:
                eligibility_rows.append({
                    "horizon_code": horizon["horizon_code"],
                    "horizon_days": horizon["horizon_days"],
                    "forecast_method": route,
                    "candidate_model": model,
                    "candidate_eligible": True,
                    "baseline_model": model in contract["required_baselines"],
                    "winner_selected": False,
                    "forecast_generation_authorized": False,
                })

    architecture = pd.DataFrame(architecture_rows)
    eligibility = pd.DataFrame(eligibility_rows)
    validation_rows = []
    for metric in policy["metrics"]:
        validation_rows.append({
            "metric": metric,
            "required_for_every_horizon": True,
            "used_for_winner_selection": True,
            "forecast_generation_authorized": False,
        })
    validation = pd.DataFrame(validation_rows)

    expected_matrix_rows = int(contract["expected_active_product_count"]) * int(contract["expected_horizon_count"])
    if len(horizon_input) != expected_matrix_rows:
        diagnostics.append({"severity": "BLOCKING", "code": "UPSTREAM_HORIZON_MATRIX_DRIFT", "detail": str(len(horizon_input))})
    if architecture["horizon_code"].nunique() != int(contract["expected_horizon_count"]):
        diagnostics.append({"severity": "BLOCKING", "code": "ARCHITECTURE_HORIZON_COVERAGE_FAILURE", "detail": ""})
    route_count = products["forecast_method"].nunique()
    if route_count != len(contract["route_model_families"]):
        diagnostics.append({"severity": "BLOCKING", "code": "ROUTE_COVERAGE_DRIFT", "detail": str(route_count)})

    diagnostics_frame = pd.DataFrame(diagnostics, columns=["severity", "code", "detail"])
    blocking = int(diagnostics_frame["severity"].eq("BLOCKING").sum()) if not diagnostics_frame.empty else 0
    status = "PASS" if blocking == 0 else "REVIEW_REQUIRED"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    frames = {
        outputs["horizon_architecture_csv"]: architecture,
        outputs["route_model_eligibility_csv"]: eligibility.sort_values(["horizon_days", "forecast_method", "candidate_model"]),
        outputs["validation_policy_csv"]: validation,
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
        "active_product_rows": len(products),
        "forecast_horizon_count": len(architecture),
        "product_horizon_input_rows": len(horizon_input),
        "route_count": route_count,
        "candidate_model_eligibility_rows": len(eligibility),
        "validation_metric_rows": len(validation),
        "blocking_diagnostic_rows": blocking,
        "independent_tournament_per_horizon": True,
        "next_stage": contract["next_stage_if_certified"],
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_analysis_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
        "uip_delivery_authorized": False,
    }
    summary_out = OUTPUT_DIR / outputs["summary_json"]
    summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "upstream_product_input_sha256": sha256_file(product_path),
        "upstream_horizon_input_sha256": sha256_file(horizon_input_path),
        "output_sha256": {name: sha256_file(path) for name, path in sorted(output_paths.items())},
        "forecast_generation_authorized": False,
    }
    manifest_out = OUTPUT_DIR / outputs["manifest_json"]
    manifest_out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_HORIZON_SPECIFIC_TOURNAMENT_ARCHITECTURE_BUILD" if status == "PASS" else "REVIEW_PRECOLLECTOR_HORIZON_SPECIFIC_TOURNAMENT_ARCHITECTURE_BUILD")
    print(f"ACTIVE_PRODUCT_ROWS={len(products)}")
    print(f"FORECAST_HORIZON_COUNT={len(architecture)}")
    print(f"PRODUCT_HORIZON_INPUT_ROWS={len(horizon_input)}")
    print(f"ROUTE_COUNT={route_count}")
    print(f"CANDIDATE_MODEL_ELIGIBILITY_ROWS={len(eligibility)}")
    print(f"VALIDATION_METRIC_ROWS={len(validation)}")
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
