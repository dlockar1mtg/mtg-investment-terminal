from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = (
    ROOT
    / "docs"
    / "phase_8"
    / "secret_lair_export_recovery"
)
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

INVENTORY_CSV = OUTPUT_ROOT / "secret_lair_source_inventory.csv"
FIELD_MATRIX_CSV = OUTPUT_ROOT / "secret_lair_field_matrix.csv"
COVERAGE_CSV = OUTPUT_ROOT / "secret_lair_coverage_reconciliation.csv"
SUMMARY_JSON = OUTPUT_ROOT / "secret_lair_recovery_audit.json"
REPORT_MD = OUTPUT_ROOT / "PHASE_8_2_1A_SECRET_LAIR_RECOVERY_AUDIT.md"

TEXT_EXTENSIONS = {
    ".csv",
    ".json",
    ".jsonl",
    ".ndjson",
    ".html",
    ".htm",
    ".js",
    ".py",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
}

DATABASE_EXTENSIONS = {
    ".duckdb",
    ".db",
    ".sqlite",
    ".sqlite3",
}

SKIP_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
}

SECRET_LAIR_TERMS = (
    "secret lair",
    "secret_lair",
    "secretlair",
)

INTELLIGENCE_ALIASES = {
    "current_price": {
        "price",
        "current_price",
        "market_price",
        "latest_price",
        "observed_price",
        "point_forecast",
    },
    "msrp": {
        "msrp",
        "release_price",
        "original_price",
        "retail_price",
    },
    "annualized_return": {
        "annualized_return",
        "annualized_return_pct",
        "ann_return",
        "annret",
        "realized_cagr",
        "historical_cagr",
        "cagr",
    },
    "return_30d": {
        "return_30d",
        "r30",
        "ret_30d",
        "thirty_day_return",
    },
    "return_90d": {
        "return_90d",
        "r90",
        "ret_90d",
        "ninety_day_return",
    },
    "return_1y": {
        "return_1y",
        "return_365d",
        "r365",
        "one_year_return",
        "year_return",
    },
    "maximum_drawdown": {
        "maximum_drawdown",
        "max_drawdown",
        "peak_drawdown",
        "drawdown",
        "dd",
    },
    "investment_score": {
        "investment_score",
        "score",
        "model_score",
    },
    "risk_adjusted_score": {
        "risk_adjusted_score",
        "risk_adjusted",
        "ras",
    },
    "recommendation_score": {
        "recommendation_score",
        "rec_score",
        "recscore",
    },
    "composite_score": {
        "composite_score",
        "comp_score",
        "compscore",
    },
    "momentum_score": {
        "momentum_score",
        "momentum",
        "mom",
    },
    "scarcity_score": {
        "scarcity_score",
        "scarcity",
    },
    "liquidity_score": {
        "liquidity_score",
        "liquidity",
    },
    "value_score": {
        "value_score",
        "value",
    },
    "risk_score": {
        "risk_score",
        "riskscore",
    },
    "risk_rating": {
        "risk_rating",
        "risk_level",
        "risk",
    },
    "confidence_score": {
        "confidence_score",
        "confidence",
        "conf",
    },
    "recommendation": {
        "recommendation",
        "rating",
        "signal",
        "rec",
        "conv_tier",
        "convtier",
    },
    "universe_rank": {
        "universe_rank",
        "rank",
        "composite_rank",
        "comp_rank",
        "comprank",
    },
    "history": {
        "history",
        "hist",
        "price_history",
        "observations",
    },
    "forecast_horizon_months": {
        "forecast_horizon_months",
        "horizon_months",
        "forecast_months",
    },
    "point_forecast": {
        "point_forecast",
        "forecast_value",
        "projected_value",
        "median_forecast",
    },
    "expected_return": {
        "expected_return",
        "forecast_return",
        "projected_return",
    },
    "forecast_cagr": {
        "forecast_cagr",
        "projected_cagr",
        "expected_cagr",
    },
    "lower_bound": {
        "lower_bound",
        "forecast_low",
        "p05",
        "low_estimate",
    },
    "upper_bound": {
        "upper_bound",
        "forecast_high",
        "p95",
        "high_estimate",
    },
}


