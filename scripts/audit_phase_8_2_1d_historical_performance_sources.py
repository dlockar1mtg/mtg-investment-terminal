from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT
    / "docs"
    / "phase_8"
    / "mtg_intelligence_recovery"
    / "historical_performance_forecast_separation"
)

TEXT_SUFFIXES = {
    ".py", ".md", ".json", ".yaml", ".yml", ".toml",
    ".sql", ".txt", ".csv",
}

# Repository discovery must remain memory-bounded. Keyword ranking only needs
# a representative text sample, while CSV schema discovery uses a capped row
# sample rather than loading arbitrarily large datasets in full.
MAX_TEXT_SCAN_BYTES = 2 * 1024 * 1024
MAX_CSV_SAMPLE_ROWS = 100_000

EXCLUDED_PARTS = {
    ".git", ".pytest_cache", "__pycache__", ".venv", "venv",
    "node_modules", "data/operations/phase_8_2_1d_repair_input",
}

SEARCH_TERMS = {
    "historical_performance": (
        "historical", "realized", "return", "returns", "cagr",
        "annualized", "appreciation", "price history", "price_history",
    ),
    "forward_forecast": (
        "forecast", "projection", "projected", "future value",
        "one_year", "three_year", "five_year", "1y", "3y", "5y",
        "horizon_model_certified",
    ),
    "valuation": (
        "valuation", "current_market_value", "native_forecast",
        "native_valuation", "fair value", "market value",
    ),
    "secret_lair": (
        "secret lair", "secret_lair", "SECRET_LAIR",
    ),
}

HISTORICAL_FIELD_RE = re.compile(
    r"(historical|realized|cagr|annualized|return|roi|appreciation|price_change)",
    re.I,
)
FORECAST_FIELD_RE = re.compile(
    r"(forecast|projected|projection|future|one_year|three_year|five_year|(^|_)(1y|3y|5y)($|_))",
    re.I,
)
DATE_FIELD_RE = re.compile(
    r"(date|timestamp|observed_at|as_of|period_start|period_end)",
    re.I,
)
PRICE_FIELD_RE = re.compile(
    r"(price|value|market_value|amount|usd)",
    re.I,
)
ID_FIELD_RE = re.compile(
    r"(product_id|investment_product_id|canonical_product_id|asset_id|universal_mtg_product_id)",
    re.I,
)

LIKELY_CORE_FILES = [
    ROOT / "terminal2" / "return_analytics" / "contracts.py",
    ROOT / "terminal2" / "return_analytics" / "engine.py",
    ROOT / "terminal2" / "return_analytics" / "exports.py",
    ROOT / "terminal2_publish_universal_return_analytics.py",
    ROOT / "docs" / "UNIVERSAL_RETURN_ANALYTICS_GUIDE.md",
    ROOT / "terminal2" / "forecast" / "engine.py",
    ROOT / "terminal2" / "forecast" / "exports.py",
    ROOT / "scripts" / "build_full_secret_lair_model_evaluation.py",
    ROOT / "scripts" / "build_unified_mtg_intelligence.py",
    ROOT / "scripts" / "build_phase_10_10_universal_export.py",
    ROOT / "scripts" / "build_mtg_hosted_uip_delivery.py",
]

CURRENT_OUTPUTS = [
    ROOT / "data" / "validation" / "phase_10" / "ebay_matching"
    / "production_refresh" / "full_model_evaluation"
    / "secret_lair_full_model_evaluation.csv",
    ROOT / "data" / "validation" / "phase_10" / "ebay_matching"
    / "production_refresh" / "full_model_evaluation"
    / "secret_lair_full_forecast_inputs.csv",
    ROOT / "data" / "validation" / "phase_10" / "unified_mtg_intelligence"
    / "unified_mtg_intelligence_interface.csv",
    ROOT / "data" / "operations" / "mtg_uip_delivery" / "latest"
    / "forecasts.csv",
]


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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def excluded(path: Path) -> bool:
    rel = relative(path).replace("\\", "/")
    parts = set(path.parts)
    return bool(parts & EXCLUDED_PARTS) or any(
        rel.startswith(prefix)
        for prefix in EXCLUDED_PARTS
        if "/" in prefix
    )


def read_text(
    path: Path,
    max_bytes: int = MAX_TEXT_SCAN_BYTES,
) -> str:
    """Read a bounded text sample without loading the whole file."""

    try:
        with path.open("rb") as handle:
            raw = handle.read(max_bytes)
    except OSError:
        return ""

    if not raw:
        return ""

    return raw.decode(
        "utf-8-sig",
        errors="replace",
    )


