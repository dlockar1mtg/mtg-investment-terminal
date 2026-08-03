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
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_live_supply_collection_contract_v1.json"
HISTORICAL_AUTHORITY_BUILDER = ROOT / "scripts/build_precollector_historical_price_authority_review.py"
EBAY_RUNNER = ROOT / "scripts/run_daily_ebay_collection.py"
OUTPUT_DIR = ROOT / "artifacts/precollector/live_supply_collection"


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
    precollector_root = ROOT / "artifacts/precollector"
    if precollector_root.exists():
        shutil.rmtree(precollector_root)

    run([sys.executable, str(HISTORICAL_AUTHORITY_BUILDER)])

    source_map = ROOT / contract["product_map_source"]
    eligibility_path = ROOT / contract["eligibility_source"]
    if not source_map.is_file():
        raise RuntimeError(f"PRECOLLECTOR_PRODUCT_MAP_MISSING:{source_map.relative_to(ROOT)}")
    if not eligibility_path.is_file():
        raise RuntimeError(f"PRECOLLECTOR_ELIGIBILITY_MISSING:{eligibility_path.relative_to(ROOT)}")

    product_map = pd.read_csv(source_map, dtype=str).fillna("")
    eligibility = pd.read_csv(eligibility_path, dtype=str).fillna("")
    if len(eligibility) != int(contract["expected_product_count"]):
        raise RuntimeError(f"ELIGIBILITY_COUNT_DRIFT:{len(eligibility)}")
    if "canonical_product_id" not in product_map.columns:
        raise RuntimeError("PRODUCT_MAP_SCHEMA_DRIFT:canonical_product_id")
    if "canonical_product_id" not in eligibility.columns or "model_input_status" not in eligibility.columns:
        raise RuntimeError("ELIGIBILITY_SCHEMA_DRIFT")

    candidates = eligibility[eligibility["model_input_status"].eq("MODEL_INPUT_CANDIDATE")].copy()
    if len(candidates) != int(contract["expected_model_input_candidate_count"]):
        raise RuntimeError(f"MODEL_INPUT_CANDIDATE_COUNT_DRIFT:{len(candidates)}")

    target_ids = set(candidates["canonical_product_id"].astype(str))
    target_map = product_map[product_map["canonical_product_id"].astype(str).isin(target_ids)].copy()
    if len(target_map) != len(target_ids):
        missing = sorted(target_ids - set(target_map["canonical_product_id"].astype(str)))
        raise RuntimeError(f"TARGET_PRODUCT_MAP_RECONCILIATION_FAILED:{missing}")
    if target_map["canonical_product_id"].duplicated().any():
        raise RuntimeError("DUPLICATE_TARGET_CANONICAL_PRODUCT_ID")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    target_map_path = OUTPUT_DIR / outputs["target_product_map_csv"]
    dry_summary_path = OUTPUT_DIR / outputs["dry_run_summary_json"]
    live_summary_path = OUTPUT_DIR / outputs["live_run_summary_json"]
    target_map.to_csv(target_map_path, index=False)

    run([
        sys.executable,
        str(EBAY_RUNNER),
        "--product-map",
        str(target_map_path),
        "--limit-per-product",
        str(contract["limit_per_product"]),
        "--dry-run",
        "--summary-output",
        str(dry_summary_path),
    ])
    dry_summary = load_json(dry_summary_path)
    if dry_summary.get("status") != "DRY_RUN" or dry_summary.get("live_api_called") is not False:
        raise RuntimeError("PRECOLLECTOR_EBAY_DRY_RUN_FAILED")

    run([
        sys.executable,
        str(EBAY_RUNNER),
        "--product-map",
        str(target_map_path),
        "--limit-per-product",
        str(contract["limit_per_product"]),
        "--summary-output",
        str(live_summary_path),
    ])
    live_summary = load_json(live_summary_path)
    if live_summary.get("status") != "PASS" or live_summary.get("live_api_called") is not True:
        raise RuntimeError("PRECOLLECTOR_EBAY_LIVE_COLLECTION_FAILED")

    summary = {
        "certification_status": "PASS_PRECOLLECTOR_LIVE_SUPPLY_COLLECTION_BUILD",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_product_rows": len(target_map),
        "limit_per_product": int(contract["limit_per_product"]),
        "matcher_version": live_summary.get("matcher_version", ""),
        "live_api_called": True,
        "next_stage": contract["next_stage_if_collection_passes"],
        "historical_append_authorized": False,
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
    }
    summary_path = OUTPUT_DIR / outputs["collection_summary_json"]
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "source_product_map_sha256": sha256_file(source_map),
        "eligibility_sha256": sha256_file(eligibility_path),
        "target_product_map_sha256": sha256_file(target_map_path),
        "dry_run_summary_sha256": sha256_file(dry_summary_path),
        "live_run_summary_sha256": sha256_file(live_summary_path),
        "collection_summary_sha256": sha256_file(summary_path),
        "cross_lane_identity_borrowing_detected": False,
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("PASS_PRECOLLECTOR_LIVE_SUPPLY_COLLECTION_BUILD")
    print(f"TARGET_PRODUCT_ROWS={len(target_map)}")
    print(f"LIMIT_PER_PRODUCT={contract['limit_per_product']}")
    print("LIVE_API_CALLED=TRUE")
    print("NEXT_STAGE=PRECOLLECTOR_SUPPLY_AND_LIQUIDITY_AUTHORITY")
    print("HISTORICAL_APPEND_AUTHORIZED=FALSE")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
