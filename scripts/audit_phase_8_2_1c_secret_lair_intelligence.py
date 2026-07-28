from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = (
    ROOT
    / "docs"
    / "phase_8"
    / "mtg_intelligence_recovery"
    / "secret_lair_intelligence_recovery"
)

CORE_PATHS = {
    "registry": ROOT / "data" / "validation" / "phase_10" / "secret_lair" / "full_registry" / "secret_lair_full_registry.csv",
    "evaluation": ROOT / "data" / "validation" / "phase_10" / "secret_lair" / "full_evaluation" / "secret_lair_full_model_evaluation.csv",
    "forecast": ROOT / "data" / "validation" / "phase_10" / "secret_lair" / "full_evaluation" / "secret_lair_full_model_forecasts.csv",
    "recommendation": ROOT / "data" / "validation" / "phase_10" / "secret_lair" / "full_evaluation" / "secret_lair_full_model_recommendations.csv",
    "unified": ROOT / "data" / "validation" / "phase_10" / "unified_mtg_intelligence" / "unified_mtg_intelligence_interface.csv",
    "uip_forecasts": ROOT / "data" / "operations" / "mtg_uip_delivery" / "latest" / "forecasts.csv",
    "uip_recommendations": ROOT / "data" / "operations" / "mtg_uip_delivery" / "latest" / "recommendations.csv",
}

SOURCE_CODE = [
    ROOT / "scripts" / "build_full_secret_lair_model_evaluation.py",
    ROOT / "scripts" / "build_unified_mtg_intelligence.py",
    ROOT / "scripts" / "build_phase_10_10_universal_export.py",
    ROOT / "scripts" / "build_mtg_hosted_uip_delivery.py",
    ROOT / "scripts" / "certify_phase_10_secret_lair_closeout.py",
    ROOT / "terminal2" / "portfolio" / "secret_lair_full_registry.py",
]

TEST_FILES = [
    ROOT / "tests" / "test_full_secret_lair_model_evaluation.py",
    ROOT / "tests" / "test_phase_10_secret_lair_production_closeout.py",
    ROOT / "tests" / "test_unified_mtg_intelligence.py",
    ROOT / "tests" / "test_mtg_hosted_uip_delivery.py",
    ROOT / "tests" / "test_uip_handoff.py",
]

HISTORICAL_HINTS = (
    "history", "historical", "realized", "annualized", "cagr",
    "return", "roi", "price_change", "appreciation",
)
FORECAST_HINTS = (
    "forecast", "projection", "projected", "future", "expected",
    "one_year", "three_year", "five_year", "1y", "3y", "5y",
    "downside", "base", "upside", "p05", "p50", "p95",
)
VALUATION_HINTS = (
    "market_value", "current_price", "current_value", "reference_price",
    "valuation", "fair_value", "native_forecast_low",
    "native_forecast_base", "native_forecast_high",
)
QUALITY_HINTS = (
    "confidence", "liquidity", "observations", "sample",
    "freshness", "coverage", "quality", "evidence",
)
IDENTITY_HINTS = (
    "id", "name", "product", "drop", "edition", "finish",
    "foil", "nonfoil", "sealed", "variant", "release",
)

RATE_RE = re.compile(r"(cagr|annualized|return|roi|growth_rate|appreciation)", re.I)
HORIZON_RE = re.compile(r"(^|_)(1y|3y|5y|one_year|three_year|five_year)($|_)", re.I)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean(value: Any) -> str:
    return str(value or "").strip()


def number(value: Any) -> float | None:
    text = clean(value).replace("$", "").replace(",", "").replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def classify_field(field: str) -> str:
    lowered = field.lower()
    if any(h in lowered for h in HISTORICAL_HINTS):
        return "HISTORICAL_PERFORMANCE"
    if any(h in lowered for h in FORECAST_HINTS):
        return "FORWARD_FORECAST"
    if any(h in lowered for h in VALUATION_HINTS):
        return "CURRENT_OR_RANGE_VALUATION"
    if any(h in lowered for h in QUALITY_HINTS):
        return "QUALITY_OR_LIQUIDITY"
    if any(h in lowered for h in IDENTITY_HINTS):
        return "IDENTITY_OR_PRODUCT"
    return "OTHER"


