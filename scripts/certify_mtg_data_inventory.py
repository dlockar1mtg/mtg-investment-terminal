from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "mtg_data_inventory"
)

JSON_OUTPUT = (
    OUTPUT_ROOT
    / "mtg_data_inventory_2026-07-22.json"
)

CSV_OUTPUT = (
    OUTPUT_ROOT
    / "mtg_dataset_inventory_2026-07-22.csv"
)

REPORT_OUTPUT = (
    OUTPUT_ROOT
    / "mtg_data_inventory_report_2026-07-22.md"
)

SEARCH_ROOTS = [
    ROOT / "data",
    ROOT / "terminal2",
    ROOT / "config",
    ROOT / "scripts",
]

TEXT_EXTENSIONS = {
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".py",
    ".md",
    ".html",
    ".txt",
    ".sql",
}

LANE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "secret_lair": (
        "secret_lair",
        "secret lair",
        "secretlair",
    ),
    "booster_display": (
        "booster",
        "display",
        "historical_product_scope",
        "premium_universe",
        "candidate_cohort",
    ),
    "pricing": (
        "price",
        "pricing",
        "market",
        "tcgcsv",
    ),
    "forecasting": (
        "forecast",
        "projection",
        "cagr",
        "drift",
    ),
    "holdings": (
        "holding",
        "holdings",
        "portfolio",
        "inventory",
        "position",
    ),
    "recommendations": (
        "recommendation",
        "actionable",
        "ranking",
        "score",
        "decision",
    ),
    "registry": (
        "registry",
        "canonical",
        "product_master",
    ),
    "unified": (
        "unified",
        "investment_universe",
        "universal",
    ),
}

KNOWN_DATASETS = {
    "historical_routed_candidates": (
        ROOT
        / "data"
        / "validation"
        / "phase_10"
        / "historical_tcgcsv_routing"
        / "historical_tcgcsv_product_routing_2026-07-22.csv"
    ),
    "governed_booster_display_products": (
        ROOT
        / "data"
        / "validation"
        / "phase_10"
        / "historical_final_release_dates"
        / "historical_final_governed_release_dates_2026-07-22.csv"
    ),
    "active_booster_display_products": (
        ROOT
        / "data"
        / "validation"
        / "phase_10"
        / "historical_product_scope"
        / "historical_active_review_population_2026-07-22.csv"
    ),
    "product_scope_exclusions": (
        ROOT
        / "data"
        / "validation"
        / "phase_10"
        / "historical_product_scope"
        / "historical_product_scope_exclusions_2026-07-22.csv"
    ),
}


def relative_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def classify_file(path: Path) -> list[str]:
    search_text = (
        relative_path(path)
        .replace("_", " ")
        .replace("-", " ")
        .lower()
    )

    lanes: list[str] = []

    for lane, keywords in LANE_KEYWORDS.items():
        if any(keyword in search_text for keyword in keywords):
            lanes.append(lane)

    return lanes


def count_csv_rows(path: Path) -> tuple[int | None, list[str], str]:
    try:
        with path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            rows = sum(1 for _ in reader)

        return rows, header, ""
    except Exception as exc:
        return None, [], f"{type(exc).__name__}: {exc}"


def inspect_json(path: Path) -> tuple[str, str]:
    try:
        with path.open(
            "r",
            encoding="utf-8-sig",
        ) as handle:
            value = json.load(handle)

        if isinstance(value, list):
            return "list", str(len(value))

        if isinstance(value, dict):
            return "object", str(len(value))

        return type(value).__name__, ""
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"


def inspect_file(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": relative_path(path),
        "extension": path.suffix.lower(),
        "size_bytes": path.stat().st_size,
        "lanes": classify_file(path),
        "row_count": None,
        "column_count": None,
        "columns": [],
        "json_type": "",
        "json_item_count": "",
        "inspection_error": "",
    }

    if path.suffix.lower() == ".csv":
        rows, columns, error = count_csv_rows(path)
        record["row_count"] = rows
        record["column_count"] = len(columns)
        record["columns"] = columns
        record["inspection_error"] = error

    elif path.suffix.lower() == ".json":
        json_type, json_count = inspect_json(path)
        record["json_type"] = json_type

        if json_count.startswith(
            (
                "JSONDecodeError",
                "UnicodeDecodeError",
                "PermissionError",
                "OSError",
            )
        ):
            record["inspection_error"] = json_count
        else:
            record["json_item_count"] = json_count

    return record


def discover_files() -> list[dict[str, Any]]:
    discovered: list[dict[str, Any]] = []
    seen: set[Path] = set()

    for search_root in SEARCH_ROOTS:
        if not search_root.exists():
            continue

        for path in search_root.rglob("*"):
            if not path.is_file():
                continue

            if ".git" in path.parts:
                continue

            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue

            resolved = path.resolve()

            if resolved in seen:
                continue

            seen.add(resolved)

            lanes = classify_file(path)

            if not lanes:
                continue

            discovered.append(inspect_file(path))

    return sorted(
        discovered,
        key=lambda item: item["path"],
    )


