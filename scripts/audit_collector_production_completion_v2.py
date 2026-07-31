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
DEFAULT_OUTPUT = ROOT / "data/operations/collector_production_completion/baseline_v2_0_0"

DATASETS = {
    "registry": ROOT / "data/product_master/investment_products.csv",
    "model": ROOT / "data/product_master/product_master_model_input.csv",
    "history": ROOT / "data/operations/collector_booster_history_certification/candidate_v1_0_0/collector_history_product_certification.csv",
    "evidence": ROOT / "data/operations/collector_evidence_normalization/candidate_v1_0_0/collector_normalized_evidence.csv",
    "routes": ROOT / "data/operations/collector_forecast_method_routing/candidate_v1_0_0/collector_forecast_method_routes.csv",
    "comparable_targets": ROOT / "data/operations/collector_comparable_selection/candidate_v1_0_0/collector_comparable_target_status.csv",
    "selected_comparables": ROOT / "data/operations/collector_comparable_selection/candidate_v1_0_0/collector_selected_comparables.csv",
}

SUPPORTED_METHODS = {
    "DIRECT_HISTORY_CALIBRATED",
    "DIRECT_HISTORY_LIMITED",
    "COMPARABLE_PRODUCT_ADJUSTED",
    "FUNDAMENTAL_COMPARABLE_HYBRID",
    "DEFERRED_IDENTITY",
    "DEFERRED_MISSING_PRICE",
    "DEFERRED_INSUFFICIENT_EVIDENCE",
}

ACTIVE_PRODUCTION_FILES = {
    "scripts/build_mtg_hosted_uip_delivery.py",
    "scripts/build_mtg_uip_export.py",
    "scripts/build_unified_mtg_intelligence.py",
    "scripts/build_universal_mtg_daily_history.py",
    "scripts/build_universal_mtg_history_ledger.py",
    "scripts/build_universal_mtg_market_valuation.py",
    "scripts/normalize_collector_evidence.py",
    "scripts/route_collector_forecast_methods.py",
    "scripts/select_collector_comparables.py",
}

COUNT_CONTEXT = re.compile(r"(?i)(expected|required|must\s+equal|assert|len\s*\(|row_count|product_count)")
COUNT_LITERAL = re.compile(r"(?<!\d)(47|51|83|973|1141|1363|4787)(?!\d)")


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


def first_present(row: dict[str, str], names: Iterable[str]) -> str:
    for name in names:
        value = clean(row.get(name))
        if value:
            return value
    return ""


def product_id(row: dict[str, str]) -> str:
    return first_present(row, ("investment_product_id", "target_product_id", "canonical_product_id", "product_id", "asset_id"))


def product_name(row: dict[str, str]) -> str:
    return first_present(row, ("product_name", "target_product_name", "box_name_master", "box_name", "approved_product_name", "name"))


def is_collector_row(row: dict[str, str]) -> bool:
    product_type = first_present(row, ("investment_product_type", "product_lane", "lane", "product_class")).upper().replace("_", " ")
    name = product_name(row).upper()
    positive = product_type in {"COLLECTOR BOOSTER DISPLAY", "COLLECTOR BOOSTER", "COLLECTOR BOOSTER BOX"} or "COLLECTOR BOOSTER DISPLAY" in name
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