def normalized(value: Any) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "_",
        str(value).strip().lower(),
    ).strip("_")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def is_secret_lair_text(value: str) -> bool:
    lowered = value.lower()
    return any(term in lowered for term in SECRET_LAIR_TERMS)


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRECTORIES for part in path.parts)


def safe_read_text(path: Path, limit: int | None = None) -> str:
    try:
        if limit is None:
            return path.read_text(encoding="utf-8", errors="replace")

        with path.open(
            "r",
            encoding="utf-8",
            errors="replace",
        ) as handle:
            return handle.read(limit)

    except Exception:
        return ""


def inspect_csv(path: Path) -> dict[str, Any]:
    record_count = 0
    secret_lair_count = 0
    columns: list[str] = []
    sample_names: list[str] = []
    classifications = Counter()

    with path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []

        probable_name_columns = [
            column
            for column in columns
            if normalized(column)
            in {
                "name",
                "product",
                "product_name",
                "asset_name",
                "drop_name",
                "title",
            }
        ]

        probable_class_columns = [
            column
            for column in columns
            if normalized(column)
            in {
                "asset_class",
                "asset_subclass",
                "product_type",
                "category",
                "class",
                "type",
                "universe",
            }
        ]

        for row in reader:
            record_count += 1

            joined = " ".join(
                str(value)
                for value in row.values()
                if value is not None
            )

            if is_secret_lair_text(joined):
                secret_lair_count += 1

                for column in probable_name_columns:
                    value = str(row.get(column, "")).strip()

                    if value and value not in sample_names:
                        sample_names.append(value)

                        if len(sample_names) >= 5:
                            break

            for column in probable_class_columns:
                value = str(row.get(column, "")).strip()

                if value:
                    classifications[value] += 1

    return {
        "record_count": record_count,
        "secret_lair_count": secret_lair_count,
        "columns": columns,
        "sample_names": sample_names[:5],
        "classifications": dict(classifications.most_common(10)),
    }


def inspect_json(path: Path) -> dict[str, Any]:
    text = safe_read_text(path)
    data = json.loads(text)

    records: list[dict[str, Any]] = []

    if isinstance(data, list):
        records = [
            item
            for item in data
            if isinstance(item, dict)
        ]

    elif isinstance(data, dict):
        for key in (
            "secret_lairs",
            "secretLairs",
            "secret_lair",
            "sl",
            "records",
            "products",
            "assets",
            "data",
        ):
            value = data.get(key)

            if isinstance(value, list):
                records.extend(
                    item
                    for item in value
                    if isinstance(item, dict)
                )

        if not records:
            records = [data]

    columns = sorted(
        {
            str(key)
            for record in records
            for key in record.keys()
        }
    )

    secret_records = [
        record
        for record in records
        if is_secret_lair_text(
            json.dumps(record, default=str)
        )
    ]

    names = []

    for record in secret_records:
        for key in (
            "name",
            "product_name",
            "asset_name",
            "drop_name",
            "title",
        ):
            value = record.get(key)

            if value:
                names.append(str(value))
                break

    return {
        "record_count": len(records),
        "secret_lair_count": len(secret_records),
        "columns": columns,
        "sample_names": names[:5],
        "classifications": {},
    }


