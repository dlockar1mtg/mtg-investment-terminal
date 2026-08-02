from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_historical_feature_availability"
LEDGER = AUDIT_DIR / "collector_v1_historical_feature_availability_ledger.csv"
CONTRACT = ROOT / "config/mtg/standards/collector_historical_row_level_temporal_verification_contract_v1.json"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_historical_row_level_temporal_verification"
AS_OF_DATE = pd.Timestamp("2026-08-01", tz="UTC")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_frame(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, dtype=str, encoding="utf-8-sig", low_memory=False).fillna("")
    if suffix == ".xlsx":
        return pd.read_excel(path, dtype=str).fillna("")
    if suffix == ".parquet":
        return pd.read_parquet(path).fillna("")
    if suffix == ".feather":
        return pd.read_feather(path).fillna("")
    if suffix in {".json", ".jsonl"}:
        if suffix == ".jsonl":
            return pd.read_json(path, lines=True, dtype=False).fillna("")
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(payload, list):
            return pd.DataFrame(payload).fillna("")
        if isinstance(payload, dict):
            for value in payload.values():
                if isinstance(value, list) and (not value or isinstance(value[0], dict)):
                    return pd.DataFrame(value).fillna("")
            return pd.DataFrame([payload]).fillna("")
    raise ValueError(f"unsupported_format:{suffix}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)

    missing = [str(p.relative_to(ROOT)) for p in (LEDGER, CONTRACT) if not p.is_file()]
    if missing:
        summary = {
            "block_name": "Collector V1 Historical Row-Level Temporal Verification",
            "critical_failures": [f"missing_required_files:{'|'.join(missing)}"],
            "status": "FAIL_COLLECTOR_V1_HISTORICAL_ROW_LEVEL_TEMPORAL_VERIFICATION_INPUTS_MISSING",
        }
        (OUT / "collector_v1_historical_row_level_temporal_verification_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1 if args.strict else 0

    ledger = pd.read_csv(LEDGER, dtype=str, encoding="utf-8-sig").fillna("")
    contract = json.loads(CONTRACT.read_text(encoding="utf-8-sig"))
    candidates = ledger[ledger["replay_eligible"].str.lower().eq("true")].copy()
    rows: list[dict] = []

    for _, source in candidates.iterrows():
        source_path = str(source["source_path"])
        path = ROOT / source_path
        base = {
            "source_path": source_path,
            "source_sha256": str(source["source_sha256"]),
            "feature_family": str(source["feature_family"]),
            "semantic_role": str(source["semantic_role"]),
            "date_field": str(source["date_field"]),
            "identity_field": str(source["identity_field"]),
        }
        try:
            frame = read_frame(path)
        except Exception as exc:
            rows.append({**base, "row_count": 0, "valid_date_row_count": 0, "invalid_date_row_count": 0,
                         "minimum_observation_date": "", "maximum_observation_date": "", "distinct_product_count": 0,
                         "blank_identity_row_count": 0, "duplicate_identity_date_row_count": 0, "future_dated_row_count": 0,
                         "checkpoint_coverage_count": 0, "row_level_replay_eligible": False,
                         "exclusion_reason": f"read_error:{type(exc).__name__}"})
            continue

        row_count = len(frame)
        date_field = base["date_field"]
        identity_field = base["identity_field"]
        static_authority = base["semantic_role"] == "STATIC_AUTHORITY"
        identity_exists = bool(identity_field and identity_field in frame.columns)
        date_exists = bool(date_field and date_field in frame.columns)
        blank_identity = int(frame[identity_field].astype(str).str.strip().eq("").sum()) if identity_exists else row_count
        distinct_products = int(frame[identity_field].astype(str).str.strip().replace("", pd.NA).nunique()) if identity_exists else 0

        valid_dates = pd.Series(dtype="datetime64[ns, UTC]")
        invalid_date_count = 0
        future_count = 0
        duplicate_count = 0
        min_date = ""
        max_date = ""
        checkpoint_coverage = 0

        if date_exists:
            parsed = pd.to_datetime(frame[date_field], errors="coerce", utc=True)
            valid_mask = parsed.notna()
            valid_dates = parsed[valid_mask]
            invalid_date_count = int((~valid_mask).sum())
            future_count = int((valid_dates > AS_OF_DATE).sum())
            if not valid_dates.empty:
                min_date = valid_dates.min().date().isoformat()
                max_date = valid_dates.max().date().isoformat()
                checkpoint_coverage = int(valid_dates.dt.normalize().nunique())
            if identity_exists:
                keys = pd.DataFrame({"identity": frame[identity_field].astype(str).str.strip(), "date": parsed})
                keys = keys[keys["identity"].ne("") & keys["date"].notna()]
                duplicate_count = int(keys.duplicated(["identity", "date"], keep=False).sum())

        reasons: list[str] = []
        if row_count == 0:
            reasons.append("empty_source")
        if not identity_exists:
            reasons.append("identity_field_missing")
        if blank_identity > 0 and not static_authority:
            reasons.append("blank_identity_rows")
        if not static_authority and not date_exists:
            reasons.append("observation_date_field_missing")
        if not static_authority and date_exists and len(valid_dates) == 0:
            reasons.append("no_valid_observation_dates")
        if invalid_date_count > 0:
            reasons.append("invalid_observation_dates")
        if future_count > 0:
            reasons.append("future_dated_rows")
        if base["semantic_role"] not in {"OBSERVATION_CANDIDATE", "STATIC_AUTHORITY"}:
            reasons.append("semantic_role_not_authorized")

        eligible = not reasons
        rows.append({
            **base,
            "row_count": row_count,
            "valid_date_row_count": int(len(valid_dates)),
            "invalid_date_row_count": invalid_date_count,
            "minimum_observation_date": min_date,
            "maximum_observation_date": max_date,
            "distinct_product_count": distinct_products,
            "blank_identity_row_count": blank_identity,
            "duplicate_identity_date_row_count": duplicate_count,
            "future_dated_row_count": future_count,
            "checkpoint_coverage_count": checkpoint_coverage,
            "row_level_replay_eligible": eligible,
            "exclusion_reason": "|".join(reasons),
        })

    verification = pd.DataFrame(rows)
    verification_path = OUT / "collector_v1_historical_row_level_temporal_verification.csv"
    verification.to_csv(verification_path, index=False)
    eligible = verification[verification["row_level_replay_eligible"].eq(True)] if not verification.empty else verification
    exclusions = verification[verification["row_level_replay_eligible"].eq(False)] if not verification.empty else verification
    exclusions_path = OUT / "collector_v1_historical_row_level_temporal_exclusions.csv"
    exclusions.to_csv(exclusions_path, index=False)

    checks = {
        "candidate_sources_present": len(candidates) > 0,
        "all_candidates_verified": len(verification) == len(candidates),
        "required_output_fields_present": set(contract["required_verification_outputs"]).issubset(verification.columns),
        "derived_outputs_not_verified_as_replay": not bool(verification.loc[verification["semantic_role"].eq("DERIVED_OR_OPERATIONAL_OUTPUT"), "row_level_replay_eligible"].any()) if not verification.empty else True,
        "panel_build_not_yet_authorized": contract["authorization"]["lifecycle_panel_build_authorized"] is False,
    }
    failures = [k for k, v in checks.items() if not bool(v)]
    summary = {
        "block_name": "Collector V1 Historical Row-Level Temporal Verification",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_source_count": len(candidates),
        "verified_source_count": len(verification),
        "row_level_replay_eligible_source_count": len(eligible),
        "row_level_excluded_source_count": len(exclusions),
        "total_rows_reviewed": int(pd.to_numeric(verification.get("row_count", pd.Series(dtype=int)), errors="coerce").fillna(0).sum()),
        "invalid_date_rows": int(pd.to_numeric(verification.get("invalid_date_row_count", pd.Series(dtype=int)), errors="coerce").fillna(0).sum()),
        "blank_identity_rows": int(pd.to_numeric(verification.get("blank_identity_row_count", pd.Series(dtype=int)), errors="coerce").fillna(0).sum()),
        "duplicate_identity_date_rows": int(pd.to_numeric(verification.get("duplicate_identity_date_row_count", pd.Series(dtype=int)), errors="coerce").fillna(0).sum()),
        "future_dated_rows": int(pd.to_numeric(verification.get("future_dated_row_count", pd.Series(dtype=int)), errors="coerce").fillna(0).sum()),
        "verification_path": str(verification_path.relative_to(ROOT)),
        "verification_sha256": sha256(verification_path),
        "exclusions_path": str(exclusions_path.relative_to(ROOT)),
        "exclusions_sha256": sha256(exclusions_path),
        "checks": checks,
        "critical_failures": failures,
        "row_level_temporal_verification_certified": not failures,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "purchase_recommendations_authorized": False,
        "status": "PASS_COLLECTOR_V1_HISTORICAL_ROW_LEVEL_TEMPORAL_VERIFICATION" if not failures else "FAIL_COLLECTOR_V1_HISTORICAL_ROW_LEVEL_TEMPORAL_VERIFICATION",
    }
    summary_path = OUT / "collector_v1_historical_row_level_temporal_verification_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
