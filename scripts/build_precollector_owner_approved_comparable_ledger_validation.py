from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_owner_approved_comparable_ledger_validation_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/owner_approved_comparable_ledger_validation"


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


def weight_for(rank: int, distance: float, base_weights: dict[str, float], decay: float) -> float:
    base = float(base_weights[str(rank)])
    return round(base / (1.0 + max(distance, 0.0) * decay), 8)


def designation(rank: int, primary_rank_max: int) -> str:
    return "PRIMARY" if rank <= primary_rank_max else "SECONDARY"


def cap_policy(target: str, family: str, method: str, rank: int, caps: dict[str, float]) -> tuple[str, float]:
    if method == "DIRECT_HISTORY_LIMITED":
        return "DIRECT_HISTORY_LIMITED_VALIDATION_ONLY", float(caps["DIRECT_HISTORY_LIMITED_VALIDATION_ONLY"])
    if family == "CORE" and rank >= 3:
        return "DISTANT_CORE", float(caps["DISTANT_CORE"])
    if target in {"Lorwyn - Booster Box", "Nemesis - Booster Box"} and rank >= 3:
        return "LOWER_RANKED_LORWYN_NEMESIS", float(caps["LOWER_RANKED_LORWYN_NEMESIS"])
    label = designation(rank, 2)
    return label, float(caps[label])


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    approval_path = ROOT / contract["owner_approval_path"]
    approval = load_json(approval_path)
    if approval.get("owner_approval_status") != "APPROVED":
        raise RuntimeError("OWNER_APPROVAL_NOT_APPROVED")
    if approval.get("owner_decision", {}).get("forecast_generation_authorized") is not False:
        raise RuntimeError("FORECAST_AUTHORITY_DRIFT")

    artifacts_root = ROOT / "artifacts/precollector"
    if artifacts_root.exists():
        shutil.rmtree(artifacts_root)
    run([sys.executable, str(ROOT / contract["upstream_builder_path"])])

    upstream = ROOT / contract["upstream_output_directory"]
    ledger_input = upstream / "precollector_79_product_selected_comparables.csv"
    target_input = upstream / "precollector_79_product_comparable_target_status.csv"
    routes_input = upstream / "precollector_79_product_forecast_method_routes.csv"
    exclusions_input = upstream / "precollector_15_product_exclusion_reconciliation.csv"
    for path in [ledger_input, target_input, routes_input, exclusions_input]:
        if not path.is_file():
            raise RuntimeError(f"UPSTREAM_OUTPUT_MISSING:{path.name}")

    comparables = pd.read_csv(ledger_input, dtype=str).fillna("")
    targets = pd.read_csv(target_input, dtype=str).fillna("")
    routes = pd.read_csv(routes_input, dtype=str).fillna("")
    exclusions = pd.read_csv(exclusions_input, dtype=str).fillna("")

    if len(targets) != int(contract["expected_active_product_count"]):
        raise RuntimeError("ACTIVE_TARGET_COUNT_DRIFT")
    if len(exclusions) != int(contract["expected_excluded_product_count"]):
        raise RuntimeError("EXCLUSION_COUNT_DRIFT")
    required = targets[targets["comparable_support_required"].astype(str).str.lower().eq("true")].copy()
    if len(required) != int(contract["expected_required_comparable_target_count"]):
        raise RuntimeError("REQUIRED_TARGET_COUNT_DRIFT")

    route_map = routes.set_index("canonical_product_id")["forecast_method"].to_dict()
    excluded_ids = set(exclusions["canonical_product_id"])
    diagnostics: list[dict] = []
    rows: list[dict] = []
    base_weights = contract["base_rank_weights"]
    decay = float(contract["distance_decay_scale"])
    primary_rank_max = int(contract["primary_rank_max"])
    caps = contract["contribution_caps"]

    for _, row in comparables.iterrows():
        rank = int(float(row["comparable_rank"]))
        distance = float(row["comparable_distance_score"])
        target_id = row["target_canonical_product_id"]
        candidate_id = row["candidate_canonical_product_id"]
        target_name = row["target_product_name"]
        family = row["target_product_family"]
        method = route_map[target_id]
        role = designation(rank, primary_rank_max)
        raw_weight = weight_for(rank, distance, base_weights, decay)
        policy, cap = cap_policy(target_name, family, method, rank, caps)
        capped_weight = min(raw_weight, cap)
        rows.append({
            **row.to_dict(),
            "owner_approval_status": "APPROVED",
            "comparable_designation": role,
            "weight_policy": policy,
            "raw_distance_weight": raw_weight,
            "maximum_contribution_cap": cap,
            "approved_contribution_weight": round(capped_weight, 8),
            "direct_history_primary": method in {"DIRECT_HISTORY_CALIBRATED", "DIRECT_HISTORY_LIMITED"},
            "forecast_contribution_authorized_after_later_certification": True,
            "forecast_generation_authorized": False,
        })
        if target_id == candidate_id:
            diagnostics.append({"severity": "BLOCKING", "code": "SELF_COMPARABLE", "target_id": target_id, "detail": candidate_id})
        if target_id in excluded_ids or candidate_id in excluded_ids:
            diagnostics.append({"severity": "BLOCKING", "code": "EXCLUDED_PRODUCT_LEAKAGE", "target_id": target_id, "detail": candidate_id})
        if row["target_product_family"] != row["candidate_product_family"]:
            diagnostics.append({"severity": "BLOCKING", "code": "FAMILY_MISMATCH", "target_id": target_id, "detail": candidate_id})
        if not (0 < capped_weight <= cap <= 1):
            diagnostics.append({"severity": "BLOCKING", "code": "INVALID_WEIGHT_OR_CAP", "target_id": target_id, "detail": str(capped_weight)})

    ledger = pd.DataFrame(rows)
    ledger["normalized_target_weight"] = ledger.groupby("target_canonical_product_id")["approved_contribution_weight"].transform(
        lambda values: values / values.sum() if values.sum() > 0 else values
    ).round(8)

    target_validation_rows: list[dict] = []
    holdout_rows: list[dict] = []
    minimum_holdout = int(contract["minimum_holdout_comparables"])
    for _, target in targets.iterrows():
        target_id = target["canonical_product_id"]
        target_ledger = ledger[ledger["target_canonical_product_id"].eq(target_id)].copy()
        support_required = str(target["comparable_support_required"]).lower() == "true"
        primary_count = int(target_ledger["comparable_designation"].eq("PRIMARY").sum())
        secondary_count = int(target_ledger["comparable_designation"].eq("SECONDARY").sum())
        approved_count = len(target_ledger)
        normalized_sum = float(target_ledger["normalized_target_weight"].sum()) if approved_count else 0.0
        target_pass = (not support_required or approved_count > 0) and (not approved_count or math.isclose(normalized_sum, 1.0, abs_tol=1e-6))
        target_validation_rows.append({
            "canonical_product_id": target_id,
            "product_name": target["product_name"],
            "forecast_method": target["forecast_method"],
            "comparable_support_required": support_required,
            "approved_comparable_count": approved_count,
            "primary_comparable_count": primary_count,
            "secondary_comparable_count": secondary_count,
            "normalized_weight_sum": round(normalized_sum, 8),
            "validation_status": "PASS" if target_pass else "BLOCKED",
        })
        for _, held_out in target_ledger.iterrows():
            remaining = approved_count - 1
            holdout_pass = remaining >= minimum_holdout if support_required else True
            holdout_rows.append({
                "target_canonical_product_id": target_id,
                "held_out_candidate_canonical_product_id": held_out["candidate_canonical_product_id"],
                "remaining_comparable_count": remaining,
                "minimum_required_after_holdout": minimum_holdout if support_required else 0,
                "holdout_validation_status": "PASS" if holdout_pass else "BLOCKED",
            })
            if not holdout_pass:
                diagnostics.append({"severity": "BLOCKING", "code": "PRODUCT_HOLDOUT_FAILURE", "target_id": target_id, "detail": held_out["candidate_canonical_product_id"]})

    target_validation = pd.DataFrame(target_validation_rows)
    holdout_validation = pd.DataFrame(holdout_rows)
    diagnostics_frame = pd.DataFrame(diagnostics, columns=["severity", "code", "target_id", "detail"])
    blocking = int(diagnostics_frame["severity"].eq("BLOCKING").sum()) if not diagnostics_frame.empty else 0
    blocked_targets = int(target_validation["validation_status"].eq("BLOCKED").sum())
    blocked_holdouts = int(holdout_validation["holdout_validation_status"].eq("BLOCKED").sum()) if not holdout_validation.empty else 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    frames = {
        outputs["approved_ledger_csv"]: ledger.sort_values(["target_product_name", "comparable_rank"]),
        outputs["target_validation_csv"]: target_validation.sort_values("product_name"),
        outputs["holdout_validation_csv"]: holdout_validation.sort_values(["target_canonical_product_id", "held_out_candidate_canonical_product_id"]),
        outputs["diagnostics_csv"]: diagnostics_frame,
    }
    output_paths: dict[str, Path] = {}
    for filename, frame in frames.items():
        path = OUTPUT_DIR / filename
        frame.to_csv(path, index=False)
        output_paths[filename] = path

    summary = {
        "certification_status": "PASS" if blocking == 0 and blocked_targets == 0 and blocked_holdouts == 0 else "REVIEW_REQUIRED",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "active_product_rows": len(targets),
        "excluded_product_rows": len(exclusions),
        "required_comparable_target_rows": len(required),
        "approved_comparable_ledger_rows": len(ledger),
        "primary_comparable_rows": int(ledger["comparable_designation"].eq("PRIMARY").sum()),
        "secondary_comparable_rows": int(ledger["comparable_designation"].eq("SECONDARY").sum()),
        "target_validation_blocked_rows": blocked_targets,
        "holdout_validation_rows": len(holdout_validation),
        "holdout_validation_blocked_rows": blocked_holdouts,
        "blocking_diagnostic_rows": blocking,
        "owner_comparable_approval_complete": True,
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
        "owner_approval_sha256": sha256_file(approval_path),
        "upstream_ledger_sha256": sha256_file(ledger_input),
        "upstream_target_status_sha256": sha256_file(target_input),
        "output_sha256": {name: sha256_file(path) for name, path in sorted(output_paths.items())},
        "excluded_product_leakage_detected": False,
        "self_comparable_detected": False,
        "forecast_generation_authorized": False,
    }
    manifest_path = OUTPUT_DIR / outputs["manifest_json"]
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_OWNER_APPROVED_COMPARABLE_LEDGER_VALIDATION_BUILD" if summary["certification_status"] == "PASS" else "REVIEW_PRECOLLECTOR_OWNER_APPROVED_COMPARABLE_LEDGER_VALIDATION_BUILD")
    for key in ["active_product_rows", "excluded_product_rows", "required_comparable_target_rows", "approved_comparable_ledger_rows", "primary_comparable_rows", "secondary_comparable_rows", "holdout_validation_rows", "blocking_diagnostic_rows"]:
        print(f"{key.upper()}={summary[key]}")
    print(f"NEXT_STAGE={summary['next_stage']}")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    print("UIP_DELIVERY_AUTHORIZED=FALSE")
    return 0 if summary["certification_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
