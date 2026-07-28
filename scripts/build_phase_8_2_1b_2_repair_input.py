from __future__ import annotations

import csv
import json
import re
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "operations"
    / "phase_8_2_1b_2_repair_input"
)

SOURCE_ROOT = OUTPUT_ROOT / "source"
EVIDENCE_ROOT = OUTPUT_ROOT / "evidence"

TARGET_PRODUCT_NUMBER = "489207"

TARGET_SOURCE_FILES = [
    "terminal2/market_sources/collector_box_evaluation.py",
    "scripts/build_unified_mtg_intelligence.py",
    "scripts/build_phase_10_10_universal_export.py",
    "scripts/build_mtg_hosted_uip_delivery.py",
    "scripts/apply_mtg_live_uip_overlay.py",
]

TARGET_TEST_PATTERNS = [
    "*collector*evaluation*.py",
    "*unified*mtg*intelligence*.py",
    "*universal*export*.py",
    "*hosted*uip*delivery*.py",
    "*uip*handoff*.py",
    "*forecast*.py",
]

AUTHORITATIVE_FILES = [
    "data/product_master/product_master_model_input.csv",
    "data/warehouse/current/governed_terminal/dashboard.csv",
    "data/warehouse/current/governed_terminal/forecasts.csv",
    "data/warehouse/current/governed_terminal/market_provenance.csv",
    "data/warehouse/current/governed_terminal/rankings.csv",
    "data/warehouse/current/governed_terminal/recommendations.csv",
    "data/warehouse/current/governed_terminal/universal_mtg_consumption_interface.csv",
    "data/operations/mtg_terminal_delivery/latest/dashboard.csv",
    "data/operations/mtg_terminal_delivery/latest/forecasts.csv",
    "data/operations/mtg_terminal_delivery/latest/market_provenance.csv",
    "data/operations/mtg_terminal_delivery/latest/recommendations.csv",
    "data/operations/mtg_terminal_delivery/latest/universal_mtg_consumption_interface.csv",
    "data/operations/mtg_uip_delivery/latest/asset_master.csv",
    "data/operations/mtg_uip_delivery/latest/forecasts.csv",
    "data/operations/mtg_uip_delivery/latest/recommendations.csv",
    "data/operations/mtg_uip_delivery/latest/risk_metrics.csv",
]

KEY_TERMS = (
    "current_market_value_usd",
    "selected_reference_price",
    "reference_price",
    "native_forecast",
    "one_year",
    "three_year",
    "five_year",
    "forecast_horizon",
    "expected_return",
    "forecast_cagr",
    "TIER_GUARDED_SCENARIO_BANDS",
    "collector_evaluation",
)


def normalized(value: Any) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "_",
        str(value or "").strip().lower(),
    ).strip("_")


def product_number(value: Any) -> str:
    match = re.search(
        r"(\d{4,})$",
        str(value or "").strip(),
    )

    return match.group(1) if match else ""


def row_matches_product(row: dict[str, Any]) -> bool:
    for key, value in row.items():
        key_norm = normalized(key)

        if (
            "id" in key_norm
            or "product" in key_norm
            or "asset" in key_norm
        ):
            if product_number(value) == TARGET_PRODUCT_NUMBER:
                return True

    joined = " ".join(
        str(value or "")
        for value in row.values()
    ).lower()

    return (
        "march of the machine" in joined
        and "aftermath" in joined
        and "collector booster" in joined
    )


def is_secret_lair(row: dict[str, Any]) -> bool:
    joined = " ".join(
        str(value or "")
        for value in row.values()
    ).lower()

    return (
        "secret lair" in joined
        or "secret_lair" in joined
        or "secretlair" in joined
    )


def copy_source(relative: str) -> dict[str, Any]:
    source = ROOT / relative
    destination = SOURCE_ROOT / relative

    if not source.is_file():
        return {
            "path": relative,
            "status": "MISSING",
            "size_bytes": None,
        }

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(source, destination)

    return {
        "path": relative,
        "status": "COPIED",
        "size_bytes": source.stat().st_size,
    }


def write_rows(
    destination: Path,
    rows: list[dict[str, Any]],
) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not rows:
        destination.write_text(
            "",
            encoding="utf-8",
        )
        return

    columns = []

    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)

    with destination.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)


def extract_authoritative_rows(
    relative: str,
) -> dict[str, Any]:
    source = ROOT / relative

    result = {
        "path": relative,
        "status": "MISSING",
        "row_count": 0,
        "column_count": 0,
        "aftermath_rows": 0,
        "secret_lair_rows": 0,
    }

    if not source.is_file():
        return result

    aftermath_rows: list[dict[str, Any]] = []
    secret_lair_rows: list[dict[str, Any]] = []

    with source.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []

        row_count = 0

        for row_number, row in enumerate(
            reader,
            start=2,
        ):
            row_count += 1

            if row_matches_product(row):
                aftermath_rows.append(
                    {
                        "_source_path": relative,
                        "_row_number": row_number,
                        **row,
                    }
                )

            if (
                is_secret_lair(row)
                and len(secret_lair_rows) < 20
            ):
                secret_lair_rows.append(
                    {
                        "_source_path": relative,
                        "_row_number": row_number,
                        **row,
                    }
                )

    safe_name = relative.replace("/", "__")

    write_rows(
        EVIDENCE_ROOT
        / "aftermath"
        / safe_name,
        aftermath_rows,
    )

    write_rows(
        EVIDENCE_ROOT
        / "secret_lair_samples"
        / safe_name,
        secret_lair_rows,
    )

    result.update(
        {
            "status": "EXTRACTED",
            "row_count": row_count,
            "column_count": len(columns),
            "columns": columns,
            "aftermath_rows": len(aftermath_rows),
            "secret_lair_rows": len(secret_lair_rows),
        }
    )

    return result


