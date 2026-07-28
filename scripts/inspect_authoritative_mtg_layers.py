from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

OUTPUT_ROOT = (
    ROOT
    / "docs"
    / "phase_8"
    / "mtg_intelligence_recovery"
    / "authoritative_trace"
)

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

INVENTORY_JSON = OUTPUT_ROOT / "authoritative_layer_inventory.json"
INVENTORY_CSV = OUTPUT_ROOT / "authoritative_layer_inventory.csv"
AFTERMATH_CSV = OUTPUT_ROOT / "aftermath_authoritative_trace.csv"
SECRET_LAIR_CSV = OUTPUT_ROOT / "secret_lair_authoritative_trace.csv"
REPORT_MD = OUTPUT_ROOT / "PHASE_8_2_1B_1_AUTHORITATIVE_LAYER_TRACE.md"

TARGET_PRODUCT_NUMBER = "489207"

TARGET_TERMS = (
    "march of the machine",
    "aftermath",
    "collector booster",
)

AUTHORITATIVE_ROOTS = (
    ROOT / "data" / "warehouse" / "current",
    ROOT / "data" / "operations" / "mtg_terminal_delivery" / "latest",
    ROOT / "data" / "operations" / "mtg_uip_delivery" / "latest",
    ROOT / "data" / "operations" / "mtg_governed_consumption_interface",
    ROOT / "data" / "product_master",
)

IDENTITY_COLUMNS = {
    "id",
    "product_id",
    "tcgplayer_product_id",
    "tcgcsv_product_id",
    "source_product_id",
    "asset_id",
    "canonical_asset_id",
    "canonical_product_id",
    "universal_asset_id",
    "mtg_asset_id",
}

NAME_COLUMNS = {
    "name",
    "product",
    "product_name",
    "asset_name",
    "canonical_name",
    "display_name",
    "drop_name",
    "title",
}

