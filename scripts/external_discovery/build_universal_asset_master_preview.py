from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

DEFAULT_GOVERNED_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "canonical_registry_governance"
    / "governed_canonical_mtg_registry_2026-07-22.csv"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "universal_mapping"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "universal_mapping"
)

CONTRACT_VERSION = "1.0.0"
PLATFORM_ID = "mtg"
MAPPING_VERSION = "10.5R.1C.2.2"

ASSET_MASTER_COLUMNS = [
    "contract_version",
    "platform_id",
    "run_id",
    "universal_asset_id",
    "platform_asset_id",
    "asset_name",
    "asset_symbol",
    "asset_class",
    "asset_subclass",
    "currency",
    "market_or_region",
    "is_active",
    "investable",
    "liquidity_tier",
    "data_source",
    "first_available_date",
    "last_updated_at_utc",
]


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).replace(
        microsecond=0
    ).isoformat().replace(
        "+00:00",
        "Z",
    )


def clean_text(value: object) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return re.sub(
        r"\s+",
        " ",
        str(value).strip(),
    )


def build_run_id() -> str:
    return (
        "mtg-canonical-asset-master-"
        "preview-20260722"
    )


def universal_asset_id(
    canonical_product_id: str,
) -> str:
    normalized = (
        clean_text(
            canonical_product_id
        )
        .casefold()
        .replace(
            "mtg-canon-tcgplayer-",
            "",
        )
    )

    return f"mtg:tcgplayer:{normalized}"


def asset_subclass(
    product_class: str,
) -> str:
    if product_class == (
        "secret_lair_product"
    ):
        return "mtg_secret_lair_product"

    if product_class == (
        "sealed_product"
    ):
        return "mtg_sealed_product"

    return "mtg_other_product"


def is_investable(
    *,
    eligibility_status: str,
    approval_status: str,
) -> bool:
    return (
        eligibility_status == "eligible"
        and approval_status == "approved"
    )


def build_asset_master(
    governed: pd.DataFrame,
) -> pd.DataFrame:
    generated_at = utc_now()
    run_id = build_run_id()

    rows: list[
        dict[str, Any]
    ] = []

    for _, row in governed.iterrows():
        canonical_id = clean_text(
            row.get(
                "canonical_product_id"
            )
        )

        product_class = clean_text(
            row.get(
                "canonical_product_class"
            )
        )

        lifecycle_status = clean_text(
            row.get(
                "identity_lifecycle_status"
            )
        )

        source_status = clean_text(
            row.get(
                "source_availability_status"
            )
        )

        eligibility_status = clean_text(
            row.get(
                "investment_eligibility_status"
            )
        )

        approval_status = clean_text(
            row.get(
                "investment_approval_status"
            )
        )

        active = (
            lifecycle_status == "active"
            and source_status == "available"
        )

        investable = is_investable(
            eligibility_status=(
                eligibility_status
            ),
            approval_status=approval_status,
        )

        rows.append(
            {
                "contract_version": (
                    CONTRACT_VERSION
                ),
                "platform_id": PLATFORM_ID,
                "run_id": run_id,
                "universal_asset_id": (
                    universal_asset_id(
                        canonical_id
                    )
                ),
                "platform_asset_id": (
                    canonical_id
                ),
                "asset_name": clean_text(
                    row.get(
                        "canonical_product_name"
                    )
                ),
                "asset_symbol": "",
                "asset_class": "collectible",
                "asset_subclass": (
                    asset_subclass(
                        product_class
                    )
                ),
                "currency": "USD",
                "market_or_region": "global",
                "is_active": active,
                "investable": investable,
                "liquidity_tier": "illiquid",
                "data_source": "TCGCSV",
                "first_available_date": "",
                "last_updated_at_utc": (
                    generated_at
                ),
            }
        )

    asset_master = pd.DataFrame(
        rows,
        columns=ASSET_MASTER_COLUMNS,
    )

    return asset_master.sort_values(
        [
            "asset_subclass",
            "asset_name",
            "platform_asset_id",
        ],
        kind="stable",
    ).reset_index(drop=True)


def validate_asset_master(
    asset_master: pd.DataFrame,
) -> list[str]:
    errors: list[str] = []

    required_columns = {
        "contract_version",
        "platform_id",
        "run_id",
        "universal_asset_id",
        "platform_asset_id",
        "asset_name",
        "asset_class",
        "is_active",
        "investable",
        "last_updated_at_utc",
    }

    missing_columns = sorted(
        required_columns
        - set(asset_master.columns)
    )

    if missing_columns:
        errors.append(
            "missing_columns:"
            + ",".join(missing_columns)
        )

    for column in sorted(
        required_columns
        - {
            "is_active",
            "investable",
        }
    ):
        blank_count = int(
            asset_master[column]
            .fillna("")
            .astype(str)
            .str.strip()
            .eq("")
            .sum()
        )

        if blank_count:
            errors.append(
                f"blank_required_field:"
                f"{column}:{blank_count}"
            )

    if asset_master[
        "universal_asset_id"
    ].duplicated().any():
        errors.append(
            "duplicate_universal_asset_id"
        )

    if asset_master[
        "platform_asset_id"
    ].duplicated().any():
        errors.append(
            "duplicate_platform_asset_id"
        )

    if not asset_master[
        "platform_id"
    ].eq(PLATFORM_ID).all():
        errors.append(
            "invalid_platform_id"
        )

    if not asset_master[
        "contract_version"
    ].eq(CONTRACT_VERSION).all():
        errors.append(
            "invalid_contract_version"
        )

    if not asset_master[
        "asset_class"
    ].eq("collectible").all():
        errors.append(
            "invalid_asset_class"
        )

    return errors


