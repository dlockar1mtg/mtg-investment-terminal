from __future__ import annotations

import ast
import csv
import importlib.util
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

DATABASE_PATH = (
    ROOT
    / "data"
    / "terminal2"
    / "mtg_investment_terminal.sqlite"
)

PRODUCT_REGISTRY_PATH = (
    ROOT
    / "data"
    / "product_master"
    / "investment_products.csv"
)

SOURCE_DEFINITIONS = {
    "tcgcsv": {
        "candidate_files": [
            "collectors/tcgcsv.py",
            "collectors/tcgcsv_collector.py",
            "collectors/tcgcsv_discovery.py",
            "terminal2/sources/tcgcsv_archive.py",
            "terminal2/sources/product_discovery.py",
            "terminal2_sync_products.py",
        ],
        "expected_capabilities": [
            "sealed_product_discovery",
            "product_identifiers",
            "market_prices",
            "historical_archives",
        ],
    },
    "tcgplayer_api": {
        "candidate_files": [
            "collectors/tcgplayer_api_collector.py",
        ],
        "expected_capabilities": [
            "product_identifiers",
            "market_prices",
        ],
    },
    "scryfall": {
        "candidate_files": [
            "collectors/scryfall.py",
            "collectors/scryfall_collector.py",
            "terminal2/secret_lair/master_database/sources.py",
            "terminal2/secret_lair/discovery/parsers.py",
        ],
        "expected_capabilities": [
            "card_catalog",
            "set_metadata",
            "secret_lair_discovery",
        ],
    },
    "mtgjson": {
        "candidate_files": [
            "collectors/mtgjson.py",
            "collectors/mtgjson_collector.py",
            "terminal2/secret_lair/master_database/sources.py",
            "terminal2/secret_lair/discovery/parsers.py",
        ],
        "expected_capabilities": [
            "card_catalog",
            "set_metadata",
            "sealed_product_enrichment",
            "secret_lair_discovery",
        ],
    },
    "wizards": {
        "candidate_files": [
            "terminal2/secret_lair/master_database/sources.py",
            "terminal2/secret_lair/master_database/config.py",
        ],
        "expected_capabilities": [
            "official_release_metadata",
            "secret_lair_discovery",
        ],
    },
    "ebay": {
        "candidate_files": [],
        "expected_capabilities": [
            "market_prices",
            "sold_listings",
            "supply_demand",
        ],
    },
    "cardmarket": {
        "candidate_files": [],
        "expected_capabilities": [
            "market_prices",
            "supply_demand",
        ],
    },
    "card_kingdom": {
        "candidate_files": [],
        "expected_capabilities": [
            "retail_prices",
            "inventory",
        ],
    },
    "star_city_games": {
        "candidate_files": [],
        "expected_capabilities": [
            "retail_prices",
            "inventory",
        ],
    },
    "coolstuffinc": {
        "candidate_files": [],
        "expected_capabilities": [
            "retail_prices",
            "inventory",
        ],
    },
}

NETWORK_TERMS = (
    "requests.get",
    "requests.post",
    "httpx.get",
    "httpx.post",
    "urllib.request",
    "urlopen",
    "session.get",
    "session.post",
)

WRITE_TERMS = (
    "to_csv(",
    "to_json(",
    "executemany(",
    "execute(",
    "write_text(",
    "write_bytes(",
)

PLACEHOLDER_TERMS = (
    "notimplementederror",
    "todo",
    "placeholder",
    "stub",
    "mock",
)

CONFIG_TERMS = (
    "api_key",
    "token",
    "base_url",
    "endpoint",
    "category_id",
    "group_id",
)

PRODUCT_DISCOVERY_TERMS = (
    "discover",
    "products",
    "product_id",
    "category",
    "group",
    "catalog",
)

PRICE_TERMS = (
    "market_price",
    "low_price",
    "mid_price",
    "high_price",
    "price",
)

