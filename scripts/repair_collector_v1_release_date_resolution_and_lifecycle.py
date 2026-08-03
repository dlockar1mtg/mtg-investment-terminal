from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_release_date_resolution_and_lifecycle_repair_contract_v1.json"
FOUNDATION = ROOT / "data/governance/permanence/certification/collector_v1_august1_snapshot_bound_current_foundation/collector_v1_august1_snapshot_bound_current_foundation.csv"
PREMODEL = ROOT / "data/governance/permanence/certification/collector_v1_premodel_reasonableness_audit/collector_premodel_product_reasonableness.csv"
LEDGER = ROOT / "data/governance/permanence/certification/collector_v1_august1_historical_observation_ledger/collector_august1_historical_observation_ledger.csv"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_release_date_resolution_and_lifecycle_repair"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def clean(value: Any) -> str:
    return str(value or "").strip()


def parse_date(value: Any) -> datetime | None:
    text = clean(value)
    if not text:
        return None
    normalized = text[:10]
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def resolve_release_date(foundation: dict[str, str], premodel: dict[str, str]) -> tuple[datetime | None, str, str]:
    candidates = [
        ("foundation.identity__raw_released_on", foundation.get("identity__raw_released_on")),
        ("foundation.identity__released_on", foundation.get("identity__released_on")),
        ("foundation.identity__official_release_date", foundation.get("identity__official_release_date")),
        ("foundation.release_date", foundation.get("release_date")),
        ("foundation.released_on", foundation.get("released_on")),
        ("premodel.release_date", premodel.get("release_date")),
    ]
    invalid: list[str] = []
    for source, raw in candidates:
        if not clean(raw):
            continue
        parsed = parse_date(raw)
        if parsed is not None:
            return parsed, source, clean(raw)
        invalid.append(f"{source}={clean(raw)}")
    return None, "", ";".join(invalid)


def lifecycle_band(days: int, bands: dict[str, list[int]]) -> str:
    for name, bounds in bands.items():
        if int(bounds[0]) <= days <= int(bounds[1]):
            return name
    return "UNCLASSIFIED"


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    foundation_rows = read_csv(FOUNDATION)
    premodel_rows = read_csv(PREMODEL)
    ledger_rows = read_csv(LEDGER)

    failures: list[str] = []
    if len(foundation_rows) != contract["required_product_count"]:
        failures.append("FOUNDATION_PRODUCT_COUNT_MISMATCH")
    if len(premodel_rows) != contract["required_product_count"]:
        failures.append("PREMODEL_PRODUCT_COUNT_MISMATCH")
    if len(ledger_rows) != contract["required_ledger_rows"]:
        failures.append("LEDGER_ROW_COUNT_MISMATCH")

    foundation_by_id = {clean(r.get("identity__canonical_product_id")): r for r in foundation_rows}
    premodel_by_id = {clean(r.get("canonical_product_id")): r for r in premodel_rows}
    ledger_counts = Counter(clean(r.get("canonical_product_id")) for r in ledger_rows)

    authority_rows: list[dict[str, Any]] = []
    release_by_id: dict[str, datetime] = {}
    unresolved_products: list[str] = []

    for canonical_id in sorted(foundation_by_id):
        foundation = foundation_by_id[canonical_id]
        premodel = premodel_by_id.get(canonical_id, {})
        release, source, invalid_values = resolve_release_date(foundation, premodel)
        status = "RESOLVED_GOVERNED_SOURCE" if release else "UNRESOLVED_FAIL_CLOSED"
        if release:
            release_by_id[canonical_id] = release
        else:
            unresolved_products.append(canonical_id)
            failures.append(f"RELEASE_DATE_UNRESOLVED:{canonical_id}:affected_rows={ledger_counts.get(canonical_id, 0)}")
        authority_rows.append({
            "canonical_product_id": canonical_id,
            "tcgplayer_product_id": clean(foundation.get("tcgplayer_product_id")),
            "product_name": clean(foundation.get("identity__canonical_product_name")) or clean(premodel.get("product_name")),
            "release_date": release.date().isoformat() if release else "",
            "release_date_source": source,
            "resolution_status": status,
            "affected_ledger_rows": ledger_counts.get(canonical_id, 0),
            "invalid_candidate_values": invalid_values,
        })

    lifecycle_rows: list[dict[str, Any]] = []
    unclassified = 0
    for row in ledger_rows:
        canonical_id = clean(row.get("canonical_product_id"))
        release = release_by_id.get(canonical_id)
        observation = parse_date(row.get("observation_date"))
        if release is None or observation is None:
            days: int | str = ""
            band = "UNCLASSIFIED"
            unclassified += 1
        else:
            days = (observation - release).days
            band = lifecycle_band(days, contract["lifecycle_bands"])
            if band == "UNCLASSIFIED":
                unclassified += 1
        lifecycle_rows.append({
            "ledger_observation_id": clean(row.get("ledger_observation_id")),
            "canonical_product_id": canonical_id,
            "tcgplayer_product_id": clean(row.get("tcgplayer_product_id")),
            "product_name": clean(row.get("canonical_product_name")),
            "observation_date": clean(row.get("observation_date"))[:10],
            "release_date": release.date().isoformat() if release else "",
            "days_from_release": days,
            "lifecycle_band": band,
            "selected_price": clean(row.get("selected_price")),
            "selection_method": clean(row.get("selection_method")),
            "panel_status": "CANDIDATE_NOT_YET_AUTHORIZED",
        })

    if unclassified:
        failures.append(f"UNCLASSIFIED_LIFECYCLE_ROWS:{unclassified}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    authority_path = OUTPUT / "collector_release_date_resolution_authority.csv"
    lifecycle_path = OUTPUT / "collector_lifecycle_panel_repaired_candidate.csv"
    summary_path = OUTPUT / "collector_release_date_resolution_and_lifecycle_repair_summary.json"

    write_csv(authority_path, authority_rows, [
        "canonical_product_id", "tcgplayer_product_id", "product_name", "release_date",
        "release_date_source", "resolution_status", "affected_ledger_rows", "invalid_candidate_values"
    ])
    write_csv(lifecycle_path, lifecycle_rows, [
        "ledger_observation_id", "canonical_product_id", "tcgplayer_product_id", "product_name",
        "observation_date", "release_date", "days_from_release", "lifecycle_band",
        "selected_price", "selection_method", "panel_status"
    ])

    status = (
        "PASS_COLLECTOR_RELEASE_DATE_RESOLUTION_AND_LIFECYCLE_REPAIR"
        if not failures else
        "FAIL_COLLECTOR_RELEASE_DATE_RESOLUTION_AND_LIFECYCLE_REPAIR"
    )
    summary = {
        "block_name": "Collector Release-Date Resolution and Lifecycle Repair",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "governing_snapshot_id": contract["governing_snapshot_id"],
        "product_rows": len(authority_rows),
        "resolved_release_date_products": len(release_by_id),
        "unresolved_release_date_products": len(unresolved_products),
        "ledger_rows": len(lifecycle_rows),
        "classified_lifecycle_rows": len(lifecycle_rows) - unclassified,
        "unclassified_lifecycle_rows": unclassified,
        "release_date_authority_certified": not failures,
        "lifecycle_candidate_repaired": not failures,
        "model_tournament_authorized": False,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": status,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
