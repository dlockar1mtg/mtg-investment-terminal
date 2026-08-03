from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config/mtg/governance/tcgcsv_collector_admission_policy_v1.json"
RAW_DIR = ROOT / "data/raw/tcgcsv"
DEFAULT_DAILY = ROOT / "data/staging/purchase_refresh/2026-07-31/daily_price_observations.csv"
DEFAULT_OUT = ROOT / "data/governance/permanence/certification/tcgcsv_collector_admission"


def norm(value: object) -> str:
    return " ".join(str(value or "").strip().lower().replace("-", " ").split())


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def classify_name(name: str, policy: dict) -> tuple[str, str]:
    value = norm(name)
    excluded = [term for term in policy["excluded_name_terms"] if norm(term) in value]
    if excluded:
        return "EXCLUDED_CONFIGURATION", ";".join(excluded)
    eligible = [term for term in policy["eligible_name_terms"] if norm(term) in value]
    if not eligible:
        return "EXCLUDED_NOT_COLLECTOR_DISPLAY", "eligible_display_term_missing"
    return "CONFIGURATION_ELIGIBLE_LANGUAGE_UNVERIFIED", ";".join(eligible)


def iter_products() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(RAW_DIR.glob("products_1_*.json")):
        try:
            payload = load_json(path)
        except Exception:
            continue
        for product in payload.get("results", []):
            row = dict(product)
            row["source_file"] = path.name
            rows.append(row)
    return rows


def iter_prices() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(RAW_DIR.glob("prices_1_*.json")):
        try:
            payload = load_json(path)
        except Exception:
            continue
        for price in payload.get("results", []):
            row = dict(price)
            row["source_file"] = path.name
            rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily-observations", type=Path, default=DEFAULT_DAILY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    policy = load_json(POLICY)
    products = iter_products()
    prices = iter_prices()
    by_product: dict[str, dict] = {}
    duplicate_product_ids: Counter[str] = Counter()
    candidate_rows: list[dict] = []

    for product in products:
        pid = str(product.get("productId") or "").strip()
        if not pid:
            continue
        duplicate_product_ids[pid] += 1
        status, reason = classify_name(str(product.get("name") or ""), policy)
        presale = product.get("presaleInfo") or {}
        candidate = {
            "tcgplayer_product_id": pid,
            "raw_name": product.get("name"),
            "clean_name": product.get("cleanName"),
            "category_id": product.get("categoryId"),
            "group_id": product.get("groupId"),
            "configuration_status": status,
            "configuration_reason": reason,
            "language_status": "LANGUAGE_UNVERIFIED",
            "is_presale": presale.get("isPresale"),
            "released_on": presale.get("releasedOn"),
            "source_file": product.get("source_file"),
        }
        candidate_rows.append(candidate)
        by_product[pid] = candidate

    price_groups: dict[str, list[dict]] = defaultdict(list)
    for row in prices:
        pid = str(row.get("productId") or "").strip()
        if pid:
            price_groups[pid].append(row)

    price_audit_rows: list[dict] = []
    unsafe_price_products = 0
    for pid, rows in sorted(price_groups.items()):
        normal_rows = [r for r in rows if norm(r.get("subTypeName")) == "normal"]
        status = "NORMAL_SUBTYPE_UNIQUE"
        if len(normal_rows) == 0:
            status = "NORMAL_SUBTYPE_MISSING"
            unsafe_price_products += 1
        elif len(normal_rows) > 1:
            status = "NORMAL_SUBTYPE_DUPLICATE"
            unsafe_price_products += 1
        price_audit_rows.append({
            "tcgplayer_product_id": pid,
            "price_row_count": len(rows),
            "normal_subtype_row_count": len(normal_rows),
            "selection_status": status,
            "all_subtypes": ";".join(sorted({str(r.get("subTypeName") or "") for r in rows})),
        })

    daily_rows: list[dict] = []
    if args.daily_observations.is_file():
        with args.daily_observations.open("r", encoding="utf-8-sig", newline="") as handle:
            daily_rows = list(csv.DictReader(handle))

    daily_missing_catalog = 0
    daily_not_configuration_eligible = 0
    daily_language_unverified = 0
    daily_review_rows: list[dict] = []
    for row in daily_rows:
        pid = str(row.get("tcgplayer_product_id") or "").strip()
        candidate = by_product.get(pid)
        if candidate is None:
            daily_missing_catalog += 1
            status = "CATALOG_IDENTITY_MISSING"
        elif candidate["configuration_status"] != "CONFIGURATION_ELIGIBLE_LANGUAGE_UNVERIFIED":
            daily_not_configuration_eligible += 1
            status = candidate["configuration_status"]
        else:
            daily_language_unverified += 1
            status = "CONFIGURATION_ELIGIBLE_LANGUAGE_UNVERIFIED"
        daily_review_rows.append({**row, "admission_status": status})

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "collector_product_admission_candidates.csv", candidate_rows, [
        "tcgplayer_product_id", "raw_name", "clean_name", "category_id", "group_id",
        "configuration_status", "configuration_reason", "language_status", "is_presale",
        "released_on", "source_file"
    ])
    write_csv(args.output_dir / "price_subtype_audit.csv", price_audit_rows, [
        "tcgplayer_product_id", "price_row_count", "normal_subtype_row_count",
        "selection_status", "all_subtypes"
    ])
    daily_fields = list(daily_rows[0].keys()) + ["admission_status"] if daily_rows else ["admission_status"]
    write_csv(args.output_dir / "daily_observation_admission_review.csv", daily_review_rows, daily_fields)

    config_counts = Counter(row["configuration_status"] for row in candidate_rows)
    summary = {
        "audit_name": "TCGCSV Collector Admission Audit",
        "audit_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "raw_product_rows": len(products),
        "unique_product_ids": len(by_product),
        "duplicate_catalog_product_id_count": sum(1 for count in duplicate_product_ids.values() if count > 1),
        "configuration_counts": dict(sorted(config_counts.items())),
        "raw_price_rows": len(prices),
        "price_product_count": len(price_groups),
        "unsafe_price_subtype_product_count": unsafe_price_products,
        "daily_observation_rows": len(daily_rows),
        "daily_missing_catalog_identity_count": daily_missing_catalog,
        "daily_not_configuration_eligible_count": daily_not_configuration_eligible,
        "daily_language_unverified_count": daily_language_unverified,
        "certified_daily_observation_count": 0,
        "first_row_price_selection_forbidden": True,
        "fresh_direct_historical_append_authorized": False,
        "forecasting_resume_authorized": False,
        "status": "REVIEW_REQUIRED",
    }
    failures: list[str] = []
    if args.strict:
        if daily_missing_catalog:
            failures.append("daily_observations_missing_catalog_identity")
        if daily_not_configuration_eligible:
            failures.append("daily_observations_include_non_display_configuration")
        if daily_language_unverified:
            failures.append("daily_observations_lack_explicit_english_evidence")
        if unsafe_price_products:
            failures.append("price_products_lack_unique_normal_subtype")
    summary["failure_count"] = len(failures)
    summary["failures"] = failures
    if args.strict:
        summary["status"] = "PASS" if not failures else "FAIL"

    summary_path = args.output_dir / "tcgcsv_collector_admission_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