def find_id(row: dict[str, str]) -> str:
    for field in (
        "universal_mtg_product_id", "asset_id", "canonical_product_id",
        "source_product_id", "secret_lair_product_id", "product_id",
        "investment_product_id", "id",
    ):
        value = clean(row.get(field))
        if value:
            return value
    return ""


def is_secret_lair(row: dict[str, str]) -> bool:
    combined = " ".join(
        clean(row.get(field))
        for field in (
            "lane", "asset_subclass", "product_class", "category",
            "product_type", "universal_mtg_product_id", "asset_id",
        )
    ).upper()
    return "SECRET_LAIR" in combined or "SECRET LAIR" in combined


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def row_semantic_flags(row: dict[str, str]) -> dict[str, Any]:
    fields = list(row)
    rate_fields = [f for f in fields if RATE_RE.search(f)]
    horizon_fields = [f for f in fields if HORIZON_RE.search(f)]
    populated_rates = [f for f in rate_fields if clean(row.get(f))]
    populated_horizons = [f for f in horizon_fields if clean(row.get(f))]

    method = clean(row.get("forecast_method"))
    forecast_status = clean(row.get("forecast_status"))
    forecast_eligible = clean(row.get("forecast_eligible")).upper()
    rec_eligible = clean(row.get("recommendation_eligible")).upper()

    historical_values_in_forecast_fields = []
    for field in populated_horizons:
        value = number(row.get(field))
        if value is not None and field.lower().endswith(("return", "return_pct", "cagr")):
            historical_values_in_forecast_fields.append(field)

    suspicious_method = bool(
        method
        and any(token in method.upper() for token in ("HISTORICAL", "REALIZED", "CAGR"))
    )

    has_native_range = all(
        clean(row.get(field))
        for field in (
            "native_forecast_low_usd",
            "native_forecast_base_usd",
            "native_forecast_high_usd",
        )
    )
    has_any_horizon = bool(populated_horizons)

    return {
        "product_id": find_id(row),
        "forecast_method": method,
        "forecast_status": forecast_status,
        "forecast_eligible": forecast_eligible,
        "recommendation_eligible": rec_eligible,
        "populated_rate_fields": "|".join(populated_rates),
        "populated_horizon_fields": "|".join(populated_horizons),
        "has_native_range": "YES" if has_native_range else "NO",
        "has_any_horizon": "YES" if has_any_horizon else "NO",
        "suspicious_forecast_method": "YES" if suspicious_method else "NO",
        "historical_values_in_forecast_fields": "|".join(historical_values_in_forecast_fields),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--package", action="store_true")
    args = parser.parse_args()

    output = args.output_root
    output.mkdir(parents=True, exist_ok=True)

    dataset_summary: list[dict[str, Any]] = []
    field_matrix: list[dict[str, Any]] = []
    semantic_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    source_inventory: list[dict[str, Any]] = []

    dataset_rows: dict[str, list[dict[str, str]]] = {}

    for key, path in CORE_PATHS.items():
        rows = read_csv(path)
        if key.startswith("uip_") or key == "unified":
            rows = [row for row in rows if is_secret_lair(row)]
        dataset_rows[key] = rows

        fields = list(rows[0]) if rows else []
        ids = [find_id(row) for row in rows if find_id(row)]
        duplicate_count = len(ids) - len(set(ids))
        dataset_summary.append({
            "dataset": key,
            "path": str(path.relative_to(ROOT)) if path.exists() else str(path),
            "exists": path.is_file(),
            "rows": len(rows),
            "unique_ids": len(set(ids)),
            "duplicate_ids": duplicate_count,
            "field_count": len(fields),
            "sha256": sha256(path) if path.is_file() else "",
        })

        for field in fields:
            populated = sum(bool(clean(row.get(field))) for row in rows)
            numeric = sum(number(row.get(field)) is not None for row in rows)
            examples = []
            for row in rows:
                value = clean(row.get(field))
                if value and value not in examples:
                    examples.append(value)
                if len(examples) == 3:
                    break
            field_matrix.append({
                "dataset": key,
                "field": field,
                "semantic_class": classify_field(field),
                "populated_rows": populated,
                "numeric_rows": numeric,
                "example_1": examples[0] if len(examples) > 0 else "",
                "example_2": examples[1] if len(examples) > 1 else "",
                "example_3": examples[2] if len(examples) > 2 else "",
            })

        if key in {"forecast", "unified", "uip_forecasts"}:
            for row in rows:
                flags = row_semantic_flags(row)
                flags["dataset"] = key
                semantic_rows.append(flags)

    all_ids: set[str] = set()
    id_sets: dict[str, set[str]] = {}
    for key, rows in dataset_rows.items():
        ids = {find_id(row) for row in rows if find_id(row)}
        id_sets[key] = ids
        all_ids |= ids

    for product_id in sorted(all_ids):
        coverage_rows.append({
            "product_id": product_id,
            **{f"in_{key}": "YES" if product_id in ids else "NO" for key, ids in id_sets.items()},
        })

    for path in SOURCE_CODE + TEST_FILES:
        source_inventory.append({
            "type": "SOURCE" if path in SOURCE_CODE else "TEST",
            "path": str(path.relative_to(ROOT)),
            "exists": path.is_file(),
            "bytes": path.stat().st_size if path.is_file() else 0,
            "sha256": sha256(path) if path.is_file() else "",
        })

    method_counts = Counter()
    status_counts = Counter()
    eligibility_counts = Counter()
    rec_counts = Counter()
    suspicious_count = 0
    horizon_count = 0
    native_range_count = 0

    for row in semantic_rows:
        dataset = row["dataset"]
        method_counts[(dataset, row["forecast_method"] or "<BLANK>")] += 1
        status_counts[(dataset, row["forecast_status"] or "<BLANK>")] += 1
        eligibility_counts[(dataset, row["forecast_eligible"] or "<BLANK>")] += 1
        rec_counts[(dataset, row["recommendation_eligible"] or "<BLANK>")] += 1
        suspicious_count += row["suspicious_forecast_method"] == "YES"
        horizon_count += row["has_any_horizon"] == "YES"
        native_range_count += row["has_native_range"] == "YES"

    aggregate_rows = []
    for (dataset, value), count in sorted(method_counts.items()):
        aggregate_rows.append({"dimension": "forecast_method", "dataset": dataset, "value": value, "count": count})
    for (dataset, value), count in sorted(status_counts.items()):
        aggregate_rows.append({"dimension": "forecast_status", "dataset": dataset, "value": value, "count": count})
    for (dataset, value), count in sorted(eligibility_counts.items()):
        aggregate_rows.append({"dimension": "forecast_eligible", "dataset": dataset, "value": value, "count": count})
    for (dataset, value), count in sorted(rec_counts.items()):
        aggregate_rows.append({"dimension": "recommendation_eligible", "dataset": dataset, "value": value, "count": count})

    checks = {
        "core_datasets_present": all(CORE_PATHS[k].is_file() for k in ("evaluation", "forecast", "recommendation", "unified", "uip_forecasts")),
        "unified_secret_lair_rows_present": len(dataset_rows["unified"]) > 0,
        "uip_secret_lair_rows_present": len(dataset_rows["uip_forecasts"]) > 0,
        "source_code_present": all(path.is_file() for path in SOURCE_CODE),
        "tests_present": all(path.is_file() for path in TEST_FILES),
        "identity_coverage_nonzero": bool(all_ids),
    }

    report = {
        "status": "PASS" if all(checks.values()) else "REVIEW",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "8.2.1C",
        "purpose": "Secret Lair intelligence semantic and coverage baseline",
        "checks": checks,
        "counts": {
            "datasets": len(dataset_summary),
            "unique_ids_across_layers": len(all_ids),
            "semantic_rows": len(semantic_rows),
            "rows_with_native_ranges": native_range_count,
            "rows_with_any_horizon_field": horizon_count,
            "rows_with_suspicious_forecast_method": suspicious_count,
        },
        "important_rule": (
            "Historical or realized CAGR/return fields must not be mapped into "
            "forward forecast fields without an independently certified horizon model."
        ),
    }

    write_csv(output / "secret_lair_dataset_summary.csv", dataset_summary)
    write_csv(output / "secret_lair_field_semantic_matrix.csv", field_matrix)
    write_csv(output / "secret_lair_semantic_row_audit.csv", semantic_rows)
    write_csv(output / "secret_lair_coverage_matrix.csv", coverage_rows)
    write_csv(output / "secret_lair_semantic_aggregates.csv", aggregate_rows)
    write_csv(output / "secret_lair_source_inventory.csv", source_inventory)
    (output / "PHASE_8_2_1C_BASELINE_AUDIT.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    md = [
        "# Phase 8.2.1C — Secret Lair Intelligence Recovery Baseline",
        "",
        f"**Status:** {report['status']}",
        "",
        "## Purpose",
        "",
        "Establish the exact current Secret Lair source, schema, coverage, and semantic state before producer changes.",
        "",
        "## Governing semantic rule",
        "",
        report["important_rule"],
        "",
        "## Counts",
        "",
    ]
    md.extend(f"- {key}: {value}" for key, value in report["counts"].items())
    md.extend(["", "## Checks", ""])
    md.extend(f"- {key}: {'PASS' if value else 'REVIEW'}" for key, value in checks.items())
    md.extend([
        "",
        "## Generated evidence",
        "",
        "- `secret_lair_dataset_summary.csv`",
        "- `secret_lair_field_semantic_matrix.csv`",
        "- `secret_lair_semantic_row_audit.csv`",
        "- `secret_lair_coverage_matrix.csv`",
        "- `secret_lair_semantic_aggregates.csv`",
        "- `secret_lair_source_inventory.csv`",
        "- `PHASE_8_2_1C_BASELINE_AUDIT.json`",
        "",
    ])
    (output / "PHASE_8_2_1C_BASELINE_AUDIT.md").write_text(
        "\n".join(md),
        encoding="utf-8",
    )

    package_path = None
    if args.package:
        package_root = (
            ROOT
            / "data"
            / "operations"
            / "phase_8_2_1c_repair_input"
        )
        if package_root.exists():
            shutil.rmtree(package_root)
        package_root.mkdir(parents=True, exist_ok=True)

        evidence_dest = package_root / "evidence"
        shutil.copytree(output, evidence_dest)

        for path in SOURCE_CODE + TEST_FILES:
            if path.is_file():
                destination = package_root / "repo" / path.relative_to(ROOT)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)

        for key, path in CORE_PATHS.items():
            if path.is_file():
                destination = package_root / "data" / key / path.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)

        package_path = package_root.with_suffix(".zip")
        if package_path.exists():
            package_path.unlink()
        shutil.make_archive(
            str(package_root),
            "zip",
            root_dir=package_root.parent,
            base_dir=package_root.name,
        )

    print("=" * 78)
    print("PHASE 8.2.1C — SECRET LAIR BASELINE AUDIT")
    print("=" * 78)
    for item in dataset_summary:
        print(
            f"{item['dataset']:20} "
            f"{item['rows']:6} rows | "
            f"{item['unique_ids']:6} unique IDs | "
            f"{'FOUND' if item['exists'] else 'MISSING'}"
        )
    print("-" * 78)
    print(f"Unique IDs across layers: {len(all_ids)}")
    print(f"Semantic rows audited: {len(semantic_rows)}")
    print(f"Rows with native ranges: {native_range_count}")
    print(f"Rows with horizon fields: {horizon_count}")
    print(f"Suspicious forecast methods: {suspicious_count}")
    print(f"Status: {report['status']}")
    print(f"Evidence: {output}")
    if package_path:
        print(f"Repair input package: {package_path}")
    print("PHASE 8.2.1C BASELINE AUDIT: COMPLETE")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
