from __future__ import annotations

import ast
import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "source_coverage"
)

EXCLUDED_DIRECTORIES = {
    ".git",
    ".pytest_cache",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
}

DATA_EXTENSIONS = {
    ".csv",
    ".json",
    ".jsonl",
    ".parquet",
    ".xlsx",
    ".xls",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".duckdb",
    ".yaml",
    ".yml",
    ".txt",
    ".zip",
    ".7z",
}

DATABASE_EXTENSIONS = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".duckdb",
}

CODE_EXTENSIONS = {
    ".py",
    ".ps1",
    ".sql",
    ".js",
    ".ts",
    ".html",
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
}

SOURCE_KEYWORDS = {
    "tcgplayer": (
        "tcgplayer",
        "tcg csv",
        "tcgcsv",
    ),
    "scryfall": (
        "scryfall",
        "api.scryfall.com",
    ),
    "mtgjson": (
        "mtgjson",
        "mtgjson.com",
    ),
    "ebay": (
        "ebay",
        "api.ebay.com",
    ),
    "cardmarket": (
        "cardmarket",
        "mkmapi",
    ),
    "card_kingdom": (
        "card kingdom",
        "cardkingdom",
    ),
    "star_city_games": (
        "star city games",
        "starcitygames",
    ),
    "coolstuffinc": (
        "coolstuffinc",
        "cool stuff inc",
    ),
    "wizards": (
        "wizards.com",
        "magic.wizards.com",
        "wizards of the coast",
    ),
    "secret_lair": (
        "secret lair",
        "secretlair",
    ),
    "pricecharting": (
        "pricecharting",
    ),
    "scrydex": (
        "scrydex",
    ),
}

PRODUCT_FIELD_TERMS = {
    "product_id": (
        "product_id",
        "productid",
        "tcgplayer_product_id",
        "approved_tcgplayer_product_id",
    ),
    "product_name": (
        "product_name",
        "name",
        "box_name",
        "approved_product_name",
    ),
    "set_name": (
        "set_name",
        "set",
        "group_name",
    ),
    "set_code": (
        "set_code",
        "code",
    ),
    "release_date": (
        "release_date",
        "released_at",
        "releaseDate",
    ),
    "product_type": (
        "product_type",
        "investment_product_type",
        "category",
    ),
    "price": (
        "price",
        "market_price",
        "low_price",
        "mid_price",
        "high_price",
    ),
    "listing_count": (
        "listing_count",
        "listings",
        "inventory_count",
    ),
    "secret_lair_card_count": (
        "card_count",
        "secret_lair_card_count",
    ),
}

