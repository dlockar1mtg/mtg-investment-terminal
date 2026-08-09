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
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_canonical_universe_freeze_contract_v1.json"
APPROVAL_PATH = ROOT / "config/mtg/governance/precollector_canonical_universe_owner_approval_v1.json"
V7_BUILDER = ROOT / "scripts/build_precollector_final_universe_resolution_v7.py"
V7_OUTPUT = ROOT / "artifacts/precollector/final_universe_resolution"
OUTPUT_DIR = ROOT / "artifacts/precollector/canonical_universe_freeze"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pick(frame: pd.DataFrame, *names: str, required: bool = True) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return frame[name]
    if required:
        raise RuntimeError(f"REQUIRED_COLUMN_MISSING: {names}")
    return pd.Series("", index=frame.index, dtype="object")


def run_v7_builder() -> None:
    if not V7_BUILDER.exists():
        raise RuntimeError(f"V7_BUILDER_MISSING: {V7_BUILDER}")
    completed = subprocess.run(
        [sys.executable, str(V7_BUILDER)],
        cwd=ROOT,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"V7_BUILDER_FAILED: {completed.returncode}")


def build_canonical(ready: pd.DataFrame, approval: dict) -> pd.DataFrame:
    canonical = pd.DataFrame({
        "canonical_product_id": pick(ready, "canonical_product_id").astype(str),
        "governed_asset_key": pick(ready, "governed_asset_key").astype(str),
        "product_name": pick(ready, "product_name_august1", "product_name").astype(str),
        "release_name": pick(ready, "release_or_group_name", "reconciliation_group_name").astype(str),
        "governed_release_date": pick(ready, "governed_release_date").astype(str),
        "release_date_authority": pick(ready, "release_date_authority").astype(str),
        "language": "English",
        "configuration": "INDIVIDUAL_FACTORY_SEALED_BOOSTER_BOX",
        "scope_status": "CANONICAL_INCLUDED_OWNER_APPROVED",
        "owner_approval_id": approval["approval_id"],
    })
    canonical = canonical.sort_values(
        ["governed_release_date", "release_name", "product_name", "canonical_product_id"],
        kind="stable",
    ).reset_index(drop=True)
    return canonical