def scan_active_hard_coded_counts() -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for relative in sorted(ACTIVE_PRODUCTION_FILES):
        path = ROOT / relative
        if not path.exists():
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
            if not COUNT_CONTEXT.search(line):
                continue
            for match in COUNT_LITERAL.finditer(line):
                findings.append({
                    "path": relative,
                    "line_number": line_number,
                    "literal": int(match.group(1)),
                    "classification": "ACTIVE_PRODUCTION_REVIEW",
                    "line": line.strip()[:500],
                })
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit dynamic Collector production reconciliation.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    loaded: dict[str, list[dict[str, str]]] = {}
    inventory: list[dict[str, Any]] = []
    missing: list[str] = []
    for name, path in DATASETS.items():
        if path.exists():
            rows = read_csv(path)
            loaded[name] = rows
            inventory.append({"dataset": name, "path": path.relative_to(ROOT).as_posix(), "exists": True, "row_count": len(rows), "column_count": len(rows[0]) if rows else 0})
        else:
            loaded[name] = []
            missing.append(name)
            inventory.append({"dataset": name, "path": path.relative_to(ROOT).as_posix(), "exists": False, "row_count": 0, "column_count": 0})

    indexes: dict[str, dict[str, dict[str, str]]] = {}
    identity_issues: list[dict[str, str]] = []
    for name, rows in loaded.items():
        indexed, issues = index_unique(rows, name)
        indexes[name] = indexed
        identity_issues.extend(issues)

    registry_ids = {product_id(row) for row in loaded["registry"] if product_id(row) and is_collector_row(row)}
    model_ids = {product_id(row) for row in loaded["model"] if product_id(row) and is_collector_row(row)}
    history_ids = set(indexes["history"])
    evidence_ids = set(indexes["evidence"])
    route_ids = set(indexes["routes"])
    comparable_ids = set(indexes["comparable_targets"])
    universe_ids = route_ids or evidence_ids or history_ids or registry_ids

    all_ids = sorted(universe_ids | registry_ids | model_ids | history_ids | evidence_ids | route_ids | comparable_ids)
    method_distribution: Counter[str] = Counter()
    reconciliation: list[dict[str, Any]] = []
    structural_failures: list[str] = []

    for key in all_ids:
        route = indexes["routes"].get(key, {})
        method = clean(route.get("forecast_method"))
        if method:
            method_distribution[method] += 1
        expected_comparable = method in {"COMPARABLE_PRODUCT_ADJUSTED", "FUNDAMENTAL_COMPARABLE_HYBRID"}
        issues: list[str] = []
        if key in universe_ids and key not in registry_ids:
            issues.append("MISSING_FROM_COLLECTOR_REGISTRY")
        if key in universe_ids and key not in model_ids:
            issues.append("MISSING_FROM_COLLECTOR_MODEL")
        if key in universe_ids and key not in history_ids:
            issues.append("MISSING_HISTORY_CERTIFICATION")
        if key in universe_ids and key not in evidence_ids:
            issues.append("MISSING_NORMALIZED_EVIDENCE")
        if key in universe_ids and key not in route_ids:
            issues.append("MISSING_METHOD_ROUTE")
        if method and method not in SUPPORTED_METHODS:
            issues.append("UNSUPPORTED_METHOD")
        if expected_comparable and key not in comparable_ids:
            issues.append("MISSING_COMPARABLE_SELECTION")
        structural_failures.extend(f"{key}:{issue}" for issue in issues)
        source = route or indexes["model"].get(key, {}) or indexes["registry"].get(key, {})
        reconciliation.append({
            "investment_product_id": key,
            "product_name": product_name(source),
            "in_governed_universe": key in universe_ids,
            "in_registry": key in registry_ids,
            "in_model": key in model_ids,
            "history_present": key in history_ids,
            "evidence_present": key in evidence_ids,
            "route_present": key in route_ids,
            "comparable_target_present": key in comparable_ids,
            "forecast_method": method,
            "issues": "|".join(issues),
        })

    hard_counts = scan_active_hard_coded_counts()
    output = args.output
    write_csv(output / "collector_pipeline_inventory.csv", inventory, ["dataset", "path", "exists", "row_count", "column_count"])
    write_csv(output / "collector_product_reconciliation.csv", reconciliation, ["investment_product_id", "product_name", "in_governed_universe", "in_registry", "in_model", "history_present", "evidence_present", "route_present", "comparable_target_present", "forecast_method", "issues"])
    write_csv(output / "collector_identity_issues.csv", identity_issues, ["dataset", "product_id", "issue"])
    write_csv(output / "collector_active_hard_coded_count_findings.csv", hard_counts, ["path", "line_number", "literal", "classification", "line"])

    summary = {
        "audit_name": "Collector Production Completion Baseline",
        "audit_version": "2.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dynamic_universe_count": len(universe_ids),
        "registry_collector_count": len(registry_ids),
        "model_collector_count": len(model_ids),
        "history_count": len(history_ids),
        "normalized_evidence_count": len(evidence_ids),
        "method_route_count": len(route_ids),
        "comparable_target_count": len(comparable_ids),
        "selected_comparable_row_count": len(loaded["selected_comparables"]),
        "method_distribution": dict(sorted(method_distribution.items())),
        "missing_datasets": missing,
        "identity_issue_count": len(identity_issues),
        "structural_failure_count": len(set(structural_failures)),
        "structural_failures": sorted(set(structural_failures)),
        "active_hard_coded_count_finding_count": len(hard_counts),
        "projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "owner_approval_status": "NOT_REQUESTED",
        "status": "PASS" if not missing and not identity_issues and not structural_failures else "REVIEW_REQUIRED",
        "governing_note": "Counts are observations for this run only. Certification depends on reconciliation, semantic review, and explicit owner approval.",
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "collector_production_baseline_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and summary["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
