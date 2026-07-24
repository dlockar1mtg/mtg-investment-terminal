from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

RELEASE_QUEUE_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_release_timing"
    / "historical_external_release_timing_queue_2026-07-22.csv"
)

CACHED_DATE_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_release_timing"
    / "historical_cached_release_dates_available_2026-07-22.csv"
)

DATA_ROOT = ROOT / "data"

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_release_source_discovery"
)

SCHEMA_VERSION = "10.5R.1D.2.4B.1"

SEARCH_SUFFIXES = {
    ".csv",
    ".json",
}

EXCLUDED_DISCOVERY_ROOTS = (
    OUTPUT_ROOT,
    ROOT
    / "data"
    / "raw"
    / "mtgjson",
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_mtgjson_set_routing",
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_mtgjson_set_aliases",
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_mtgjson_set_alias_resolution",
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_mtgjson_sealed_products",
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_release_adjudication",
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_product_scope",
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_set_date_fallback",
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_release_date_governance",
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_final_release_dates",
)

RELEASE_FIELD_NAMES = {
    "releaseDate",
    "release_date",
    "released_at",
    "releasedOn",
    "released_on",
    "first_available_date",
}

IDENTITY_FIELD_NAMES = {
    "name",
    "setName",
    "set_name",
    "productName",
    "product_name",
    "canonical_product_name",
    "tcgplayerProductId",
    "tcgplayer_product_id",
}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def clean_text(value: object) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip()


def normalized_name(value: object) -> str:
    text = clean_text(value).casefold()

    replacements = {
        " - draft booster box": "",
        " - draft booster display": "",
        " - booster box": "",
        " - booster display": "",
        " draft booster box": "",
        " draft booster display": "",
        " booster box": "",
        " booster display": "",
    }

    for old, new in replacements.items():
        if text.endswith(old):
            text = text[: -len(old)] + new

    return " ".join(
        text.replace(":", " ")
        .replace("-", " ")
        .replace("'", "")
        .split()
    )


def inspect_csv(
    path: Path,
    target_names: set[str],
) -> dict[str, Any]:
    try:
        frame = pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            low_memory=False,
            nrows=10000,
        )
    except Exception as exc:
        return {
            "status": "read_error",
            "error": f"{type(exc).__name__}: {exc}",
        }

    columns = [
        clean_text(value)
        for value in frame.columns
    ]

    release_fields = sorted(
        set(columns)
        & RELEASE_FIELD_NAMES
    )

    identity_fields = sorted(
        set(columns)
        & IDENTITY_FIELD_NAMES
    )

    matched_names: set[str] = set()

    for column in identity_fields:
        for value in frame[column].tolist():
            normalized = normalized_name(value)

            if normalized in target_names:
                matched_names.add(normalized)

    return {
        "status": "read",
        "row_count_inspected": int(len(frame)),
        "columns": "|".join(columns),
        "release_fields": "|".join(release_fields),
        "identity_fields": "|".join(identity_fields),
        "matched_target_names": len(matched_names),
        "error": "",
    }


def walk_json(
    value: object,
    *,
    release_fields: set[str],
    identity_values: list[str],
    depth: int = 0,
) -> None:
    if depth > 8:
        return

    if isinstance(value, dict):
        for key, child in value.items():
            key_text = clean_text(key)

            if key_text in RELEASE_FIELD_NAMES:
                release_fields.add(key_text)

            if key_text in IDENTITY_FIELD_NAMES:
                identity_values.append(
                    clean_text(child)
                )

            walk_json(
                child,
                release_fields=release_fields,
                identity_values=identity_values,
                depth=depth + 1,
            )

    elif isinstance(value, list):
        for child in value[:10000]:
            walk_json(
                child,
                release_fields=release_fields,
                identity_values=identity_values,
                depth=depth + 1,
            )


def inspect_json(
    path: Path,
    target_names: set[str],
) -> dict[str, Any]:
    try:
        with path.open(
            "r",
            encoding="utf-8-sig",
        ) as handle:
            payload = json.load(handle)

    except Exception as exc:
        return {
            "status": "read_error",
            "error": f"{type(exc).__name__}: {exc}",
        }

    release_fields: set[str] = set()
    identity_values: list[str] = []

    walk_json(
        payload,
        release_fields=release_fields,
        identity_values=identity_values,
    )

    matched_names = {
        normalized
        for normalized in (
            normalized_name(value)
            for value in identity_values
        )
        if normalized in target_names
    }

    top_level_type = type(
        payload
    ).__name__

    top_level_keys = (
        "|".join(
            clean_text(key)
            for key in payload.keys()
        )
        if isinstance(payload, dict)
        else ""
    )

    return {
        "status": "read",
        "row_count_inspected": "",
        "columns": top_level_keys,
        "release_fields": "|".join(
            sorted(release_fields)
        ),
        "identity_fields": (
            "nested_json_identity_fields"
            if identity_values
            else ""
        ),
        "matched_target_names": len(
            matched_names
        ),
        "top_level_type": top_level_type,
        "error": "",
    }


