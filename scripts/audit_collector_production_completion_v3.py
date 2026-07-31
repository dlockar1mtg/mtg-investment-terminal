from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data/operations/collector_production_completion/baseline_v3_0_0"

DATASETS = {
    "registry": ROOT / "data/product_master/investment_products.csv",
    "model": ROOT / "data/product_master/product_master_model_input.csv",
    "history": ROOT / "data/operations/collector_booster_history_certification/candidate_v1_0_0/collector_history_product_certification.csv",
    "evidence": ROOT / "data/operations/collector_evidence_normalization/candidate_v1_0_0/collector_normalized_evidence.csv",
    "routes": ROOT / "data/operations/collector_forecast_method_routing/candidate_v1_0_0/collector_forecast_method_routes.csv",
    "comparable_targets": ROOT / "data/operations/collector_comparable_selection/candidate_v1_0_0/collector_comparable_target_status.csv",
    "selected_comparables": ROOT / "data/operations/collector_comparable_selection/candidate_v1_0_0/collector_selected_comparables.csv",
}

HYBRID_OVERRIDE = ROOT / "data/governance/mtg/collector_comparables/collector_japanese_edition_hybrid_override_v1.json"
CONTROL_TRACEABILITY = ROOT / "config/mtg/governance/collector_control_traceability_v1.json"

SUPPORTED_METHODS = {
    "DIRECT_HISTORY_CALIBRATED",
    "DIRECT_HISTORY_LIMITED",
    "COMPARABLE_PRODUCT_ADJUSTED",
    "FUNDAMENTAL_COMPARABLE_HYBRID",
    "DEFERRED_IDENTITY",
    "DEFERRED_MISSING_PRICE",
    "DEFERRED_INSUFFICIENT_EVIDENCE",
}

ACTIVE_COUNT_SCAN_PATHS = {
    "scripts/build_mtg_hosted_uip_delivery.py",
    "scripts/build_unified_mtg_intelligence.py",
    "scripts/build_universal_mtg_daily_history.py",
    "scripts/build_universal_mtg_history_ledger.py",
    "scripts/build_universal_mtg_market_valuation.py",
    "scripts/normalize_collector_evidence.py",
}
COUNT_LITERALS = {47, 51, 83, 973, 1141, 1363, 4787}
COUNT_CONTEXT = re.compile(r"(?i)(expected|required|must\s+equal|len\s*\(|row_count|product_count|count)")


def clean(value: Any) -> str:
    return str(value or "").strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def first_present(row: dict[str, str], names: Iterable[str]) -> str:
    for name in names:
        value = clean(row.get(name))
        if value:
            return value
    return ""


def product_id(row: dict[str, str]) -> str:
    return first_present(row, ("investment_product_id", "target_product_id", "canonical_product_id", "product_id", "asset_id"))


def product_name(row: dict[str, str]) -> str:
    return first_present(row, ("product_name", "target_product_name", "box_name", "box_name_master", "approved_product_name", "name", "asset_name"))


def is_collector_row(row: dict[str, str]) -> bool:
    product_type = first_present(row, ("investment_product_type", "product_lane", "lane", "product_class")).upper()
    name = product_name(row).upper()
    positive = product_type in {
        "COLLECTOR BOOSTER DISPLAY",
        "COLLECTOR_BOOSTER",
        "COLLECTOR_BOOSTER_BOX",
    } or "COLLECTOR BOOSTER DISPLAY" in name
    excluded = any(term in name for term in (" CASE", " PACK", " BUNDLE"))
    return positive and not excluded


def index_unique(rows: list[dict[str, str]], dataset: str) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    indexed: dict[str, dict[str, str]] = {}
    issues: list[dict[str, str]] = []
    for row in rows:
        key = product_id(row)
        if not key:
            issues.append({"dataset": dataset, "product_id": "", "issue": "MISSING_PRODUCT_ID"})
        elif key in indexed:
            issues.append({"dataset": dataset, "product_id": key, "issue": "DUPLICATE_PRODUCT_ID"})
        else:
            indexed[key] = row
    return indexed, issues


