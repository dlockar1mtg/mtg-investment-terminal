from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_final_ranking_eligibility_contract_v1.json"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_final_ranking_eligibility"


def clean(value: Any) -> str:
    return str(value or "").strip()


def truthy(value: Any) -> bool:
    return clean(value).lower() in {"true", "1", "yes"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    paths = {name: ROOT / relative for name, relative in contract["authorities"].items()}
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise SystemExit("MISSING_REQUIRED_AUTHORITY:" + ";".join(missing))

    candidate_rows = read_csv(paths["eligibility_candidate"])
    review_rows = read_csv(paths["review_queue"])
    forecast_rows = read_csv(paths["forecast_rows"])
    calibration_rows = read_csv(paths["calibration_rows"])
    candidate_summary = json.loads(paths["eligibility_summary"].read_text(encoding="utf-8"))

    failures: list[str] = []
    if candidate_summary.get("status") != "PASS_COLLECTOR_CALIBRATION_REVIEW_AND_RANKING_ELIGIBILITY_CANDIDATE":
        failures.append("CANDIDATE_ELIGIBILITY_NOT_PASS")
    if len(candidate_rows) != int(contract["required_products"]):
        failures.append(f"CANDIDATE_PRODUCT_COUNT:{len(candidate_rows)}")
    if len(forecast_rows) != int(contract["required_forecast_rows"]):
        failures.append(f"FORECAST_ROW_COUNT:{len(forecast_rows)}")
    if len(calibration_rows) != int(contract["required_forecast_rows"]):
        failures.append(f"CALIBRATION_ROW_COUNT:{len(calibration_rows)}")

    review_by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in review_rows:
        review_by_id[clean(row.get("canonical_product_id"))].append(row)

    calibration_by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in calibration_rows:
        calibration_by_id[clean(row.get("canonical_product_id"))].append(row)

    final_rows: list[dict[str, Any]] = []
    resolution_rows: list[dict[str, Any]] = []
    penalties = contract["penalties"]

    for row in candidate_rows:
        cid = clean(row.get("canonical_product_id"))
        product_name = clean(row.get("product_name"))
        candidate = clean(row.get("ranking_eligibility_candidate"))
        product_reviews = review_by_id.get(cid, [])
        primary_issues = [review for review in product_reviews if truthy(review.get("primary_horizon_affected"))]
        supporting_issues = [review for review in product_reviews if not truthy(review.get("primary_horizon_affected"))]
        product_calibration = calibration_by_id.get(cid, [])
        blocked_rows = [item for item in product_calibration if clean(item.get("calibration_status")) == "BLOCKED"]
        penalty = 0.0
        limitations: list[str] = []

        if blocked_rows:
            final_status = "RANKING_BLOCKED"
            purchase_eligible = False
            ranking_eligible = False
            basis = "STRUCTURAL_OR_LINEAGE_FAILURE"
        elif primary_issues:
            final_status = "RANKING_REVIEW_REQUIRED"
            purchase_eligible = False
            ranking_eligible = False
            basis = "UNRESOLVED_PRIMARY_HORIZON_REVIEW"
        elif candidate == "INSUFFICIENT_FOR_RANKING":
            final_status = "CONDITIONAL_RANKING_ELIGIBLE"
            purchase_eligible = False
            ranking_eligible = True
            penalty += float(penalties["conditional_no_realized_primary_validation"])
            limitations.append("NO_REALIZED_SHORT_OR_PRIMARY_VALIDATION")
            basis = "FULL_COMPETITION_WITH_EXPLICIT_EVIDENCE_PENALTY"
        else:
            final_status = "RANKING_ELIGIBLE_WITH_LIMITATIONS"
            purchase_eligible = True
            ranking_eligible = True
            penalty += float(penalties["ranking_eligible_with_limitations"])
            basis = "CALIBRATED_OR_LIMITED_PRIMARY_EVIDENCE"

        if supporting_issues:
            penalty += float(penalties["supporting_horizon_review"])
            limitations.append("SUPPORTING_HORIZON_REVIEW_OPEN")
            resolution_rows.extend({
                "canonical_product_id": cid,
                "product_name": product_name,
                "issue_source": clean(issue.get("issue_source")),
                "previous_horizon_days": clean(issue.get("previous_horizon_days")),
                "horizon_days": clean(issue.get("horizon_days")),
                "issue_flags": clean(issue.get("issue_flags")),
                "resolution": "RETAINED_AS_SUPPORTING_HORIZON_LIMITATION",
                "primary_ranking_horizons_affected": False,
                "forecast_values_modified": False,
            } for issue in supporting_issues)

        final_rows.append({
            "canonical_product_id": cid,
            "product_name": product_name,
            "candidate_status": candidate,
            "final_ranking_eligibility_status": final_status,
            "ranking_eligible": ranking_eligible,
            "ranking_penalty_points": penalty,
            "purchase_eligible_at_this_stage": purchase_eligible,
            "eligibility_basis": basis,
            "limitations": "|".join(limitations),
            "open_primary_horizon_issues": len(primary_issues),
            "open_supporting_horizon_issues": len(supporting_issues),
            "forecast_values_modified": False,
        })

    ids = [row["canonical_product_id"] for row in final_rows]
    if len(set(ids)) != len(ids):
        failures.append("DUPLICATE_FINAL_PRODUCT_ID")
    if any(not row["canonical_product_id"] for row in final_rows):
        failures.append("MISSING_FINAL_PRODUCT_ID")
    if any(row["final_ranking_eligibility_status"] in {"RANKING_BLOCKED", "RANKING_REVIEW_REQUIRED"} for row in final_rows):
        failures.append("UNRESOLVED_BLOCKING_RANKING_STATUS")
    if sum(bool(row["ranking_eligible"]) for row in final_rows) != int(contract["required_products"]):
        failures.append("NOT_ALL_PRODUCTS_ENTER_RANKING_COMPETITION")
    if any(row["forecast_values_modified"] for row in final_rows + resolution_rows):
        failures.append("FORECAST_VALUES_MODIFIED")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_supporting_horizon_review_resolution.csv", resolution_rows)
    write_csv(OUTPUT / "collector_final_ranking_eligibility_authority.csv", final_rows)

    counts = Counter(row["final_ranking_eligibility_status"] for row in final_rows)
    status = contract["expected_status"] if not failures else "FAIL_COLLECTOR_FINAL_RANKING_ELIGIBILITY_CERTIFICATION"
    summary = {
        "contract_name": contract["contract_name"],
        "contract_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "products_evaluated": len(final_rows),
        "ranking_competition_products": sum(bool(row["ranking_eligible"]) for row in final_rows),
        "eligibility_counts": dict(counts),
        "supporting_horizon_review_rows_resolved": len(resolution_rows),
        "conditional_products": counts.get("CONDITIONAL_RANKING_ELIGIBLE", 0),
        "purchase_ineligible_products": sum(not bool(row["purchase_eligible_at_this_stage"]) for row in final_rows),
        "forecast_values_modified": False,
        "ranking_execution_authorized": not failures,
        "purchase_recommendations_authorized": False,
        "authority_hashes": {name: sha256(path) for name, path in paths.items()},
        "critical_failures": failures,
        "status": status,
    }
    (OUTPUT / "collector_final_ranking_eligibility_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