def read_csv(
    path: Path,
    max_rows: int = MAX_CSV_SAMPLE_ROWS,
) -> list[dict[str, str]]:
    """Read at most max_rows records for memory-safe discovery."""

    rows: list[dict[str, str]] = []

    try:
        with path.open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
            newline="",
        ) as handle:
            reader = csv.DictReader(handle)

            for index, row in enumerate(reader):
                if index >= max_rows:
                    break

                rows.append(dict(row))

    except (OSError, csv.Error, UnicodeError):
        return []

    return rows


def field_class(field: str) -> str:
    # Explicit horizon or projection language takes precedence over generic
    # words such as "return", because projected returns are forward-looking.
    if FORECAST_FIELD_RE.search(field):
        return "FORWARD_FORECAST"
    if HISTORICAL_FIELD_RE.search(field):
        return "HISTORICAL_PERFORMANCE"
    if DATE_FIELD_RE.search(field):
        return "DATE_OR_PERIOD"
    if PRICE_FIELD_RE.search(field):
        return "PRICE_OR_VALUE"
    if ID_FIELD_RE.search(field):
        return "IDENTITY"
    return "OTHER"


def contains_secret_lair(text: str) -> bool:
    lowered = text.lower()
    return "secret_lair" in lowered or "secret lair" in lowered


def scan_files() -> list[Path]:
    result: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or excluded(path):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        result.append(path)
    return result


