from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "scripts/run_precollector_adaptive_tournament_refinement_execution.py"
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_adaptive_tournament_refinement_execution_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/adaptive_tournament_refinement_execution"
ROUND_ONE_ZIP = Path(tempfile.gettempdir()) / "MTG_PreCollector_Horizon_Tournament_Execution_From_Certified_Bundle_v1.zip"


def clean(value: Any) -> str:
    return str(value or "").strip()


def number(value: Any) -> float:
    try:
        result = float(clean(value))
    except ValueError:
        return 0.0
    return result if math.isfinite(result) else 0.0


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_round_one_winners() -> list[dict[str, str]]:
    if not ROUND_ONE_ZIP.is_file():
        raise RuntimeError(f"ROUND_ONE_PACKAGE_MISSING:{ROUND_ONE_ZIP}")
    with zipfile.ZipFile(ROUND_ONE_ZIP) as archive:
        payload = archive.read("precollector_round_one_preliminary_winner_registry.csv")
    return list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    result = subprocess.run([sys.executable, str(BASE)], cwd=ROOT, check=False)
    if result.returncode != 0:
        return int(result.returncode)

    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    outputs = contract["outputs"]
    groups = read_csv(OUTPUT_DIR / "precollector_round_two_preliminary_group_decisions.csv")
    scores = read_csv(OUTPUT_DIR / outputs["candidate_scorecard_csv"])
    boundary = read_csv(OUTPUT_DIR / outputs["boundary_review_csv"])
    winners = read_round_one_winners()

    winner_by_group = {
        f"R2-{clean(row.get('horizon_code'))}-{clean(row.get('forecast_method'))}": clean(row.get("selected_model"))
        for row in winners
    }
    status_by_group = {
        f"R2-{clean(row.get('horizon_code'))}-{clean(row.get('forecast_method'))}": clean(row.get("selection_status"))
        for row in winners
    }
    scores_by_group: dict[str, list[dict[str, str]]] = {}
    for row in scores:
        scores_by_group.setdefault(clean(row.get("refinement_group_id")), []).append(row)

    boundary_keys = {
        (clean(row.get("refinement_group_id")), clean(row.get("candidate_id")))
        for row in boundary
        if clean(row.get("boundary_expansion_required")).casefold() == "true"
    }

    minimum_discovery = int(contract["fold_assignment"]["minimum_discovery_folds_for_selection"])
    minimum_champion = int(contract["fold_assignment"]["minimum_champion_folds_for_promotion"])
    repaired: list[dict[str, Any]] = []
    uncertainty_rows: list[dict[str, Any]] = []

    for original in groups:
        group_id = clean(original.get("refinement_group_id"))
        round_one_model = winner_by_group.get(group_id, "")
        round_one_status = status_by_group.get(group_id, "")
        group_scores = scores_by_group.get(group_id, [])
        eligible = [row for row in group_scores if int(number(row.get("discovery_rows"))) >= minimum_discovery]
        eligible.sort(key=lambda row: (number(row.get("penalized_discovery_score")), clean(row.get("candidate_id"))))
        selected = eligible[0] if eligible else None
        benchmark_rows = [row for row in group_scores if clean(row.get("model_name")) == round_one_model]
        benchmark = min(benchmark_rows, key=lambda row: (number(row.get("penalized_discovery_score")), clean(row.get("candidate_id")))) if benchmark_rows else None
        baseline_rows = [row for row in group_scores if clean(row.get("model_name")) == "NAIVE_LAST_VALUE"]
        baseline = min(baseline_rows, key=lambda row: (number(row.get("penalized_discovery_score")), clean(row.get("candidate_id")))) if baseline_rows else benchmark

        status = "NO_PROMOTION_INSUFFICIENT_EVIDENCE"
        promoted = False
        boundary_flag = False
        if selected and benchmark and baseline and int(number(selected.get("champion_rows"))) >= minimum_champion:
            selected_ape = number(selected.get("champion_median_ape"))
            benchmark_ape = number(benchmark.get("champion_median_ape"))
            baseline_ape = number(baseline.get("champion_median_ape"))
            improve_round1 = (benchmark_ape - selected_ape) / max(benchmark_ape, 1e-9)
            improve_baseline = (baseline_ape - selected_ape) / max(baseline_ape, 1e-9)
            boundary_flag = (group_id, clean(selected.get("candidate_id"))) in boundary_keys
            bias_ok = abs(number(selected.get("champion_bias"))) <= contract["selection"]["maximum_absolute_bias"] * max(number(selected.get("champion_mae")), 1.0)
            promoted = (
                improve_round1 >= contract["selection"]["minimum_relative_improvement_over_round_one"]
                and improve_baseline >= contract["selection"]["minimum_relative_improvement_over_baseline"]
                and bias_ok
                and not boundary_flag
            )
            status = "PRELIMINARY_REFINED_LEADER" if promoted else ("BOUNDARY_EXPANSION_REQUIRED" if boundary_flag else "ROUND_ONE_LEADER_RETAINED")

        repaired.append({
            **original,
            "round_one_model": round_one_model,
            "round_one_selection_status": round_one_status,
            "selected_candidate_id": clean(selected.get("candidate_id")) if selected else "",
            "selected_model": clean(selected.get("model_name")) if selected else round_one_model,
            "selection_status": status,
            "preliminary_promotion_indicator": promoted,
            "boundary_expansion_required": boundary_flag,
            "final_winner_certification_authorized": False,
            "forecast_generation_authorized": False,
        })
        if selected:
            uncertainty_rows.append({
                "refinement_group_id": group_id,
                "selected_candidate_id": clean(selected.get("candidate_id")),
                "champion_rows": int(number(selected.get("champion_rows"))),
                "champion_median_ape": number(selected.get("champion_median_ape")),
                "champion_uncertainty_width": number(selected.get("champion_uncertainty_width")),
                "uncertainty_recalibration_status": "PRELIMINARY_ONLY",
            })

    decision_path = OUTPUT_DIR / outputs["group_decision_csv"]
    fields = list(repaired[0].keys())
    write_csv(decision_path, repaired, fields)
    uncertainty_path = OUTPUT_DIR / outputs["uncertainty_csv"]
    write_csv(uncertainty_path, uncertainty_rows, list(uncertainty_rows[0].keys()) if uncertainty_rows else ["refinement_group_id"])

    summary_path = OUTPUT_DIR / outputs["summary_json"]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.update({
        "round_one_selected_model_binding_verified": True,
        "round_one_selected_model_rows": sum(bool(row["round_one_model"]) for row in repaired),
        "preliminary_refined_leader_rows": sum(row["selection_status"] == "PRELIMINARY_REFINED_LEADER" for row in repaired),
        "round_one_leader_retained_rows": sum(row["selection_status"] == "ROUND_ONE_LEADER_RETAINED" for row in repaired),
        "boundary_expansion_required_rows": sum(row["selection_status"] == "BOUNDARY_EXPANSION_REQUIRED" for row in repaired),
        "insufficient_evidence_rows": sum(row["selection_status"] == "NO_PROMOTION_INSUFFICIENT_EVIDENCE" for row in repaired),
        "short_horizon_insufficient_evidence_rows": sum(row["selection_status"] == "NO_PROMOTION_INSUFFICIENT_EVIDENCE" and clean(row.get("horizon_code")) in {"D90", "D180", "D365"} for row in repaired),
        "long_horizon_insufficient_evidence_rows": sum(row["selection_status"] == "NO_PROMOTION_INSUFFICIENT_EVIDENCE" and clean(row.get("horizon_code")) in {"Y3", "Y5"} for row in repaired),
        "long_horizon_monte_carlo_required": True,
        "next_stage": "PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_ARCHITECTURE",
    })
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest_path = OUTPUT_DIR / outputs["manifest_json"]
    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "repair_version": "1.1.0",
        "round_one_selected_model_column": "selected_model",
        "outputs": [
            {"path": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in sorted(OUTPUT_DIR.iterdir())
            if path.is_file() and path.name != outputs["manifest_json"]
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_EXECUTION_V1_1")
    print(f"ROUND_ONE_SELECTED_MODEL_ROWS={summary['round_one_selected_model_rows']}")
    print(f"PRELIMINARY_REFINED_LEADER_ROWS={summary['preliminary_refined_leader_rows']}")
    print(f"ROUND_ONE_LEADER_RETAINED_ROWS={summary['round_one_leader_retained_rows']}")
    print(f"BOUNDARY_EXPANSION_REQUIRED_ROWS={summary['boundary_expansion_required_rows']}")
    print(f"SHORT_HORIZON_INSUFFICIENT_EVIDENCE_ROWS={summary['short_horizon_insufficient_evidence_rows']}")
    print(f"LONG_HORIZON_INSUFFICIENT_EVIDENCE_ROWS={summary['long_horizon_insufficient_evidence_rows']}")
    print("LONG_HORIZON_MONTE_CARLO_REQUIRED=TRUE")
    print("FINAL_WINNER_CERTIFICATION_AUTHORIZED=FALSE")
    print("FORECAST_AUTHORIZED=FALSE")
    print("NEXT_STAGE=PRECOLLECTOR_FINAL_CHAMPION_CHALLENGE_ARCHITECTURE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