def extract_terminal_data(path: Path) -> dict[str, Any]:
    text = safe_read_text(path)

    marker_match = re.search(
        r"\bconst\s+DATA\s*=\s*",
        text,
    )

    if not marker_match:
        return {
            "record_count": 0,
            "secret_lair_count": 0,
            "columns": [],
            "sample_names": [],
            "classifications": {},
            "terminal_data_found": False,
        }

    start = marker_match.end()
    decoder = json.JSONDecoder()

    try:
        data, _ = decoder.raw_decode(text[start:])
    except Exception as exc:
        return {
            "record_count": 0,
            "secret_lair_count": 0,
            "columns": [],
            "sample_names": [],
            "classifications": {},
            "terminal_data_found": True,
            "parse_error": str(exc),
        }

    secret_records: list[dict[str, Any]] = []

    if isinstance(data, dict):
        for key in (
            "sl",
            "secret_lairs",
            "secretLairs",
            "secret_lair",
        ):
            value = data.get(key)

            if isinstance(value, list):
                secret_records.extend(
                    item
                    for item in value
                    if isinstance(item, dict)
                )

    columns = sorted(
        {
            str(key)
            for record in secret_records
            for key in record.keys()
        }
    )

    names = [
        str(
            record.get("name")
            or record.get("product_name")
            or record.get("asset_name")
            or record.get("drop_name")
            or ""
        )
        for record in secret_records[:5]
    ]

    return {
        "record_count": len(secret_records),
        "secret_lair_count": len(secret_records),
        "columns": columns,
        "sample_names": names,
        "classifications": {},
        "terminal_data_found": True,
    }