def load_hybrid_override() -> dict[str, Any]:
    if not HYBRID_OVERRIDE.exists():
        return {}
    return json.loads(HYBRID_OVERRIDE.read_text(encoding="utf-8"))


def load_control_traceability() -> dict[str, Any]:
    if not CONTROL_TRACEABILITY.exists():
        return {}
    return json.loads(CONTROL_TRACEABILITY.read_text(encoding="utf-8"))


def scan_active_hard_coded_counts() -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for relative in sorted(ACTIVE_COUNT_SCAN_PATHS):
        path = ROOT / relative
        if not path.exists():
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
            if not COUNT_CONTEXT.search(line):
                continue
            for literal in sorted(COUNT_LITERALS):
                if re.search(rf"(?<!\d){literal}(?!\d)", line):
                    findings.append({
                        "path": relative,
                        "line_number": line_number,
                        "literal": literal,
                        "line": line.strip()[:500],
                        "classification": "ACTIVE_PRODUCTION_REVIEW",
                    })
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Collector production completion using approved MTG standards only.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    generated_at = datetime.now(timezone.utc).isoformat()
    loaded: dict[str, list[dict[str, str]]] = {}
    inventory_rows: list[dict[str, Any]] = []
    missing_datasets: list[str] = []

    for name, path in DATASETS.items():
        rows = read_csv(path) if path.exists() else []
        loaded[name] = rows
        if not path.exists():
            missing_datasets.append(name)
        inventory_rows.append({
            "dataset": name,
            "path": path.relative_to(ROOT).as_posix(),
            "exists": path.exists(),
            "row_count": len(rows),
            "column_count": len(rows[0]) if rows else 0,
        })

    unique_dataset_names = ("registry", "model", "history", "evidence", "routes", "comparable_targets")
    indexes: dict[str, dict[str, dict[str, str]]] = {}
    identity_issues: list[dict[str, str]] = []
    for name in unique_dataset_names:
        indexes[name], issues = index_unique(loaded[name], name)
        identity_issues.extend(issues)

    selected_rows = loaded["selected_comparables"]
    selected_by_target: Counter[str] = Counter(product_id(row) for row in selected_rows if product_id(row))

    override = load_hybrid_override()
    override_product_id = clean(override.get("investment_product_id"))
    override_primary_comparable = clean(override.get("primary_comparable_product_id"))
    override_approved_method = clean(override.get("approved_method"))

    route_ids = set(indexes["routes"])
    history_ids = set(indexes["history"])
    evidence_ids = set(indexes["evidence"])
    comparable_target_ids = set(indexes["comparable_targets"])
    registry_collector_ids = {product_id(row) for row in loaded["registry"] if product_id(row) and is_collector_row(row)}
    model_collector_ids = {product_id(row) for row in loaded["model"] if product_id(row) and is_collector_row(row)}
    universe_ids = set(route_ids)

    all_ids = sorted(universe_ids | registry_collector_ids | model_collector_ids | history_ids | evidence_ids | comparable_target_ids)
    reconciliation_rows: list[dict[str, Any]] = []
    structural_failures: list[str] = []
    method_counter: Counter[str] = Counter()

    for key in all_ids:
        route = indexes["routes"].get(key, {})
        method = clean(route.get("forecast_method"))
        if key in universe_ids and method:
            method_counter[method] += 1

        standard_comparable_present = key in comparable_target_ids and selected_by_target[key] > 0
        hybrid_override_present = (
            key == override_product_id
            and method == override_approved_method
            and bool(override_primary_comparable)
            and override_primary_comparable in universe_ids
        )
        comparable_requirement_satisfied = standard_comparable_present or hybrid_override_present

        issues: list[str] = []
        if key in universe_ids and key not in registry_collector_ids:
            issues.append("MISSING_FROM_COLLECTOR_REGISTRY")
        if key in universe_ids and key not in model_collector_ids:
            issues.append("MISSING_FROM_COLLECTOR_MODEL")
        if key in universe_ids and key not in history_ids:
            issues.append("MISSING_HISTORY_CERTIFICATION")
        if key in universe_ids and key not in evidence_ids:
            issues.append("MISSING_NORMALIZED_EVIDENCE")
        if key in universe_ids and not method:
            issues.append("MISSING_METHOD_ROUTE")
        if method and method not in SUPPORTED_METHODS:
            issues.append("UNSUPPORTED_METHOD")
        if method in {"COMPARABLE_PRODUCT_ADJUSTED", "FUNDAMENTAL_COMPARABLE_HYBRID"} and not comparable_requirement_satisfied:
            issues.append("MISSING_APPROVED_COMPARABLE_EVIDENCE")

        if key in universe_ids:
            structural_failures.extend(f"{key}:{issue}" for issue in issues)

        source = route or indexes["evidence"].get(key, {}) or indexes["history"].get(key, {}) or indexes["registry"].get(key, {})
        reconciliation_rows.append({
            "investment_product_id": key,
            "product_name": product_name(source),
            "in_governed_universe": key in universe_ids,
            "in_registry": key in registry_collector_ids,
            "in_model": key in model_collector_ids,
            "history_present": key in history_ids,
            "evidence_present": key in evidence_ids,
            "route_present": key in route_ids,
            "forecast_method": method,
            "standard_comparable_present": standard_comparable_present,
            "hybrid_override_present": hybrid_override_present,
            "approved_comparable_requirement_satisfied": comparable_requirement_satisfied,
            "issues": "|".join(issues),
        })

    control_traceability = load_control_traceability()
    unapproved_controls = [
        row for row in control_traceability.get("controls", [])
        if row.get("authority_status") not in {"MTG_STANDARD", "OWNER_APPROVED"}
        and row.get("implementation_status") == "ACTIVE"
    ]

    hard_coded_findings = scan_active_hard_coded_counts()

    write_csv(args.output / "collector_pipeline_inventory.csv", inventory_rows, ["dataset", "path", "exists", "row_count", "column_count"])
    write_csv(args.output / "collector_product_reconciliation.csv", reconciliation_rows, [
        "investment_product_id", "product_name", "in_governed_universe", "in_registry", "in_model",
        "history_present", "evidence_present", "route_present", "forecast_method",
        "standard_comparable_present", "hybrid_override_present",
        "approved_comparable_requirement_satisfied", "issues",
    ])
    write_csv(args.output / "collector_identity_issues.csv", identity_issues, ["dataset", "product_id", "issue"])
    write_csv(args.output / "collector_active_hard_coded_count_findings.csv", hard_coded_findings, ["path", "line_number", "literal", "classification", "line"])

    summary = {
        "audit_name": "Collector Production Completion Baseline",
        "audit_version": "3.0.0",
        "generated_at_utc": generated_at,
        "dynamic_universe_count": len(universe_ids),
        "registry_collector_count": len(registry_collector_ids),
        "registry_not_in_governed_universe_count": len(registry_collector_ids - universe_ids),
        "model_collector_count": len(model_collector_ids),
        "history_count": len(history_ids),
        "normalized_evidence_count": len(evidence_ids),
        "method_route_count": len(route_ids),
        "comparable_target_count": len(comparable_target_ids),
        "selected_comparable_row_count": len(selected_rows),
        "approved_hybrid_override_count": 1 if override_product_id else 0,
        "method_distribution": dict(sorted(method_counter.items())),
        "missing_datasets": missing_datasets,
        "identity_issue_count": len(identity_issues),
        "structural_failure_count": len(set(structural_failures)),
        "structural_failures": sorted(set(structural_failures)),
        "active_hard_coded_count_finding_count": len(hard_coded_findings),
        "active_unapproved_control_count": len(unapproved_controls),
        "active_unapproved_controls": unapproved_controls,
        "projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "owner_approval_status": "NOT_REQUESTED",
        "status": "PASS" if not missing_datasets and not identity_issues and not structural_failures and not unapproved_controls else "REVIEW_REQUIRED",
        "governing_note": "Only controls authorized by the MTG standards or explicit owner approval may be active.",
    }
    write_json(args.output / "collector_production_baseline_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.strict and summary["status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
