from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_wizards_release_date_authority_contract_v1.json"
EVIDENCE = ROOT / "data/governance/mtg/standards/collector_wizards_release_date_evidence_v1.csv"
PRODUCTS = ROOT / "data/governance/permanence/certification/collector_v1_premodel_reasonableness_audit/collector_premodel_product_reasonableness.csv"
LEDGER = ROOT / "data/governance/permanence/certification/collector_v1_august1_historical_observation_ledger/collector_august1_historical_observation_ledger.csv"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_wizards_release_date_authority"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def clean(value: object) -> str:
    return str(value or "").strip()


def parse_date(value: object) -> datetime | None:
    text = clean(value)[:10]
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def fingerprint(row: dict[str, str]) -> str:
    payload = "|".join(clean(row.get(k)) for k in sorted(row))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def lifecycle_band(days: int, bands: dict[str, list[int]]) -> str:
    for name, bounds in bands.items():
        if int(bounds[0]) <= days <= int(bounds[1]):
            return name
    return "UNCLASSIFIED"


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    products = read_csv(PRODUCTS)
    evidence = read_csv(EVIDENCE)
    ledger = read_csv(LEDGER)
    failures: list[str] = []

    if len(products) != contract["required_product_count"]:
        failures.append("PRODUCT_COUNT_MISMATCH")
    if len(evidence) != contract["required_missing_evidence_rows"]:
        failures.append("EVIDENCE_ROW_COUNT_MISMATCH")
    if len(ledger) != contract["required_ledger_rows"]:
        failures.append("LEDGER_ROW_COUNT_MISMATCH")

    product_by_id = {clean(r.get("canonical_product_id")): r for r in products}
    evidence_by_id: dict[str, dict[str, str]] = {}
    evidence_cert: list[dict[str, object]] = []

    for row in evidence:
        cid = clean(row.get("canonical_product_id"))
        host = urlparse(clean(row.get("wizards_source_url"))).hostname or ""
        date = parse_date(row.get("official_release_date"))
        row_failures: list[str] = []
        if cid not in product_by_id:
            row_failures.append("IDENTITY_NOT_IN_CURRENT_UNIVERSE")
        if host.lower() != contract["official_domain"]:
            row_failures.append("NON_WIZARDS_SOURCE")
        if date is None:
            row_failures.append("INVALID_RELEASE_DATE")
        if clean(row.get("evidence_status")) != "OFFICIAL_WIZARDS_EVIDENCE":
            row_failures.append("EVIDENCE_STATUS_INVALID")
        if cid in evidence_by_id:
            row_failures.append("DUPLICATE_EVIDENCE_IDENTITY")
        evidence_by_id[cid] = row
        evidence_cert.append({**row, "evidence_fingerprint": fingerprint(row), "certification_status": "PASS" if not row_failures else "FAIL", "certification_failures": ";".join(row_failures)})
        failures.extend(f"EVIDENCE:{cid}:{item}" for item in row_failures)

    authority_rows: list[dict[str, object]] = []
    authority_by_id: dict[str, dict[str, object]] = {}
    for cid, product in product_by_id.items():
        existing = parse_date(product.get("release_date"))
        evidence_row = evidence_by_id.get(cid)
        evidence_date = parse_date(evidence_row.get("official_release_date")) if evidence_row else None
        if existing and evidence_date and existing.date() != evidence_date.date():
            failures.append(f"RELEASE_DATE_CONFLICT:{cid}:{existing.date()}:{evidence_date.date()}")
            selected = None
            source = "CONFLICT"
            source_url = clean(evidence_row.get("wizards_source_url"))
        elif evidence_date:
            selected = evidence_date
            source = "WIZARDS_OFFICIAL_EVIDENCE_V1"
            source_url = clean(evidence_row.get("wizards_source_url"))
        elif existing:
            selected = existing
            source = "PRIOR_GOVERNED_RELEASE_DATE"
            source_url = ""
        else:
            selected = None
            source = "UNRESOLVED"
            source_url = ""
            failures.append(f"RELEASE_DATE_UNRESOLVED:{cid}")
        row = {
            "canonical_product_id": cid,
            "tcgplayer_product_id": clean(product.get("tcgplayer_product_id")),
            "product_name": clean(product.get("product_name")),
            "official_release_date": selected.date().isoformat() if selected else "",
            "release_date_source": source,
            "wizards_source_url": source_url,
            "resolution_status": "RESOLVED_GOVERNED_SOURCE" if selected else "BLOCKED_UNRESOLVED",
        }
        authority_rows.append(row)
        authority_by_id[cid] = row

    lifecycle_rows: list[dict[str, object]] = []
    for row in ledger:
        cid = clean(row.get("canonical_product_id"))
        release = parse_date(authority_by_id.get(cid, {}).get("official_release_date"))
        observation = parse_date(row.get("observation_date"))
        if not release or not observation:
            band = "UNCLASSIFIED"
            days: int | str = ""
        else:
            days = (observation - release).days
            band = lifecycle_band(days, contract["lifecycle_bands"])
        lifecycle_rows.append({
            "ledger_observation_id": clean(row.get("ledger_observation_id")),
            "canonical_product_id": cid,
            "tcgplayer_product_id": clean(row.get("tcgplayer_product_id")),
            "product_name": clean(row.get("canonical_product_name")),
            "observation_date": clean(row.get("observation_date"))[:10],
            "official_release_date": release.date().isoformat() if release else "",
            "days_from_release": days,
            "lifecycle_band": band,
            "selected_price": clean(row.get("selected_price")),
            "selection_method": clean(row.get("selection_method")),
            "panel_status": "FINAL_CANDIDATE_NOT_MODEL_AUTHORIZED",
        })

    unresolved = [r for r in authority_rows if r["resolution_status"] != "RESOLVED_GOVERNED_SOURCE"]
    unclassified = [r for r in lifecycle_rows if r["lifecycle_band"] == "UNCLASSIFIED"]
    if unresolved:
        failures.append(f"UNRESOLVED_RELEASE_DATES:{len(unresolved)}")
    if unclassified:
        failures.append(f"UNCLASSIFIED_LIFECYCLE_ROWS:{len(unclassified)}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_wizards_release_date_evidence_certification.csv", evidence_cert, list(evidence_cert[0].keys()))
    write_csv(OUTPUT / "collector_wizards_release_date_authority.csv", authority_rows, list(authority_rows[0].keys()))
    write_csv(OUTPUT / "collector_lifecycle_panel_final_candidate.csv", lifecycle_rows, list(lifecycle_rows[0].keys()))

    passed = not failures and len(authority_rows) == 50 and len(lifecycle_rows) == 1215
    summary = {
        "block_name": "Collector Wizards Official Release-Date Authority",
        "block_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "governing_snapshot_id": contract["governing_snapshot_id"],
        "product_rows": len(authority_rows),
        "official_wizards_evidence_rows": len(evidence_cert),
        "resolved_release_date_products": len(authority_rows) - len(unresolved),
        "unresolved_release_date_products": len(unresolved),
        "ledger_rows": len(lifecycle_rows),
        "classified_lifecycle_rows": len(lifecycle_rows) - len(unclassified),
        "unclassified_lifecycle_rows": len(unclassified),
        "release_date_authority_certified": passed,
        "lifecycle_panel_build_authorized": passed,
        "model_tournament_authorized": False,
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": "PASS_COLLECTOR_WIZARDS_RELEASE_DATE_AUTHORITY" if passed else "FAIL_COLLECTOR_WIZARDS_RELEASE_DATE_AUTHORITY",
    }
    (OUTPUT / "collector_wizards_release_date_authority_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
