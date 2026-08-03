from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_ID = "706142"
SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_star_trek_history_recovery_adjudication"

CANDIDATES = [
    "data/governance/permanence/certification/collector_current_authority/collector_current_authority_all.csv",
    "data/governance/permanence/certification/collector_current_authority/collector_current_authority_authorized.csv",
    "data/governance/permanence/certification/collector_historical_candidate_panel/collector_historical_governed_products_without_history.csv",
    "data/governance/permanence/certification/collector_identity_language_release/collector_identity_language_release_all.csv",
    "data/governance/permanence/certification/collector_identity_language_release/collector_identity_language_review_queue.csv",
    "data/governance/permanence/certification/collector_official_release_date_authority/collector_official_release_date_authority.csv",
    "data/governance/permanence/certification/collector_safe_monthly_history/collector_safe_monthly_products_without_released_history.csv",
    "data/governance/permanence/certification/collector_v1_active_english_universe/collector_v1_active_release.csv",
    "data/governance/permanence/certification/tcgcsv_collector_admission/daily_observation_admission_review.csv",
    "data/governance/permanence/certification/tcgcsv_collector_current_prices/collector_current_price_language_queue.csv",
]

ID_ALIASES = ("tcgplayer_product_id", "resolved_tcgplayer_product_id", "product_id")
DATE_ALIASES = (
    "observation_date_utc", "observation_date", "observed_at", "collected_at",
    "source_observation_at_utc", "price_date", "snapshot_date", "as_of_date",
    "release_date", "official_release_date", "generated_at", "generated_at_utc",
)
PRICE_ALIASES = (
    "market_price", "current_price", "price", "median_price", "low_price",
    "observed_price", "price_usd",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def first(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    return next((name for name in aliases if name in columns), None)


def classify(path: str, date_col: str | None, price_col: str | None, row: dict[str, str]) -> tuple[str, str]:
    lower_path = path.lower()
    date_value = str(row.get(date_col or "", "")).strip()
    price_value = str(row.get(price_col or "", "")).strip()
    if "without_history" in lower_path or "without_released_history" in lower_path:
        return "REJECT_NO_HISTORY_DECLARATION", "File explicitly records absence of released/canonical history."
    if "release_date" in (date_col or "") or "release" in lower_path or "identity" in lower_path or "active_english_universe" in lower_path:
        return "REJECT_METADATA_DATE", "Date is release/identity metadata, not a market observation timestamp."
    if "review" in lower_path or "queue" in lower_path:
        return "REJECT_REVIEW_QUEUE", "Row is unresolved review/queue evidence and is not an authorized history observation."
    if not date_col or not date_value:
        return "REJECT_NO_OBSERVATION_DATE", "No usable dated market observation is present."
    if not price_col or not price_value:
        return "REJECT_NO_OBSERVED_PRICE", "No usable market-price observation is present."
    if date_col in {"generated_at", "generated_at_utc"}:
        return "REJECT_GENERATED_DATE", "Generated timestamp cannot substitute for an observation date."
    return "CANDIDATE_REQUIRES_MANUAL_AUTHORITY_REVIEW", "Row has an apparent date and price but requires source-role and authority validation."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    evidence: list[dict[str, object]] = []
    for relative in CANDIDATES:
        path = ROOT / relative
        record: dict[str, object] = {"path": relative, "exists": path.is_file()}
        if not path.is_file():
            record.update({"disposition": "REJECT_FILE_MISSING", "reason": "Candidate file is missing."})
            evidence.append(record)
            continue
        frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
        columns = frame.columns.astype(str).tolist()
        id_col = first(columns, ID_ALIASES)
        date_col = first(columns, DATE_ALIASES)
        price_col = first(columns, PRICE_ALIASES)
        record.update({
            "sha256": sha256(path),
            "row_count": int(len(frame)),
            "id_column": id_col or "",
            "date_column": date_col or "",
            "price_column": price_col or "",
        })
        if not id_col:
            record.update({"matched_rows": 0, "disposition": "REJECT_NO_PRODUCT_ID", "reason": "No supported product ID column."})
            evidence.append(record)
            continue
        matched = frame[frame[id_col].astype(str).str.strip().str.removesuffix(".0") == PRODUCT_ID]
        record["matched_rows"] = int(len(matched))
        if matched.empty:
            record.update({"disposition": "REJECT_NO_MATCH", "reason": "No row for governed product 706142."})
            evidence.append(record)
            continue
        row = {str(k): str(v) for k, v in matched.iloc[0].to_dict().items()}
        disposition, reason = classify(relative, date_col, price_col, row)
        record.update({
            "date_value": str(row.get(date_col or "", "")).strip(),
            "price_value": str(row.get(price_col or "", "")).strip(),
            "product_name": str(row.get("canonical_product_name", row.get("product_name", row.get("name", "")))).strip(),
            "disposition": disposition,
            "reason": reason,
        })
        evidence.append(record)

    evidence_df = pd.DataFrame(evidence)
    evidence_path = OUT / "collector_v1_star_trek_history_recovery_evidence.csv"
    evidence_df.to_csv(evidence_path, index=False)
    promotable = evidence_df[evidence_df["disposition"].astype(str).eq("CANDIDATE_REQUIRES_MANUAL_AUTHORITY_REVIEW")]
    authorized = False
    summary = {
        "block_name": "Collector V1 Star Trek History Recovery Adjudication",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_snapshot_id": SNAPSHOT_ID,
        "tcgplayer_product_id": PRODUCT_ID,
        "canonical_product_name": "Star Trek - Collector Booster Display",
        "candidate_files_reviewed": len(evidence_df),
        "candidate_files_with_matching_rows": int((evidence_df["matched_rows"].fillna(0).astype(int) > 0).sum()),
        "apparent_dated_price_candidates": int(len(promotable)),
        "automatic_history_recovery_authorized": authorized,
        "current_foundation_authorized": False,
        "forecast_ranking_rebuild_authorized": False,
        "purchase_recommendations_authorized": False,
        "evidence_path": str(evidence_path.relative_to(ROOT)),
        "evidence_sha256": sha256(evidence_path),
        "critical_failures": ["no_authorized_historical_market_observation_for_product_706142"],
        "status": "BLOCKED_COLLECTOR_V1_STAR_TREK_HISTORY_RECOVERY_NOT_AUTHORIZED",
    }
    summary_path = OUT / "collector_v1_star_trek_history_recovery_adjudication_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