def source_match_rows(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        # CSV content is evaluated structurally by csv_schema_rows(). Avoid
        # duplicating large data-file reads during text keyword ranking.
        if path.suffix.lower() == ".csv":
            continue

        text = read_text(path)

        if not text:
            continue

        lowered = text.casefold()
        matches: dict[str, list[str]] = {}
        for category, terms in SEARCH_TERMS.items():
            found = [term for term in terms if term.lower() in lowered]
            if found:
                matches[category] = found
        if not matches:
            continue
        secret = contains_secret_lair(text) or contains_secret_lair(relative(path))
        score = (
            len(matches.get("historical_performance", [])) * 4
            + len(matches.get("forward_forecast", [])) * 2
            + len(matches.get("valuation", []))
            + (6 if secret else 0)
        )
        rows.append({
            "path": relative(path),
            "suffix": path.suffix.lower(),
            "bytes": path.stat().st_size,
            "secret_lair_relevant": "YES" if secret else "NO",
            "relevance_score": score,
            "historical_terms": "|".join(matches.get("historical_performance", [])),
            "forecast_terms": "|".join(matches.get("forward_forecast", [])),
            "valuation_terms": "|".join(matches.get("valuation", [])),
            "sha256": sha256(path),
        })
    return sorted(
        rows,
        key=lambda row: (
            -int(row["relevance_score"]),
            row["path"],
        ),
    )


def csv_schema_rows(paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    schemas: list[dict[str, Any]] = []
    datasets: list[dict[str, Any]] = []

    for path in paths:
        if path.suffix.lower() != ".csv":
            continue

        rows = read_csv(path)
        if not rows:
            continue

        fields = list(rows[0])
        classified = [field_class(field) for field in fields]
        has_historical = "HISTORICAL_PERFORMANCE" in classified
        has_forecast = "FORWARD_FORECAST" in classified
        has_date = "DATE_OR_PERIOD" in classified
        has_price = "PRICE_OR_VALUE" in classified
        secret = contains_secret_lair(relative(path)) or any(
            contains_secret_lair(" ".join(clean(v) for v in row.values()))
            for row in rows[:100]
        )

        if not (
            has_historical
            or has_forecast
            or (has_date and has_price)
            or secret
        ):
            continue

        ids = []
        for row in rows:
            for field in fields:
                if field_class(field) == "IDENTITY" and clean(row.get(field)):
                    ids.append(clean(row.get(field)))
                    break

        datasets.append({
            "path": relative(path),
            "sampled_rows": len(rows),
            "sample_limit": MAX_CSV_SAMPLE_ROWS,
            "sample_truncated": (
                "YES"
                if len(rows) >= MAX_CSV_SAMPLE_ROWS
                else "NO"
            ),
            "rows": len(rows),
            "fields": len(fields),
            "unique_ids": len(set(ids)),
            "duplicate_ids": len(ids) - len(set(ids)),
            "secret_lair_relevant": "YES" if secret else "NO",
            "has_historical_fields": "YES" if has_historical else "NO",
            "has_forecast_fields": "YES" if has_forecast else "NO",
            "has_date_fields": "YES" if has_date else "NO",
            "has_price_fields": "YES" if has_price else "NO",
            "sha256": sha256(path),
        })

        for field in fields:
            populated = sum(bool(clean(row.get(field))) for row in rows)
            numeric = sum(number(row.get(field)) is not None for row in rows)
            examples: list[str] = []
            for row in rows:
                value = clean(row.get(field))
                if value and value not in examples:
                    examples.append(value)
                if len(examples) == 3:
                    break
            schemas.append({
                "path": relative(path),
                "field": field,
                "semantic_class": field_class(field),
                "populated_rows": populated,
                "numeric_rows": numeric,
                "example_1": examples[0] if len(examples) > 0 else "",
                "example_2": examples[1] if len(examples) > 1 else "",
                "example_3": examples[2] if len(examples) > 2 else "",
            })

    return datasets, schemas


def python_symbol_rows(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        if path.suffix.lower() != ".py":
            continue
        text = read_text(path)
        if not text:
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            name = node.name
            classification = field_class(name)
            if classification == "OTHER":
                source = ast.get_source_segment(text, node) or ""
                if not (
                    HISTORICAL_FIELD_RE.search(source)
                    or FORECAST_FIELD_RE.search(source)
                    or contains_secret_lair(source)
                ):
                    continue
            rows.append({
                "path": relative(path),
                "symbol": name,
                "symbol_type": type(node).__name__,
                "line": getattr(node, "lineno", ""),
                "semantic_class": classification,
                "secret_lair_relevant": (
                    "YES"
                    if contains_secret_lair(name)
                    or contains_secret_lair(ast.get_source_segment(text, node) or "")
                    else "NO"
                ),
            })
    return rows


def current_contract_rows() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in CURRENT_OUTPUTS:
        rows = read_csv(path)
        if not rows:
            results.append({
                "path": relative(path),
                "exists": path.is_file(),
                "rows": 0,
                "secret_lair_rows": 0,
                "historical_fields": "",
                "forecast_fields": "",
                "populated_historical_cells": 0,
                "populated_horizon_cells": 0,
            })
            continue

        secret_rows = [
            row for row in rows
            if contains_secret_lair(
                " ".join(
                    clean(row.get(field))
                    for field in (
                        "lane", "asset_id", "universal_mtg_product_id",
                        "asset_subclass", "product_class",
                    )
                )
            )
        ]
        active = secret_rows or rows
        fields = list(rows[0])
        historical_fields = [
            field for field in fields
            if field_class(field) == "HISTORICAL_PERFORMANCE"
        ]
        forecast_fields = [
            field for field in fields
            if field_class(field) == "FORWARD_FORECAST"
        ]
        populated_historical = sum(
            bool(clean(row.get(field)))
            for row in active
            for field in historical_fields
        )
        horizon_fields = [
            field for field in forecast_fields
            if re.search(
                r"(one_year|three_year|five_year|(^|_)(1y|3y|5y)($|_))",
                field,
                re.I,
            )
        ]
        populated_horizons = sum(
            bool(clean(row.get(field)))
            for row in active
            for field in horizon_fields
        )
        results.append({
            "path": relative(path),
            "exists": path.is_file(),
            "rows": len(rows),
            "secret_lair_rows": len(active),
            "historical_fields": "|".join(historical_fields),
            "forecast_fields": "|".join(forecast_fields),
            "populated_historical_cells": populated_historical,
            "populated_horizon_cells": populated_horizons,
        })
    return results


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--package", action="store_true")
    args = parser.parse_args()

    output = args.output_root
    output.mkdir(parents=True, exist_ok=True)

    paths = scan_files()
    matches = source_match_rows(paths)
    datasets, schemas = csv_schema_rows(paths)
    symbols = python_symbol_rows(paths)
    contract = current_contract_rows()

    likely_historical_datasets = [
        row for row in datasets
        if row["has_historical_fields"] == "YES"
        or (
            row["has_date_fields"] == "YES"
            and row["has_price_fields"] == "YES"
        )
    ]
    likely_secret_lair_historical = [
        row for row in likely_historical_datasets
        if row["secret_lair_relevant"] == "YES"
    ]

    checks = {
        "current_secret_lair_contract_present": all(
            row["exists"] for row in contract
        ),
        "current_horizon_values_suppressed": all(
            int(row["populated_horizon_cells"]) == 0
            for row in contract
        ),
        "return_analytics_components_found": all(
            path.is_file() for path in LIKELY_CORE_FILES[:5]
        ),
        "historical_candidates_found": len(likely_historical_datasets) > 0,
        "secret_lair_historical_candidates_found": (
            len(likely_secret_lair_historical) > 0
        ),
    }

    status = (
        "PASS"
        if all(checks.values())
        else "REVIEW"
    )

    report = {
        "status": status,
        "phase": "8.2.1D.1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": (
            "Locate and classify historical performance sources before "
            "building a separate Secret Lair return analytics layer."
        ),
        "governance": {
            "historical_performance_is_not_forecast": True,
            "historical_cagr_must_use_observed_start_and_end_dates": True,
            "forward_horizons_remain_suppressed_until_certified": True,
            "historical_analytics_do_not_enable_recommendations": True,
        },
        "counts": {
            "text_files_scanned": len(paths),
            "source_matches": len(matches),
            "candidate_csv_datasets": len(datasets),
            "historical_dataset_candidates": len(
                likely_historical_datasets
            ),
            "secret_lair_historical_candidates": len(
                likely_secret_lair_historical
            ),
            "python_symbols": len(symbols),
        },
        "checks": checks,
    }

    write_csv(output / "phase_8_2_1d_source_matches.csv", matches)
    write_csv(output / "phase_8_2_1d_dataset_inventory.csv", datasets)
    write_csv(output / "phase_8_2_1d_field_semantic_matrix.csv", schemas)
    write_csv(output / "phase_8_2_1d_python_symbol_inventory.csv", symbols)
    write_csv(output / "phase_8_2_1d_current_contract.csv", contract)

    core_inventory = []
    for path in LIKELY_CORE_FILES:
        core_inventory.append({
            "path": relative(path),
            "exists": path.is_file(),
            "bytes": path.stat().st_size if path.is_file() else 0,
            "sha256": sha256(path) if path.is_file() else "",
        })
    write_csv(output / "phase_8_2_1d_core_component_inventory.csv", core_inventory)

    (output / "PHASE_8_2_1D_1_DISCOVERY.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    markdown = [
        "# Phase 8.2.1D.1 — Historical Performance Source Discovery",
        "",
        f"**Status:** {status}",
        "",
        "## Purpose",
        "",
        report["purpose"],
        "",
        "## Governance",
        "",
        "- Historical performance is descriptive, not predictive.",
        "- CAGR requires observed start value, end value, and elapsed time.",
        "- One-, three-, and five-year forecast fields remain blank until a separately certified horizon model exists.",
        "- Historical analytics alone cannot enable an investment recommendation.",
        "",
        "## Counts",
        "",
    ]
    markdown.extend(
        f"- {key}: {value}"
        for key, value in report["counts"].items()
    )
    markdown.extend(["", "## Checks", ""])
    markdown.extend(
        f"- {key}: {'PASS' if value else 'REVIEW'}"
        for key, value in checks.items()
    )
    markdown.extend([
        "",
        "## Evidence",
        "",
        "- `phase_8_2_1d_source_matches.csv`",
        "- `phase_8_2_1d_dataset_inventory.csv`",
        "- `phase_8_2_1d_field_semantic_matrix.csv`",
        "- `phase_8_2_1d_python_symbol_inventory.csv`",
        "- `phase_8_2_1d_current_contract.csv`",
        "- `phase_8_2_1d_core_component_inventory.csv`",
        "- `PHASE_8_2_1D_1_DISCOVERY.json`",
        "",
    ])
    (output / "PHASE_8_2_1D_1_DISCOVERY.md").write_text(
        "\n".join(markdown),
        encoding="utf-8",
    )

    package_path = None
    if args.package:
        package_root = (
            ROOT
            / "data"
            / "operations"
            / "phase_8_2_1d_repair_input"
        )
        if package_root.exists():
            shutil.rmtree(package_root)
        package_root.mkdir(parents=True, exist_ok=True)

        shutil.copytree(
            output,
            package_root / "evidence",
        )

        selected_paths: set[Path] = set()
        selected_paths.update(
            path for path in LIKELY_CORE_FILES if path.is_file()
        )

        top_match_paths = [
            ROOT / row["path"]
            for row in matches[:150]
            if (ROOT / row["path"]).is_file()
        ]
        selected_paths.update(top_match_paths)

        for row in likely_historical_datasets[:100]:
            path = ROOT / row["path"]
            if path.is_file():
                selected_paths.add(path)

        selected_paths.update(
            path for path in CURRENT_OUTPUTS if path.is_file()
        )

        for path in sorted(selected_paths):
            destination = (
                package_root
                / "repo"
                / path.relative_to(ROOT)
            )
            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
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
    print("PHASE 8.2.1D.1 — HISTORICAL PERFORMANCE SOURCE DISCOVERY")
    print("=" * 78)
    print(f"Text files scanned: {len(paths)}")
    print(f"Source matches: {len(matches)}")
    print(f"Candidate CSV datasets: {len(datasets)}")
    print(
        "Historical dataset candidates: "
        f"{len(likely_historical_datasets)}"
    )
    print(
        "Secret Lair historical candidates: "
        f"{len(likely_secret_lair_historical)}"
    )
    print(f"Python symbols inventoried: {len(symbols)}")
    print(f"Status: {status}")
    print(f"Evidence: {output}")
    if package_path:
        print(f"Repair input package: {package_path}")
    print("PHASE 8.2.1D.1 DISCOVERY: COMPLETE")
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
