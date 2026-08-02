from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_historical_feature_availability_contract_v1.json"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_historical_feature_availability"
SCAN_ROOTS = [ROOT / "data", ROOT / "artifacts", ROOT / "terminal2"]
DATE_HINTS = ("date", "timestamp", "observed_at", "collected_at", "as_of", "generated_at", "release")
IDENTITY_HINTS = ("tcgplayer_product_id", "product_id", "investment_product_id", "sku", "name")
FEATURE_FAMILIES = {
    "price": ("price", "market_value", "valuation"),
    "product_identity": ("product_id", "tcgplayer", "product_name", "sku"),
    "release_and_age": ("release_date", "product_age", "days_since_release"),
    "structural_product_attributes": ("configuration", "franchise", "premium", "serialized", "reprint"),
    "supply": ("supply", "inventory", "quantity", "sealed_supply"),
    "demand": ("demand", "sales", "velocity", "watch", "views"),
    "listing_market": ("listing", "seller", "ask", "ebay"),
    "liquidity": ("liquidity", "spread", "turnover", "depth"),
    "comparable_features": ("comparable", "similarity", "peer"),
    "market_regime": ("regime", "market_index", "macro"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def classify_family(text: str) -> str:
    low = text.lower()
    for family, terms in FEATURE_FAMILIES.items():
        if any(term in low for term in terms):
            return family
    return "other"


def candidate_files() -> list[Path]:
    allowed = {".csv", ".json", ".jsonl", ".parquet", ".feather", ".xlsx"}
    files: list[Path] = []
    for base in SCAN_ROOTS:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in allowed and ".git" not in path.parts:
                files.append(path)
    return sorted(set(files))


def inspect_tabular(path: Path) -> tuple[list[str], int | None]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            frame = pd.read_csv(path, nrows=200, dtype=str, encoding="utf-8-sig")
        elif suffix in {".parquet", ".feather"}:
            frame = pd.read_parquet(path) if suffix == ".parquet" else pd.read_feather(path)
            frame = frame.head(200)
        elif suffix == ".xlsx":
            frame = pd.read_excel(path, nrows=200, dtype=str)
        else:
            return [], None
        return [str(c) for c in frame.columns], len(frame)
    except Exception:
        return [], None


def inspect_json(path: Path) -> list[str]:
    try:
        if path.suffix.lower() == ".jsonl":
            with path.open("r", encoding="utf-8-sig") as handle:
                first_line = next((line for line in handle if line.strip()), "")
            payload = json.loads(first_line) if first_line else None
        else:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    if isinstance(payload, dict):
        return [str(k) for k in payload.keys()]
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return [str(k) for k in payload[0].keys()]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8-sig"))
    rows: list[dict] = []
    for path in candidate_files():
        rel = str(path.relative_to(ROOT))
        columns, sample_rows = inspect_tabular(path)
        if path.suffix.lower() in {".json", ".jsonl"}:
            columns = inspect_json(path)
        combined = " ".join([rel, *columns]).lower()
        family = classify_family(combined)
        if family == "other":
            continue
        date_field = next((c for c in columns if any(h in c.lower() for h in DATE_HINTS)), "")
        identity_field = next((c for c in columns if any(h == c.lower() or h in c.lower() for h in IDENTITY_HINTS)), "")
        static_family = family in {"product_identity", "structural_product_attributes", "release_and_age"}
        if date_field and identity_field:
            state = "DIRECT_POINT_IN_TIME"
            eligible = True
            reason = ""
        elif static_family and identity_field:
            state = "STATIC_KNOWN_BY_CHECKPOINT"
            eligible = True
            reason = ""
        elif date_field:
            state = "DATE_UNVERIFIED"
            eligible = False
            reason = "identity_field_not_verified"
        else:
            state = "DATE_UNVERIFIED"
            eligible = False
            reason = "historical_observation_date_not_verified"
        rows.append({
            "feature_name": Path(rel).stem,
            "feature_family": family,
            "source_path": rel,
            "source_sha256": sha256(path),
            "source_format": path.suffix.lower().lstrip("."),
            "date_field": date_field,
            "identity_field": identity_field,
            "minimum_observation_date": "",
            "maximum_observation_date": "",
            "availability_state": state,
            "replay_eligible": eligible,
            "exclusion_reason": reason,
            "provenance_notes": f"schema-level audit; sampled_rows={sample_rows if sample_rows is not None else ''}",
        })
    ledger = pd.DataFrame(rows)
    ledger_path = OUT / "collector_v1_historical_feature_availability_ledger.csv"
    ledger.to_csv(ledger_path, index=False)
    eligible = ledger[ledger["replay_eligible"].eq(True)] if not ledger.empty else ledger
    family_summary = (
        ledger.groupby(["feature_family", "availability_state"], dropna=False)
        .size()
        .reset_index(name="source_count")
        if not ledger.empty
        else pd.DataFrame(columns=["feature_family", "availability_state", "source_count"])
    )
    family_path = OUT / "collector_v1_historical_feature_availability_summary.csv"
    family_summary.to_csv(family_path, index=False)
    checks = {
        "contract_present": CONTRACT.is_file(),
        "candidate_sources_found": len(ledger) > 0,
        "required_ledger_fields_present": set(contract["required_ledger_fields"]).issubset(ledger.columns),
        "no_current_state_backfill_authorized": contract["controls"]["current_state_backfill_prohibited"] is True,
        "historical_zero_fill_prohibited": contract["controls"]["historical_zero_fill_prohibited"] is True,
        "unknown_date_not_point_in_time": contract["controls"]["unknown_date_is_not_point_in_time"] is True,
        "panel_build_not_yet_authorized": contract["authorization"]["lifecycle_panel_build_authorized"] is False,
    }
    failures = [k for k, v in checks.items() if not bool(v)]
    summary = {
        "block_name": "Collector V1 Historical Feature Availability Audit",
        "block_version": "1.0.1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources_reviewed": len(ledger),
        "replay_eligible_sources": len(eligible),
        "availability_state_counts": ledger["availability_state"].value_counts().sort_index().to_dict() if not ledger.empty else {},
        "feature_family_counts": ledger["feature_family"].value_counts().sort_index().to_dict() if not ledger.empty else {},
        "ledger_path": str(ledger_path.relative_to(ROOT)),
        "ledger_sha256": sha256(ledger_path),
        "family_summary_path": str(family_path.relative_to(ROOT)),
        "family_summary_sha256": sha256(family_path),
        "checks": checks,
        "critical_failures": failures,
        "feature_availability_audit_certified": not failures,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "purchase_recommendations_authorized": False,
        "status": "PASS_COLLECTOR_V1_HISTORICAL_FEATURE_AVAILABILITY_AUDIT" if not failures else "FAIL_COLLECTOR_V1_HISTORICAL_FEATURE_AVAILABILITY_AUDIT",
    }
    (OUT / "collector_v1_historical_feature_availability_audit_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if not failures else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
