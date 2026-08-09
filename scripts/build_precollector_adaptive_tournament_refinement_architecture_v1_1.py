from __future__ import annotations

import csv
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE_BUILDER = ROOT / "scripts/build_precollector_adaptive_tournament_refinement_architecture.py"
BASE_CONTRACT = ROOT / "config/mtg/standards/precollector_adaptive_tournament_refinement_architecture_contract_v1.json"
RECOVERY_CONTRACT = ROOT / "config/mtg/standards/precollector_adaptive_tournament_refinement_architecture_recovery_contract_v1_1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/adaptive_tournament_refinement_architecture"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parameter_combinations(grid: dict[str, list[Any]], limit: int) -> list[dict[str, Any]]:
    names = list(grid)
    values = [grid[name] for name in names]
    rows: list[dict[str, Any]] = []
    for combo in itertools.product(*values):
        rows.append(dict(zip(names, combo)))
        if len(rows) >= limit:
            break
    return rows


def load_base_builder():
    spec = importlib.util.spec_from_file_location("precollector_round_two_architecture_base", BASE_BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError("BASE_ARCHITECTURE_BUILDER_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    base_contract = json.loads(BASE_CONTRACT.read_text(encoding="utf-8"))
    recovery = json.loads(RECOVERY_CONTRACT.read_text(encoding="utf-8"))

    base_module = load_base_builder()
    base_exit = int(base_module.main())

    outputs = base_contract["outputs"]
    group_path = OUTPUT_DIR / outputs["group_registry_csv"]
    contender_path = OUTPUT_DIR / outputs["contender_registry_csv"]
    parameter_path = OUTPUT_DIR / outputs["parameter_registry_csv"]
    boundary_path = OUTPUT_DIR / outputs["boundary_policy_csv"]
    summary_path = OUTPUT_DIR / outputs["summary_json"]
    manifest_path = OUTPUT_DIR / outputs["manifest_json"]

    required = [group_path, contender_path, parameter_path, boundary_path, summary_path]
    for path in required:
        if not path.is_file():
            raise RuntimeError(f"BASE_ARCHITECTURE_OUTPUT_MISSING:{path.name}")

    groups = read_csv(group_path)
    contenders = read_csv(contender_path)
    parameters = read_csv(parameter_path)
    boundaries = read_csv(boundary_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    contenders_by_group: dict[str, list[dict[str, str]]] = {}
    for row in contenders:
        contenders_by_group.setdefault(row["refinement_group_id"], []).append(row)
    parameters_by_group: dict[str, list[dict[str, str]]] = {}
    for row in parameters:
        parameters_by_group.setdefault(row["refinement_group_id"], []).append(row)

    recovered_groups: list[str] = []
    min_fallback = int(recovery["minimum_per_fallback_group"])
    max_per_group = int(recovery["maximum_per_group"])

    for group in groups:
        if group.get("refinement_mode") != "EVIDENCE_RECOVERY_CHALLENGE":
            continue
        group_id = group["refinement_group_id"]
        route = group["forecast_method"]
        current_rows = parameters_by_group.setdefault(group_id, [])
        if len(current_rows) >= min_fallback:
            continue

        governed_models = recovery["governed_recovery_models_by_route"].get(route, [])
        existing_models = [row["model_name"] for row in contenders_by_group.setdefault(group_id, [])]
        rank = len(existing_models)
        generated = len(current_rows)

        for model in governed_models:
            if model not in existing_models:
                rank += 1
                contender = {
                    "refinement_group_id": group_id,
                    "contender_rank": rank,
                    "model_name": model,
                    "advancement_reason": "GOVERNED_ROUTE_EVIDENCE_RECOVERY_SEED",
                    "round_one_winner_indicator": "False",
                    "baseline_indicator": str(model == "NAIVE_LAST_VALUE"),
                    "fallback_recovery_indicator": "True",
                }
                contenders.append(contender)
                contenders_by_group[group_id].append(contender)
                existing_models.append(model)

            grid = base_contract["parameter_grids"].get(model, {"governed_default": ["DEFAULT"]})
            remaining = max_per_group - generated
            if remaining <= 0:
                break
            combos = parameter_combinations(grid, remaining)
            existing_for_model = sum(1 for row in current_rows if row["model_name"] == model)
            for combo_index, params in enumerate(combos, start=existing_for_model + 1):
                if generated >= max_per_group:
                    break
                candidate = {
                    "refinement_group_id": group_id,
                    "candidate_id": f"{group_id}-REC-{model}-{combo_index:03d}",
                    "model_name": model,
                    "parameter_json": json.dumps(params, sort_keys=True, separators=(",", ":")),
                    "round_one_winner_indicator": str(model == group.get("round_one_winner")),
                    "baseline_indicator": str(model == "NAIVE_LAST_VALUE"),
                    "discovery_fold_role": "INNER_DISCOVERY",
                    "champion_fold_role": "OUTER_UNTOUCHED_CHALLENGE",
                    "multiple_testing_penalty_required": "True",
                    "complexity_penalty_required": "True",
                    "boundary_review_required": "True",
                    "current_only_features_used": "False",
                }
                parameters.append(candidate)
                current_rows.append(candidate)
                generated += 1

            existing_boundary_keys = {
                (row["refinement_group_id"], row["model_name"], row["parameter_name"])
                for row in boundaries
            }
            for parameter_name, values in grid.items():
                key = (group_id, model, parameter_name)
                if key in existing_boundary_keys:
                    continue
                numeric = bool(values) and all(isinstance(v, (int, float)) for v in values)
                boundaries.append({
                    "refinement_group_id": group_id,
                    "model_name": model,
                    "parameter_name": parameter_name,
                    "grid_minimum": min(values) if numeric else str(values[0]) if values else "",
                    "grid_maximum": max(values) if numeric else str(values[-1]) if values else "",
                    "expand_if_best_at_minimum": "True",
                    "expand_if_best_at_maximum": "True",
                    "maximum_expansion_rounds": base_contract["boundary_expansion"]["maximum_expansion_rounds"],
                    "expansion_factor": base_contract["boundary_expansion"]["continuous_parameter_expansion_factor"],
                    "retain_original_grid": "True",
                })

            if generated >= min_fallback:
                break

        group["contender_count"] = str(len(contenders_by_group[group_id]))
        if len(current_rows) >= min_fallback:
            recovered_groups.append(group_id)

    remaining_failures: list[str] = []
    for failure in summary.get("critical_failures", []):
        if not str(failure).startswith("INSUFFICIENT_REFINEMENT_CANDIDATES:"):
            remaining_failures.append(str(failure))

    counts = {group_id: len(rows) for group_id, rows in parameters_by_group.items()}
    for group in groups:
        minimum = (
            int(base_contract["candidate_limits"]["minimum_per_competitive_group"])
            if group.get("refinement_mode") == "COMPETITIVE_REFINEMENT"
            else min_fallback
        )
        observed = counts.get(group["refinement_group_id"], 0)
        if observed < minimum:
            remaining_failures.append(
                f"INSUFFICIENT_REFINEMENT_CANDIDATES:{group['refinement_group_id']}:minimum={minimum}:actual={observed}"
            )

    write_csv(group_path, groups, list(groups[0].keys()))
    write_csv(contender_path, contenders, list(contenders[0].keys()))
    write_csv(parameter_path, parameters, list(parameters[0].keys()))
    write_csv(boundary_path, boundaries, list(boundaries[0].keys()))

    passed = not remaining_failures
    summary.update({
        "certification_status": "PASS" if passed else "FAIL",
        "contender_registry_rows": len(contenders),
        "parameter_candidate_rows": len(parameters),
        "boundary_policy_rows": len(boundaries),
        "critical_failures": remaining_failures,
        "fallback_recovery_seeded_groups": len(recovered_groups),
        "fallback_recovery_seeded_group_ids": recovered_groups,
        "candidate_minimum_lowered": False,
        "round_one_fold_membership_changed": False,
        "next_stage": base_contract["next_stage_if_certified"] if passed else "REPAIR_ADAPTIVE_REFINEMENT_ARCHITECTURE",
        "refinement_execution_authorized": passed,
    })
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest = {
        "base_builder_exit_code": base_exit,
        "base_contract_sha256": sha256_file(BASE_CONTRACT),
        "recovery_contract_sha256": sha256_file(RECOVERY_CONTRACT),
        "repair_scope": recovery["repair_scope"],
        "fallback_recovery_seeded_groups": recovered_groups,
        "outputs": [
            {
                "path": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in sorted(OUTPUT_DIR.iterdir())
            if path.is_file() and path != manifest_path
        ],
        "round_one_fold_membership_changed": False,
        "candidate_minimum_lowered": False,
        "refinement_execution_performed": False,
        "upstream_rebuild_performed": False,
        "network_collection_performed": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_ARCHITECTURE_V1_1" if passed else "FAIL_PRECOLLECTOR_ADAPTIVE_TOURNAMENT_REFINEMENT_ARCHITECTURE_V1_1")
    print(f"FALLBACK_RECOVERY_SEEDED_GROUPS={len(recovered_groups)}")
    print(f"CONTENDER_REGISTRY_ROWS={len(contenders)}")
    print(f"PARAMETER_CANDIDATE_ROWS={len(parameters)}")
    print(f"BOUNDARY_POLICY_ROWS={len(boundaries)}")
    print("CANDIDATE_MINIMUM_LOWERED=FALSE")
    print("ROUND_ONE_FOLD_MEMBERSHIP_CHANGED=FALSE")
    print("REFINEMENT_EXECUTION_PERFORMED=FALSE")
    print("NO_UPSTREAM_REBUILD_PERFORMED=TRUE")
    print("NO_LIVE_NETWORK_COLLECTION_PERFORMED=TRUE")
    print(f"NEXT_STAGE={summary['next_stage']}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