SECRET_LAIR_TERMS = (
    "secret lair",
    "secret_lair",
    "secretlair",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative_path(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def safe_read(path: Path) -> str:
    try:
        return path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return ""


def count_matches(
    folded_text: str,
    terms: tuple[str, ...],
) -> int:
    return sum(
        folded_text.count(term.casefold())
        for term in terms
    )


def inspect_python_file(path: Path) -> dict[str, Any]:
    text = safe_read(path)
    folded = text.casefold()

    result: dict[str, Any] = {
        "exists": path.is_file(),
        "syntax_valid": False,
        "function_count": 0,
        "class_count": 0,
        "import_count": 0,
        "network_reference_count": count_matches(
            folded,
            NETWORK_TERMS,
        ),
        "write_reference_count": count_matches(
            folded,
            WRITE_TERMS,
        ),
        "placeholder_reference_count": count_matches(
            folded,
            PLACEHOLDER_TERMS,
        ),
        "config_reference_count": count_matches(
            folded,
            CONFIG_TERMS,
        ),
        "product_discovery_reference_count": count_matches(
            folded,
            PRODUCT_DISCOVERY_TERMS,
        ),
        "price_reference_count": count_matches(
            folded,
            PRICE_TERMS,
        ),
        "secret_lair_reference_count": count_matches(
            folded,
            SECRET_LAIR_TERMS,
        ),
        "syntax_error": "",
    }

    if not path.is_file():
        return result

    try:
        tree = ast.parse(text)

        result["syntax_valid"] = True
        result["function_count"] = sum(
            isinstance(node, ast.FunctionDef)
            or isinstance(node, ast.AsyncFunctionDef)
            for node in ast.walk(tree)
        )
        result["class_count"] = sum(
            isinstance(node, ast.ClassDef)
            for node in ast.walk(tree)
        )
        result["import_count"] = sum(
            isinstance(node, ast.Import)
            or isinstance(node, ast.ImportFrom)
            for node in ast.walk(tree)
        )

    except SyntaxError as exc:
        result["syntax_error"] = (
            f"{exc.msg} at line {exc.lineno}"
        )

    return result


def infer_implementation_status(
    inspection: dict[str, Any],
) -> str:
    if not inspection["exists"]:
        return "missing"

    if not inspection["syntax_valid"]:
        return "invalid_python"

    meaningful_definitions = (
        inspection["function_count"]
        + inspection["class_count"]
    )

    if meaningful_definitions == 0:
        return "configuration_or_thin_wrapper"

    if (
        inspection["placeholder_reference_count"] > 0
        and inspection["network_reference_count"] == 0
        and inspection["write_reference_count"] == 0
    ):
        return "likely_placeholder"

    if (
        inspection["network_reference_count"] > 0
        and meaningful_definitions > 0
    ):
        return "implemented_network_collector"

    if (
        inspection["write_reference_count"] > 0
        and meaningful_definitions > 0
    ):
        return "implemented_local_processor"

    return "implemented_support_module"


def inspect_sources() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for source_name, definition in SOURCE_DEFINITIONS.items():
        candidate_files = definition[
            "candidate_files"
        ]

        if not candidate_files:
            rows.append(
                {
                    "source_name": source_name,
                    "relative_path": "",
                    "file_exists": False,
                    "syntax_valid": False,
                    "function_count": 0,
                    "class_count": 0,
                    "network_reference_count": 0,
                    "write_reference_count": 0,
                    "placeholder_reference_count": 0,
                    "config_reference_count": 0,
                    "product_discovery_reference_count": 0,
                    "price_reference_count": 0,
                    "secret_lair_reference_count": 0,
                    "implementation_status": (
                        "no_operational_file_identified"
                    ),
                    "expected_capabilities": "|".join(
                        definition[
                            "expected_capabilities"
                        ]
                    ),
                    "syntax_error": "",
                }
            )
            continue

        for relative in candidate_files:
            path = ROOT / relative
            inspection = inspect_python_file(path)

            rows.append(
                {
                    "source_name": source_name,
                    "relative_path": relative,
                    "file_exists": inspection["exists"],
                    "syntax_valid": inspection[
                        "syntax_valid"
                    ],
                    "function_count": inspection[
                        "function_count"
                    ],
                    "class_count": inspection[
                        "class_count"
                    ],
                    "network_reference_count": inspection[
                        "network_reference_count"
                    ],
                    "write_reference_count": inspection[
                        "write_reference_count"
                    ],
                    "placeholder_reference_count": inspection[
                        "placeholder_reference_count"
                    ],
                    "config_reference_count": inspection[
                        "config_reference_count"
                    ],
                    "product_discovery_reference_count": inspection[
                        "product_discovery_reference_count"
                    ],
                    "price_reference_count": inspection[
                        "price_reference_count"
                    ],
                    "secret_lair_reference_count": inspection[
                        "secret_lair_reference_count"
                    ],
                    "implementation_status": (
                        infer_implementation_status(
                            inspection
                        )
                    ),
                    "expected_capabilities": "|".join(
                        definition[
                            "expected_capabilities"
                        ]
                    ),
                    "syntax_error": inspection[
                        "syntax_error"
                    ],
                }
            )

    return pd.DataFrame(rows)


def inspect_product_registry() -> dict[str, Any]:
    result: dict[str, Any] = {
        "file_exists": PRODUCT_REGISTRY_PATH.is_file(),
        "row_count": 0,
        "approved_count": 0,
        "unapproved_count": 0,
        "unique_investment_product_ids": 0,
        "unique_tcgplayer_product_ids": 0,
        "product_type_counts": {},
        "approval_status_counts": {},
        "column_coverage": {},
    }

    if not PRODUCT_REGISTRY_PATH.is_file():
        return result

    frame = pd.read_csv(
        PRODUCT_REGISTRY_PATH,
        low_memory=False,
    )

    result["row_count"] = int(len(frame))

    if "approval_status" in frame.columns:
        status = (
            frame["approval_status"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.casefold()
        )

        result["approved_count"] = int(
            status.eq("approved").sum()
        )
        result["unapproved_count"] = int(
            (~status.eq("approved")).sum()
        )
        result["approval_status_counts"] = {
            str(key): int(value)
            for key, value in (
                status.replace("", "(blank)")
                .value_counts()
                .to_dict()
                .items()
            )
        }

    for column in (
        "investment_product_id",
        "approved_tcgplayer_product_id",
    ):
        if column in frame.columns:
            populated = (
                frame[column]
                .notna()
                & frame[column]
                .astype(str)
                .str.strip()
                .ne("")
            )

            key = (
                "unique_investment_product_ids"
                if column == "investment_product_id"
                else "unique_tcgplayer_product_ids"
            )

            result[key] = int(
                frame.loc[
                    populated,
                    column,
                ].nunique()
            )

    if "investment_product_type" in frame.columns:
        result["product_type_counts"] = {
            str(key): int(value)
            for key, value in (
                frame[
                    "investment_product_type"
                ]
                .fillna("(blank)")
                .astype(str)
                .str.strip()
                .replace("", "(blank)")
                .value_counts()
                .to_dict()
                .items()
            )
        }

    for column in frame.columns:
        populated = (
            frame[column]
            .notna()
            & frame[column]
            .astype(str)
            .str.strip()
            .ne("")
        )

        result["column_coverage"][column] = {
            "populated_rows": int(populated.sum()),
            "coverage_pct": round(
                float(populated.mean() * 100),
                4,
            ),
        }

    return result


def inspect_database_products() -> dict[str, Any]:
    result: dict[str, Any] = {
        "database_exists": DATABASE_PATH.is_file(),
        "product_count": 0,
        "column_coverage": {},
        "product_type_counts": {},
        "approval_status_counts": {},
        "source_table_counts": {},
    }

    if not DATABASE_PATH.is_file():
        return result

    connection = sqlite3.connect(
        f"file:{DATABASE_PATH}?mode=ro",
        uri=True,
    )

    try:
        products = pd.read_sql_query(
            "SELECT * FROM products",
            connection,
        )

        result["product_count"] = int(
            len(products)
        )

        for column in products.columns:
            populated = (
                products[column]
                .notna()
                & products[column]
                .astype(str)
                .str.strip()
                .ne("")
            )

            result["column_coverage"][column] = {
                "populated_rows": int(
                    populated.sum()
                ),
                "coverage_pct": round(
                    float(
                        populated.mean() * 100
                    ),
                    4,
                ),
            }

        if "product_type" in products.columns:
            result["product_type_counts"] = {
                str(key): int(value)
                for key, value in (
                    products[
                        "product_type"
                    ]
                    .fillna("(blank)")
                    .astype(str)
                    .str.strip()
                    .replace("", "(blank)")
                    .value_counts()
                    .to_dict()
                    .items()
                )
            }

        if "approval_status" in products.columns:
            result["approval_status_counts"] = {
                str(key): int(value)
                for key, value in (
                    products[
                        "approval_status"
                    ]
                    .fillna("(blank)")
                    .astype(str)
                    .str.strip()
                    .replace("", "(blank)")
                    .value_counts()
                    .to_dict()
                    .items()
                )
            }

        table_names = [
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        ]

        for table_name in table_names:
            escaped = table_name.replace(
                '"',
                '""',
            )

            count = connection.execute(
                f'SELECT COUNT(*) '
                f'FROM "{escaped}"'
            ).fetchone()[0]

            result["source_table_counts"][
                table_name
            ] = int(count)

    finally:
        connection.close()

    return result


def summarize_sources(
    source_frame: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for source_name, group in source_frame.groupby(
        "source_name",
        dropna=False,
    ):
        files_present = int(
            group["file_exists"].astype(bool).sum()
        )

        operational_files = int(
            group["implementation_status"].isin(
                {
                    "implemented_network_collector",
                    "implemented_local_processor",
                    "implemented_support_module",
                    "configuration_or_thin_wrapper",
                }
            ).sum()
        )

        network_files = int(
            group["network_reference_count"]
            .fillna(0)
            .astype(int)
            .gt(0)
            .sum()
        )

        discovery_files = int(
            group[
                "product_discovery_reference_count"
            ]
            .fillna(0)
            .astype(int)
            .gt(0)
            .sum()
        )

        price_files = int(
            group["price_reference_count"]
            .fillna(0)
            .astype(int)
            .gt(0)
            .sum()
        )

        if files_present == 0:
            status = "not_implemented"
        elif network_files > 0:
            status = "operational_candidate"
        elif operational_files > 0:
            status = "local_or_support_only"
        else:
            status = "unverified"

        rows.append(
            {
                "source_name": source_name,
                "candidate_file_count": int(
                    len(group)
                ),
                "files_present": files_present,
                "operational_file_count": (
                    operational_files
                ),
                "network_capable_file_count": (
                    network_files
                ),
                "product_discovery_file_count": (
                    discovery_files
                ),
                "price_related_file_count": (
                    price_files
                ),
                "provisional_operational_status": (
                    status
                ),
                "expected_capabilities": (
                    group[
                        "expected_capabilities"
                    ].iloc[0]
                ),
            }
        )

    return pd.DataFrame(rows)


def main() -> int:
    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    source_frame = inspect_sources()
    source_summary_frame = summarize_sources(
        source_frame
    )
    registry_summary = inspect_product_registry()
    database_summary = inspect_database_products()

    source_detail_path = (
        OUTPUT_ROOT
        / "operational_source_file_audit.csv"
    )

    source_summary_path = (
        OUTPUT_ROOT
        / "operational_source_summary.csv"
    )

    registry_summary_path = (
        OUTPUT_ROOT
        / "product_registry_coverage.json"
    )

    database_summary_path = (
        OUTPUT_ROOT
        / "database_product_coverage.json"
    )

    certification_path = (
        OUTPUT_ROOT
        / "source_coverage_verification.json"
    )

    source_frame.to_csv(
        source_detail_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    source_summary_frame.to_csv(
        source_summary_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    registry_summary_path.write_text(
        json.dumps(
            registry_summary,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    database_summary_path.write_text(
        json.dumps(
            database_summary,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    operational_sources = sorted(
        source_summary_frame.loc[
            source_summary_frame[
                "provisional_operational_status"
            ].eq("operational_candidate"),
            "source_name",
        ].astype(str)
    )

    absent_sources = sorted(
        source_summary_frame.loc[
            source_summary_frame[
                "provisional_operational_status"
            ].eq("not_implemented"),
            "source_name",
        ].astype(str)
    )

    verification = {
        "generated_at": utc_now(),
        "verification_status": (
            "OPERATIONAL_SOURCE_REVIEW_COMPLETE"
        ),
        "operational_source_candidates": (
            operational_sources
        ),
        "not_implemented_sources": (
            absent_sources
        ),
        "registry_source_rows": (
            registry_summary["row_count"]
        ),
        "registry_approved_rows": (
            registry_summary["approved_count"]
        ),
        "database_product_rows": (
            database_summary["product_count"]
        ),
        "certification_status": (
            "NOT_CERTIFIED_EXTERNAL_COVERAGE_REQUIRED"
        ),
        "conclusions": [
            (
                "Code presence is evidence of implementation, "
                "not proof of current successful retrieval."
            ),
            (
                "The approved registry is not considered a "
                "complete external MTG product universe."
            ),
            (
                "External catalog reconciliation is required "
                "before investment eligibility certification."
            ),
            (
                "Secret Lair templates do not count as "
                "populated product coverage."
            ),
        ],
        "next_phase": (
            "10.5R.1B External Product Discovery"
        ),
    }

    certification_path.write_text(
        json.dumps(
            verification,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print("=" * 76)
    print(
        "Phase 10.5R.1A.2 Operational "
        "Source Verification"
    )
    print("=" * 76)

    print("Source status:")
    for row in source_summary_frame.sort_values(
        "source_name"
    ).itertuples(index=False):
        print(
            f"  {row.source_name}: "
            f"{row.provisional_operational_status}"
        )

    print()
    print(
        "Product-registry rows: "
        f"{registry_summary['row_count']}"
    )
    print(
        "Approved registry rows: "
        f"{registry_summary['approved_count']}"
    )
    print(
        "Database product rows: "
        f"{database_summary['product_count']}"
    )
    print()
    print(
        f"Source detail: {source_detail_path}"
    )
    print(
        f"Source summary: {source_summary_path}"
    )
    print(
        f"Registry coverage: "
        f"{registry_summary_path}"
    )
    print(
        f"Database coverage: "
        f"{database_summary_path}"
    )
    print(
        f"Verification: {certification_path}"
    )
    print()
    print(
        "PHASE 10.5R.1A.2 OPERATIONAL "
        "SOURCE VERIFICATION: PASS"
    )
    print(
        "Certification: NOT CERTIFIED — "
        "EXTERNAL COVERAGE REQUIRED"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())