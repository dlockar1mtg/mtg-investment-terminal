from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from collectors.tcgcsv_discovery import (
    fetch_groups,
    fetch_products,
    resolve_category_id,
)


SNAPSHOT_ROOT = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "external_discovery"
    / "tcgcsv"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "external_discovery"
    / "tcgcsv"
)

SOURCE_NAME = "tcgcsv"
SCHEMA_VERSION = "10.5R.1B.2.1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_missing_value(value: object) -> bool:
    if value is None:
        return True

    if isinstance(
        value,
        (
            dict,
            list,
            tuple,
            set,
        ),
    ):
        return False

    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False

    if result is pd.NA:
        return True

    try:
        return bool(result)
    except (TypeError, ValueError):
        return False


def clean_text(value: object) -> str:
    if is_missing_value(value):
        return ""

    if isinstance(
        value,
        (
            dict,
            list,
            tuple,
            set,
        ),
    ):
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

    return re.sub(
        r"\s+",
        " ",
        str(value).strip(),
    )


def first_value(
    row: pd.Series,
    *columns: str,
) -> object:
    for column in columns:
        if column not in row.index:
            continue

        value = row[column]

        if is_missing_value(value):
            continue

        if clean_text(value):
            return value

    return None


def normalize_identifier(value: object) -> str:
    if value is None or pd.isna(value):
        return ""

    text = clean_text(value)

    try:
        number = float(text)

        if number.is_integer():
            return str(int(number))
    except (TypeError, ValueError):
        pass

    return text


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def stable_snapshot_record_id(
    category_id: str,
    group_id: str,
    product_id: str,
) -> str:
    raw = (
        f"{SOURCE_NAME}|"
        f"{category_id}|"
        f"{group_id}|"
        f"{product_id}"
    )

    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:24]

    return f"TCGCSV-SNAPSHOT-{digest.upper()}"


def flatten_product_record(
    *,
    category_id: str,
    group: pd.Series,
    product: pd.Series,
    collected_at: str,
) -> dict[str, Any]:
    group_id = normalize_identifier(
        first_value(
            group,
            "groupId",
            "group_id",
        )
    )

    product_id = normalize_identifier(
        first_value(
            product,
            "productId",
            "product_id",
        )
    )

    group_name = clean_text(
        first_value(
            group,
            "name",
            "groupName",
            "group_name",
        )
    )

    product_name = clean_text(
        first_value(
            product,
            "name",
            "productName",
            "product_name",
        )
    )

    published_on = clean_text(
        first_value(
            group,
            "publishedOn",
            "published_on",
            "releaseDate",
            "release_date",
        )
    )

    modified_on = clean_text(
        first_value(
            product,
            "modifiedOn",
            "modified_on",
        )
    )

    clean_name = clean_text(
        first_value(
            product,
            "cleanName",
            "clean_name",
        )
    )

    url = clean_text(
        first_value(
            product,
            "url",
            "productUrl",
            "product_url",
        )
    )

    image_url = clean_text(
        first_value(
            product,
            "imageUrl",
            "image_url",
        )
    )

    category_identifier = normalize_identifier(
        category_id
    )

    return {
        "snapshot_record_id": (
            stable_snapshot_record_id(
                category_identifier,
                group_id,
                product_id,
            )
        ),
        "source_name": SOURCE_NAME,
        "schema_version": SCHEMA_VERSION,
        "collected_at_utc": collected_at,
        "tcgcsv_category_id": (
            category_identifier
        ),
        "tcgcsv_group_id": group_id,
        "tcgplayer_product_id": product_id,
        "group_name": group_name,
        "group_abbreviation": clean_text(
            first_value(
                group,
                "abbreviation",
                "groupAbbreviation",
                "group_abbreviation",
            )
        ),
        "group_published_on": published_on,
        "product_name": product_name,
        "product_clean_name": clean_name,
        "product_url": url,
        "product_image_url": image_url,
        "product_modified_on": modified_on,
        "product_is_presale": first_value(
            product,
            "presaleInfo",
            "isPresale",
            "is_presale",
        ),
        "product_extended_data": json.dumps(
            first_value(
                product,
                "extendedData",
                "extended_data",
            ),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ),
        "raw_group_payload": json.dumps(
            group.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ),
        "raw_product_payload": json.dumps(
            product.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ),
    }


