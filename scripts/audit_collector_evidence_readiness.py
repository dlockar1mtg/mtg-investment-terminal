from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def configure_csv_field_limit() -> int:
    """
    Raise the CSV parser limit for repository audit files that may contain
    serialized evidence, embedded HTML, long descriptions, or source traces.
    """
    candidate_limit = 2_147_483_647

    while candidate_limit > 131_072:
        try:
            csv.field_size_limit(candidate_limit)
            return candidate_limit
        except OverflowError:
            candidate_limit //= 10

    csv.field_size_limit(131_072)
    return 131_072


CSV_FIELD_LIMIT = configure_csv_field_limit()


ROOT = Path(__file__).resolve().parents[1]

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "operations"
    / "collector_evidence_readiness"
    / "candidate_v1_0_0"
)

REGISTRY_PATH = (
    ROOT
    / "data"
    / "product_master"
    / "investment_products.csv"
)

MODEL_PATH = (
    ROOT
    / "data"
    / "product_master"
    / "product_master_model_input.csv"
)

ROUTER_PATH = (
    ROOT
    / "data"
    / "operations"
    / "collector_forecast_method_routing"
    / "candidate_v1_0_0"
    / "collector_forecast_method_routes.csv"
)

HISTORY_PATH = (
    ROOT
    / "data"
    / "operations"
    / "collector_booster_history_certification"
    / "candidate_v1_0_0"
    / "collector_history_product_certification.csv"
)

SEARCH_ROOTS = [
    ROOT / "data",
    ROOT / "models",
    ROOT / "scripts",
    ROOT / "terminal2",
    ROOT / "config",
]

EXCLUDED_PARTS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "archive",
    "artifacts",
    ".venv",
    "venv",
}

SIGNAL_GROUPS = {
    "SUPPLY": [
        "supply",
        "print_run",
        "print_structure",
        "print_to_demand",
        "limited_print",
        "availability",
        "available",
        "listing_count",
        "listings",
        "stock",
        "stockout",
        "restock",
        "sealed_supply",
        "distribution",
        "scarcity",
        "inventory",
    ],
    "DEMAND": [
        "demand",
        "sales_velocity",
        "sales_count",
        "transaction_count",
        "transactions",
        "sold_count",
        "volume",
        "absorption",
        "franchise_strength",
        "gameplay_demand",
        "chase_card",
        "premium_contents",
        "expected_value",
        "search_interest",
        "attention",
        "popularity",
    ],
    "LIQUIDITY": [
        "liquidity",
        "days_to_sell",
        "sell_through",
        "spread",
        "bid_ask",
        "turnover",
        "market_depth",
        "listing_velocity",
        "transaction_frequency",
    ],
    "COMPARABLE": [
        "comparable",
        "similarity",
        "peer_group",
        "cohort",
        "release_era",
        "lifecycle",
        "price_band",
        "configuration",
        "product_type",
        "franchise",
        "premium",
        "reprint_exposure",
    ],
    "PRICE": [
        "current_price",
        "market_price",
        "latest_price",
        "price_date",
        "price_change",
        "return",
        "volatility",
        "drawdown",
        "cagr",
    ],
}

SUPPORTED_TEXT_SUFFIXES = {
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".md",
    ".txt",
}

SUPPORTED_TABLE_SUFFIXES = {
    ".csv",
}


def clean(value: object) -> str:
    return str(value or "").strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fields: list[str],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )
        writer.writeheader()
        writer.writerows(rows)


def classify_name(name: str) -> list[str]:
    normalized = name.lower()
    groups: list[str] = []

    for group, tokens in SIGNAL_GROUPS.items():
        if any(token in normalized for token in tokens):
            groups.append(group)

    return groups


def infer_value_type(values: list[str]) -> str:
    nonblank = [
        clean(value)
        for value in values
        if clean(value)
    ]

    if not nonblank:
        return "EMPTY"

    lowered = {
        value.lower()
        for value in nonblank
    }

    if lowered.issubset(
        {"true", "false", "yes", "no", "0", "1"}
    ):
        return "BOOLEAN_LIKE"

    numeric_count = 0

    for value in nonblank:
        try:
            float(value.replace(",", ""))
            numeric_count += 1
        except ValueError:
            pass

    if numeric_count == len(nonblank):
        return "NUMERIC"

    if numeric_count / len(nonblank) >= 0.8:
        return "MOSTLY_NUMERIC"

    return "TEXT_OR_CATEGORY"


