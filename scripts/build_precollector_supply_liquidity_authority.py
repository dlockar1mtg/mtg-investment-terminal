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


def normalize(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    historical_contract = load_json(HISTORICAL_CONTRACT_PATH)

    precollector_root = ROOT / "artifacts/precollector"
    if precollector_root.exists():
        shutil.rmtree(precollector_root)
    run([sys.executable, str(HISTORICAL_BUILDER)])

    eligibility_path = HISTORICAL_DIR / historical_contract["outputs"]["model_eligibility_csv"]
    coverage_path = ROOT / contract["live_coverage_source"]
    listing_path = ROOT / contract["live_listing_source"]
    live_summary_path = ROOT / contract["live_summary_source"]
    required_paths = [eligibility_path, coverage_path, listing_path, live_summary_path]
    missing = [str(path.relative_to(ROOT)) for path in required_paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"SUPPLY_LIQUIDITY_INPUT_MISSING:{missing}")

    eligibility = pd.read_csv(eligibility_path, dtype=str).fillna("")
    coverage = pd.read_csv(coverage_path, dtype=str).fillna("")
    listings = pd.read_csv(listing_path, dtype=str).fillna("")
    live_summary = load_json(live_summary_path)

    if len(eligibility) != int(contract["expected_product_count"]):
        raise RuntimeError(f"ELIGIBILITY_COUNT_DRIFT:{len(eligibility)}")
    candidate_count = int(eligibility["model_input_status"].eq("MODEL_INPUT_CANDIDATE").sum())
    if candidate_count != int(contract["expected_model_input_candidate_count"]):
        raise RuntimeError(f"MODEL_INPUT_CANDIDATE_COUNT_DRIFT:{candidate_count}")
    if len(coverage) != int(contract["expected_live_collection_product_count"]):
        raise RuntimeError(f"LIVE_COVERAGE_PRODUCT_COUNT_DRIFT:{len(coverage)}")
    if len(listings) != int(contract["expected_live_listing_rows"]):
        raise RuntimeError(f"LIVE_LISTING_ROW_COUNT_DRIFT:{len(listings)}")

    expected_summary = {
        "products": int(contract["expected_live_collection_product_count"]),
        "listing_rows": int(contract["expected_live_listing_rows"]),
        "accepted_rows": int(contract["expected_live_accepted_rows"]),
        "review_rows": int(contract["expected_live_review_rows"]),
        "rejected_rows": int(contract["expected_live_rejected_rows"]),
    }
    for key, expected in expected_summary.items():
        if int(live_summary.get(key, -1)) != expected:
            raise RuntimeError(f"LIVE_SUMMARY_COUNT_DRIFT:{key}:{live_summary.get(key)}")
    if live_summary.get("aborted_early") is not False:
        raise RuntimeError("LIVE_COLLECTION_ABORTED_EARLY")
    if live_summary.get("missing_tcgplayer_product_ids"):
        raise RuntimeError("LIVE_COLLECTION_MISSING_PRODUCT_IDS")
    if live_summary.get("matcher_fail_closed") is not True:
        raise RuntimeError("LIVE_MATCHER_NOT_FAIL_CLOSED")

    required_coverage_columns = {
        "canonical_product_id",
        "tcgplayer_product_id",
        "canonical_product_name",
        "accepted_listing_count",
        "review_listing_count",
        "rejected_listing_count",
        "median_accepted_landed_price",
        "lowest_accepted_landed_price",
        "accepted_seller_count",
        "coverage_state",
        "source_error",
    }
    missing_columns = sorted(required_coverage_columns - set(coverage.columns))
    if missing_columns:
        raise RuntimeError(f"LIVE_SUPPLY_SCHEMA_DRIFT:{missing_columns}")

    eligibility["tcgplayer_product_id"] = normalize(eligibility["tcgplayer_product_id"])
    coverage["tcgplayer_product_id"] = normalize(coverage["tcgplayer_product_id"])
    if eligibility["tcgplayer_product_id"].duplicated().any():
        raise RuntimeError("DUPLICATE_ELIGIBILITY_TCGPLAYER_PRODUCT_ID")
    if coverage["tcgplayer_product_id"].duplicated().any():
        raise RuntimeError("DUPLICATE_LIVE_COVERAGE_TCGPLAYER_PRODUCT_ID")

    for column in [
        "accepted_listing_count",
        "review_listing_count",
        "rejected_listing_count",
        "median_accepted_landed_price",
        "lowest_accepted_landed_price",
        "accepted_seller_count",
    ]:
        coverage[column] = pd.to_numeric(coverage[column], errors="coerce")

    if coverage[["accepted_listing_count", "review_listing_count", "rejected_listing_count", "accepted_seller_count"]].isna().any().any():
        raise RuntimeError("INVALID_LIVE_SUPPLY_COUNT_VALUES")

    observed = datetime.fromisoformat(str(live_summary["observed_at_utc"]).replace("Z", "+00:00"))
    observed_date = observed.date()
    expected_date = date.fromisoformat(contract["live_supply_observation_date"])
    if observed_date != expected_date:
        raise RuntimeError("LIVE_SUPPLY_OBSERVATION_DATE_DRIFT")
    age_days = (date.today() - observed_date).days
    if age_days < 0:
        raise RuntimeError("FUTURE_SUPPLY_OBSERVATION_DATE")
    if age_days > int(contract["maximum_supply_age_days"]):
        raise RuntimeError(f"STALE_LIVE_SUPPLY_EVIDENCE:{age_days}")

    coverage_subset = coverage[[
        "tcgplayer_product_id",
        "canonical_product_name",
        "accepted_listing_count",
        "review_listing_count",
        "rejected_listing_count",
        "median_accepted_landed_price",
        "lowest_accepted_landed_price",
        "accepted_seller_count",
        "coverage_state",
        "source_error",
    ]].rename(columns={"canonical_product_name": "live_supply_product_name"})

    review = eligibility.merge(
        coverage_subset,
        on="tcgplayer_product_id",
        how="left",
        validate="one_to_one",
        indicator="live_supply_join",
    )
    review["live_supply_identity_match"] = review["live_supply_join"].eq("both")
    review["supply_evidence_age_days"] = age_days

    accepted = pd.to_numeric(review["accepted_listing_count"], errors="coerce").fillna(0)
    sellers = pd.to_numeric(review["accepted_seller_count"], errors="coerce").fillna(0)
    median_price = pd.to_numeric(review["median_accepted_landed_price"], errors="coerce").fillna(0)
    source_clear = normalize(review["source_error"]).eq("")
    strong = review["coverage_state"].eq(contract["required_coverage_state"])

    supply_ok = (
        review["live_supply_identity_match"]
        & accepted.ge(int(contract["minimum_accepted_listing_count"]))
        & sellers.ge(int(contract["minimum_accepted_seller_count"]))
        & median_price.ge(float(contract["minimum_positive_median_listing_price"]))
        & source_clear
        & strong
    )
    review["supply_liquidity_status"] = supply_ok.map({
        True: "SUPPLY_LIQUIDITY_AUTHORIZED",
        False: "SUPPLY_LIQUIDITY_BLOCKED",
    })

    blocking_reasons: list[str] = []
    adjusted_status: list[str] = []
    for _, row in review.iterrows():
        reasons: list[str] = []
        if row["model_input_status"] != "MODEL_INPUT_CANDIDATE":
            reasons.append("CURRENT_AND_HISTORY_AUTHORITY_REQUIRED")
        if not bool(row["live_supply_identity_match"]):
            reasons.append("PRECOLLECTOR_LIVE_SUPPLY_EVIDENCE_REQUIRED")
        else:
            if float(row.get("accepted_listing_count") or 0) < int(contract["minimum_accepted_listing_count"]):
                reasons.append("MINIMUM_ACCEPTED_LISTINGS_REQUIRED")
            if float(row.get("accepted_seller_count") or 0) < int(contract["minimum_accepted_seller_count"]):
                reasons.append("MINIMUM_DISTINCT_SELLERS_REQUIRED")
            if float(row.get("median_accepted_landed_price") or 0) < float(contract["minimum_positive_median_listing_price"]):
                reasons.append("POSITIVE_MEDIAN_LANDED_PRICE_REQUIRED")
            if str(row.get("coverage_state") or "") != contract["required_coverage_state"]:
                reasons.append("STRONG_MATCH_COVERAGE_REQUIRED")
            if str(row.get("source_error") or "").strip():
                reasons.append("SOURCE_ERROR_PRESENT")
        blocking_reasons.append(";".join(reasons))
        adjusted_status.append(
            "SUPPLY_ADJUSTED_MODEL_INPUT_CANDIDATE"
            if row["model_input_status"] == "MODEL_INPUT_CANDIDATE"
            and row["supply_liquidity_status"] == "SUPPLY_LIQUIDITY_AUTHORIZED"
            else "SUPPLY_ADJUSTED_MODEL_INPUT_BLOCKED"
        )

    review["supply_liquidity_blocking_reasons"] = blocking_reasons
    review["supply_adjusted_model_input_status"] = adjusted_status
    review["forecast_authorized"] = False
    review["ranking_authorized"] = False
    review["purchase_recommendation_authorized"] = False
    review["automatic_execution_authorized"] = False

    authority = review[review["supply_liquidity_status"].eq("SUPPLY_LIQUIDITY_AUTHORIZED")].copy()
    blocked = review[review["supply_liquidity_status"].eq("SUPPLY_LIQUIDITY_BLOCKED")].copy()
    source_coverage = review[review["live_supply_identity_match"]].copy()
    candidate_authorized = int(
        review["supply_adjusted_model_input_status"].eq("SUPPLY_ADJUSTED_MODEL_INPUT_CANDIDATE").sum()
    )
    candidate_blocked = candidate_count - candidate_authorized
    next_stage = (
        contract["next_stage_if_any_candidate_authorized"]
        if candidate_authorized > 0
        else contract["next_stage_if_no_candidate_authorized"]
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    authority_path = OUTPUT_DIR / outputs["authority_csv"]
    eligibility_output = OUTPUT_DIR / outputs["model_eligibility_csv"]
    blocked_path = OUTPUT_DIR / outputs["blocked_products_csv"]
    coverage_output = OUTPUT_DIR / outputs["source_coverage_csv"]
    authority.to_csv(authority_path, index=False)
    review.to_csv(eligibility_output, index=False)
    blocked.to_csv(blocked_path, index=False)
    source_coverage.to_csv(coverage_output, index=False)

    summary = {
        "certification_status": "PASS_PRECOLLECTOR_SUPPLY_LIQUIDITY_AUTHORITY_BUILD",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "canonical_product_rows": len(review),
        "model_input_candidate_rows": candidate_count,
        "live_supply_product_rows": len(coverage),
        "live_listing_rows": len(listings),
        "live_accepted_listing_rows": int(live_summary["accepted_rows"]),
        "live_review_listing_rows": int(live_summary["review_rows"]),
        "live_rejected_listing_rows": int(live_summary["rejected_rows"]),
        "live_supply_identity_overlap_rows": int(review["live_supply_identity_match"].sum()),
        "supply_liquidity_authorized_rows": len(authority),
        "supply_liquidity_blocked_rows": len(blocked),
        "supply_adjusted_model_input_candidate_rows": candidate_authorized,
        "supply_adjusted_model_input_blocked_rows": candidate_blocked,
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
        "live_coverage_sha256": sha256_file(coverage_path),
        "live_listing_sha256": sha256_file(listing_path),
        "live_summary_sha256": sha256_file(live_summary_path),
        "authority_sha256": sha256_file(authority_path),
        "model_eligibility_sha256": sha256_file(eligibility_output),
        "blocked_products_sha256": sha256_file(blocked_path),
        "source_coverage_sha256": sha256_file(coverage_output),
        "cross_lane_identity_borrowing_detected": False,
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("PASS_PRECOLLECTOR_SUPPLY_LIQUIDITY_AUTHORITY_BUILD")
    print(f"CANONICAL_PRODUCT_ROWS={len(review)}")
    print(f"MODEL_INPUT_CANDIDATE_ROWS={candidate_count}")
    print(f"LIVE_SUPPLY_PRODUCT_ROWS={len(coverage)}")
    print(f"LIVE_LISTING_ROWS={len(listings)}")
    print(f"LIVE_ACCEPTED_LISTING_ROWS={live_summary['accepted_rows']}")
    print(f"LIVE_SUPPLY_IDENTITY_OVERLAP_ROWS={summary['live_supply_identity_overlap_rows']}")
    print(f"SUPPLY_LIQUIDITY_AUTHORIZED_ROWS={len(authority)}")
    print(f"SUPPLY_LIQUIDITY_BLOCKED_ROWS={len(blocked)}")
    print(f"SUPPLY_ADJUSTED_MODEL_INPUT_CANDIDATE_ROWS={candidate_authorized}")
    print(f"SUPPLY_ADJUSTED_MODEL_INPUT_BLOCKED_ROWS={candidate_blocked}")
    print(f"NEXT_STAGE={next_stage}")
    print("HISTORICAL_APPEND_AUTHORIZED=FALSE")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