def snapshot_tcgcsv_products(
    *,
    category_id: int | None,
    max_groups: int | None,
    sleep_seconds: float,
) -> dict[str, Any]:
    resolved_category_id = resolve_category_id(
        category_id
    )

    collected_at = utc_now()

    groups = fetch_groups(
        resolved_category_id
    )

    if groups.empty:
        raise RuntimeError(
            "TCGCSV groups endpoint returned no groups."
        )

    original_group_count = len(groups)

    if max_groups is not None:
        groups = groups.head(
            int(max_groups)
        ).copy()

    SNAPSHOT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    VALIDATION_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    group_rows: list[dict[str, Any]] = []
    product_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []

    for position, (_, group) in enumerate(
        groups.iterrows(),
        start=1,
    ):
        group_id = normalize_identifier(
            first_value(
                group,
                "groupId",
                "group_id",
            )
        )

        group_name = clean_text(
            first_value(
                group,
                "name",
                "groupName",
                "group_name",
            )
        )

        group_rows.append(
            {
                "source_name": SOURCE_NAME,
                "schema_version": (
                    SCHEMA_VERSION
                ),
                "collected_at_utc": (
                    collected_at
                ),
                "tcgcsv_category_id": (
                    str(resolved_category_id)
                ),
                "tcgcsv_group_id": group_id,
                "group_name": group_name,
                "group_published_on": (
                    clean_text(
                        first_value(
                            group,
                            "publishedOn",
                            "published_on",
                        )
                    )
                ),
                "raw_group_payload": (
                    json.dumps(
                        group.to_dict(),
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    )
                ),
            }
        )

        if not group_id:
            audit_rows.append(
                {
                    "tcgcsv_group_id": "",
                    "group_name": group_name,
                    "status": (
                        "skipped_missing_group_id"
                    ),
                    "product_count": 0,
                    "message": (
                        "Group did not contain "
                        "a usable identifier."
                    ),
                }
            )
            continue

        print(
            f"[{position}/{len(groups)}] "
            f"Fetching group {group_id}: "
            f"{group_name}"
        )

        try:
            products = fetch_products(
                resolved_category_id,
                int(group_id),
            )
        except Exception as exc:
            audit_rows.append(
                {
                    "tcgcsv_group_id": group_id,
                    "group_name": group_name,
                    "status": "failed",
                    "product_count": 0,
                    "message": (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
                }
            )

            print(
                f"  FAILED: "
                f"{type(exc).__name__}: {exc}"
            )

            time.sleep(sleep_seconds)
            continue

        if products.empty:
            audit_rows.append(
                {
                    "tcgcsv_group_id": group_id,
                    "group_name": group_name,
                    "status": "success_empty",
                    "product_count": 0,
                    "message": "",
                }
            )

            print("  Products returned: 0")
            time.sleep(sleep_seconds)
            continue

        valid_product_count = 0
        missing_product_id_count = 0

        for _, product in products.iterrows():
            product_id = normalize_identifier(
                first_value(
                    product,
                    "productId",
                    "product_id",
                )
            )

            if not product_id:
                missing_product_id_count += 1
                continue

            product_rows.append(
                flatten_product_record(
                    category_id=str(
                        resolved_category_id
                    ),
                    group=group,
                    product=product,
                    collected_at=collected_at,
                )
            )

            valid_product_count += 1

        audit_rows.append(
            {
                "tcgcsv_group_id": group_id,
                "group_name": group_name,
                "status": "success",
                "product_count": (
                    valid_product_count
                ),
                "message": (
                    ""
                    if missing_product_id_count == 0
                    else (
                        f"{missing_product_id_count} "
                        "products skipped because "
                        "product ID was missing."
                    )
                ),
            }
        )

        print(
            f"  Products captured: "
            f"{valid_product_count}"
        )

        time.sleep(sleep_seconds)

    group_frame = pd.DataFrame(
        group_rows
    )

    product_frame = pd.DataFrame(
        product_rows
    )

    audit_frame = pd.DataFrame(
        audit_rows
    )

    if product_frame.empty:
        raise RuntimeError(
            "TCGCSV snapshot captured no products."
        )

    product_frame = product_frame.sort_values(
        [
            "tcgcsv_group_id",
            "product_name",
            "tcgplayer_product_id",
        ],
        kind="stable",
    ).reset_index(drop=True)

    group_frame = group_frame.sort_values(
        [
            "group_name",
            "tcgcsv_group_id",
        ],
        kind="stable",
    ).reset_index(drop=True)

    audit_frame = audit_frame.sort_values(
        [
            "status",
            "group_name",
            "tcgcsv_group_id",
        ],
        kind="stable",
    ).reset_index(drop=True)

    snapshot_date = datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d")

    products_path = (
        SNAPSHOT_ROOT
        / (
            "tcgcsv_magic_products_"
            f"{snapshot_date}.csv"
        )
    )

    groups_path = (
        SNAPSHOT_ROOT
        / (
            "tcgcsv_magic_groups_"
            f"{snapshot_date}.csv"
        )
    )

    audit_path = (
        VALIDATION_ROOT
        / (
            "tcgcsv_snapshot_audit_"
            f"{snapshot_date}.csv"
        )
    )

    manifest_path = (
        VALIDATION_ROOT
        / (
            "tcgcsv_snapshot_manifest_"
            f"{snapshot_date}.json"
        )
    )

    product_frame.to_csv(
        products_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    group_frame.to_csv(
        groups_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    audit_frame.to_csv(
        audit_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    duplicate_product_ids = int(
        product_frame[
            "tcgplayer_product_id"
        ].duplicated(keep=False).sum()
    )

    duplicate_snapshot_ids = int(
        product_frame[
            "snapshot_record_id"
        ].duplicated(keep=False).sum()
    )

    failed_groups = int(
        audit_frame[
            "status"
        ].eq("failed").sum()
    )

    successful_groups = int(
        audit_frame[
            "status"
        ].isin(
            {
                "success",
                "success_empty",
            }
        ).sum()
    )

    manifest = {
        "source_name": SOURCE_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "collection_started_at_utc": (
            collected_at
        ),
        "tcgcsv_category_id": str(
            resolved_category_id
        ),
        "remote_group_count_before_limit": int(
            original_group_count
        ),
        "groups_attempted": int(
            len(groups)
        ),
        "successful_groups": (
            successful_groups
        ),
        "failed_groups": failed_groups,
        "captured_group_rows": int(
            len(group_frame)
        ),
        "captured_product_rows": int(
            len(product_frame)
        ),
        "unique_group_ids": int(
            product_frame[
                "tcgcsv_group_id"
            ].nunique()
        ),
        "unique_product_ids": int(
            product_frame[
                "tcgplayer_product_id"
            ].nunique()
        ),
        "unique_snapshot_record_ids": int(
            product_frame[
                "snapshot_record_id"
            ].nunique()
        ),
        "duplicate_product_id_rows": (
            duplicate_product_ids
        ),
        "duplicate_snapshot_id_rows": (
            duplicate_snapshot_ids
        ),
        "limited_run": (
            max_groups is not None
        ),
        "max_groups": max_groups,
        "sleep_seconds": sleep_seconds,
        "classification_applied": False,
        "eligibility_changed": False,
        "prices_requested": False,
        "snapshot_status": (
            "COMPLETE"
            if failed_groups == 0
            else "COMPLETE_WITH_FAILURES"
        ),
        "files": {
            "products": {
                "path": str(products_path),
                "sha256": sha256_file(
                    products_path
                ),
            },
            "groups": {
                "path": str(groups_path),
                "sha256": sha256_file(
                    groups_path
                ),
            },
            "audit": {
                "path": str(audit_path),
                "sha256": sha256_file(
                    audit_path
                ),
            },
        },
    }

    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    if duplicate_snapshot_ids:
        raise RuntimeError(
            "Snapshot record identifiers "
            "are not unique."
        )

    print()
    print("=" * 76)
    print(
        "Phase 10.5R.1B.2.1 Raw "
        "TCGCSV Product-Universe Snapshot"
    )
    print("=" * 76)
    print(
        f"Category ID: "
        f"{resolved_category_id}"
    )
    print(
        f"Remote groups before limit: "
        f"{original_group_count}"
    )
    print(
        f"Groups attempted: "
        f"{len(groups)}"
    )
    print(
        f"Successful groups: "
        f"{successful_groups}"
    )
    print(
        f"Failed groups: "
        f"{failed_groups}"
    )
    print(
        f"Products captured: "
        f"{len(product_frame)}"
    )
    print(
        f"Unique product IDs: "
        f"{manifest['unique_product_ids']}"
    )
    print(
        f"Duplicate product-ID rows: "
        f"{duplicate_product_ids}"
    )
    print()
    print(f"Products: {products_path}")
    print(f"Groups: {groups_path}")
    print(f"Audit: {audit_path}")
    print(f"Manifest: {manifest_path}")
    print()
    print(
        "PHASE 10.5R.1B.2.1 RAW "
        "TCGCSV SNAPSHOT: PASS"
    )
    print(
        "Classification: NOT APPLIED"
    )
    print(
        "Eligibility: UNCHANGED"
    )

    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create an unfiltered snapshot of "
            "the TCGCSV Magic product catalog."
        )
    )

    parser.add_argument(
        "--category-id",
        type=int,
        default=None,
        help=(
            "Explicit TCGCSV Magic category ID. "
            "Defaults to existing configuration "
            "or automatic detection."
        ),
    )

    parser.add_argument(
        "--max-groups",
        type=int,
        default=None,
        help=(
            "Optional group limit for a test run. "
            "Omit for the complete snapshot."
        ),
    )

    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.10,
        help=(
            "Delay after each group request."
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    snapshot_tcgcsv_products(
        category_id=args.category_id,
        max_groups=args.max_groups,
        sleep_seconds=max(
            0.0,
            args.sleep_seconds,
        ),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())