def inspect_csv(path: Path) -> list[dict[str, Any]]:
    rows = read_csv(path)

    if not rows:
        return []

    fields = list(rows[0].keys())
    results: list[dict[str, Any]] = []

    for field in fields:
        groups = classify_name(field)

        if not groups:
            continue

        values = [
            clean(row.get(field))
            for row in rows
        ]

        nonblank = [
            value
            for value in values
            if value
        ]

        unique_values = list(
            dict.fromkeys(nonblank)
        )

        results.append({
            "source_path": (
                path.relative_to(ROOT).as_posix()
            ),
            "source_type": "CSV_COLUMN",
            "signal_groups": "|".join(groups),
            "field_or_term": field,
            "row_count": len(rows),
            "nonblank_count": len(nonblank),
            "population_rate": (
                round(
                    len(nonblank) / len(rows),
                    6,
                )
                if rows
                else 0
            ),
            "unique_nonblank_count": len(
                set(nonblank)
            ),
            "inferred_value_type": infer_value_type(
                values
            ),
            "sample_values": "|".join(
                unique_values[:5]
            ),
        })

    return results


def inspect_text(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(
            encoding="utf-8-sig",
            errors="ignore",
        )
    except OSError:
        return []

    lowered = text.lower()
    results: list[dict[str, Any]] = []

    for group, tokens in SIGNAL_GROUPS.items():
        matched_tokens = [
            token
            for token in tokens
            if token in lowered
        ]

        if not matched_tokens:
            continue

        results.append({
            "source_path": (
                path.relative_to(ROOT).as_posix()
            ),
            "source_type": "TEXT_REFERENCE",
            "signal_groups": group,
            "field_or_term": "|".join(
                sorted(set(matched_tokens))
            ),
            "row_count": "",
            "nonblank_count": "",
            "population_rate": "",
            "unique_nonblank_count": "",
            "inferred_value_type": "",
            "sample_values": "",
        })

    return results


def iter_candidate_files() -> list[Path]:
    files: list[Path] = []

    for root in SEARCH_ROOTS:
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if not path.is_file():
                continue

            relative = path.relative_to(ROOT)

            if any(
                part in EXCLUDED_PARTS
                for part in relative.parts
            ):
                continue

            if (
                path.suffix.lower()
                in SUPPORTED_TEXT_SUFFIXES
                or path.suffix.lower()
                in SUPPORTED_TABLE_SUFFIXES
            ):
                files.append(path)

    return sorted(set(files))


def key_field_profile(
    path: Path,
    label: str,
) -> list[dict[str, Any]]:
    rows = read_csv(path)

    if not rows:
        return []

    results: list[dict[str, Any]] = []

    for field in rows[0].keys():
        groups = classify_name(field)

        if not groups:
            continue

        values = [
            clean(row.get(field))
            for row in rows
        ]

        nonblank = [
            value
            for value in values
            if value
        ]

        results.append({
            "dataset": label,
            "dataset_path": (
                path.relative_to(ROOT).as_posix()
            ),
            "field": field,
            "signal_groups": "|".join(groups),
            "row_count": len(rows),
            "nonblank_count": len(nonblank),
            "population_rate": round(
                len(nonblank) / len(rows),
                6,
            ),
            "inferred_value_type": infer_value_type(
                values
            ),
            "sample_values": "|".join(
                list(
                    dict.fromkeys(nonblank)
                )[:5]
            ),
        })

    return results


def main() -> None:
    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    inventory_rows: list[dict[str, Any]] = []

    for path in iter_candidate_files():
        if path.suffix.lower() == ".csv":
            inventory_rows.extend(
                inspect_csv(path)
            )
        else:
            inventory_rows.extend(
                inspect_text(path)
            )

    inventory_fields = [
        "source_path",
        "source_type",
        "signal_groups",
        "field_or_term",
        "row_count",
        "nonblank_count",
        "population_rate",
        "unique_nonblank_count",
        "inferred_value_type",
        "sample_values",
    ]

    write_csv(
        OUTPUT_ROOT
        / "collector_evidence_repository_inventory.csv",
        inventory_rows,
        inventory_fields,
    )

    core_profiles: list[dict[str, Any]] = []

    for path, label in [
        (REGISTRY_PATH, "REGISTRY"),
        (MODEL_PATH, "MODEL_INPUT"),
        (ROUTER_PATH, "METHOD_ROUTER"),
        (HISTORY_PATH, "HISTORY_CERTIFICATION"),
    ]:
        core_profiles.extend(
            key_field_profile(
                path,
                label,
            )
        )

    write_csv(
        OUTPUT_ROOT
        / "collector_core_evidence_field_profile.csv",
        core_profiles,
        [
            "dataset",
            "dataset_path",
            "field",
            "signal_groups",
            "row_count",
            "nonblank_count",
            "population_rate",
            "inferred_value_type",
            "sample_values",
        ],
    )

    group_counts = Counter()

    csv_field_counts = Counter()

    for row in inventory_rows:
        for group in clean(
            row["signal_groups"]
        ).split("|"):
            if group:
                group_counts[group] += 1

                if row["source_type"] == "CSV_COLUMN":
                    csv_field_counts[group] += 1

    core_group_counts = Counter()

    for row in core_profiles:
        for group in clean(
            row["signal_groups"]
        ).split("|"):
            if group:
                core_group_counts[group] += 1

    required_groups = [
        "SUPPLY",
        "DEMAND",
        "LIQUIDITY",
        "COMPARABLE",
        "PRICE",
    ]

    readiness_rows = []

    for group in required_groups:
        core_fields = [
            row
            for row in core_profiles
            if group in clean(
                row["signal_groups"]
            ).split("|")
        ]

        populated_core_fields = [
            row
            for row in core_fields
            if float(
                row["population_rate"]
            ) > 0
        ]

        if populated_core_fields:
            status = "PARTIAL_CORE_EVIDENCE"
        elif csv_field_counts[group] > 0:
            status = "FOUND_OUTSIDE_CORE"
        elif group_counts[group] > 0:
            status = "REFERENCED_IN_CODE_OR_DOCS_ONLY"
        else:
            status = "NOT_FOUND"

        readiness_rows.append({
            "signal_group": group,
            "readiness_status": status,
            "repository_references": (
                group_counts[group]
            ),
            "csv_fields_found": (
                csv_field_counts[group]
            ),
            "core_fields_found": len(
                core_fields
            ),
            "populated_core_fields": len(
                populated_core_fields
            ),
            "certified_for_forecasting": "false",
            "required_next_action": (
                "Review inventory and establish "
                "governed contract."
            ),
        })

    write_csv(
        OUTPUT_ROOT
        / "collector_evidence_readiness_summary.csv",
        readiness_rows,
        [
            "signal_group",
            "readiness_status",
            "repository_references",
            "csv_fields_found",
            "core_fields_found",
            "populated_core_fields",
            "certified_for_forecasting",
            "required_next_action",
        ],
    )

    router_rows = read_csv(ROUTER_PATH)

    comparable_ids = {
        clean(row.get("investment_product_id"))
        for row in router_rows
        if clean(
            row.get("forecast_method")
        )
        == "COMPARABLE_PRODUCT_ADJUSTED"
    }

    core_ids = {
        clean(row.get("investment_product_id"))
        for row in read_csv(MODEL_PATH)
    }

    missing_model_ids = sorted(
        comparable_ids - core_ids
    )

    manifest = {
        "status": "AUDIT_COMPLETE",
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "csv_field_size_limit": CSV_FIELD_LIMIT,
        "collector_router_product_count": len(
            router_rows
        ),
        "comparable_required_product_count": len(
            comparable_ids
        ),
        "comparable_products_missing_from_model": (
            missing_model_ids
        ),
        "signal_group_summary": {
            row["signal_group"]: {
                "readiness_status": (
                    row["readiness_status"]
                ),
                "repository_references": (
                    row["repository_references"]
                ),
                "csv_fields_found": (
                    row["csv_fields_found"]
                ),
                "core_fields_found": (
                    row["core_fields_found"]
                ),
                "populated_core_fields": (
                    row["populated_core_fields"]
                ),
                "certified_for_forecasting": False,
            }
            for row in readiness_rows
        },
        "certification_status": {
            "supply_evidence_contract": (
                "NOT_CERTIFIED"
            ),
            "demand_evidence_contract": (
                "NOT_CERTIFIED"
            ),
            "liquidity_evidence_contract": (
                "NOT_CERTIFIED"
            ),
            "comparable_evidence_readiness": (
                "NOT_CERTIFIED"
            ),
            "comparable_selection": (
                "NOT_IMPLEMENTED"
            ),
            "comparable_projections": (
                "NOT_AUTHORIZED"
            ),
            "purchase_authorization": False,
        },
        "outputs": {
            "repository_inventory": str(
                (
                    OUTPUT_ROOT
                    / "collector_evidence_repository_inventory.csv"
                ).resolve()
            ),
            "core_field_profile": str(
                (
                    OUTPUT_ROOT
                    / "collector_core_evidence_field_profile.csv"
                ).resolve()
            ),
            "readiness_summary": str(
                (
                    OUTPUT_ROOT
                    / "collector_evidence_readiness_summary.csv"
                ).resolve()
            ),
        },
    }

    (
        OUTPUT_ROOT
        / "collector_evidence_readiness_manifest.json"
    ).write_text(
        json.dumps(
            manifest,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "COLLECTOR EVIDENCE READINESS AUDIT COMPLETE"
    )
    print(
        f"Repository evidence references: "
        f"{len(inventory_rows)}"
    )
    print(
        f"Core evidence fields: "
        f"{len(core_profiles)}"
    )
    print(
        f"Comparable-required products: "
        f"{len(comparable_ids)}"
    )

    for row in readiness_rows:
        print(
            f"{row['signal_group']}: "
            f"{row['readiness_status']}"
        )


if __name__ == "__main__":
    main()