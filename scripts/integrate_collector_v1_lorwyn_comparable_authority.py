from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_lorwyn_comparable_authority_integration_contract_v1.json"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_lorwyn_comparable_authority_integration"
OUTPUT_AUTHORITY_NAME = "collector_integrated_comparable_pool_authority.csv"
OUTPUT_AUDIT_NAME = "collector_lorwyn_supplemental_comparable_integration_audit.csv"
OUTPUT_SUMMARY_NAME = "collector_lorwyn_comparable_authority_integration_summary.json"

ORIGINAL_FIELDS = [
    "comparable_group_id",
    "target_canonical_product_id",
    "target_product_name",
    "target_release_date",
    "target_licensed_family",
    "comparable_rank",
    "comparable_canonical_product_id",
    "comparable_product_name",
    "comparable_release_date",
    "comparable_observation_count",
    "release_distance_days",
    "price_ratio",
    "licensed_family_match",
    "selection_score",
    "selection_basis",
    "time_safe_rule",
    "certification_status",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


def norm(value: Any) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in clean(value)).split())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ORIGINAL_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def number(value: Any) -> float | None:
    text = clean(value).replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    paths = {name: ROOT / relative for name, relative in contract["authorities"].items()}
    failures: list[str] = []

    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise SystemExit("MISSING_REQUIRED_AUTHORITY:" + ";".join(missing))

    original_hash_before = sha256(paths["original_comparable_pool"])
    current_rows = read_csv(paths["product_and_current_price"])
    release_rows = read_csv(paths["release_date"])
    history_rows = read_csv(paths["historical_observations"])
    original_rows = read_csv(paths["original_comparable_pool"])
    supplemental_rows = read_csv(paths["supplemental_lorwyn_group"])
    supplemental_summary = json.loads(paths["supplemental_lorwyn_summary"].read_text(encoding="utf-8"))

    current_by_id = {clean(row["canonical_product_id"]): row for row in current_rows}
    release_by_id = {clean(row["canonical_product_id"]): row for row in release_rows}
    history_counts = Counter(clean(row["canonical_product_id"]) for row in history_rows)

    if supplemental_summary.get("status") != "PASS_COLLECTOR_LORWYN_TARGET_SPECIFIC_COMPARABLE_CERTIFICATION":
        failures.append("SUPPLEMENTAL_LORWYN_CERTIFICATION_NOT_PASS")
    if int(supplemental_summary.get("certified_comparable_rows", -1)) != int(contract["required_supplemental_rows"]):
        failures.append("SUPPLEMENTAL_SUMMARY_ROW_COUNT_MISMATCH")
    if len(original_rows) != int(contract["required_original_rows"]):
        failures.append(f"ORIGINAL_COMPARABLE_ROW_COUNT:{len(original_rows)}")
    if len(supplemental_rows) != int(contract["required_supplemental_rows"]):
        failures.append(f"SUPPLEMENTAL_COMPARABLE_ROW_COUNT:{len(supplemental_rows)}")

    requested_name = norm(contract["requested_product_name"])
    target_matches = [row for row in current_rows if norm(row["product_name"]) == requested_name]
    if len(target_matches) != 1:
        failures.append(f"TARGET_AUTHORITY_RESOLUTION_COUNT:{len(target_matches)}")
    target_authority = target_matches[0] if len(target_matches) == 1 else None
    target_id = clean(target_authority.get("canonical_product_id")) if target_authority else ""

    mapped_rows: list[dict[str, Any]] = []
    supplemental_audit: list[dict[str, Any]] = []
    for row in supplemental_rows:
        row_target_id = clean(row.get("target_canonical_product_id"))
        member_id = clean(row.get("comparable_canonical_product_id"))
        row_target = current_by_id.get(row_target_id)
        member = current_by_id.get(member_id)
        target_release = release_by_id.get(row_target_id)
        member_release = release_by_id.get(member_id)
        reasons: list[str] = []

        if row_target_id != target_id:
            reasons.append("SUPPLEMENTAL_TARGET_ID_NOT_AUTHORITY_RESOLVED_LORWYN")
        if row_target is None or member is None:
            reasons.append("TARGET_OR_MEMBER_ID_UNKNOWN")
        if row_target_id == member_id:
            reasons.append("SELF_COMPARISON")
        if row_target and norm(row.get("target_product_name")) != norm(row_target.get("product_name")):
            reasons.append("TARGET_NAME_MISMATCH")
        if member and norm(row.get("comparable_product_name")) != norm(member.get("product_name")):
            reasons.append("MEMBER_NAME_MISMATCH")
        if target_release is None or member_release is None:
            reasons.append("TARGET_OR_MEMBER_RELEASE_AUTHORITY_MISSING")
        else:
            governed_target_release = clean(target_release.get("official_release_date"))
            governed_member_release = clean(member_release.get("official_release_date"))
            if clean(row.get("target_release_date")) != governed_target_release:
                reasons.append("TARGET_RELEASE_DATE_MISMATCH")
            if clean(row.get("comparable_release_date")) != governed_member_release:
                reasons.append("MEMBER_RELEASE_DATE_MISMATCH")
            if governed_member_release >= governed_target_release:
                reasons.append("MEMBER_RELEASE_NOT_BEFORE_TARGET")
        if history_counts[member_id] < 2:
            reasons.append("MEMBER_HISTORY_INSUFFICIENT")
        if clean(row.get("certification_status")) != "CERTIFIED_SUPPLEMENTAL_COMPARABLE":
            reasons.append("SUPPLEMENTAL_ROW_NOT_CERTIFIED")

        target_price = number(row_target.get("current_price")) if row_target else None
        member_price = number(member.get("current_price")) if member else None
        price_ratio = ""
        if target_price and member_price and member_price > 0:
            price_ratio = round(target_price / member_price, 6)

        mapped = {
            "comparable_group_id": "LORWYN-SUPPLEMENTAL-20260801",
            "target_canonical_product_id": row_target_id,
            "target_product_name": clean(row.get("target_product_name")),
            "target_release_date": clean(row.get("target_release_date")),
            "target_licensed_family": "STANDARD_OR_CORE_MAGIC",
            "comparable_rank": clean(row.get("comparable_rank")),
            "comparable_canonical_product_id": member_id,
            "comparable_product_name": clean(row.get("comparable_product_name")),
            "comparable_release_date": clean(row.get("comparable_release_date")),
            "comparable_observation_count": clean(row.get("comparable_observation_count")),
            "release_distance_days": clean(row.get("release_distance_days")),
            "price_ratio": price_ratio,
            "licensed_family_match": clean(row.get("franchise_class_similarity")) == "100.0",
            "selection_score": clean(row.get("selection_score")),
            "selection_basis": "CERTIFIED_SUPPLEMENTAL_TARGET_SPECIFIC_COMPARABLE_AUTHORITY",
            "time_safe_rule": clean(row.get("time_safe_rule")),
            "certification_status": "CERTIFIED_SUPPLEMENTAL_COMPARABLE",
        }
        mapped_rows.append(mapped)
        supplemental_audit.append({
            **mapped,
            "history_observation_count_reconciled": history_counts[member_id],
            "identity_release_semantic_reconciled": not reasons,
            "failure_reasons": "|".join(reasons),
        })
        if reasons:
            failures.append(f"SUPPLEMENTAL_ROW_RECONCILIATION_FAILED:{member_id}:{'|'.join(reasons)}")

    original_pairs = {
        (clean(row.get("target_canonical_product_id")), clean(row.get("comparable_canonical_product_id")))
        for row in original_rows
    }
    supplemental_pairs = {
        (clean(row.get("target_canonical_product_id")), clean(row.get("comparable_canonical_product_id")))
        for row in mapped_rows
    }
    if len(supplemental_pairs) != len(mapped_rows):
        failures.append("DUPLICATE_SUPPLEMENTAL_TARGET_MEMBER_PAIR")
    if original_pairs.intersection(supplemental_pairs):
        failures.append("SUPPLEMENTAL_PAIR_COLLIDES_WITH_ORIGINAL_AUTHORITY")

    integrated_rows = [dict(row) for row in original_rows] + mapped_rows
    integrated_pairs = {
        (clean(row.get("target_canonical_product_id")), clean(row.get("comparable_canonical_product_id")))
        for row in integrated_rows
    }
    integrated_targets = {clean(row.get("target_canonical_product_id")) for row in integrated_rows}
    original_targets = {clean(row.get("target_canonical_product_id")) for row in original_rows}

    if len(integrated_rows) != int(contract["required_integrated_rows"]):
        failures.append(f"INTEGRATED_COMPARABLE_ROW_COUNT:{len(integrated_rows)}")
    if len(integrated_pairs) != len(integrated_rows):
        failures.append("DUPLICATE_INTEGRATED_TARGET_MEMBER_PAIR")
    if len(original_targets) != int(contract["required_original_targets"]):
        failures.append(f"ORIGINAL_TARGET_COUNT:{len(original_targets)}")
    if len(integrated_targets) != int(contract["required_integrated_targets"]):
        failures.append(f"INTEGRATED_TARGET_COUNT:{len(integrated_targets)}")
    if target_id not in integrated_targets:
        failures.append("LORWYN_TARGET_NOT_PRESENT_IN_INTEGRATED_AUTHORITY")
    if sha256(paths["original_comparable_pool"]) != original_hash_before:
        failures.append("ORIGINAL_COMPARABLE_AUTHORITY_MODIFIED")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    output_authority = OUTPUT / OUTPUT_AUTHORITY_NAME
    expected_output_authority = ROOT / contract["output_authority"]
    if output_authority.resolve() != expected_output_authority.resolve():
        failures.append("OUTPUT_AUTHORITY_PATH_CONTRACT_MISMATCH")
    write_csv(output_authority, integrated_rows)
    write_csv(OUTPUT / OUTPUT_AUDIT_NAME, supplemental_audit)

    status = contract["expected_status"] if not failures else "FAIL_COLLECTOR_LORWYN_COMPARABLE_AUTHORITY_INTEGRATION"
    summary = {
        "contract_name": contract["contract_name"],
        "contract_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "resolved_target_canonical_product_id": target_id,
        "original_rows": len(original_rows),
        "supplemental_rows": len(mapped_rows),
        "integrated_rows": len(integrated_rows),
        "original_targets": len(original_targets),
        "integrated_targets": len(integrated_targets),
        "integrated_unique_pairs": len(integrated_pairs),
        "original_authority_sha256_before": original_hash_before,
        "original_authority_sha256_after": sha256(paths["original_comparable_pool"]),
        "supplemental_authority_sha256": sha256(paths["supplemental_lorwyn_group"]),
        "integrated_authority_sha256": sha256(output_authority),
        "projection_authorized": False,
        "production_forecast_authorized": False,
        "ranking_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": status,
    }
    (OUTPUT / OUTPUT_SUMMARY_NAME).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
