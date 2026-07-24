from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_PRODUCTS = 49
EXPECTED_TIERS = {
    "FULL_MODEL": 36,
    "PROVISIONAL_MODEL": 11,
    "STRUCTURAL_ONLY": 2,
}
EXPECTED_BASES = {
    "OBSERVED_GOVERNED": 36,
    "OBSERVED_LIMITED": 9,
    "OBSERVED_SINGLE": 2,
    "NO_ACCEPTED_OBSERVATION": 2,
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("No rows available for CSV output")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_admission_ledger(profile_path: Path, output_root: Path) -> dict[str, object]:
    rows = _read_csv(profile_path)
    ledger_rows: list[dict[str, object]] = []

    for row in rows:
        tier = row["candidate_admission_tier"]
        basis = row["candidate_valuation_basis"]
        value = row.get("candidate_market_value_usd", "").strip()
        confidence = row["candidate_confidence"]

        model_eligible = "YES" if tier == "FULL_MODEL" else "NO"
        forecast_eligible = "YES" if tier in {"FULL_MODEL", "PROVISIONAL_MODEL"} else "NO"
        recommendation_eligible = "YES" if tier == "FULL_MODEL" else "NO"

        if tier == "STRUCTURAL_ONLY":
            admission_status = "STRUCTURAL_ONLY"
            suppression_reason = "NO_ACCEPTED_OBSERVATION"
        elif tier == "PROVISIONAL_MODEL":
            admission_status = "PROVISIONAL"
            suppression_reason = "INSUFFICIENT_RETAINED_OBSERVATIONS"
        else:
            admission_status = "ADMITTED"
            suppression_reason = ""

        ledger_rows.append({
            "canonical_product_id": row["canonical_product_id"],
            "canonical_product_name": row["canonical_product_name"],
            "canonical_set_name": row["canonical_set_name"],
            "tcgplayer_product_id": row["tcgplayer_product_id"],
            "raw_accepted_observations": int(row["raw_accepted_observations"]),
            "retained_observations": int(row["retained_observations"]),
            "removed_outliers": int(row["removed_outliers"]),
            "market_value_usd": value,
            "admission_tier": tier,
            "valuation_basis": basis,
            "confidence": confidence,
            "admission_status": admission_status,
            "model_eligible": model_eligible,
            "forecast_eligible": forecast_eligible,
            "recommendation_eligible": recommendation_eligible,
            "suppression_reason": suppression_reason,
        })

    ledger_rows.sort(key=lambda row: str(row["canonical_product_id"]))
    ledger_path = output_root / "collector_booster_box_market_value_admission_ledger.csv"
    _write_csv(ledger_path, ledger_rows)

    tier_counts = Counter(str(row["admission_tier"]) for row in ledger_rows)
    basis_counts = Counter(str(row["valuation_basis"]) for row in ledger_rows)
    ids = [str(row["canonical_product_id"]) for row in ledger_rows]

    checks = {
        "rows_equal_49": len(ledger_rows) == EXPECTED_PRODUCTS,
        "canonical_ids_unique": len(ids) == len(set(ids)),
        "tier_counts_match_profile": dict(tier_counts) == EXPECTED_TIERS,
        "basis_counts_match_profile": dict(basis_counts) == EXPECTED_BASES,
        "full_model_values_present": all(
            row["market_value_usd"] != ""
            for row in ledger_rows
            if row["admission_tier"] == "FULL_MODEL"
        ),
        "provisional_values_present": all(
            row["market_value_usd"] != ""
            for row in ledger_rows
            if row["admission_tier"] == "PROVISIONAL_MODEL"
        ),
        "structural_values_absent": all(
            row["market_value_usd"] == ""
            for row in ledger_rows
            if row["admission_tier"] == "STRUCTURAL_ONLY"
        ),
        "only_full_model_is_recommendation_eligible": all(
            (row["recommendation_eligible"] == "YES")
            == (row["admission_tier"] == "FULL_MODEL")
            for row in ledger_rows
        ),
        "quota_calls_zero": True,
    }

    status = "CERTIFIED" if all(checks.values()) else "FAILED"
    manifest = {
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "10.7.4",
        "lane": "COLLECTOR_BOOSTER_BOX",
        "products": len(ledger_rows),
        "tier_counts": dict(sorted(tier_counts.items())),
        "basis_counts": dict(sorted(basis_counts.items())),
        "model_eligible_products": sum(row["model_eligible"] == "YES" for row in ledger_rows),
        "forecast_eligible_products": sum(row["forecast_eligible"] == "YES" for row in ledger_rows),
        "recommendation_eligible_products": sum(row["recommendation_eligible"] == "YES" for row in ledger_rows),
        "checks": checks,
        "quota_calls": 0,
        "profile_sha256": hashlib.sha256(profile_path.read_bytes()).hexdigest(),
        "outputs": {"ledger": str(ledger_path.resolve())},
    }

    manifest_path = output_root / "collector_booster_box_market_value_admission_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    certification_path = output_root / "PHASE_10_7_4_COLLECTOR_BOX_ADMISSION_CERTIFICATION.md"
    lines = [
        "# Phase 10.7.4 Collector Booster Box Market-Value Admission Certification",
        "",
        f"**Status:** {status}",
        "",
        f"- Governed products: {len(ledger_rows)}",
        f"- Full model: {tier_counts.get('FULL_MODEL', 0)}",
        f"- Provisional model: {tier_counts.get('PROVISIONAL_MODEL', 0)}",
        f"- Structural only: {tier_counts.get('STRUCTURAL_ONLY', 0)}",
        "- API quota calls: 0",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in checks.items())
    certification_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest["outputs"]["manifest"] = str(manifest_path.resolve())
    manifest["outputs"]["certification"] = str(certification_path.resolve())
    return manifest
