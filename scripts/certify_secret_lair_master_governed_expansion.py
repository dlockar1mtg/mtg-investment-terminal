from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATION_ROOT = ROOT / "data/validation/phase_10/premium_universe_eligibility"
FULL_PATH = VALIDATION_ROOT / "secret_lair_master_governed_universe.csv"
READY_PATH = VALIDATION_ROOT / "secret_lair_master_registry_ready_universe.csv"
REVIEW_PATH = VALIDATION_ROOT / "secret_lair_master_review_required_universe.csv"
OWNED_PATH = VALIDATION_ROOT / "secret_lair_owned_inventory_master_crosswalk.csv"
SUMMARY_PATH = VALIDATION_ROOT / "secret_lair_master_expansion_summary.csv"
REPORT_CSV = VALIDATION_ROOT / "secret_lair_master_expansion_certification.csv"
REPORT_JSON = VALIDATION_ROOT / "secret_lair_master_expansion_certification.json"

EXPECTED_MASTER_ROWS = 1008
EXPECTED_OWNED_ROWS = 12
ALLOWED_CONFIGURATIONS = {
    "individual_drop",
    "bundle",
    "festival_in_a_box",
    "deck",
    "kit",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def clean(value: object) -> str:
    return " ".join(str(value or "").split())


def is_true(value: object) -> bool:
    return clean(value).lower() in {"true", "1", "yes"}


def main() -> None:
    full = read_csv(FULL_PATH)
    ready = read_csv(READY_PATH)
    review = read_csv(REVIEW_PATH)
    owned = read_csv(OWNED_PATH)
    summary = read_csv(SUMMARY_PATH)

    summary_map = {clean(row.get("metric")): clean(row.get("value")) for row in summary}
    checks: list[dict[str, object]] = []

    def add_check(name: str, passed: bool, actual: object, expected: object, details: str = "") -> None:
        checks.append(
            {
                "check_name": name,
                "status": "PASS" if passed else "FAIL",
                "actual": actual,
                "expected": expected,
                "details": details,
            }
        )

    add_check("master_row_count", len(full) == EXPECTED_MASTER_ROWS, len(full), EXPECTED_MASTER_ROWS)
    add_check("ready_plus_review_reconciles", len(ready) + len(review) == len(full), len(ready) + len(review), len(full))
    add_check("owned_row_count", len(owned) == EXPECTED_OWNED_ROWS, len(owned), EXPECTED_OWNED_ROWS)

    ids = [clean(row.get("secret_lair_id")) for row in full]
    duplicate_ids = sorted(key for key, count in Counter(ids).items() if key and count > 1)
    blank_ids = sum(not key for key in ids)
    add_check("secret_lair_ids_present", blank_ids == 0, blank_ids, 0)
    add_check("secret_lair_ids_unique", not duplicate_ids, len(duplicate_ids), 0, "|".join(duplicate_ids[:20]))

    ready_ids = {clean(row.get("secret_lair_id")) for row in ready}
    review_ids = {clean(row.get("secret_lair_id")) for row in review}
    overlap = sorted(ready_ids & review_ids)
    add_check("ready_review_disjoint", not overlap, len(overlap), 0, "|".join(overlap[:20]))

    bad_ready_status = [row for row in ready if clean(row.get("governance_status")) != "REGISTRY_READY"]
    bad_review_status = [row for row in review if clean(row.get("governance_status")) != "REVIEW_REQUIRED"]
    add_check("ready_status_consistent", not bad_ready_status, len(bad_ready_status), 0)
    add_check("review_status_consistent", not bad_review_status, len(bad_review_status), 0)

    ready_missing_tcg = [row for row in ready if not clean(row.get("tcgplayer_product_id"))]
    ready_blocked = [row for row in ready if not is_true(row.get("ebay_matching_allowed"))]
    review_allowed = [row for row in review if is_true(row.get("ebay_matching_allowed"))]
    add_check("ready_has_tcgplayer_id", not ready_missing_tcg, len(ready_missing_tcg), 0)
    add_check("ready_ebay_allowed", not ready_blocked, len(ready_blocked), 0)
    add_check("review_ebay_blocked", not review_allowed, len(review_allowed), 0)

    invalid_configs = sorted({clean(row.get("sealed_configuration")) for row in full if clean(row.get("sealed_configuration")) not in ALLOWED_CONFIGURATIONS})
    add_check("sealed_configuration_domain", not invalid_configs, len(invalid_configs), 0, "|".join(invalid_configs))

    ready_unknown_individual = [
        row for row in ready
        if clean(row.get("sealed_configuration")) == "individual_drop"
        and clean(row.get("detailed_finish")) in {"", "unknown"}
    ]
    add_check("ready_individual_finish_known", not ready_unknown_individual, len(ready_unknown_individual), 0)

    unresolved_owned = [row for row in owned if clean(row.get("crosswalk_status")) == "MISSING_NEEDS_ID_RESOLUTION"]
    owned_missing_ids = [row for row in owned if not clean(row.get("tcgplayer_product_id"))]
    owned_bad_governance = [row for row in owned if clean(row.get("governance_status")) != "REGISTRY_READY"]
    add_check("owned_no_unresolved", not unresolved_owned, len(unresolved_owned), 0)
    add_check("owned_has_tcgplayer_id", not owned_missing_ids, len(owned_missing_ids), 0)
    add_check("owned_registry_ready", not owned_bad_governance, len(owned_bad_governance), 0)

    summary_ready = int(summary_map.get("registry_ready_rows", "-1"))
    summary_review = int(summary_map.get("review_required_rows", "-1"))
    summary_owned_missing = int(summary_map.get("owned_missing", "-1"))
    add_check("summary_ready_reconciles", summary_ready == len(ready), summary_ready, len(ready))
    add_check("summary_review_reconciles", summary_review == len(review), summary_review, len(review))
    add_check("summary_owned_missing_zero", summary_owned_missing == 0, summary_owned_missing, 0)

    overall = "PASS" if all(row["status"] == "PASS" for row in checks) else "FAIL"
    timestamp = datetime.now(timezone.utc).isoformat()

    REPORT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["check_name", "status", "actual", "expected", "details"])
        writer.writeheader()
        writer.writerows(checks)

    payload = {
        "certification": "SECRET_LAIR_MASTER_GOVERNED_EXPANSION",
        "status": overall,
        "generated_at_utc": timestamp,
        "master_rows": len(full),
        "registry_ready_rows": len(ready),
        "review_required_rows": len(review),
        "owned_rows": len(owned),
        "checks": checks,
    }
    REPORT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("SECRET LAIR MASTER GOVERNED EXPANSION CERTIFICATION")
    print("=" * 64)
    for row in checks:
        print(f"{row['status']}: {row['check_name']} (actual={row['actual']}, expected={row['expected']})")
    print("-" * 64)
    print(f"FINAL STATUS: {overall}")
    print(f"Master rows: {len(full)}")
    print(f"Registry-ready rows: {len(ready)}")
    print(f"Review-required rows: {len(review)}")
    print(f"Owned rows: {len(owned)}")
    print(f"CSV report: {REPORT_CSV.relative_to(ROOT)}")
    print(f"JSON report: {REPORT_JSON.relative_to(ROOT)}")
    print("Active eBay universe source was not changed.")

    if overall != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