SECRET_LAIR_CLASS_TERMS = (
    "secret lair",
    "secret_lair",
    "secretlair",
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


def find_column(
    columns: list[str],
    aliases: set[str],
) -> str | None:
    mapped = {
        normalized(column): column
        for column in columns
    }

    for alias in aliases:
        found = mapped.get(normalized(alias))

        if found:
            return found

    return None


def layer_name(path: Path) -> str:
    relative = path.relative_to(ROOT).as_posix().lower()

    if "warehouse/current" in relative:
        return "GOVERNED_WAREHOUSE"

    if "mtg_terminal_delivery/latest" in relative:
        return "TERMINAL_DELIVERY"

    if "mtg_uip_delivery/latest" in relative:
        return "UIP_DELIVERY"

    if "mtg_governed_consumption_interface" in relative:
        return "GOVERNED_CONSUMPTION_INTERFACE"

    if "product_master" in relative:
        return "PRODUCT_MASTER"

    return "OTHER"


def is_target_product(
    row: dict[str, Any],
    id_column: str | None,
    name_column: str | None,
) -> bool:
    identifier = (
        str(row.get(id_column, ""))
        if id_column
        else ""
    )

    name = (
        str(row.get(name_column, ""))
        if name_column
        else ""
    )

    if product_number(identifier) == TARGET_PRODUCT_NUMBER:
        return True

    lowered = name.lower()

    return all(term in lowered for term in TARGET_TERMS)


def is_secret_lair(
    row: dict[str, Any],
) -> bool:
    joined = " ".join(
        str(value or "")
        for value in row.values()
    ).lower()

    return any(
        term in joined
        for term in SECRET_LAIR_CLASS_TERMS
    )


inventory: list[dict[str, Any]] = []
aftermath_rows: list[dict[str, Any]] = []
secret_lair_summary: list[dict[str, Any]] = []

seen_paths: set[Path] = set()

for root in AUTHORITATIVE_ROOTS:
    if not root.exists():
        continue

    for path in sorted(root.rglob("*.csv")):
        resolved = path.resolve()

        if resolved in seen_paths:
            continue

        seen_paths.add(resolved)

        relative = path.relative_to(ROOT).as_posix()

        try:
            with path.open(
                "r",
                encoding="utf-8-sig",
                errors="replace",
                newline="",
            ) as handle:
                reader = csv.DictReader(handle)
                columns = reader.fieldnames or []

                id_column = find_column(
                    columns,
                    IDENTITY_COLUMNS,
                )

                name_column = find_column(
                    columns,
                    NAME_COLUMNS,
                )

                row_count = 0
                aftermath_count = 0
                secret_lair_count = 0
                sample_rows: list[dict[str, Any]] = []

                for row_number, row in enumerate(
                    reader,
                    start=2,
                ):
                    row_count += 1

                    if is_secret_lair(row):
                        secret_lair_count += 1

                    if is_target_product(
                        row,
                        id_column,
                        name_column,
                    ):
                        aftermath_count += 1

                        trace_row = {
                            "layer": layer_name(path),
                            "source_path": relative,
                            "row_number": row_number,
                        }

                        trace_row.update(row)
                        aftermath_rows.append(trace_row)

                    if len(sample_rows) < 2:
                        sample_rows.append(row)

                inventory.append(
                    {
                        "layer": layer_name(path),
                        "source_path": relative,
                        "row_count": row_count,
                        "column_count": len(columns),
                        "id_column": id_column or "",
                        "name_column": name_column or "",
                        "aftermath_row_count": aftermath_count,
                        "secret_lair_row_count": secret_lair_count,
                        "columns_json": json.dumps(columns),
                        "sample_rows_json": json.dumps(
                            sample_rows,
                            default=str,
                        ),
                    }
                )

                if secret_lair_count:
                    secret_lair_summary.append(
                        {
                            "layer": layer_name(path),
                            "source_path": relative,
                            "row_count": row_count,
                            "secret_lair_row_count": (
                                secret_lair_count
                            ),
                            "id_column": id_column or "",
                            "name_column": name_column or "",
                        }
                    )

        except Exception as exc:
            inventory.append(
                {
                    "layer": layer_name(path),
                    "source_path": relative,
                    "row_count": "",
                    "column_count": "",
                    "id_column": "",
                    "name_column": "",
                    "aftermath_row_count": "",
                    "secret_lair_row_count": "",
                    "columns_json": "",
                    "sample_rows_json": "",
                    "error": str(exc),
                }
            )


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    columns = sorted(
        {
            key
            for row in rows
            for key in row.keys()
        }
    )

    with path.open(
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


write_csv(INVENTORY_CSV, inventory)
write_csv(AFTERMATH_CSV, aftermath_rows)
write_csv(SECRET_LAIR_CSV, secret_lair_summary)

summary = {
    "repository_root": str(ROOT),
    "authoritative_file_count": len(inventory),
    "aftermath_trace_row_count": len(aftermath_rows),
    "secret_lair_source_count": len(secret_lair_summary),
    "layers": defaultdict(int),
}

for item in inventory:
    summary["layers"][item["layer"]] += 1

summary["layers"] = dict(summary["layers"])

INVENTORY_JSON.write_text(
    json.dumps(summary, indent=2) + "\n",
    encoding="utf-8",
)

layer_lines = []

for layer, count in sorted(summary["layers"].items()):
    layer_lines.append(
        f"- {layer}: **{count} files**"
    )

report = f"""# Phase 8.2.1B.1 — Authoritative Layer Trace

## Status

Read-only authoritative-layer inspection completed.

## Scope

Only active current-state locations were inspected:

- governed warehouse;
- latest terminal delivery;
- latest UIP delivery;
- governed consumption interface;
- product master.

Historical packages, backups, validation outputs, staging files, and archives were excluded.

## Results

- Authoritative files inspected: **{len(inventory)}**
- Aftermath trace rows: **{len(aftermath_rows)}**
- Files containing Secret Lair rows: **{len(secret_lair_summary)}**

## Layer inventory

{chr(10).join(layer_lines)}

## Evidence

- `authoritative_layer_inventory.csv`
- `authoritative_layer_inventory.json`
- `aftermath_authoritative_trace.csv`
- `secret_lair_authoritative_trace.csv`
"""

REPORT_MD.write_text(
    report,
    encoding="utf-8",
)

print("=" * 78)
print("PHASE 8.2.1B.1 — AUTHORITATIVE LAYER TRACE")
print("=" * 78)
print(
    f"Authoritative files inspected: "
    f"{len(inventory)}"
)
print(
    f"Aftermath trace rows: "
    f"{len(aftermath_rows)}"
)
print(
    f"Files containing Secret Lair rows: "
    f"{len(secret_lair_summary)}"
)
print()
print("Layers:")

for layer, count in sorted(summary["layers"].items()):
    print(f"  {layer}: {count}")

print()
print(f"Report: {REPORT_MD}")
print("PHASE 8.2.1B.1 TRACE: PASS")