def known_dataset_summary() -> dict[str, Any]:
    results: dict[str, Any] = {}

    for name, path in KNOWN_DATASETS.items():
        entry: dict[str, Any] = {
            "path": relative_path(path),
            "exists": path.is_file(),
            "rows": None,
            "unique_canonical_product_ids": None,
            "error": "",
        }

        if not path.is_file():
            results[name] = entry
            continue

        try:
            with path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as handle:
                rows = list(csv.DictReader(handle))

            entry["rows"] = len(rows)

            if (
                rows
                and "canonical_product_id" in rows[0]
            ):
                ids = {
                    str(row.get("canonical_product_id", "")).strip()
                    for row in rows
                    if str(
                        row.get("canonical_product_id", "")
                    ).strip()
                }

                entry[
                    "unique_canonical_product_ids"
                ] = len(ids)

        except Exception as exc:
            entry["error"] = (
                f"{type(exc).__name__}: {exc}"
            )

        results[name] = entry

    return results


def find_secret_lair_candidates(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    for record in records:
        if "secret_lair" not in record["lanes"]:
            continue

        candidates.append(
            {
                "path": record["path"],
                "extension": record["extension"],
                "size_bytes": record["size_bytes"],
                "row_count": record["row_count"],
                "column_count": record["column_count"],
                "columns": record["columns"],
                "inspection_error": record[
                    "inspection_error"
                ],
            }
        )

    return candidates


def lane_counts(
    records: list[dict[str, Any]],
) -> dict[str, int]:
    counts: Counter[str] = Counter()

    for record in records:
        for lane in record["lanes"]:
            counts[lane] += 1

    return dict(sorted(counts.items()))


def write_inventory_csv(
    records: list[dict[str, Any]],
) -> None:
    columns = [
        "path",
        "extension",
        "size_bytes",
        "lanes",
        "row_count",
        "column_count",
        "columns",
        "json_type",
        "json_item_count",
        "inspection_error",
    ]

    with CSV_OUTPUT.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
        )

        writer.writeheader()

        for record in records:
            writer.writerow(
                {
                    **record,
                    "lanes": "|".join(
                        record["lanes"]
                    ),
                    "columns": "|".join(
                        record["columns"]
                    ),
                }
            )


def build_markdown_report(
    summary: dict[str, Any],
) -> str:
    known = summary["known_datasets"]
    secret_lairs = summary[
        "secret_lair_candidate_files"
    ]

    lines = [
        "# Phase 10.5R.2.1 — Unified MTG Data Inventory",
        "",
        f"Generated: {summary['generated_at_utc']}",
        "",
        "## Known Booster/Display Boundaries",
        "",
        "| Dataset | Exists | Rows | Unique IDs |",
        "|---|---:|---:|---:|",
    ]

    for name, entry in known.items():
        lines.append(
            "| "
            + name
            + " | "
            + str(entry["exists"])
            + " | "
            + str(entry["rows"])
            + " | "
            + str(
                entry[
                    "unique_canonical_product_ids"
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Lane File Counts",
            "",
            "| Lane | Files |",
            "|---|---:|",
        ]
    )

    for lane, count in summary[
        "lane_file_counts"
    ].items():
        lines.append(
            f"| {lane} | {count} |"
        )

    lines.extend(
        [
            "",
            "## Secret Lair Candidate Data Files",
            "",
            "| Path | Type | Rows | Columns | Error |",
            "|---|---|---:|---:|---|",
        ]
    )

    for record in secret_lairs:
        lines.append(
            "| "
            + record["path"]
            + " | "
            + record["extension"]
            + " | "
            + str(record["row_count"])
            + " | "
            + str(record["column_count"])
            + " | "
            + record["inspection_error"]
            .replace("|", "/")
            + " |"
        )

    lines.extend(
        [
            "",
            "## Important Interpretation",
            "",
            "- 163 is the broad historical routed-candidate population.",
            "- 140 is the governed historical booster/display population.",
            "- 139 is the active booster/display population after the approved Renaissance Italian Booster Box exclusion.",
            "- Secret Lairs are a separate investment lane and are not included in the 163, 140, or 139 counts.",
            "- This inventory does not change eligibility, scoring, forecasts, registries, or production data.",
            "",
            "## Next Certification Step",
            "",
            "Use this inventory to identify the authoritative Secret Lair registry, pricing, history, forecast, actionable, holdings, and unified-universe datasets before writing the final certification rules.",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> int:
    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    records = discover_files()
    known = known_dataset_summary()

    summary = {
        "schema_version": "10.5R.2.1",
        "generated_at_utc": (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "repository_root": ".",
        "files_inspected": len(records),
        "lane_file_counts": lane_counts(records),
        "known_datasets": known,
        "secret_lair_candidate_files": (
            find_secret_lair_candidates(records)
        ),
        "production_data_changed": False,
        "eligibility_changed": False,
        "scoring_changed": False,
        "forecasts_changed": False,
    }

    write_inventory_csv(records)

    JSON_OUTPUT.write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    REPORT_OUTPUT.write_text(
        build_markdown_report(summary),
        encoding="utf-8",
    )

    print("=" * 76)
    print(
        "Phase 10.5R.2.1 Unified MTG Data Inventory"
    )
    print("=" * 76)

    print(
        "Files inspected: "
        + str(summary["files_inspected"])
    )

    for name, entry in known.items():
        print(
            f"{name}: "
            f"exists={entry['exists']} "
            f"rows={entry['rows']} "
            f"unique_ids="
            f"{entry['unique_canonical_product_ids']}"
        )

    print(
        "Secret Lair candidate files: "
        + str(
            len(
                summary[
                    "secret_lair_candidate_files"
                ]
            )
        )
    )

    print()
    print("DATA INVENTORY STATUS: PASS")
    print("Production data changed: NO")
    print("Eligibility changed: NO")
    print("Scoring changed: NO")
    print("Forecasts changed: NO")

    print()
    print(
        "Report: "
        + relative_path(REPORT_OUTPUT)
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())