def sqlite_tables(path: Path) -> Iterable[dict[str, Any]]:
    connection = sqlite3.connect(
        f"file:{path.as_posix()}?mode=ro",
        uri=True,
    )

    try:
        tables = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type IN ('table', 'view')
            ORDER BY name
            """
        ).fetchall()

        for (table_name,) in tables:
            try:
                quoted = '"' + table_name.replace('"', '""') + '"'
                count = connection.execute(
                    f"SELECT COUNT(*) FROM {quoted}"
                ).fetchone()[0]

                columns = [
                    row[1]
                    for row in connection.execute(
                        f"PRAGMA table_info({quoted})"
                    ).fetchall()
                ]

                yield {
                    "table_name": table_name,
                    "record_count": int(count),
                    "columns": columns,
                }

            except Exception:
                continue

    finally:
        connection.close()


def detect_fields(columns: Iterable[str]) -> dict[str, bool]:
    normalized_columns = {
        normalized(column)
        for column in columns
    }

    return {
        field: bool(
            normalized_columns.intersection(
                {
                    normalized(alias)
                    for alias in aliases
                }
            )
        )
        for field, aliases in INTELLIGENCE_ALIASES.items()
    }


inventory: list[dict[str, Any]] = []
field_rows: list[dict[str, Any]] = []

for path in sorted(ROOT.rglob("*")):
    if not path.is_file() or should_skip(path):
        continue

    suffix = path.suffix.lower()

    if suffix not in TEXT_EXTENSIONS | DATABASE_EXTENSIONS:
        continue

    relative = path.relative_to(ROOT).as_posix()
    lower_relative = relative.lower()

    path_relevant = is_secret_lair_text(lower_relative)

    header_text = ""

    if suffix in TEXT_EXTENSIONS:
        header_text = safe_read_text(path, limit=250_000)

    content_relevant = is_secret_lair_text(header_text)

    if not path_relevant and not content_relevant:
        continue

    details: dict[str, Any] = {
        "record_count": None,
        "secret_lair_count": None,
        "columns": [],
        "sample_names": [],
        "classifications": {},
    }

    source_type = suffix.lstrip(".")
    error = ""

    try:
        if suffix == ".csv":
            details = inspect_csv(path)

        elif suffix == ".json":
            details = inspect_json(path)

        elif suffix in {".html", ".htm"}:
            details = extract_terminal_data(path)

        elif suffix in DATABASE_EXTENSIONS:
            source_type = "database"

            for table in sqlite_tables(path):
                table_columns = table["columns"]
                table_relevant = (
                    is_secret_lair_text(table["table_name"])
                    or any(
                        is_secret_lair_text(column)
                        for column in table_columns
                    )
                )

                if not table_relevant:
                    continue

                source_id = (
                    f"{relative}::{table['table_name']}"
                )
                detected = detect_fields(table_columns)

                inventory.append(
                    {
                        "source_id": source_id,
                        "path": relative,
                        "source_type": "database_table",
                        "table_or_key": table["table_name"],
                        "file_size_bytes": path.stat().st_size,
                        "sha256": sha256(path),
                        "record_count": table["record_count"],
                        "secret_lair_count": "",
                        "column_count": len(table_columns),
                        "columns": json.dumps(table_columns),
                        "sample_names": "",
                        "classifications": "",
                        "error": "",
                    }
                )

                field_rows.append(
                    {
                        "source_id": source_id,
                        **detected,
                    }
                )

            continue

    except Exception as exc:
        error = str(exc)

    source_id = relative
    detected = detect_fields(details.get("columns", []))

    inventory.append(
        {
            "source_id": source_id,
            "path": relative,
            "source_type": source_type,
            "table_or_key": "",
            "file_size_bytes": path.stat().st_size,
            "sha256": sha256(path),
            "record_count": details.get("record_count"),
            "secret_lair_count": details.get(
                "secret_lair_count"
            ),
            "column_count": len(
                details.get("columns", [])
            ),
            "columns": json.dumps(
                details.get("columns", [])
            ),
            "sample_names": json.dumps(
                details.get("sample_names", [])
            ),
            "classifications": json.dumps(
                details.get("classifications", {})
            ),
            "error": (
                error
                or details.get("parse_error", "")
            ),
        }
    )

    field_rows.append(
        {
            "source_id": source_id,
            **detected,
        }
    )


def source_priority(item: dict[str, Any]) -> tuple[int, int]:
    secret_count = item.get("secret_lair_count")

    try:
        count = int(secret_count)
    except (TypeError, ValueError):
        count = 0

    path_value = str(item.get("path", "")).lower()

    priority = 0

    if "terminal" in path_value or "dashboard" in path_value:
        priority += 5

    if "universal" in path_value or "export" in path_value:
        priority += 4

    if "production" in path_value:
        priority += 3

    if "master" in path_value:
        priority += 2

    return priority, count


inventory.sort(
    key=source_priority,
    reverse=True,
)

inventory_fields = [
    "source_id",
    "path",
    "source_type",
    "table_or_key",
    "file_size_bytes",
    "sha256",
    "record_count",
    "secret_lair_count",
    "column_count",
    "columns",
    "sample_names",
    "classifications",
    "error",
]

with INVENTORY_CSV.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=inventory_fields,
    )
    writer.writeheader()
    writer.writerows(inventory)

field_names = [
    "source_id",
    *INTELLIGENCE_ALIASES.keys(),
]

with FIELD_MATRIX_CSV.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=field_names,
    )
    writer.writeheader()
    writer.writerows(field_rows)

terminal_sources = [
    item
    for item in inventory
    if (
        item.get("source_type") in {"html", "htm"}
        and int(item.get("secret_lair_count") or 0) > 0
    )
]

universal_sources = [
    item
    for item in inventory
    if (
        "universal" in str(item.get("path", "")).lower()
        or "export" in str(item.get("path", "")).lower()
    )
]

production_sources = [
    item
    for item in inventory
    if "production" in str(item.get("path", "")).lower()
]

candidate_counts = []

for item in inventory:
    try:
        secret_count = int(
            item.get("secret_lair_count") or 0
        )
    except (TypeError, ValueError):
        secret_count = 0

    if secret_count:
        candidate_counts.append(
            {
                "source_id": item["source_id"],
                "secret_lair_count": secret_count,
                "record_count": item.get("record_count"),
                "source_type": item.get("source_type"),
                "path": item.get("path"),
            }
        )

candidate_counts.sort(
    key=lambda item: item["secret_lair_count"],
    reverse=True,
)

maximum_count = (
    candidate_counts[0]["secret_lair_count"]
    if candidate_counts
    else 0
)

coverage_rows = []

for item in candidate_counts:
    count = item["secret_lair_count"]

    coverage_rows.append(
        {
            **item,
            "maximum_detected_count": maximum_count,
            "missing_vs_maximum": maximum_count - count,
            "coverage_pct_vs_maximum": (
                round(count / maximum_count, 6)
                if maximum_count
                else 0
            ),
        }
    )

with COVERAGE_CSV.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "source_id",
            "path",
            "source_type",
            "record_count",
            "secret_lair_count",
            "maximum_detected_count",
            "missing_vs_maximum",
            "coverage_pct_vs_maximum",
        ],
    )
    writer.writeheader()
    writer.writerows(coverage_rows)

summary = {
    "repository_root": str(ROOT),
    "inventory_source_count": len(inventory),
    "sources_with_secret_lair_rows": len(
        candidate_counts
    ),
    "maximum_detected_secret_lair_count": maximum_count,
    "terminal_source_count": len(terminal_sources),
    "universal_or_export_source_count": len(
        universal_sources
    ),
    "production_source_count": len(
        production_sources
    ),
    "largest_sources": candidate_counts[:20],
    "terminal_sources": terminal_sources[:20],
    "universal_sources": universal_sources[:30],
    "production_sources": production_sources[:30],
    "outputs": {
        "inventory_csv": str(INVENTORY_CSV),
        "field_matrix_csv": str(FIELD_MATRIX_CSV),
        "coverage_csv": str(COVERAGE_CSV),
        "summary_json": str(SUMMARY_JSON),
        "report_markdown": str(REPORT_MD),
    },
}

SUMMARY_JSON.write_text(
    json.dumps(
        summary,
        indent=2,
        default=str,
    )
    + "\n",
    encoding="utf-8",
)

largest_lines = []

for item in candidate_counts[:20]:
    largest_lines.append(
        "| "
        + " | ".join(
            [
                str(item["secret_lair_count"]),
                str(item["record_count"]),
                str(item["source_type"]),
                str(item["path"]).replace("|", "\\|"),
            ]
        )
        + " |"
    )

if not largest_lines:
    largest_lines.append(
        "| 0 | 0 | none | No populated source detected |"
    )

report = f"""# Phase 8.2.1A — Secret Lair Recovery Audit

