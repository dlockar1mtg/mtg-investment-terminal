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
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_94_product_evidence_comparable_review_contract_v1.json"
SUPPLY_BUILDER = ROOT / "scripts/build_precollector_supply_liquidity_authority.py"
SUPPLY_DIR = ROOT / "artifacts/precollector/supply_liquidity_authority"
HISTORICAL_DIR = ROOT / "artifacts/precollector/historical_price_authority_review"
CURRENT_DIR = ROOT / "artifacts/precollector/current_price_authority_review"
OUTPUT_DIR = ROOT / "artifacts/precollector/94_product_evidence_comparable_review"


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


def classify_family(name: str) -> str:
    value = name.lower()
    if "masters" in value or "master" in value:
        return "MASTERS"
    if any(token in value for token in ["edition", "magic 20", "core set", "magic origins"]):
        return "CORE"
    if any(token in value for token in ["conspiracy", "battlebond", "unstable", "chronicles", "portal"]):
        return "SUPPLEMENTAL"
    return "STANDARD_EXPANSION"


def classify_era(year: int) -> str:
    if year <= 1999:
        return "PRE_2000"
    if year <= 2004:
        return "2000_2004"
    if year <= 2009:
        return "2005_2009"
    if year <= 2014:
        return "2010_2014"
    return "2015_2019"


def classify_price_tier(price: float) -> str:
    if price >= 2500:
        return "VERY_HIGH"
    if price >= 1000:
        return "HIGH"
    if price >= 500:
        return "UPPER_MID"
    if price >= 250:
        return "MID"
    return "LOWER"


