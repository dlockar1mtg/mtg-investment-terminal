from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "data/operations/mtg_marketplace/lanes/tcgcsv_price_observations.csv"
LEDGER = ROOT / "data/operations/mtg_universal_history_ledger/universal_mtg_historical_observation_ledger.csv"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_tcgcsv_historical_authority"
EXPECTED_SHA256 = "65e5699179f88921d9c8471cd0461c26fad4909bc5661d21c434d52998cf6ab3"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def first_present(frame: pd.DataFrame, names: list[str]) -> str | None:
    return next((name for name in names if name in frame.columns), None)


def load(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")


def normalize_id(value: object) -> str:
    text = str(value or "").strip().removeprefix("TCGPLAYER-")
    return text[:-2] if text.endswith(".0") else text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    if not CANDIDATE.is_file():
        failures.append("candidate_missing")
    if not LEDGER.is_file():
        failures.append("governed_ledger_missing")
    if failures:
        summary = {"critical_failures": failures, "status": "FAIL_TCGCSV_AUTHORITY_INPUTS_MISSING"}
        print(json.dumps(summary, indent=2))
        return 1 if args.strict else 0

    candidate_hash = sha256(CANDIDATE)
    candidate = load(CANDIDATE)
    ledger = load(LEDGER)

    id_col = first_present(candidate, ["tcgplayer_product_id", "source_product_id", "product_id"])
    date_col = first_present(candidate, ["collected_at", "observed_at_utc", "observation_date", "date"])
    price_col = first_present(candidate, ["market_price", "price", "median_price"])
    source_col = first_present(candidate, ["source_name", "source", "provider"])
    required_fields_present = all([id_col, date_col, price_col, source_col])

    if required_fields_present:
        candidate["normalized_product_id"] = candidate[id_col].map(normalize_id)
        candidate["parsed_timestamp"] = pd.to_datetime(candidate[date_col], errors="coerce", utc=True)
        candidate["market_price_numeric"] = pd.to_numeric(candidate[price_col], errors="coerce")
        candidate["normalized_source_name"] = candidate[source_col].astype(str).str.upper().str.strip()
    else:
        candidate["normalized_product_id"] = ""
        candidate["parsed_timestamp"] = pd.NaT
        candidate["market_price_numeric"] = pd.NA
        candidate["normalized_source_name"] = ""

    now = pd.Timestamp.now(tz="UTC")
    invalid_date_count = int(candidate["parsed_timestamp"].isna().sum())
    invalid_price_count = int((candidate["market_price_numeric"].isna() | (candidate["market_price_numeric"] <= 0)).sum())
    blank_identity_count = int(candidate["normalized_product_id"].eq("").sum())
    non_tcgcsv_source_count = int((candidate["normalized_source_name"] != "TCGCSV").sum())
    future_dated_count = int((candidate["parsed_timestamp"].notna() & (candidate["parsed_timestamp"] > now)).sum())
    duplicate_key_count = int(candidate.duplicated(subset=["normalized_product_id", "parsed_timestamp"], keep=False).sum())

    valid_dates = candidate["parsed_timestamp"].dropna()
    distinct_observation_dates = int(valid_dates.dt.strftime("%Y-%m-%d").nunique()) if not valid_dates.empty else 0
    minimum_observation_date = valid_dates.min().isoformat() if not valid_dates.empty else ""
    maximum_observation_date = valid_dates.max().isoformat() if not valid_dates.empty else ""
    calendar_span_days = int((valid_dates.max() - valid_dates.min()).days) if len(valid_dates) else 0
    distinct_product_count = int(candidate["normalized_product_id"].replace("", pd.NA).nunique())

    ledger_id_col = first_present(ledger, ["tcgplayer_product_id", "source_product_id", "product_id"])
    ledger_date_col = first_present(ledger, ["observation_date", "observed_at_utc", "collected_at", "date"])
    ledger_price_col = first_present(ledger, ["market_price", "price", "median_price"])
    ledger_source_file_col = first_present(ledger, ["source_file", "source_path"])

    ledger_matches = pd.DataFrame()
    if ledger_id_col and ledger_date_col:
        ledger["normalized_product_id"] = ledger[ledger_id_col].map(normalize_id)
        ledger["parsed_timestamp"] = pd.to_datetime(ledger[ledger_date_col], errors="coerce", utc=True)
        candidate_keys = set(zip(candidate["normalized_product_id"], candidate["parsed_timestamp"].dt.strftime("%Y-%m-%d")))
        ledger["date_key"] = ledger["parsed_timestamp"].dt.strftime("%Y-%m-%d")
        ledger_matches = ledger[
            ledger.apply(lambda row: (row["normalized_product_id"], row["date_key"]) in candidate_keys, axis=1)
        ].copy()

    exact_source_file_matches = 0
    if ledger_source_file_col and not ledger_matches.empty:
        exact_source_file_matches = int(
            ledger_matches[ledger_source_file_col]
            .astype(str)
            .str.replace("/", "\\", regex=False)
            .str.endswith("data\\operations\\mtg_marketplace\\lanes\\tcgcsv_price_observations.csv")
            .sum()
        )

    candidate_audit = candidate.copy()
    candidate_audit["row_semantics_valid"] = (
        candidate_audit["normalized_product_id"].ne("")
        & candidate_audit["parsed_timestamp"].notna()
        & candidate_audit["market_price_numeric"].gt(0)
        & candidate_audit["normalized_source_name"].eq("TCGCSV")
    )
    candidate_audit["historical_replay_eligible"] = False
    candidate_audit["historical_replay_exclusion_reason"] = "INSUFFICIENT_HISTORICAL_SPAN_AND_LEDGER_RECONCILIATION"
    candidate_audit.to_csv(OUT / "collector_tcgcsv_candidate_row_audit.csv", index=False)

    if ledger_matches.empty:
        pd.DataFrame(columns=list(ledger.columns)).to_csv(OUT / "collector_tcgcsv_ledger_reconciliation.csv", index=False)
    else:
        ledger_matches.to_csv(OUT / "collector_tcgcsv_ledger_reconciliation.csv", index=False)

    semantics_valid = (
        candidate_hash == EXPECTED_SHA256
        and required_fields_present
        and invalid_date_count == 0
        and invalid_price_count == 0
        and blank_identity_count == 0
        and non_tcgcsv_source_count == 0
        and future_dated_count == 0
        and duplicate_key_count == 0
        and len(candidate) > 0
    )
    ledger_reconciled = exact_source_file_matches == len(candidate) and len(candidate) > 0
    coverage_90d = distinct_observation_dates >= 2 and calendar_span_days >= 90
    coverage_180d = calendar_span_days >= 180
    coverage_365d = calendar_span_days >= 365

    summary = {
        "block_name": "Collector V1 TCGCSV Historical Authority Verification",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_path": str(CANDIDATE.relative_to(ROOT)),
        "candidate_sha256": candidate_hash,
        "expected_candidate_sha256": EXPECTED_SHA256,
        "candidate_hash_verified": candidate_hash == EXPECTED_SHA256,
        "candidate_row_count": int(len(candidate)),
        "distinct_product_count": distinct_product_count,
        "distinct_observation_date_count": distinct_observation_dates,
        "minimum_observation_date": minimum_observation_date,
        "maximum_observation_date": maximum_observation_date,
        "calendar_span_days": calendar_span_days,
        "invalid_date_row_count": invalid_date_count,
        "invalid_price_row_count": invalid_price_count,
        "blank_identity_row_count": blank_identity_count,
        "non_tcgcsv_source_row_count": non_tcgcsv_source_count,
        "future_dated_row_count": future_dated_count,
        "duplicate_product_timestamp_row_count": duplicate_key_count,
        "ledger_candidate_key_match_count": int(len(ledger_matches)),
        "ledger_exact_source_file_match_count": exact_source_file_matches,
        "provider_row_semantics_valid": semantics_valid,
        "governed_ledger_reconciled": ledger_reconciled,
        "coverage_90d_supported": coverage_90d,
        "coverage_180d_supported": coverage_180d,
        "coverage_365d_supported": coverage_365d,
        "first_year_replay_supported": coverage_365d,
        "tcgcsv_provider_semantics_certified": semantics_valid,
        "raw_historical_price_authority_certified": semantics_valid and ledger_reconciled and coverage_90d,
        "historical_coverage_assessment_authorized": False,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "purchase_recommendations_authorized": False,
        "authority_reason": (
            "VALID_CURRENT_TCGCSV_OBSERVATION_BUT_INSUFFICIENT_HISTORY"
            if semantics_valid and not coverage_90d
            else "UNRESOLVED_TCGCSV_PROVIDER_OR_LEDGER_SEMANTICS"
        ),
        "critical_failures": failures,
        "status": "PASS_COLLECTOR_V1_TCGCSV_HISTORICAL_AUTHORITY_VERIFICATION" if not failures else "FAIL_COLLECTOR_V1_TCGCSV_HISTORICAL_AUTHORITY_VERIFICATION",
    }
    (OUT / "collector_tcgcsv_historical_authority_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"].startswith("PASS") else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
