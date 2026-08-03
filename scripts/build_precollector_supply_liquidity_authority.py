from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_supply_liquidity_authority_contract_v1.json"
HISTORICAL_CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_historical_price_authority_review_contract_v1.json"
HISTORICAL_BUILDER = ROOT / "scripts/build_precollector_historical_price_authority_review.py"
HISTORICAL_DIR = ROOT / "artifacts/precollector/historical_price_authority_review"
OUTPUT_DIR = ROOT / "artifacts/precollector/supply_liquidity_authority"
COLLECTOR_SUPPLY = ROOT / "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline/collector_ebay_day_one_product_supply_snapshot.csv"
COLLECTOR_LEDGER = ROOT / "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline/collector_ebay_day_one_accepted_listing_ledger.csv"


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


def normalized_ids(frame: pd.DataFrame, column: str) -> pd.Series:
    return frame[column].fillna("").astype(str).str.strip()


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    historical_contract = load_json(HISTORICAL_CONTRACT_PATH)

    precollector_root = ROOT / "artifacts/precollector"
    if precollector_root.exists():
        shutil.rmtree(precollector_root)
    run([sys.executable, str(HISTORICAL_BUILDER)])

    eligibility_path = HISTORICAL_DIR / historical_contract["outputs"]["model_eligibility_csv"]
    required_paths = [eligibility_path, COLLECTOR_SUPPLY, COLLECTOR_LEDGER]
    missing = [str(path.relative_to(ROOT)) for path in required_paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"SUPPLY_LIQUIDITY_INPUT_MISSING:{missing}")

    eligibility = pd.read_csv(eligibility_path, dtype=str).fillna("")
    supply = pd.read_csv(COLLECTOR_SUPPLY, low_memory=False)
    ledger = pd.read_csv(COLLECTOR_LEDGER, low_memory=False)

    if len(eligibility) != int(contract["expected_product_count"]):
        raise RuntimeError(f"ELIGIBILITY_COUNT_DRIFT:{len(eligibility)}")
    candidate_count = int(eligibility["model_input_status"].eq("MODEL_INPUT_CANDIDATE").sum())
    if candidate_count != int(contract["expected_model_input_candidate_count"]):
        raise RuntimeError(f"MODEL_INPUT_CANDIDATE_COUNT_DRIFT:{candidate_count}")
    if len(supply) != int(contract["collector_supply_snapshot_expected_rows"]):
        raise RuntimeError(f"COLLECTOR_SUPPLY_ROW_COUNT_DRIFT:{len(supply)}")
    if len(ledger) != int(contract["collector_accepted_listing_ledger_expected_rows"]):
        raise RuntimeError(f"COLLECTOR_LEDGER_ROW_COUNT_DRIFT:{len(ledger)}")

    required_supply_columns = {
        "canonical_product_id",
        "tcgplayer_product_id",
        "product_name",
        "accepted_listing_count",
        "median_listing_price",
        "supply_observation_date",
    }
    missing_supply_columns = sorted(required_supply_columns - set(supply.columns))
    if missing_supply_columns:
        raise RuntimeError(f"COLLECTOR_SUPPLY_SCHEMA_DRIFT:{missing_supply_columns}")

    eligibility["canonical_product_id"] = normalized_ids(eligibility, "canonical_product_id")
    supply["canonical_product_id"] = normalized_ids(supply, "canonical_product_id")
    if eligibility["canonical_product_id"].duplicated().any():
        raise RuntimeError("DUPLICATE_PRECOLLECTOR_CANONICAL_PRODUCT_ID")
    if supply["canonical_product_id"].duplicated().any():
        raise RuntimeError("DUPLICATE_COLLECTOR_SUPPLY_CANONICAL_PRODUCT_ID")

    supply["accepted_listing_count"] = pd.to_numeric(supply["accepted_listing_count"], errors="coerce")
    supply["median_listing_price"] = pd.to_numeric(supply["median_listing_price"], errors="coerce")
    supply["supply_observation_date"] = pd.to_datetime(supply["supply_observation_date"], errors="coerce").dt.date
    invalid_supply = supply[
        supply["accepted_listing_count"].isna()
        | supply["median_listing_price"].isna()
        | supply["supply_observation_date"].isna()
    ]
    if not invalid_supply.empty:
        raise RuntimeError(f"INVALID_COLLECTOR_SUPPLY_ROWS:{len(invalid_supply)}")

    expected_date = date.fromisoformat(contract["collector_supply_observation_date"])
    if set(supply["supply_observation_date"]) != {expected_date}:
        raise RuntimeError("COLLECTOR_SUPPLY_OBSERVATION_DATE_DRIFT")
    age_days = (date.today() - expected_date).days
    if age_days < 0:
        raise RuntimeError("FUTURE_SUPPLY_OBSERVATION_DATE")

    supply_subset = supply[[
        "canonical_product_id",
        "tcgplayer_product_id",
        "product_name",
        "accepted_listing_count",
        "distinct_seller_count" if "distinct_seller_count" in supply.columns else "canonical_product_id",
        "seller_concentration" if "seller_concentration" in supply.columns else "canonical_product_id",
        "median_listing_price",
        "listing_price_dispersion" if "listing_price_dispersion" in supply.columns else "canonical_product_id",
        "supply_category" if "supply_category" in supply.columns else "canonical_product_id",
        "supply_observation_date",
        "source_snapshot_id" if "source_snapshot_id" in supply.columns else "canonical_product_id",
    ]].copy()
    supply_subset = supply_subset.loc[:, ~supply_subset.columns.duplicated()]
    supply_subset = supply_subset.rename(columns={
        "product_name": "collector_supply_product_name",
        "tcgplayer_product_id": "collector_supply_tcgplayer_product_id",
    })

    review = eligibility.merge(
        supply_subset,
        on="canonical_product_id",
        how="left",
        validate="one_to_one",
        indicator="collector_supply_join",
    )
    review["collector_supply_identity_match"] = review["collector_supply_join"].eq("both")
    review["supply_evidence_age_days"] = age_days

    listing_count = pd.to_numeric(review.get("accepted_listing_count"), errors="coerce").fillna(0)
    median_price = pd.to_numeric(review.get("median_listing_price"), errors="coerce").fillna(0)
    fresh = age_days <= int(contract["maximum_supply_age_days"])
    supply_ok = (
        review["collector_supply_identity_match"]
        & listing_count.ge(int(contract["minimum_accepted_listing_count"]))
        & median_price.ge(float(contract["minimum_positive_median_listing_price"]))
        & fresh
    )
    review["supply_liquidity_status"] = supply_ok.map({
        True: "SUPPLY_LIQUIDITY_AUTHORIZED",
        False: "SUPPLY_LIQUIDITY_BLOCKED",
    })

    reasons: list[str] = []
    final_status: list[str] = []
    for _, row in review.iterrows():
        row_reasons: list[str] = []
        if row["model_input_status"] != "MODEL_INPUT_CANDIDATE":
            row_reasons.append("CURRENT_AND_HISTORY_AUTHORITY_REQUIRED")
        if not bool(row["collector_supply_identity_match"]):
            row_reasons.append("PRECOLLECTOR_SUPPLY_EVIDENCE_REQUIRED")
        else:
            if float(row.get("accepted_listing_count") or 0) < int(contract["minimum_accepted_listing_count"]):
                row_reasons.append("POSITIVE_ACCEPTED_LISTING_COUNT_REQUIRED")
            if float(row.get("median_listing_price") or 0) < float(contract["minimum_positive_median_listing_price"]):
                row_reasons.append("POSITIVE_MEDIAN_LISTING_PRICE_REQUIRED")
            if not fresh:
                row_reasons.append("FRESH_SUPPLY_EVIDENCE_REQUIRED")
        reasons.append(";".join(row_reasons))
        final_status.append(
            "SUPPLY_ADJUSTED_MODEL_INPUT_CANDIDATE"
            if row["model_input_status"] == "MODEL_INPUT_CANDIDATE"
            and row["supply_liquidity_status"] == "SUPPLY_LIQUIDITY_AUTHORIZED"
            else "SUPPLY_ADJUSTED_MODEL_INPUT_BLOCKED"
        )

    review["supply_liquidity_blocking_reasons"] = reasons
    review["supply_adjusted_model_input_status"] = final_status
    review["forecast_authorized"] = False
    review["ranking_authorized"] = False
    review["purchase_recommendation_authorized"] = False
    review["automatic_execution_authorized"] = False

    authority = review[review["supply_liquidity_status"].eq("SUPPLY_LIQUIDITY_AUTHORIZED")].copy()
    blocked = review[review["supply_liquidity_status"].eq("SUPPLY_LIQUIDITY_BLOCKED")].copy()
    overlap = review[review["collector_supply_identity_match"]].copy()
    candidate_supply_authorized = int(
        review["supply_adjusted_model_input_status"].eq("SUPPLY_ADJUSTED_MODEL_INPUT_CANDIDATE").sum()
    )
    candidate_supply_blocked = candidate_count - candidate_supply_authorized
    next_stage = (
        contract["next_stage_if_full_candidate_coverage"]
        if candidate_supply_blocked == 0
        else contract["next_stage_if_incomplete_candidate_coverage"]
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    authority_path = OUTPUT_DIR / outputs["authority_csv"]
    eligibility_output = OUTPUT_DIR / outputs["model_eligibility_csv"]
    blocked_path = OUTPUT_DIR / outputs["blocked_products_csv"]
    overlap_path = OUTPUT_DIR / outputs["source_overlap_csv"]
    authority.to_csv(authority_path, index=False)
    review.to_csv(eligibility_output, index=False)
    blocked.to_csv(blocked_path, index=False)
    overlap.to_csv(overlap_path, index=False)

    summary = {
        "certification_status": "PASS_PRECOLLECTOR_SUPPLY_LIQUIDITY_AUTHORITY_BUILD",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "canonical_product_rows": len(review),
        "model_input_candidate_rows": candidate_count,
        "collector_supply_source_rows": len(supply),
        "collector_accepted_listing_rows": len(ledger),
        "collector_supply_identity_overlap_rows": int(review["collector_supply_identity_match"].sum()),
        "supply_liquidity_authorized_rows": len(authority),
        "supply_liquidity_blocked_rows": len(blocked),
        "supply_adjusted_model_input_candidate_rows": candidate_supply_authorized,
        "supply_adjusted_model_input_blocked_rows": candidate_supply_blocked,
        "supply_evidence_age_days": age_days,
        "next_stage": next_stage,
        "historical_append_authorized": False,
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
    }
    summary_path = OUTPUT_DIR / outputs["summary_json"]
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "historical_contract_sha256": sha256_file(HISTORICAL_CONTRACT_PATH),
        "historical_eligibility_sha256": sha256_file(eligibility_path),
        "collector_supply_snapshot_sha256": sha256_file(COLLECTOR_SUPPLY),
        "collector_accepted_listing_ledger_sha256": sha256_file(COLLECTOR_LEDGER),
        "authority_sha256": sha256_file(authority_path),
        "model_eligibility_sha256": sha256_file(eligibility_output),
        "blocked_products_sha256": sha256_file(blocked_path),
        "source_overlap_sha256": sha256_file(overlap_path),
        "cross_lane_identity_borrowing_detected": False,
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print("PASS_PRECOLLECTOR_SUPPLY_LIQUIDITY_AUTHORITY_BUILD")
    print(f"CANONICAL_PRODUCT_ROWS={len(review)}")
    print(f"MODEL_INPUT_CANDIDATE_ROWS={candidate_count}")
    print(f"COLLECTOR_SUPPLY_SOURCE_ROWS={len(supply)}")
    print(f"COLLECTOR_ACCEPTED_LISTING_ROWS={len(ledger)}")
    print(f"COLLECTOR_SUPPLY_IDENTITY_OVERLAP_ROWS={summary['collector_supply_identity_overlap_rows']}")
    print(f"SUPPLY_LIQUIDITY_AUTHORIZED_ROWS={len(authority)}")
    print(f"SUPPLY_LIQUIDITY_BLOCKED_ROWS={len(blocked)}")
    print(f"SUPPLY_ADJUSTED_MODEL_INPUT_CANDIDATE_ROWS={candidate_supply_authorized}")
    print(f"SUPPLY_ADJUSTED_MODEL_INPUT_BLOCKED_ROWS={candidate_supply_blocked}")
    print(f"NEXT_STAGE={next_stage}")
    print("HISTORICAL_APPEND_AUTHORIZED=FALSE")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