def write_outputs(
    *,
    asset_master: pd.DataFrame,
    governed_path: Path,
) -> dict[str, Any]:
    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    VALIDATION_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    preview_path = (
        OUTPUT_ROOT
        / "asset_master_preview_2026-07-22.csv"
    )

    identity_map_path = (
        VALIDATION_ROOT
        / "canonical_to_universal_identity_map_2026-07-22.csv"
    )

    summary_path = (
        VALIDATION_ROOT
        / "asset_master_mapping_summary_2026-07-22.json"
    )

    validation_path = (
        VALIDATION_ROOT
        / "asset_master_mapping_validation_2026-07-22.json"
    )

    asset_master.to_csv(
        preview_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    identity_map = asset_master[
        [
            "universal_asset_id",
            "platform_asset_id",
            "asset_name",
            "asset_class",
            "asset_subclass",
            "is_active",
            "investable",
        ]
    ].copy()

    identity_map.to_csv(
        identity_map_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    errors = validate_asset_master(
        asset_master
    )

    summary = {
        "schema_version": MAPPING_VERSION,
        "generated_at_utc": utc_now(),
        "mapping_status": (
            "PASS"
            if not errors
            else "FAIL"
        ),
        "contract_version": (
            CONTRACT_VERSION
        ),
        "platform_id": PLATFORM_ID,
        "asset_master_rows": int(
            len(asset_master)
        ),
        "unique_universal_asset_ids": int(
            asset_master[
                "universal_asset_id"
            ].nunique()
        ),
        "unique_platform_asset_ids": int(
            asset_master[
                "platform_asset_id"
            ].nunique()
        ),
        "active_rows": int(
            asset_master[
                "is_active"
            ].eq(True).sum()
        ),
        "investable_rows": int(
            asset_master[
                "investable"
            ].eq(True).sum()
        ),
        "non_investable_rows": int(
            asset_master[
                "investable"
            ].eq(False).sum()
        ),
        "asset_class_counts": {
            str(key): int(value)
            for key, value in (
                asset_master[
                    "asset_class"
                ]
                .value_counts()
                .to_dict()
                .items()
            )
        },
        "asset_subclass_counts": {
            str(key): int(value)
            for key, value in (
                asset_master[
                    "asset_subclass"
                ]
                .value_counts()
                .to_dict()
                .items()
            )
        },
        "input_files": {
            "governed_registry": str(
                governed_path
            ),
        },
        "output_files": {
            "asset_master_preview": str(
                preview_path
            ),
            "identity_map": str(
                identity_map_path
            ),
        },
        "validation_errors": errors,
        "universal_package_created": False,
        "universal_database_changed": False,
        "mtg_production_registry_changed": False,
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

    validation = {
        "schema_version": MAPPING_VERSION,
        "validation_status": (
            "PASS"
            if not errors
            else "FAIL"
        ),
        "errors": errors,
        "required_column_count": 10,
        "actual_column_count": int(
            len(asset_master.columns)
        ),
        "row_count": int(
            len(asset_master)
        ),
    }

    validation_path.write_text(
        json.dumps(
            validation,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print("=" * 76)
    print(
        "Phase 10.5R.1C.2.2 "
        "Universal asset_master Mapping Preview"
    )
    print("=" * 76)
    print(
        f"Mapped rows: "
        f"{len(asset_master)}"
    )
    print(
        "Unique universal asset IDs: "
        f"{asset_master['universal_asset_id'].nunique()}"
    )
    print(
        "Unique platform asset IDs: "
        f"{asset_master['platform_asset_id'].nunique()}"
    )
    print(
        "Active rows: "
        f"{asset_master['is_active'].eq(True).sum()}"
    )
    print(
        "Investable rows: "
        f"{asset_master['investable'].eq(True).sum()}"
    )
    print(
        "Non-investable rows: "
        f"{asset_master['investable'].eq(False).sum()}"
    )
    print()
    print("Asset subclasses:")

    for name, count in sorted(
        summary[
            "asset_subclass_counts"
        ].items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        print(
            f"  {name}: {count}"
        )

    print()
    print(
        "Validation errors: "
        f"{len(errors)}"
    )
    print(
        f"Preview: {preview_path}"
    )
    print(
        f"Summary: {summary_path}"
    )
    print()

    if errors:
        print(
            "PHASE 10.5R.1C.2.2 "
            "UNIVERSAL MAPPING PREVIEW: FAIL"
        )

        for error in errors:
            print(f"  {error}")

        return summary

    print(
        "PHASE 10.5R.1C.2.2 "
        "UNIVERSAL MAPPING PREVIEW: PASS"
    )
    print(
        "Universal package: NOT CREATED"
    )
    print(
        "Universal database: UNCHANGED"
    )
    print(
        "MTG production registry: UNCHANGED"
    )

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--governed-registry",
        type=Path,
        default=DEFAULT_GOVERNED_PATH,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    governed_path = (
        args.governed_registry.resolve()
    )

    if not governed_path.is_file():
        raise FileNotFoundError(
            "Governed registry not found: "
            f"{governed_path}"
        )

    governed = pd.read_csv(
        governed_path,
        low_memory=False,
        dtype=str,
        keep_default_na=False,
    )

    if len(governed) != 5239:
        raise RuntimeError(
            "Expected 5,239 governed rows; "
            f"found {len(governed)}."
        )

    asset_master = build_asset_master(
        governed
    )

    if len(asset_master) != len(governed):
        raise RuntimeError(
            "Mapped asset_master row count "
            "does not match governed registry."
        )

    summary = write_outputs(
        asset_master=asset_master,
        governed_path=governed_path,
    )

    if summary[
        "mapping_status"
    ] != "PASS":
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())