def validate(canonical: pd.DataFrame, exclusions: pd.DataFrame, contract: dict, approval: dict) -> None:
    expected = int(contract["required_input"]["expected_product_count"])
    if approval.get("decision") != "APPROVE_CERTIFIED_V7_PRECOLLECTOR_UNIVERSE_FOR_CANONICAL_FREEZE":
        raise RuntimeError("OWNER_APPROVAL_DECISION_MISSING")
    if int(approval.get("approved_product_count", -1)) != expected:
        raise RuntimeError("OWNER_APPROVAL_COUNT_DRIFT")
    if canonical["canonical_product_id"].duplicated().any():
        raise RuntimeError("DUPLICATE_CANONICAL_PRODUCT_ID")
    if canonical["governed_asset_key"].duplicated().any():
        raise RuntimeError("DUPLICATE_GOVERNED_ASSET_KEY")
    if len(canonical) != expected:
        raise RuntimeError(f"CANONICAL_COUNT_DRIFT: {len(canonical)}")
    for column in contract["canonical_columns"]:
        if column not in canonical.columns:
            raise RuntimeError(f"CANONICAL_COLUMN_MISSING: {column}")
        if canonical[column].fillna("").astype(str).str.strip().eq("").any():
            raise RuntimeError(f"BLANK_CANONICAL_FIELD: {column}")
    names = canonical["product_name"].str.casefold()
    prohibited = names.str.contains(r"\b(?:draft|play|collector) booster\b|\bcase\b", regex=True)
    if prohibited.any():
        raise RuntimeError("PROHIBITED_PRODUCT_IN_CANONICAL_UNIVERSE")
    if len(exclusions) != int(contract["required_input"]["expected_fresh_exclusion_count"]):
        raise RuntimeError(f"FRESH_EXCLUSION_COUNT_DRIFT: {len(exclusions)}")
    if "fresh_resolution_status" not in exclusions.columns:
        raise RuntimeError("FRESH_EXCLUSION_STATUS_MISSING")
    if exclusions["fresh_resolution_status"].ne("OWNER_EXCLUSION_RECOMMENDED").any():
        raise RuntimeError("NON_EXCLUDED_FRESH_ROW_REMAINS")


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    approval = load_json(APPROVAL_PATH)

    precollector_root = ROOT / "artifacts/precollector"
    if precollector_root.exists():
        shutil.rmtree(precollector_root)
    run_v7_builder()

    ready_path = V7_OUTPUT / "precollector_owner_approval_ready.csv"
    exclusions_path = V7_OUTPUT / "precollector_owner_exclusion_recommended.csv"
    summary_path = V7_OUTPUT / "precollector_final_universe_resolution_summary.json"
    for path in (ready_path, exclusions_path, summary_path):
        if not path.exists():
            raise RuntimeError(f"CERTIFIED_V7_INPUT_MISSING: {path}")

    v7_summary = load_json(summary_path)
    required_summary = {
        "owner_approval_ready_rows": 124,
        "existing_review_or_conflict_rows": 0,
        "fresh_exclusion_recommended_rows": 80,
        "fresh_review_rows": 0,
        "unresolved_release_date_rows": 0,
    }
    for key, expected in required_summary.items():
        if int(v7_summary.get(key, -1)) != expected:
            raise RuntimeError(f"V7_SUMMARY_NOT_FREEZE_READY: {key}={v7_summary.get(key)}")

    ready = pd.read_csv(ready_path, low_memory=False)
    exclusions = pd.read_csv(exclusions_path, low_memory=False)
    canonical = build_canonical(ready, approval)
    validate(canonical, exclusions, contract, approval)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    canonical_path = OUTPUT_DIR / outputs["canonical_universe_csv"]
    excluded_path = OUTPUT_DIR / outputs["excluded_reconciliation_csv"]
    canonical.to_csv(canonical_path, index=False)
    exclusions.to_csv(excluded_path, index=False)
    shutil.copy2(APPROVAL_PATH, OUTPUT_DIR / outputs["owner_approval_json"])

    summary = {
        "certification_status": "PASS_PRECOLLECTOR_CANONICAL_UNIVERSE_FREEZE_BUILD",
        "contract_id": contract["contract_id"],
        "contract_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "owner_approval_id": approval["approval_id"],
        "canonical_product_rows": len(canonical),
        "fresh_exclusion_rows": len(exclusions),
        "unresolved_rows": 0,
        "canonical_universe_sha256": sha256_file(canonical_path),
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
        "next_stage": contract["next_stage_if_certified"],
    }
    summary_output = OUTPUT_DIR / outputs["freeze_summary_json"]
    summary_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "owner_approval_sha256": sha256_file(APPROVAL_PATH),
        "v7_ready_input_sha256": sha256_file(ready_path),
        "v7_exclusion_input_sha256": sha256_file(exclusions_path),
        "v7_summary_input_sha256": sha256_file(summary_path),
        "canonical_universe_sha256": sha256_file(canonical_path),
        "excluded_reconciliation_sha256": sha256_file(excluded_path),
        "certified_v7_review_zip_sha256": approval["certified_v7_review_zip_sha256"],
        "scope_mutation_detected": False,
    }
    (OUTPUT_DIR / outputs["freeze_manifest_json"]).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print("PASS_PRECOLLECTOR_CANONICAL_UNIVERSE_FREEZE_BUILD")
    print(f"CANONICAL_PRODUCT_ROWS={len(canonical)}")
    print(f"FRESH_EXCLUSION_ROWS={len(exclusions)}")
    print("UNRESOLVED_ROWS=0")
    print(f"CANONICAL_UNIVERSE_SHA256={summary['canonical_universe_sha256']}")
    print("NEXT_STAGE=PRECOLLECTOR_CURRENT_PRICE_AUTHORITY")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
