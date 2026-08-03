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

DEFAULT_OUTPUT = (
    ROOT
    / "data"
    / "operations"
    / "collector_production_completion"
    / "baseline_v1_0_0"
)

DATASETS = {
    "registry": ROOT / "data/product_master/investment_products.csv",
    "model": ROOT / "data/product_master/product_master_model_input.csv",
    "history": (
        ROOT
        / "data/operations/collector_booster_history_certification"
        / "candidate_v1_0_0/collector_history_product_certification.csv"
    ),
    "evidence": (
        ROOT
        / "data/operations/collector_evidence_normalization"
        / "candidate_v1_0_0/collector_normalized_evidence.csv"
    ),
    "routes": (
        ROOT
        / "data/operations/collector_forecast_method_routing"
        / "candidate_v1_0_0/collector_forecast_method_routes.csv"
    ),
    "comparable_targets": (
        ROOT
        / "data/operations/collector_comparable_selection"
        / "candidate_v1_0_0/collector_comparable_target_summary.csv"
    ),
    "comparable_pairs": (
        ROOT
        / "data/operations/collector_comparable_selection"
        / "candidate_v1_0_0/collector_comparable_pair_scores.csv"
    ),
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

COUNT_LITERALS = {47, 51, 83, 973, 1141, 1363, 4787}
COUNT_CONTEXT = re.compile(
    r"(?i)(expected|required|must\s+equal|len\s*\(|row_count|product_count|count)"
)


def clean(value: Any) -> str:
    return str(value or "").strip()


def parse_bool(value: Any) -> bool:
    return clean(value).lower() in {"true", "1", "yes", "y"}


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
    return first_present(
        row,
        (
            "investment_product_id",
            "canonical_product_id",
            "product_id",
            "asset_id",
        ),
    )


def product_name(row: dict[str, str]) -> str:
    return first_present(row, ("product_name", "name", "asset_name"))


def index_unique(
    rows: list[dict[str, str]],
    dataset: str,
) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    indexed: dict[str, dict[str, str]] = {}
    duplicates: list[dict[str, str]] = []
    for row in rows:
        key = product_id(row)
        if not key:
            duplicates.append(
                {
                    "dataset": dataset,
                    "product_id": "",
                    "issue": "MISSING_PRODUCT_ID",
                }
            )
            continue
        if key in indexed:
            duplicates.append(
                {
                    "dataset": dataset,
                    "product_id": key,
                    "issue": "DUPLICATE_PRODUCT_ID",
                }
            )
            continue
        indexed[key] = row
    return indexed, duplicates


def is_collector_row(row: dict[str, str]) -> bool:
    lane = first_present(row, ("product_lane", "lane", "product_class")).upper()
    configuration = first_present(
        row,
        ("sealed_product_configuration", "product_configuration", "configuration"),
    ).upper()
    name = product_name(row).upper()
    positive = (
        lane in {"COLLECTOR_BOOSTER", "COLLECTOR_BOOSTER_BOX"}
        or configuration in {"COLLECTOR_BOOSTER_DISPLAY", "COLLECTOR_BOOSTER_BOX"}
        or "COLLECTOR BOOSTER" in name
    )
    excluded = any(term in name for term in (" CASE", " PACK", " BUNDLE"))
    return positive and not excluded


def scan_hard_coded_counts() -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    roots = [ROOT / "scripts", ROOT / "models", ROOT / "config", ROOT / "tests"]
    for base in roots:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".py", ".json", ".yaml", ".yml"}:
                continue
            relative = path.relative_to(ROOT).as_posix()
            try:
                lines = path.read_text(encoding="utf-8-sig").splitlines()
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(lines, start=1):
                if not COUNT_CONTEXT.search(line):
                    continue
                for literal in sorted(COUNT_LITERALS):
                    if re.search(rf"(?<!\d){literal}(?!\d)", line):
                        findings.append(
                            {
                                "path": relative,
                                "line_number": line_number,
                                "literal": literal,
                                "line": line.strip()[:500],
                                "classification": (
                                    "TEST_OR_FIXTURE_REVIEW"
                                    if relative.startswith("tests/")
                                    else "PRODUCTION_REVIEW"
                                ),
                            }
                        )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit Collector production readiness without fixed product totals."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return nonzero when structural reconciliation failures are present.",
    )
    args = parser.parse_args()

    generated_at = datetime.now(timezone.utc).isoformat()
    loaded: dict[str, list[dict[str, str]]] = {}
    inventory_rows: list[dict[str, Any]] = []
    missing_datasets: list[str] = []

    for name, path in DATASETS.items():
        if path.exists():
            rows = read_csv(path)
            loaded[name] = rows
            inventory_rows.append(
                {
                    "dataset": name,
                    "path": path.relative_to(ROOT).as_posix(),
                    "exists": True,
                    "row_count": len(rows),
                    "column_count": len(rows[0]) if rows else 0,
                }
            )
        else:
            loaded[name] = []
            missing_datasets.append(name)
            inventory_rows.append(
                {
                    "dataset": name,
                    "path": path.relative_to(ROOT).as_posix(),
                    "exists": False,
                    "row_count": 0,
                    "column_count": 0,
                }
            )

    indexes: dict[str, dict[str, dict[str, str]]] = {}
    duplicate_rows: list[dict[str, str]] = []
    for name, rows in loaded.items():
        indexed, duplicates = index_unique(rows, name)
        indexes[name] = indexed
        duplicate_rows.extend(duplicates)

    route_ids = set(indexes["routes"])
    evidence_ids = set(indexes["evidence"])
    history_ids = set(indexes["history"])
    comparable_target_ids = set(indexes["comparable_targets"])

    registry_collector_ids = {
        product_id(row)
        for row in loaded["registry"]
        if product_id(row) and is_collector_row(row)
    }

    model_collector_ids = {
        product_id(row)
        for row in loaded["model"]
        if product_id(row) and is_collector_row(row)
    }

    universe_ids = route_ids or evidence_ids or history_ids or registry_collector_ids
    all_ids = sorted(
        universe_ids
        | registry_collector_ids
        | model_collector_ids
        | evidence_ids
        | history_ids
        | comparable_target_ids
    )

    reconciliation_rows: list[dict[str, Any]] = []
    structural_failures: list[str] = []
    method_counter: Counter[str] = Counter()

    for key in all_ids:
        route = indexes["routes"].get(key, {})
        method = clean(route.get("forecast_method"))
        if method:
            method_counter[method] += 1

        in_universe = key in universe_ids
        expected_comparable = method in {
            "COMPARABLE_PRODUCT_ADJUSTED",
            "FUNDAMENTAL_COMPARABLE_HYBRID",
        }
        comparable_present = key in comparable_target_ids

        issues: list[str] = []
        if in_universe and key not in registry_collector_ids:
            issues.append("MISSING_FROM_COLLECTOR_REGISTRY")
        if in_universe and key not in model_collector_ids:
            issues.append("MISSING_FROM_COLLECTOR_MODEL")
        if in_universe and key not in evidence_ids:
            issues.append("MISSING_NORMALIZED_EVIDENCE")
        if in_universe and key not in history_ids:
            issues.append("MISSING_HISTORY_CERTIFICATION")
        if in_universe and key not in route_ids:
            issues.append("MISSING_METHOD_ROUTE")
        if method and method not in SUPPORTED_METHODS:
            issues.append("UNSUPPORTED_METHOD")
        if expected_comparable and not comparable_present:
            issues.append("MISSING_COMPARABLE_SELECTION")

        if any(
            issue in {
                "MISSING_FROM_COLLECTOR_REGISTRY",
                "MISSING_FROM_COLLECTOR_MODEL",
                "MISSING_NORMALIZED_EVIDENCE",
                "MISSING_HISTORY_CERTIFICATION",
                "MISSING_METHOD_ROUTE",
                "UNSUPPORTED_METHOD",
                "MISSING_COMPARABLE_SELECTION",
            }
            for issue in issues
        ):
            structural_failures.extend(f"{key}:{issue}" for issue in issues)

        source_row = route or indexes["evidence"].get(key, {}) or indexes["history"].get(key, {})
        reconciliation_rows.append(
            {
                "investment_product_id": key,
                "product_name": product_name(source_row),
                "in_governed_universe": in_universe,
                "in_registry": key in registry_collector_ids,
                "in_model": key in model_collector_ids,
                "history_present": key in history_ids,
                "evidence_present": key in evidence_ids,
                "route_present": key in route_ids,
                "comparable_target_present": comparable_present,
                "forecast_method": method,
                "forecast_output_allowed": clean(route.get("forecast_output_allowed")),
                "purchase_analysis_allowed": clean(route.get("purchase_analysis_allowed")),
                "purchase_recommendation_authorized": clean(
                    route.get("purchase_recommendation_authorized")
                ),
                "issues": "|".join(issues),
            }
        )

    hard_coded_findings = scan_hard_coded_counts()

    write_csv(
        args.output / "collector_pipeline_inventory.csv",
        inventory_rows,
        ["dataset", "path", "exists", "row_count", "column_count"],
    )
    write_csv(
        args.output / "collector_product_reconciliation.csv",
        reconciliation_rows,
        [
            "investment_product_id",
            "product_name",
            "in_governed_universe",
            "in_registry",
            "in_model",
            "history_present",
            "evidence_present",
            "route_present",
            "comparable_target_present",
            "forecast_method",
            "forecast_output_allowed",
            "purchase_analysis_allowed",
            "purchase_recommendation_authorized",
            "issues",
        ],
    )
    write_csv(
        args.output / "collector_identity_issues.csv",
        duplicate_rows,
        ["dataset", "product_id", "issue"],
    )
    write_csv(
        args.output / "collector_hard_coded_count_findings.csv",
        hard_coded_findings,
        ["path", "line_number", "literal", "classification", "line"],
    )

    summary = {
        "audit_name": "Collector Production Completion Baseline",
        "audit_version": "1.0.0",
        "generated_at_utc": generated_at,
        "dynamic_universe_count": len(universe_ids),
        "registry_collector_count": len(registry_collector_ids),
        "model_collector_count": len(model_collector_ids),
        "history_count": len(history_ids),
        "normalized_evidence_count": len(evidence_ids),
        "method_route_count": len(route_ids),
        "comparable_target_count": len(comparable_target_ids),
        "method_distribution": dict(sorted(method_counter.items())),
        "missing_datasets": missing_datasets,
        "duplicate_or_missing_identity_count": len(duplicate_rows),
        "structural_failure_count": len(structural_failures),
        "structural_failures": sorted(set(structural_failures)),
        "hard_coded_count_finding_count": len(hard_coded_findings),
        "production_hard_coded_count_finding_count": sum(
            row["classification"] == "PRODUCTION_REVIEW"
            for row in hard_coded_findings
        ),
        "projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "status": (
            "PASS"
            if not missing_datasets and not duplicate_rows and not structural_failures
            else "REVIEW_REQUIRED"
        ),
        "governing_note": (
            "Counts are observations for this run only. Correctness is based on "
            "identity reconciliation and method accountability, not fixed totals."
        ),
    }
    write_json(args.output / "collector_production_baseline_summary.json", summary)

    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.strict and summary["status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
