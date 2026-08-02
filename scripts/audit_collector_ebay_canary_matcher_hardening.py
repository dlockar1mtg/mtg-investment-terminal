from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANARY_ROOT = ROOT / "data/governance/permanence/certification/collector_ebay_valid_high_recall_canary"
LISTINGS = CANARY_ROOT / "collector_ebay_canary_listing_results.csv"
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_canary_matcher_hardening"

MULTI_UNIT = re.compile(r"(?:^|\s)(?:x\s*)?(?:2|3|4|5|6|8|10|12)\s*(?:x\s*)?(?:boxes?|collector booster boxes?|display boxes?)(?:\s|$)", re.I)
PREFIX_MULTI = re.compile(r"(?:^|\s)(?:2|3|4|5|6|8|10|12)\s*[xX](?=\D)")
CASE = re.compile(r"\b(?:sealed\s+)?case\b|\bmaster\s+case\b", re.I)
FOREIGN = re.compile(r"\bjapanese\b|\bjpn\b|\bfrench\b|\bgerman\b|\bitalian\b|\bspanish\b", re.I)
YEAR_QUANTITY = re.compile(r"universal_quantity:(?:19|20)\d{2}(?:\||$)")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    rows = read_csv(LISTINGS)
    findings: list[dict[str, object]] = []
    categories = Counter()

    for row in rows:
        title = row.get("title", "")
        state = row.get("match_state", "")
        reasons = row.get("exclusion_reasons", "")
        category = ""
        severity = ""
        disposition = ""

        if state == "ACCEPTED" and (MULTI_UNIT.search(title) or PREFIX_MULTI.search(title)):
            category, severity, disposition = "UNSAFE_ACCEPT_MULTI_UNIT", "BLOCKER", "DOWNGRADE_REJECTED"
        elif state == "ACCEPTED" and CASE.search(title):
            category, severity, disposition = "UNSAFE_ACCEPT_CASE", "BLOCKER", "DOWNGRADE_REJECTED"
        elif state == "ACCEPTED" and FOREIGN.search(title):
            category, severity, disposition = "UNSAFE_ACCEPT_FOREIGN_LANGUAGE", "BLOCKER", "DOWNGRADE_REJECTED"
        elif YEAR_QUANTITY.search(reasons):
            category, severity, disposition = "YEAR_PARSED_AS_QUANTITY", "BLOCKER", "FIX_QUANTITY_PARSER"
        elif state == "REVIEW" and FOREIGN.search(title):
            category, severity, disposition = "CONFIRMED_REVIEW_FOREIGN_LANGUAGE", "EXPECTED", "KEEP_EXCLUDED"
        elif state == "REVIEW" and CASE.search(title):
            category, severity, disposition = "CONFIRMED_REVIEW_CASE", "EXPECTED", "KEEP_EXCLUDED"
        elif state == "REVIEW" and "Lord of the Rings" in row.get("canonical_product_name", ""):
            category, severity, disposition = "LOTR_STANDARD_DISPLAY_REVIEW", "REQUIRES_ALIAS_REVIEW", "ADJUDICATE_PRODUCT_ALIAS"

        if category:
            categories[category] += 1
            findings.append({
                "canonical_product_name": row.get("canonical_product_name", ""),
                "ebay_item_id": row.get("ebay_item_id", ""),
                "title": title,
                "current_match_state": state,
                "match_score": row.get("match_score", ""),
                "category": category,
                "severity": severity,
                "required_disposition": disposition,
                "exclusion_reasons": reasons,
            })

    fields = ["canonical_product_name", "ebay_item_id", "title", "current_match_state", "match_score", "category", "severity", "required_disposition", "exclusion_reasons"]
    write_csv(OUT / "collector_ebay_canary_matcher_hardening_findings.csv", findings, fields)

    blocker_rows = sum(1 for row in findings if row["severity"] == "BLOCKER")
    alias_rows = sum(1 for row in findings if row["severity"] == "REQUIRES_ALIAS_REVIEW")
    summary = {
        "block_name": "Collector eBay Canary Matcher Hardening Audit",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "offline_only": True,
        "quota_calls": 0,
        "canary_listing_rows": len(rows),
        "hardening_findings": len(findings),
        "blocker_rows": blocker_rows,
        "lotr_alias_review_rows": alias_rows,
        "category_counts": dict(sorted(categories.items())),
        "full_universe_collection_authorized": False,
        "continuity_accumulation_authorized": False,
        "matcher_hardening_required": blocker_rows > 0 or alias_rows > 0,
        "status": "PASS_CANARY_HARDENING_AUDIT_REMEDIATION_REQUIRED" if findings else "PASS_CANARY_HARDENING_AUDIT_CLEAR",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "collector_ebay_canary_matcher_hardening_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if args.strict and not rows:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
