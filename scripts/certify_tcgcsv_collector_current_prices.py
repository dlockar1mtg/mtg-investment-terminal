from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMISSION_DIR = ROOT / "data/governance/permanence/certification/tcgcsv_collector_admission"
DAILY_PATH = ROOT / "data/staging/purchase_refresh/2026-07-31/daily_price_observations.csv"
OUT_DIR = ROOT / "data/governance/permanence/certification/tcgcsv_collector_current_prices"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def to_float(value: str | None) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    admission_path = ADMISSION_DIR / "daily_observation_admission_review.csv"
    subtype_path = ADMISSION_DIR / "price_subtype_audit.csv"
    required = [DAILY_PATH, admission_path, subtype_path]
    missing = [path.relative_to(ROOT).as_posix() for path in required if not path.is_file()]
    if missing:
        print(json.dumps({"status": "FAIL", "missing_required_files": missing}, indent=2))
        return 1

    daily = read_csv(DAILY_PATH)
    admission = {row["tcgplayer_product_id"]: row for row in read_csv(admission_path)}
    subtype = {row["tcgplayer_product_id"]: row for row in read_csv(subtype_path)}

    candidates: list[dict[str, object]] = []
    quarantined: list[dict[str, object]] = []

    for row in daily:
        pid = str(row.get("tcgplayer_product_id") or "").strip()
        admit = admission.get(pid, {})
        sub = subtype.get(pid, {})
        price = to_float(row.get("current_price"))

        blockers: list[str] = []
        if not pid:
            blockers.append("BLANK_PRODUCT_ID")
        if admit.get("admission_status") != "CONFIGURATION_ELIGIBLE_LANGUAGE_UNVERIFIED":
            blockers.append(admit.get("admission_status") or "CONFIGURATION_STATUS_MISSING")
        if sub.get("selection_status") != "NORMAL_SUBTYPE_UNIQUE":
            blockers.append(sub.get("selection_status") or "SUBTYPE_STATUS_MISSING")
        if price is None or price <= 0:
            blockers.append("MARKET_PRICE_INVALID")
        blockers.append("LANGUAGE_EVIDENCE_REQUIRED")

        output = {
            "observation_date": row.get("observation_date", ""),
            "investment_product_id": row.get("investment_product_id", ""),
            "tcgplayer_product_id": pid,
            "box_name": row.get("box_name", ""),
            "set_name": row.get("set_name", ""),
            "market_price": row.get("current_price", ""),
            "low_price": row.get("low_price", ""),
            "price_source": row.get("price_source", ""),
            "configuration_status": admit.get("admission_status", ""),
            "subtype_status": sub.get("selection_status", ""),
            "language_status": "LANGUAGE_UNVERIFIED",
            "candidate_status": "QUARANTINED_PENDING_LANGUAGE" if blockers == ["LANGUAGE_EVIDENCE_REQUIRED"] else "QUARANTINED",
            "blocking_reasons": ";".join(blockers),
        }
        if output["candidate_status"] == "QUARANTINED_PENDING_LANGUAGE":
            candidates.append(output)
        else:
            quarantined.append(output)

    fields = [
        "observation_date", "investment_product_id", "tcgplayer_product_id", "box_name",
        "set_name", "market_price", "low_price", "price_source", "configuration_status",
        "subtype_status", "language_status", "candidate_status", "blocking_reasons",
    ]
    write_csv(OUT_DIR / "collector_current_price_language_queue.csv", candidates, fields)
    write_csv(OUT_DIR / "collector_current_price_quarantine.csv", quarantined, fields)

    summary = {
        "audit_name": "TCGCSV Collector Current Price Certification",
        "audit_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "daily_rows": len(daily),
        "configuration_and_subtype_pass_pending_language": len(candidates),
        "quarantined_for_other_reasons": len(quarantined),
        "quarantine_reason_counts": dict(Counter(reason for row in quarantined for reason in str(row["blocking_reasons"]).split(";") if reason)),
        "certified_rows": 0,
        "language_evidence_required": True,
        "historical_append_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "status": "REVIEW_REQUIRED" if not quarantined else "FAIL",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "tcgcsv_collector_current_price_certification_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