def build_code_reference(
    relative: str,
) -> dict[str, Any]:
    path = ROOT / relative

    result = {
        "path": relative,
        "status": "MISSING",
        "matches": [],
    }

    if not path.is_file():
        return result

    lines = path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()

    matches = []

    for line_number, line in enumerate(
        lines,
        start=1,
    ):
        if any(term in line for term in KEY_TERMS):
            start = max(1, line_number - 8)
            end = min(len(lines), line_number + 12)

            excerpt = "\n".join(
                f"{index:05d}: {lines[index - 1]}"
                for index in range(start, end + 1)
            )

            matches.append(
                {
                    "term_line": line_number,
                    "excerpt_start": start,
                    "excerpt_end": end,
                    "excerpt": excerpt,
                }
            )

    result.update(
        {
            "status": "INSPECTED",
            "line_count": len(lines),
            "matches": matches,
        }
    )

    return result


if OUTPUT_ROOT.exists():
    shutil.rmtree(OUTPUT_ROOT)

SOURCE_ROOT.mkdir(
    parents=True,
    exist_ok=True,
)

EVIDENCE_ROOT.mkdir(
    parents=True,
    exist_ok=True,
)

copied_sources = [
    copy_source(relative)
    for relative in TARGET_SOURCE_FILES
]

copied_tests = []

tests_root = ROOT / "tests"

if tests_root.exists():
    seen: set[Path] = set()

    for pattern in TARGET_TEST_PATTERNS:
        for path in tests_root.rglob(pattern):
            if (
                path.is_file()
                and path not in seen
            ):
                seen.add(path)

                relative = path.relative_to(ROOT).as_posix()
                copied_tests.append(
                    copy_source(relative)
                )

authoritative_results = [
    extract_authoritative_rows(relative)
    for relative in AUTHORITATIVE_FILES
]

code_references = [
    build_code_reference(relative)
    for relative in TARGET_SOURCE_FILES
]

reference_path = (
    EVIDENCE_ROOT
    / "code_field_reference.json"
)

reference_path.write_text(
    json.dumps(
        code_references,
        indent=2,
        default=str,
    )
    + "\n",
    encoding="utf-8",
)

summary = {
    "repository_root": str(ROOT),
    "target_product_number": TARGET_PRODUCT_NUMBER,
    "source_files": copied_sources,
    "test_files": copied_tests,
    "authoritative_files": authoritative_results,
    "code_field_reference": (
        reference_path.relative_to(ROOT).as_posix()
    ),
}

summary_path = OUTPUT_ROOT / "repair_input_summary.json"

summary_path.write_text(
    json.dumps(
        summary,
        indent=2,
        default=str,
    )
    + "\n",
    encoding="utf-8",
)

report_lines = [
    "# Phase 8.2.1B.2 — Repair Input Package",
    "",
    "## Purpose",
    "",
    "Provide the exact active producer, handoff, tests, and authoritative rows",
    "needed to repair MTG forecast semantics without refreshing production data.",
    "",
    "## Source files",
    "",
]

for item in copied_sources:
    report_lines.append(
        f"- `{item['path']}`: **{item['status']}**"
    )

report_lines.extend(
    [
        "",
        "## Existing tests",
        "",
    ]
)

for item in copied_tests:
    report_lines.append(
        f"- `{item['path']}`: **{item['status']}**"
    )

report_lines.extend(
    [
        "",
        "## Authoritative evidence",
        "",
        "| File | Status | Rows | Aftermath | Secret Lair sample |",
        "|---|---|---:|---:|---:|",
    ]
)

for item in authoritative_results:
    report_lines.append(
        "| "
        + " | ".join(
            [
                f"`{item['path']}`",
                str(item["status"]),
                str(item.get("row_count", 0)),
                str(item.get("aftermath_rows", 0)),
                str(item.get("secret_lair_rows", 0)),
            ]
        )
        + " |"
    )

report_path = (
    OUTPUT_ROOT
    / "PHASE_8_2_1B_2_REPAIR_INPUT.md"
)

report_path.write_text(
    "\n".join(report_lines) + "\n",
    encoding="utf-8",
)

print("=" * 78)
print("PHASE 8.2.1B.2 — REPAIR INPUT PACKAGE")
print("=" * 78)
print()
print("Core source files:")

for item in copied_sources:
    print(
        f"  {item['status']:<8} "
        f"{item['path']}"
    )

print()
print(
    f"Existing tests copied: "
    f"{sum(item['status'] == 'COPIED' for item in copied_tests)}"
)
print()
print("Authoritative evidence:")

for item in authoritative_results:
    print(
        f"  {item['status']:<9} "
        f"Aftermath={item.get('aftermath_rows', 0):>2} "
        f"SecretLairSample={item.get('secret_lair_rows', 0):>2} "
        f"{item['path']}"
    )

print()
print(f"Output: {OUTPUT_ROOT}")
print("PHASE 8.2.1B.2 REPAIR INPUT: PASS")
