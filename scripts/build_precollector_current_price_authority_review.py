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
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_current_price_authority_review_contract_v1.json"
LIVE_BUILDER = ROOT / "scripts/build_precollector_live_current_price_collection.py"
LIVE_DIR = ROOT / "artifacts/precollector/live_current_price_collection"
OUTPUT_DIR = ROOT / "artifacts/precollector/current_price_authority_review"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def split_reasons(value: object) -> list[str]:
    return [item.strip() for item in str(value or "").split(";") if item.strip()]


def validate(authority: pd.DataFrame, contract: dict) -> None:
    expected = int(contract["expected_product_count"])
    if len(authority) != expected:
        raise RuntimeError(f"CURRENT_PRICE_REVIEW_COUNT_DRIFT: {len(authority)}")
    if authority["tcgplayer_product_id"].astype(str).duplicated().any():
        raise RuntimeError("DUPLICATE_CURRENT_PRICE_PRODUCT_ID")
    candidates = authority[authority["current_price_authority_status"].eq(contract["accepted_candidate_status"])]
    if len(candidates) < int(contract["minimum_authority_candidate_count"]):
        raise RuntimeError("CURRENT_PRICE_AUTHORITY_EMPTY")
    market = pd.to_numeric(candidates["market_price"], errors="coerce")
    if market.isna().any() or market.le(0).any():
        raise RuntimeError("NONPOSITIVE_MARKET_PRICE_IN_AUTHORITY")
    if candidates["price_selection_status"].ne(contract["accepted_selection_status"]).any():
        raise RuntimeError("NONUNIQUE_NORMAL_SUBTYPE_IN_AUTHORITY")
    if candidates["admission_status"].ne(contract["accepted_admission_status"]).any():
        raise RuntimeError("SOURCE_ADMISSION_DRIFT_IN_AUTHORITY")
    age = pd.to_numeric(candidates["observation_age_hours"], errors="coerce")
    if age.isna().any() or age.gt(float(contract["maximum_observation_age_hours"])).any():
        raise RuntimeError("STALE_OBSERVATION_IN_AUTHORITY")
    blocked = authority[authority["current_price_authority_status"].eq("BLOCKED")]
    if blocked["blocking_reasons"].fillna("").astype(str).str.strip().eq("").any():
        raise RuntimeError("BLOCKED_PRODUCT_WITHOUT_REASON")


def main() -> int:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    root = ROOT / "artifacts/precollector"
    if root.exists():
        shutil.rmtree(root)
    completed = subprocess.run([sys.executable, str(LIVE_BUILDER)], cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"LIVE_COLLECTION_REBUILD_FAILED: {completed.returncode}")

    source_path = LIVE_DIR / "precollector_live_current_price_authority_v1.csv"
    observations_path = LIVE_DIR / "precollector_live_current_price_observations_v1.csv"
    if not source_path.is_file() or not observations_path.is_file():
        raise RuntimeError("LIVE_CURRENT_PRICE_INPUT_MISSING")

    authority = pd.read_csv(source_path, low_memory=False)
    validate(authority, contract)
    authorized = authority[authority["current_price_authority_status"].eq(contract["accepted_candidate_status"])].copy()
    blocked = authority[authority["current_price_authority_status"].eq("BLOCKED")].copy()

    authorized["governed_current_price"] = pd.to_numeric(authorized["market_price"], errors="raise")
    authorized["current_price_authority_status"] = "CURRENT_PRICE_AUTHORIZED"
    authorized["historical_append_authorized"] = False
    authorized["forecast_authorized"] = False
    authorized["ranking_authorized"] = False
    authorized["purchase_recommendation_authorized"] = False

    reason_counts: dict[str, int] = {}
    for value in blocked["blocking_reasons"]:
        for reason in split_reasons(value):
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    blocker_summary = pd.DataFrame(
        [{"blocking_reason": key, "product_count": value} for key, value in sorted(reason_counts.items())]
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    authorized_path = OUTPUT_DIR / outputs["authorized_csv"]
    blocked_path = OUTPUT_DIR / outputs["blocked_csv"]
    blocker_summary_path = OUTPUT_DIR / outputs["blocker_summary_csv"]
    authorized.to_csv(authorized_path, index=False)
    blocked.to_csv(blocked_path, index=False)
    blocker_summary.to_csv(blocker_summary_path, index=False)

    summary = {
        "certification_status": "PASS_PRECOLLECTOR_CURRENT_PRICE_AUTHORITY_REVIEW_BUILD",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "canonical_product_rows": len(authority),
        "current_price_authorized_rows": len(authorized),
        "blocked_rows": len(blocked),
        "blocker_reason_counts": reason_counts,
        "historical_append_authorized": False,
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
        "next_stage": contract["next_stage_if_certified"],
    }
    summary_path = OUTPUT_DIR / outputs["summary_json"]
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "live_authority_input_sha256": sha256_file(source_path),
        "live_observations_input_sha256": sha256_file(observations_path),
        "authorized_sha256": sha256_file(authorized_path),
        "blocked_sha256": sha256_file(blocked_path),
        "blocker_summary_sha256": sha256_file(blocker_summary_path),
        "scope_mutation_detected": False,
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_CURRENT_PRICE_AUTHORITY_REVIEW_BUILD")
    print(f"CANONICAL_PRODUCT_ROWS={len(authority)}")
    print(f"CURRENT_PRICE_AUTHORIZED_ROWS={len(authorized)}")
    print(f"BLOCKED_ROWS={len(blocked)}")
    for reason, count in sorted(reason_counts.items()):
        print(f"BLOCKER_{reason}={count}")
    print("NEXT_STAGE=PRECOLLECTOR_HISTORICAL_PRICE_AUTHORITY")
    print("HISTORICAL_APPEND_AUTHORIZED=FALSE")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