def comparable_score(target: pd.Series, candidate: pd.Series) -> float:
    year_gap = abs(int(target["release_year"]) - int(candidate["release_year"]))
    target_price = max(float(target["governed_current_price"]), 0.01)
    candidate_price = max(float(candidate["governed_current_price"]), 0.01)
    price_gap = abs(math.log(target_price / candidate_price))
    family_penalty = 0.0 if target["product_family"] == candidate["product_family"] else 2.0
    era_penalty = 0.0 if target["release_era"] == candidate["release_era"] else 1.0
    return round(year_gap * 0.35 + price_gap * 2.5 + family_penalty + era_penalty, 6)


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    root = ROOT / "artifacts/precollector"
    if root.exists():
        shutil.rmtree(root)
    run([sys.executable, str(SUPPLY_BUILDER)])

    supply_path = SUPPLY_DIR / "precollector_supply_adjusted_model_eligibility_v1.csv"
    historical_path = HISTORICAL_DIR / "precollector_model_input_eligibility_v1.csv"
    current_authorized_path = CURRENT_DIR / "precollector_current_price_authority_v1.csv"
    current_blocked_path = CURRENT_DIR / "precollector_current_price_blocked_v1.csv"
    required = [supply_path, historical_path, current_authorized_path, current_blocked_path]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"REVIEW_INPUT_MISSING:{missing}")

    supply = pd.read_csv(supply_path, dtype=str).fillna("")
    historical = pd.read_csv(historical_path, dtype=str).fillna("")
    current_authorized = pd.read_csv(current_authorized_path, dtype=str).fillna("")
    current_blocked = pd.read_csv(current_blocked_path, dtype=str).fillna("")

    final_universe = supply[supply["model_input_status"].eq("MODEL_INPUT_CANDIDATE")].copy()
    expected = int(contract["expected_final_universe_count"])
    if len(final_universe) != expected:
        raise RuntimeError(f"FINAL_UNIVERSE_COUNT_DRIFT:{len(final_universe)}")
    if final_universe["canonical_product_id"].duplicated().any():
        raise RuntimeError("DUPLICATE_FINAL_UNIVERSE_PRODUCT")

    current = pd.concat([current_authorized, current_blocked], ignore_index=True)
    required_current = {"canonical_product_id", "tcgplayer_product_id", "market_price"}
    if required_current - set(current.columns):
        raise RuntimeError(f"CURRENT_PRICE_SCHEMA_DRIFT:{sorted(required_current - set(current.columns))}")
    current = current[["canonical_product_id", "tcgplayer_product_id", "market_price"]].copy()
    current["canonical_product_id"] = normalize(current["canonical_product_id"])
    current["governed_current_price"] = pd.to_numeric(current["market_price"], errors="coerce")
    if current["canonical_product_id"].duplicated().any():
        raise RuntimeError("DUPLICATE_CURRENT_PRICE_IDENTITY")

    historical_columns = [
        "canonical_product_id", "product_name", "release_date", "historical_rows",
        "distinct_observation_dates", "first_observation", "last_observation",
        "history_span_days", "latest_historical_price"
    ]
    missing_historical = sorted(set(historical_columns) - set(historical.columns))
    if missing_historical:
        raise RuntimeError(f"HISTORICAL_REVIEW_SCHEMA_DRIFT:{missing_historical}")
    historical_subset = historical[historical_columns].copy()

    evidence = final_universe.merge(
        historical_subset,
        on="canonical_product_id",
        how="left",
        validate="one_to_one",
        suffixes=("", "_historical"),
    ).merge(
        current[["canonical_product_id", "tcgplayer_product_id", "governed_current_price"]],
        on="canonical_product_id",
        how="left",
        validate="one_to_one",
        suffixes=("", "_current"),
    )

    if evidence["governed_current_price"].isna().any() or evidence["governed_current_price"].le(0).any():
        raise RuntimeError("FINAL_UNIVERSE_MISSING_POSITIVE_CURRENT_PRICE")

    evidence["release_date"] = pd.to_datetime(evidence["release_date"], errors="coerce")
    if evidence["release_date"].isna().any():
        raise RuntimeError("FINAL_UNIVERSE_MISSING_RELEASE_DATE")
    evidence["release_year"] = evidence["release_date"].dt.year.astype(int)
    evidence["product_family"] = evidence["product_name"].map(classify_family)
    evidence["release_era"] = evidence["release_year"].map(classify_era)
    evidence["price_tier"] = evidence["governed_current_price"].map(classify_price_tier)

    accepted = pd.to_numeric(evidence["accepted_listing_count"], errors="coerce").fillna(0)
    sellers = pd.to_numeric(evidence["accepted_seller_count"], errors="coerce").fillna(0)
    coverage = normalize(evidence["coverage_state"])
    direct = evidence["supply_liquidity_status"].eq("SUPPLY_LIQUIDITY_AUTHORIZED")
    limited = (~direct) & accepted.gt(0) & coverage.ne("AMBIGUOUS_RESULTS")
    evidence["proposed_model_route"] = "COMPARABLE_PRODUCT_ADJUSTED"
    evidence.loc[limited, "proposed_model_route"] = "DIRECT_HISTORY_LIMITED"
    evidence.loc[direct, "proposed_model_route"] = "DIRECT_EVIDENCE"
    evidence["comparable_support_required"] = ~direct
    evidence["confidence_penalty_required"] = ~direct

    high = evidence["governed_current_price"].ge(float(contract["high_price_review_threshold"]))
    very_high = evidence["governed_current_price"].ge(float(contract["very_high_price_review_threshold"]))
    ambiguous = coverage.eq("AMBIGUOUS_RESULTS")
    thin = sellers.lt(int(contract["minimum_direct_sellers"])) | accepted.lt(int(contract["minimum_direct_accepted_listings"]))
    evidence["owner_review_state"] = "STANDARD_REVIEW"
    evidence.loc[thin, "owner_review_state"] = "LIQUIDITY_REVIEW_REQUIRED"
    evidence.loc[high, "owner_review_state"] = "HIGH_PRICE_REVIEW_REQUIRED"
    evidence.loc[very_high, "owner_review_state"] = "VERY_HIGH_PRICE_REVIEW_REQUIRED"
    evidence.loc[ambiguous, "owner_review_state"] = "AMBIGUOUS_EVIDENCE_REVIEW_REQUIRED"

    evidence["owner_model_route_decision"] = "PENDING_OWNER_DECISION"
    evidence["owner_practicality_decision"] = "PENDING_OWNER_DECISION"
    evidence["owner_notes"] = ""
    evidence["forecast_authorized"] = False
    evidence["ranking_authorized"] = False
    evidence["purchase_recommendation_authorized"] = False
    evidence["automatic_execution_authorized"] = False

    donor_pool = evidence[evidence["proposed_model_route"].eq("DIRECT_EVIDENCE")].copy()
    if len(donor_pool) != int(contract["expected_direct_supply_authorized_count"]):
        raise RuntimeError(f"DIRECT_DONOR_COUNT_DRIFT:{len(donor_pool)}")

    comparable_rows: list[dict] = []
    max_comparables = int(contract["maximum_comparables_per_product"])
    for _, target in evidence.iterrows():
        candidates: list[dict] = []
        for _, candidate in donor_pool.iterrows():
            if candidate["canonical_product_id"] == target["canonical_product_id"]:
                continue
            score = comparable_score(target, candidate)
            candidates.append({
                "target_canonical_product_id": target["canonical_product_id"],
                "target_product_name": target["product_name"],
                "target_model_route": target["proposed_model_route"],
                "candidate_canonical_product_id": candidate["canonical_product_id"],
                "candidate_product_name": candidate["product_name"],
                "candidate_release_year": int(candidate["release_year"]),
                "candidate_product_family": candidate["product_family"],
                "candidate_release_era": candidate["release_era"],
                "candidate_current_price": float(candidate["governed_current_price"]),
                "candidate_accepted_listings": int(float(candidate["accepted_listing_count"] or 0)),
                "candidate_accepted_sellers": int(float(candidate["accepted_seller_count"] or 0)),
                "comparable_distance_score": score,
                "same_family": target["product_family"] == candidate["product_family"],
                "same_release_era": target["release_era"] == candidate["release_era"],
                "owner_comparable_decision": "PENDING_OWNER_DECISION",
                "owner_notes": "",
            })
        candidates.sort(key=lambda row: (row["comparable_distance_score"], row["candidate_product_name"]))
        for rank, row in enumerate(candidates[:max_comparables], start=1):
            row["comparable_rank"] = rank
            comparable_rows.append(row)

    comparables = pd.DataFrame(comparable_rows)
    if len(comparables) != expected * max_comparables:
        raise RuntimeError(f"COMPARABLE_MATRIX_COUNT_DRIFT:{len(comparables)}")

    evidence_columns = [
        "canonical_product_id", "tcgplayer_product_id", "product_name", "release_date", "release_year",
        "product_family", "release_era", "governed_current_price", "price_tier",
        "historical_rows", "distinct_observation_dates", "first_observation", "last_observation",
        "history_span_days", "latest_historical_price", "accepted_listing_count",
        "review_listing_count", "rejected_listing_count", "accepted_seller_count",
        "median_accepted_landed_price", "lowest_accepted_landed_price", "coverage_state",
        "supply_liquidity_status", "proposed_model_route", "comparable_support_required",
        "confidence_penalty_required", "owner_review_state", "owner_model_route_decision",
        "owner_practicality_decision", "owner_notes", "forecast_authorized", "ranking_authorized",
        "purchase_recommendation_authorized", "automatic_execution_authorized"
    ]
    missing_evidence = sorted(set(evidence_columns) - set(evidence.columns))
    if missing_evidence:
        raise RuntimeError(f"EVIDENCE_OUTPUT_SCHEMA_DRIFT:{missing_evidence}")
    evidence_output = evidence[evidence_columns].copy().sort_values(["release_date", "product_name"])
    owner_output = evidence_output[[
        "canonical_product_id", "product_name", "release_year", "governed_current_price",
        "accepted_listing_count", "accepted_seller_count", "coverage_state",
        "proposed_model_route", "owner_review_state", "owner_model_route_decision",
        "owner_practicality_decision", "owner_notes"
    ]].copy()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    evidence_path = OUTPUT_DIR / outputs["evidence_review_csv"]
    comparable_path = OUTPUT_DIR / outputs["comparable_matrix_csv"]
    owner_path = OUTPUT_DIR / outputs["owner_decision_review_csv"]
    evidence_output.to_csv(evidence_path, index=False)
    comparables.sort_values(["target_product_name", "comparable_rank"]).to_csv(comparable_path, index=False)
    owner_output.to_csv(owner_path, index=False)

    route_counts = evidence_output["proposed_model_route"].value_counts().to_dict()
    review_counts = evidence_output["owner_review_state"].value_counts().to_dict()
    summary = {
        "certification_status": "PASS_PRECOLLECTOR_94_PRODUCT_EVIDENCE_COMPARABLE_REVIEW_BUILD",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "final_universe_rows": len(evidence_output),
        "direct_evidence_rows": int(route_counts.get("DIRECT_EVIDENCE", 0)),
        "direct_history_limited_rows": int(route_counts.get("DIRECT_HISTORY_LIMITED", 0)),
        "comparable_product_adjusted_rows": int(route_counts.get("COMPARABLE_PRODUCT_ADJUSTED", 0)),
        "comparable_matrix_rows": len(comparables),
        "owner_review_state_counts": review_counts,
        "next_stage": contract["next_stage_if_certified"],
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
    }
    summary_path = OUTPUT_DIR / outputs["summary_json"]
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "supply_input_sha256": sha256_file(supply_path),
        "historical_input_sha256": sha256_file(historical_path),
        "current_authorized_sha256": sha256_file(current_authorized_path),
        "current_blocked_sha256": sha256_file(current_blocked_path),
        "evidence_review_sha256": sha256_file(evidence_path),
        "comparable_matrix_sha256": sha256_file(comparable_path),
        "owner_decision_review_sha256": sha256_file(owner_path),
        "final_universe_mutation_detected": False,
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print("PASS_PRECOLLECTOR_94_PRODUCT_EVIDENCE_COMPARABLE_REVIEW_BUILD")
    print(f"FINAL_UNIVERSE_ROWS={len(evidence_output)}")
    print(f"DIRECT_EVIDENCE_ROWS={summary['direct_evidence_rows']}")
    print(f"DIRECT_HISTORY_LIMITED_ROWS={summary['direct_history_limited_rows']}")
    print(f"COMPARABLE_PRODUCT_ADJUSTED_ROWS={summary['comparable_product_adjusted_rows']}")
    print(f"COMPARABLE_MATRIX_ROWS={len(comparables)}")
    for state, count in sorted(review_counts.items()):
        print(f"OWNER_REVIEW_{state}={count}")
    print(f"NEXT_STAGE={summary['next_stage']}")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