URL_PATTERN = re.compile(
    r"https?://[^\s\"'<>]+",
    flags=re.IGNORECASE,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def should_skip(path: Path) -> bool:
    return any(
        part in EXCLUDED_DIRECTORIES
        for part in path.parts
    )


def safe_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0


def sha256_file(
    path: Path,
    chunk_size: int = 1024 * 1024,
) -> str:
    digest = hashlib.sha256()

    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(chunk_size)

                if not chunk:
                    break

                digest.update(chunk)

        return digest.hexdigest()
    except OSError:
        return ""


def safe_read_text(
    path: Path,
    max_bytes: int = 2_000_000,
) -> str:
    try:
        with path.open("rb") as handle:
            raw = handle.read(max_bytes)

        return raw.decode(
            "utf-8",
            errors="replace",
        )
    except OSError:
        return ""


def inspect_csv(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "row_count": None,
        "column_count": None,
        "columns": [],
        "read_status": "not_attempted",
        "read_error": "",
    }

    try:
        frame = pd.read_csv(
            path,
            low_memory=False,
        )

        result.update(
            {
                "row_count": int(len(frame)),
                "column_count": int(len(frame.columns)),
                "columns": [
                    str(column)
                    for column in frame.columns
                ],
                "read_status": "success",
            }
        )
    except Exception as exc:
        result.update(
            {
                "read_status": "failed",
                "read_error": (
                    f"{type(exc).__name__}: {exc}"
                ),
            }
        )

    return result


def inspect_json(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "row_count": None,
        "column_count": None,
        "columns": [],
        "json_shape": "",
        "read_status": "not_attempted",
        "read_error": "",
    }

    try:
        with path.open(
            "r",
            encoding="utf-8",
            errors="replace",
        ) as handle:
            payload = json.load(handle)

        if isinstance(payload, list):
            result["json_shape"] = "list"
            result["row_count"] = len(payload)

            keys: set[str] = set()

            for item in payload[:100]:
                if isinstance(item, dict):
                    keys.update(
                        str(key)
                        for key in item
                    )

            result["columns"] = sorted(keys)
            result["column_count"] = len(keys)

        elif isinstance(payload, dict):
            result["json_shape"] = "object"
            result["columns"] = sorted(
                str(key)
                for key in payload
            )
            result["column_count"] = len(
                result["columns"]
            )

            for candidate_key in (
                "data",
                "results",
                "products",
                "items",
                "records",
            ):
                candidate = payload.get(
                    candidate_key
                )

                if isinstance(candidate, list):
                    result["row_count"] = len(
                        candidate
                    )
                    break
        else:
            result["json_shape"] = type(
                payload
            ).__name__

        result["read_status"] = "success"

    except Exception as exc:
        result.update(
            {
                "read_status": "failed",
                "read_error": (
                    f"{type(exc).__name__}: {exc}"
                ),
            }
        )

    return result


def inspect_excel(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "row_count": None,
        "column_count": None,
        "columns": [],
        "sheet_names": [],
        "read_status": "not_attempted",
        "read_error": "",
    }

    try:
        workbook = pd.ExcelFile(path)

        result["sheet_names"] = [
            str(sheet)
            for sheet in workbook.sheet_names
        ]

        total_rows = 0
        all_columns: set[str] = set()

        for sheet in workbook.sheet_names:
            frame = pd.read_excel(
                path,
                sheet_name=sheet,
            )

            total_rows += len(frame)
            all_columns.update(
                str(column)
                for column in frame.columns
            )

        result.update(
            {
                "row_count": int(total_rows),
                "column_count": len(all_columns),
                "columns": sorted(all_columns),
                "read_status": "success",
            }
        )

    except Exception as exc:
        result.update(
            {
                "read_status": "failed",
                "read_error": (
                    f"{type(exc).__name__}: {exc}"
                ),
            }
        )

    return result


def detect_product_fields(
    columns: list[str],
) -> list[str]:
    normalized_columns = {
        str(column).strip().casefold()
        for column in columns
    }

    detected: list[str] = []

    for field_name, terms in PRODUCT_FIELD_TERMS.items():
        if any(
            term.casefold() in normalized_columns
            for term in terms
        ):
            detected.append(field_name)

    return sorted(detected)


def classify_file_role(
    path: Path,
    columns: list[str],
    text: str,
) -> str:
    name = path.name.casefold()
    combined = " ".join(
        [
            name,
            " ".join(
                column.casefold()
                for column in columns
            ),
            text[:50_000].casefold(),
        ]
    )

    if any(
        term in combined
        for term in (
            "product_master",
            "product registry",
            "investment_products",
        )
    ):
        return "product_registry"

    if (
        "secret lair" in combined
        or "secret_lair" in combined
    ):
        return "secret_lair_source"

    if any(
        term in combined
        for term in (
            "price_history",
            "historical_price",
            "market_price",
            "daily_price",
        )
    ):
        return "price_history"

    if any(
        term in combined
        for term in (
            "listing_count",
            "inventory",
            "liquidity",
            "sales_velocity",
        )
    ):
        return "supply_demand"

    if any(
        term in combined
        for term in (
            "set_code",
            "release_date",
            "released_at",
            "set_name",
        )
    ):
        return "set_or_release_metadata"

    if columns:
        return "structured_data_other"

    return "other"


def inspect_database(
    path: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    if path.suffix.casefold() == ".duckdb":
        try:
            import duckdb
        except ImportError:
            return [
                {
                    "database_path": relative_path(
                        path
                    ),
                    "database_type": "duckdb",
                    "table_name": "",
                    "table_type": "",
                    "row_count": None,
                    "columns": "",
                    "inspection_status": (
                        "duckdb_module_unavailable"
                    ),
                    "inspection_error": "",
                }
            ]

        try:
            connection = duckdb.connect(
                str(path),
                read_only=True,
            )

            tables = connection.execute(
                """
                SELECT
                    table_schema,
                    table_name,
                    table_type
                FROM information_schema.tables
                WHERE table_schema NOT IN (
                    'information_schema',
                    'pg_catalog'
                )
                ORDER BY
                    table_schema,
                    table_name
                """
            ).fetchall()

            for (
                schema_name,
                table_name,
                table_type,
            ) in tables:
                qualified = (
                    f'"{schema_name}"."{table_name}"'
                )

                try:
                    count = connection.execute(
                        f"SELECT COUNT(*) FROM {qualified}"
                    ).fetchone()[0]
                except Exception:
                    count = None

                try:
                    description = connection.execute(
                        f"DESCRIBE {qualified}"
                    ).fetchall()

                    columns = [
                        str(item[0])
                        for item in description
                    ]
                except Exception:
                    columns = []

                rows.append(
                    {
                        "database_path": relative_path(
                            path
                        ),
                        "database_type": "duckdb",
                        "table_name": (
                            f"{schema_name}.{table_name}"
                        ),
                        "table_type": table_type,
                        "row_count": count,
                        "columns": "|".join(columns),
                        "inspection_status": "success",
                        "inspection_error": "",
                    }
                )

            connection.close()

        except Exception as exc:
            rows.append(
                {
                    "database_path": relative_path(
                        path
                    ),
                    "database_type": "duckdb",
                    "table_name": "",
                    "table_type": "",
                    "row_count": None,
                    "columns": "",
                    "inspection_status": "failed",
                    "inspection_error": (
                        f"{type(exc).__name__}: {exc}"
                    ),
                }
            )

        return rows

    try:
        connection = sqlite3.connect(
            f"file:{path}?mode=ro",
            uri=True,
        )

        table_rows = connection.execute(
            """
            SELECT
                name,
                type
            FROM sqlite_master
            WHERE type IN ('table', 'view')
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()

        for table_name, table_type in table_rows:
            escaped_table_name = table_name.replace(
                '"',
                '""',
            )

            try:
                count = connection.execute(
                    f'SELECT COUNT(*) '
                    f'FROM "{escaped_table_name}"'
                ).fetchone()[0]
            except Exception:
                count = None

            try:
                column_rows = connection.execute(
                    f'PRAGMA table_info('
                    f'"{escaped_table_name}")'
                ).fetchall()

                columns = [
                    str(row[1])
                    for row in column_rows
                ]
            except Exception:
                columns = []

            rows.append(
                {
                    "database_path": relative_path(
                        path
                    ),
                    "database_type": "sqlite",
                    "table_name": table_name,
                    "table_type": table_type,
                    "row_count": count,
                    "columns": "|".join(columns),
                    "inspection_status": "success",
                    "inspection_error": "",
                }
            )

        connection.close()

    except Exception as exc:
        rows.append(
            {
                "database_path": relative_path(path),
                "database_type": "sqlite",
                "table_name": "",
                "table_type": "",
                "row_count": None,
                "columns": "",
                "inspection_status": "failed",
                "inspection_error": (
                    f"{type(exc).__name__}: {exc}"
                ),
            }
        )

    return rows


def discover_source_references(
    path: Path,
) -> list[dict[str, Any]]:
    text = safe_read_text(path)

    if not text:
        return []

    folded = text.casefold()
    discovered: list[dict[str, Any]] = []

    for source_name, terms in SOURCE_KEYWORDS.items():
        matched_terms = sorted(
            {
                term
                for term in terms
                if term.casefold() in folded
            }
        )

        if matched_terms:
            discovered.append(
                {
                    "source_name": source_name,
                    "referencing_file": relative_path(
                        path
                    ),
                    "matched_terms": "|".join(
                        matched_terms
                    ),
                    "reference_type": (
                        "keyword_reference"
                    ),
                }
            )

    for url in sorted(set(URL_PATTERN.findall(text))):
        clean_url = url.rstrip(
            ".,);]}"
        )

        discovered.append(
            {
                "source_name": "url",
                "referencing_file": relative_path(
                    path
                ),
                "matched_terms": clean_url,
                "reference_type": "url_reference",
            }
        )

    return discovered


def main() -> int:
    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_rows: list[dict[str, Any]] = []
    data_rows: list[dict[str, Any]] = []
    database_rows: list[dict[str, Any]] = []
    reference_rows: list[dict[str, Any]] = []

    paths = sorted(
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and not should_skip(path)
    )

    for path in paths:
        suffix = path.suffix.casefold()
        rel_path = relative_path(path)
        size_bytes = safe_size(path)

        file_rows.append(
            {
                "relative_path": rel_path,
                "filename": path.name,
                "extension": suffix,
                "size_bytes": size_bytes,
                "is_data_candidate": (
                    suffix in DATA_EXTENSIONS
                ),
                "is_code_candidate": (
                    suffix in CODE_EXTENSIONS
                ),
            }
        )

        columns: list[str] = []
        inspection: dict[str, Any] = {}
        text_sample = ""

        if suffix == ".csv":
            inspection = inspect_csv(path)
            columns = inspection.get(
                "columns",
                [],
            )

        elif suffix in {".json", ".jsonl"}:
            if suffix == ".json":
                inspection = inspect_json(path)
                columns = inspection.get(
                    "columns",
                    [],
                )
            else:
                inspection = {
                    "row_count": None,
                    "column_count": None,
                    "columns": [],
                    "read_status": (
                        "jsonl_not_fully_inspected"
                    ),
                    "read_error": "",
                }

        elif suffix in {".xlsx", ".xls"}:
            inspection = inspect_excel(path)
            columns = inspection.get(
                "columns",
                [],
            )

        elif suffix in DATA_EXTENSIONS:
            inspection = {
                "row_count": None,
                "column_count": None,
                "columns": [],
                "read_status": "metadata_only",
                "read_error": "",
            }

        if suffix in DATA_EXTENSIONS:
            text_sample = (
                safe_read_text(path)
                if suffix
                in {
                    ".csv",
                    ".json",
                    ".jsonl",
                    ".yaml",
                    ".yml",
                    ".txt",
                }
                else ""
            )

            detected_fields = detect_product_fields(
                columns
            )

            source_role = classify_file_role(
                path,
                columns,
                text_sample,
            )

            data_rows.append(
                {
                    "relative_path": rel_path,
                    "filename": path.name,
                    "extension": suffix,
                    "size_bytes": size_bytes,
                    "sha256": (
                        sha256_file(path)
                        if size_bytes
                        <= 100_000_000
                        else ""
                    ),
                    "row_count": inspection.get(
                        "row_count"
                    ),
                    "column_count": inspection.get(
                        "column_count"
                    ),
                    "columns": "|".join(columns),
                    "sheet_names": "|".join(
                        inspection.get(
                            "sheet_names",
                            [],
                        )
                    ),
                    "json_shape": inspection.get(
                        "json_shape",
                        "",
                    ),
                    "detected_product_fields": (
                        "|".join(detected_fields)
                    ),
                    "detected_product_field_count": (
                        len(detected_fields)
                    ),
                    "provisional_source_role": (
                        source_role
                    ),
                    "read_status": inspection.get(
                        "read_status",
                        "",
                    ),
                    "read_error": inspection.get(
                        "read_error",
                        "",
                    ),
                }
            )

        if suffix in DATABASE_EXTENSIONS:
            database_rows.extend(
                inspect_database(path)
            )

        if suffix in CODE_EXTENSIONS:
            reference_rows.extend(
                discover_source_references(path)
            )

    files_frame = pd.DataFrame(file_rows)
    data_frame = pd.DataFrame(data_rows)
    databases_frame = pd.DataFrame(database_rows)
    references_frame = pd.DataFrame(
        reference_rows
    )

    if references_frame.empty:
        references_frame = pd.DataFrame(
            columns=[
                "source_name",
                "referencing_file",
                "matched_terms",
                "reference_type",
            ]
        )

    file_inventory_path = (
        OUTPUT_ROOT
        / "repository_file_inventory.csv"
    )

    data_inventory_path = (
        OUTPUT_ROOT
        / "candidate_data_source_inventory.csv"
    )

    database_inventory_path = (
        OUTPUT_ROOT
        / "database_table_inventory.csv"
    )

    reference_inventory_path = (
        OUTPUT_ROOT
        / "external_source_reference_inventory.csv"
    )

    source_registry_path = (
        OUTPUT_ROOT
        / "preliminary_source_registry.csv"
    )

    summary_path = (
        OUTPUT_ROOT
        / "source_coverage_audit_summary.json"
    )

    files_frame.to_csv(
        file_inventory_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    data_frame.to_csv(
        data_inventory_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    databases_frame.to_csv(
        database_inventory_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    references_frame.to_csv(
        reference_inventory_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    source_reference_counts = (
        references_frame[
            "source_name"
        ].value_counts()
        if not references_frame.empty
        else pd.Series(dtype="int64")
    )

    source_registry_rows = []

    for source_name in sorted(
        SOURCE_KEYWORDS
    ):
        source_registry_rows.append(
            {
                "source_name": source_name,
                "source_category": (
                    "external_or_marketplace"
                ),
                "repository_reference_count": int(
                    source_reference_counts.get(
                        source_name,
                        0,
                    )
                ),
                "currently_confirmed_active": (
                    "unknown"
                ),
                "product_coverage": "unknown",
                "historical_price_coverage": (
                    "unknown"
                ),
                "supply_demand_coverage": (
                    "unknown"
                ),
                "identifier_types": "unknown",
                "authority_level": "unreviewed",
                "refresh_method": "unknown",
                "review_status": (
                    "requires_manual_review"
                ),
            }
        )

    internal_roles = sorted(
        data_frame[
            "provisional_source_role"
        ].dropna().unique()
        if not data_frame.empty
        else []
    )

    for role in internal_roles:
        matching = data_frame.loc[
            data_frame[
                "provisional_source_role"
            ].eq(role)
        ]

        source_registry_rows.append(
            {
                "source_name": (
                    f"internal:{role}"
                ),
                "source_category": (
                    "internal_repository_data"
                ),
                "repository_reference_count": int(
                    len(matching)
                ),
                "currently_confirmed_active": (
                    "present_in_repository"
                ),
                "product_coverage": (
                    "requires_content_review"
                ),
                "historical_price_coverage": (
                    "requires_content_review"
                ),
                "supply_demand_coverage": (
                    "requires_content_review"
                ),
                "identifier_types": (
                    "requires_schema_review"
                ),
                "authority_level": "internal",
                "refresh_method": "unknown",
                "review_status": (
                    "requires_manual_review"
                ),
            }
        )

    source_registry_frame = pd.DataFrame(
        source_registry_rows
    )

    source_registry_frame.to_csv(
        source_registry_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    role_counts = (
        data_frame[
            "provisional_source_role"
        ].value_counts().to_dict()
        if not data_frame.empty
        else {}
    )

    extension_counts = Counter(
        row["extension"]
        for row in file_rows
    )

    summary = {
        "audit_generated_at": utc_now(),
        "repository_root": str(ROOT),
        "audit_status": (
            "DISCOVERY_COMPLETE_REVIEW_REQUIRED"
        ),
        "repository_file_count": int(
            len(files_frame)
        ),
        "candidate_data_file_count": int(
            len(data_frame)
        ),
        "database_file_count": int(
            len(
                {
                    row["database_path"]
                    for row in database_rows
                }
            )
        ),
        "database_object_count": int(
            len(databases_frame)
        ),
        "external_source_reference_count": int(
            len(references_frame)
        ),
        "distinct_named_source_count": int(
            references_frame[
                "source_name"
            ].nunique()
            if not references_frame.empty
            else 0
        ),
        "file_extension_counts": dict(
            sorted(extension_counts.items())
        ),
        "provisional_source_role_counts": {
            str(key): int(value)
            for key, value in role_counts.items()
        },
        "important_limitations": [
            (
                "Repository references do not prove "
                "that a source is currently active."
            ),
            (
                "File presence does not prove that a "
                "dataset is complete or authoritative."
            ),
            (
                "Large archives and binary files are "
                "inventoried but not fully inspected."
            ),
            (
                "External product-universe completeness "
                "has not yet been tested."
            ),
            (
                "No product has been added to or removed "
                "from the investment universe."
            ),
        ],
        "output_files": {
            "repository_file_inventory": str(
                file_inventory_path
            ),
            "candidate_data_source_inventory": str(
                data_inventory_path
            ),
            "database_table_inventory": str(
                database_inventory_path
            ),
            "external_source_reference_inventory": str(
                reference_inventory_path
            ),
            "preliminary_source_registry": str(
                source_registry_path
            ),
        },
    }

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print("=" * 76)
    print(
        "Phase 10.5R.1A MTG Product "
        "Source and Coverage Audit"
    )
    print("=" * 76)
    print(
        f"Repository files inventoried: "
        f"{len(files_frame)}"
    )
    print(
        f"Candidate data files: "
        f"{len(data_frame)}"
    )
    print(
        f"Database objects inventoried: "
        f"{len(databases_frame)}"
    )
    print(
        f"External source references: "
        f"{len(references_frame)}"
    )
    print(
        f"Distinct referenced sources: "
        f"{summary['distinct_named_source_count']}"
    )
    print()

    if role_counts:
        print("Provisional source roles:")

        for role_name, count in sorted(
            role_counts.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        ):
            print(
                f"  {role_name}: {count}"
            )

        print()

    print(f"File inventory: {file_inventory_path}")
    print(f"Data inventory: {data_inventory_path}")
    print(
        f"Database inventory: "
        f"{database_inventory_path}"
    )
    print(
        f"Source references: "
        f"{reference_inventory_path}"
    )
    print(
        f"Preliminary source registry: "
        f"{source_registry_path}"
    )
    print(f"Summary: {summary_path}")
    print()
    print(
        "PHASE 10.5R.1A SOURCE DISCOVERY: PASS"
    )
    print(
        "Status: DISCOVERY COMPLETE — "
        "CONTENT REVIEW REQUIRED"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())