def main() -> int:
    unresolved = pd.read_csv(
        RELEASE_QUEUE_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    cached = pd.read_csv(
        CACHED_DATE_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    if len(unresolved) != 99:
        raise RuntimeError(
            "Expected 99 unresolved release rows; "
            f"found {len(unresolved)}."
        )

    if len(cached) != 41:
        raise RuntimeError(
            "Expected 41 cached release dates; "
            f"found {len(cached)}."
        )

    target_names = {
        normalized_name(value)
        for value in unresolved[
            "canonical_product_name"
        ].tolist()
    }

    inventory_rows: list[
        dict[str, Any]
    ] = []

    for path in sorted(
        DATA_ROOT.rglob("*")
    ):
        if (
            not path.is_file()
            or path.suffix.casefold()
            not in SEARCH_SUFFIXES
        ):
            continue

        resolved_path = path.resolve()

        if any(
            resolved_path.is_relative_to(
                excluded_root.resolve()
            )
            for excluded_root
            in EXCLUDED_DISCOVERY_ROOTS
        ):
            continue

        relative_path = str(
            path.relative_to(ROOT)
        )

        if path.suffix.casefold() == ".csv":
            result = inspect_csv(
                path,
                target_names,
            )
        else:
            result = inspect_json(
                path,
                target_names,
            )

        release_fields = clean_text(
            result.get(
                "release_fields"
            )
        )

        matched_names = int(
            result.get(
                "matched_target_names",
                0,
            )
            or 0
        )

        likely_relevant = bool(
            release_fields
            or matched_names
            or "mtgjson" in relative_path.casefold()
            or "setlist" in relative_path.casefold()
            or "sealed" in relative_path.casefold()
        )

        if not likely_relevant:
            continue

        inventory_rows.append(
            {
                "file_path": relative_path,
                "file_suffix": path.suffix.casefold(),
                "file_size_bytes": path.stat().st_size,
                "status": clean_text(
                    result.get("status")
                ),
                "release_fields": release_fields,
                "identity_fields": clean_text(
                    result.get(
                        "identity_fields"
                    )
                ),
                "matched_unresolved_names": (
                    matched_names
                ),
                "structure_fields": clean_text(
                    result.get(
                        "columns"
                    )
                ),
                "error": clean_text(
                    result.get("error")
                ),
            }
        )

    inventory = (
        pd.DataFrame(
            inventory_rows
        )
        .sort_values(
            [
                "matched_unresolved_names",
                "file_path",
            ],
            ascending=[
                False,
                True,
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    inventory_path = (
        OUTPUT_ROOT
        / "historical_release_source_inventory_2026-07-22.csv"
    )

    ranked_path = (
        OUTPUT_ROOT
        / "historical_release_source_ranked_candidates_2026-07-22.csv"
    )

    summary_path = (
        OUTPUT_ROOT
        / "historical_release_source_discovery_summary_2026-07-22.json"
    )

    ranked = inventory[
        inventory[
            "release_fields"
        ]
        .astype(str)
        .str.strip()
        .ne("")
        | inventory[
            "matched_unresolved_names"
        ].gt(0)
    ].copy()

    inventory.to_csv(
        inventory_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    ranked.to_csv(
        ranked_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "discovery_status": "PASS",
        "unresolved_release_rows": int(
            len(unresolved)
        ),
        "existing_cached_release_rows": int(
            len(cached)
        ),
        "relevant_source_files": int(
            len(inventory)
        ),
        "ranked_candidate_files": int(
            len(ranked)
        ),
        "maximum_unresolved_name_overlap": int(
            ranked[
                "matched_unresolved_names"
            ].max()
            if len(ranked)
            else 0
        ),
        "mtgjson_named_files": int(
            inventory[
                "file_path"
            ]
            .astype(str)
            .str.casefold()
            .str.contains(
                "mtgjson"
            )
            .sum()
        ),
        "release_field_files": int(
            inventory[
                "release_fields"
            ]
            .astype(str)
            .str.strip()
            .ne("")
            .sum()
        ),
        "external_download_performed": False,
        "release_dates_assigned": False,
        "discovery_boundary_frozen": True,
        "excluded_downstream_root_count": int(
            len(EXCLUDED_DISCOVERY_ROOTS)
        ),
        "final_eligibility_assigned": False,
        "scoring_allowed_rows": 0,
        "universal_investable_allowed_rows": 0,
        "production_registry_changed": False,
        "universal_database_changed": False,
        "output_files": {
            "inventory": str(
                inventory_path
            ),
            "ranked_candidates": str(
                ranked_path
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
        "Phase 10.5R.1D.2.4B "
        "Existing Release-Evidence Discovery"
    )
    print("=" * 76)
    print(
        f"Unresolved release rows: {len(unresolved)}"
    )
    print(
        "Relevant source files: "
        f"{len(inventory)}"
    )
    print(
        "Ranked candidate files: "
        f"{len(ranked)}"
    )
    print(
        "Maximum unresolved-name overlap: "
        + str(
            summary[
                "maximum_unresolved_name_overlap"
            ]
        )
    )
    print(
        "MTGJSON-named files: "
        + str(
            summary[
                "mtgjson_named_files"
            ]
        )
    )
    print()
    print(
        "DISCOVERY STATUS: PASS"
    )
    print(
        "External download performed: NO"
    )
    print(
        "Release dates assigned: NO"
    )
    print(
        "Final eligibility: NOT ASSIGNED"
    )
    print(
        "Scoring: DISABLED"
    )
    print(
        "Production registry: UNCHANGED"
    )
    print(
        "Universal database: UNCHANGED"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())