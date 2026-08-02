from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_calibration_review_and_ranking_eligibility_contract_v1.json"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_calibration_review_and_ranking_eligibility"


def clean(value: Any) -> str:
    return str(value or "").strip()


def truthy(value: Any) -> bool:
    return clean(value).lower() in {"true", "1", "yes"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
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

    row_validation = read_csv(paths["forecast_rows"])
    product_status = read_csv(paths["product_status"])
    coherence = read_csv(paths["coherence_audit"])
    extreme = read_csv(paths["extreme_review_queue"])
    forecasts = read_csv(paths["final_forecasts"])
    calibration_summary = json.loads(paths["calibration_summary"].read_text(encoding="utf-8"))

    failures: list[str] = []
    if calibration_summary.get("status") != "PASS_COLLECTOR_FINAL_PROBABILISTIC_CALIBRATION_AND_REASONABLENESS_CERTIFICATION":
        failures.append("CALIBRATION_CERTIFICATION_NOT_PASS")
    if len(row_validation) != int(contract["required_forecast_rows"]):
        failures.append(f"FORECAST_ROW_VALIDATION_COUNT:{len(row_validation)}")
    if len(product_status) != int(contract["required_products"]):
        failures.append(f"PRODUCT_STATUS_COUNT:{len(product_status)}")
    if len(forecasts) != int(contract["required_forecast_rows"]):
        failures.append(f"FINAL_FORECAST_COUNT:{len(forecasts)}")

    by_product: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in row_validation:
        by_product[clean(row.get("canonical_product_id"))].append(row)

    coherence_issues = [row for row in coherence if truthy(row.get("review_required"))]
    issue_rows: list[dict[str, Any]] = []
    issue_map: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in extreme:
        cid = clean(row.get("canonical_product_id"))
        horizon = int(float(clean(row.get("horizon_days")) or 0))
        issue = {
            "canonical_product_id": cid,
            "product_name": clean(row.get("product_name")),
            "issue_source": "EXTREME_REVIEW_QUEUE",
            "previous_horizon_days": "",
            "horizon_days": horizon,
            "issue_flags": clean(row.get("reasonableness_flags")),
            "calibration_status": clean(row.get("calibration_status")),
            "primary_horizon_affected": horizon in contract["primary_ranking_horizons_days"],
            "review_disposition": "UNRESOLVED_REVIEW_REQUIRED",
        }
        issue_rows.append(issue)
        issue_map[cid].append(issue)

    for row in coherence_issues:
        cid = clean(row.get("canonical_product_id"))
        horizon = int(float(clean(row.get("current_horizon_days")) or 0))
        issue = {
            "canonical_product_id": cid,
            "product_name": clean(row.get("product_name")),
            "issue_source": "HORIZON_COHERENCE_AUDIT",
            "previous_horizon_days": clean(row.get("previous_horizon_days")),
            "horizon_days": horizon,
            "issue_flags": clean(row.get("coherence_flags")),
            "calibration_status": "",
            "primary_horizon_affected": horizon in contract["primary_ranking_horizons_days"],
            "review_disposition": "UNRESOLVED_REVIEW_REQUIRED",
        }
        issue_rows.append(issue)
        issue_map[cid].append(issue)

    eligibility_rows: list[dict[str, Any]] = []
    allowed_evidence_statuses = {"CALIBRATED", "CALIBRATED_WITH_LIMITATIONS"}
    primary_horizons = set(int(value) for value in contract["primary_ranking_horizons_days"])
    evidence_horizons = {90, 180, *primary_horizons}

    for cid, rows in sorted(by_product.items()):
        rows = sorted(rows, key=lambda row: int(float(clean(row.get("horizon_days")) or 0)))
        name = clean(rows[0].get("product_name")) if rows else ""
        structural_blocked = any(clean(row.get("calibration_status")) == "BLOCKED" for row in rows)
        validated_rows = [
            row for row in rows
            if int(float(clean(row.get("horizon_days")) or 0)) in evidence_horizons
            and clean(row.get("calibration_status")) in allowed_evidence_statuses
        ]
        issues = issue_map.get(cid, [])
        primary_issues = [issue for issue in issues if issue["primary_horizon_affected"]]
        supporting_issues = [issue for issue in issues if not issue["primary_horizon_affected"]]
        insufficient_rows = sum(clean(row.get("calibration_status")) == "INSUFFICIENT_REALIZED_VALIDATION" for row in rows)

        if structural_blocked:
            status = "BLOCKED"
            basis = "STRUCTURAL_CALIBRATION_BLOCK"
        elif primary_issues:
            status = "REASONABLENESS_REVIEW_REQUIRED"
            basis = "UNRESOLVED_PRIMARY_HORIZON_ISSUE"
        elif not validated_rows:
            status = "INSUFFICIENT_FOR_RANKING"
            basis = "NO_SHORT_OR_PRIMARY_REALIZED_VALIDATION"
        elif supporting_issues or insufficient_rows:
            status = "RANKING_ELIGIBLE_WITH_LIMITATIONS"
            basis = "SHORT_OR_PRIMARY_VALIDATION_PRESENT;LIMITED_LONG_HORIZON_EVIDENCE_OR_SUPPORTING_REVIEW"
        else:
            status = "RANKING_ELIGIBLE"
            basis = "STRUCTURALLY_VALID;REALIZED_VALIDATION_PRESENT;NO_OPEN_REVIEW"

        eligibility_rows.append({
            "canonical_product_id": cid,
            "product_name": name,
            "ranking_eligibility_candidate": status,
            "eligibility_basis": basis,
            "validated_short_or_primary_rows": len(validated_rows),
            "insufficient_realized_validation_rows": insufficient_rows,
            "open_primary_horizon_issues": len(primary_issues),
            "open_supporting_horizon_issues": len(supporting_issues),
            "structural_blocked": structural_blocked,
            "ranking_authorized": False,
            "purchase_recommendations_authorized": False,
        })

    if len(eligibility_rows) != int(contract["required_products"]):
        failures.append(f"ELIGIBILITY_PRODUCT_COUNT:{len(eligibility_rows)}")
    if any(row["ranking_eligibility_candidate"] not in contract["candidate_statuses"] for row in eligibility_rows):
        failures.append("UNKNOWN_ELIGIBILITY_STATUS")
    if any(row["ranking_authorized"] or row["purchase_recommendations_authorized"] for row in eligibility_rows):
        failures.append("DOWNSTREAM_AUTHORIZATION_VIOLATION")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_calibration_review_queue.csv", issue_rows)
    write_csv(OUTPUT / "collector_ranking_eligibility_candidate.csv", eligibility_rows)

    counts: dict[str, int] = defaultdict(int)
    for row in eligibility_rows:
        counts[row["ranking_eligibility_candidate"]] += 1

    status = contract["expected_status"] if not failures else "FAIL_COLLECTOR_CALIBRATION_REVIEW_AND_RANKING_ELIGIBILITY_CANDIDATE"
    summary = {
        "contract_name": contract["contract_name"],
        "contract_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "products_evaluated": len(eligibility_rows),
        "forecast_rows_referenced": len(row_validation),
        "extreme_queue_rows": len(extreme),
        "coherence_review_pairs": len(coherence_issues),
        "review_queue_rows": len(issue_rows),
        "eligibility_counts": dict(sorted(counts.items())),
        "forecast_values_modified": False,
        "ranking_authorized": False,
        "purchase_recommendations_authorized": False,
        "authority_hashes": {name: sha256(path) for name, path in paths.items()},
        "critical_failures": failures,
        "status": status,
    }
    (OUTPUT / "collector_calibration_review_and_ranking_eligibility_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    print("\nOPEN REVIEW QUEUE")
    for row in issue_rows:
        print(json.dumps(row, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