## Status

Audit generated successfully.

## Repository

`{ROOT}`

## Summary

- Inventory sources inspected: **{len(inventory)}**
- Sources with detected Secret Lair rows: **{len(candidate_counts)}**
- Maximum detected Secret Lair population: **{maximum_count}**
- Terminal HTML sources with embedded Secret Lair data: **{len(terminal_sources)}**
- Universal/export-related sources: **{len(universal_sources)}**
- Production-related sources: **{len(production_sources)}**

## Largest detected Secret Lair sources

| Secret Lair rows | Total rows | Type | Path |
|---:|---:|---|---|
{chr(10).join(largest_lines)}

## Recovery questions for Phase 8.2.1B

1. Which source contains the complete governed Secret Lair population?
2. Which source fed the previous research terminal?
3. Which source currently feeds the universal export?
4. Which records are absent from the universal package?
5. Which intelligence fields are missing from the universal contract?
6. Are missing records intentionally suppressed or accidentally omitted?
7. Can realized-return intelligence be exported without mislabeling it as a forward forecast?
8. Which Secret Lair products qualify for true horizon-based projections?

## Evidence files

- `secret_lair_source_inventory.csv`
- `secret_lair_field_matrix.csv`
- `secret_lair_coverage_reconciliation.csv`
- `secret_lair_recovery_audit.json`
"""

REPORT_MD.write_text(
    report,
    encoding="utf-8",
)

print("=" * 72)
print("PHASE 8.2.1A — SECRET LAIR EXPORT RECOVERY AUDIT")
print("=" * 72)
print(f"Repository: {ROOT}")
print(f"Sources inventoried: {len(inventory)}")
print(
    "Sources with Secret Lair rows: "
    f"{len(candidate_counts)}"
)
print(
    "Maximum detected Secret Lair count: "
    f"{maximum_count}"
)
print()
print("Largest detected sources:")

for item in candidate_counts[:15]:
    print(
        f"  {item['secret_lair_count']:>6} | "
        f"{item['source_type']:<14} | "
        f"{item['path']}"
    )

print()
print(f"Report: {REPORT_MD}")
print("PHASE 8.2.1A AUDIT: PASS")
