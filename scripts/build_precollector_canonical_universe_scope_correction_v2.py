from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile

from datetime import datetime, timezone
from pathlib import Path


EXPECTED_PRIOR_COUNT = 186
EXPECTED_KEEP_COUNT = 131
EXPECTED_CASE_COUNT = 55
EXPECTED_OTHER_COUNT = 0


def fail(message: str) -> None:
    raise RuntimeError(f"FAIL-CLOSED: {message}")


def classify_product(name: str) -> str:
    lower = name.casefold()

    case_signals = (
        "booster box case",
        "booster case",
        "sealed case",
        "master case",
    )

    if any(signal in lower for signal in case_signals):
        return "CASE_REMOVE"

    if "case of" in lower:
        return "CASE_REMOVE"

    keep_signals = (
        "booster box",
        "booster display",
        "display box",
        "booster display box",
        "theme booster display",
        "battle pack display",
        "planeswalker deck display",
    )

    if any(signal in lower for signal in keep_signals):
        return "BOX_OR_DISPLAY_KEEP"

    return "OTHER_REVIEW"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def write_csv(
    path: Path,
    rows: list[dict[str, str]],
    fields: list[str],
) -> None:
    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def read_stage9(package: Path) -> tuple[list[dict[str, str]], list[str]]:
    with zipfile.ZipFile(package, "r") as archive:
        member = "precollector_canonical_universe.csv"

        if member not in archive.namelist():
            fail(f"missing Stage-9 ZIP member: {member}")

        text = archive.read(member).decode("utf-8-sig")

    reader = csv.DictReader(text.splitlines())
    rows = list(reader)
    fields = list(reader.fieldnames or [])

    if len(rows) != EXPECTED_PRIOR_COUNT:
        fail(
            f"Stage-9 row count {len(rows)} "
            f"!= {EXPECTED_PRIOR_COUNT}"
        )

    if "canonical_product_id" not in fields:
        fail("Stage-9 universe lacks canonical_product_id")

    if "product_name" not in fields:
        fail("Stage-9 universe lacks product_name")

    return rows, fields


def identity_sha(rows: list[dict[str, str]]) -> str:
    ordered = sorted(
        rows,
        key=lambda row: int(
            str(row["canonical_product_id"]).split(":")[-1]
        ),
    )

    material = "\n".join(
        f"{row['canonical_product_id']}|{row['product_name']}"
        for row in ordered
    ) + "\n"

    return hashlib.sha256(
        material.encode("utf-8")
    ).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--stage9-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    package = args.stage9_package.resolve()
    output_root = args.output_root.resolve()

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows, fields = read_stage9(package)

    keep: list[dict[str, str]] = []
    cases: list[dict[str, str]] = []
    other: list[dict[str, str]] = []

    for row in rows:
        name = str(
            row.get("product_name") or ""
        ).strip()

        if not name:
            fail("blank product_name")

        disposition = classify_product(name)

        if disposition == "BOX_OR_DISPLAY_KEEP":
            keep.append(row)

        elif disposition == "CASE_REMOVE":
            removed = dict(row)
            removed["scope_removal_reason"] = (
                "WRONG_COMMERCIAL_UNIT_MULTI_BOX_CASE"
            )
            removed["model_exclusion"] = "false"
            cases.append(removed)

        else:
            other.append(row)

    if len(keep) != EXPECTED_KEEP_COUNT:
        fail(
            f"corrected keep count {len(keep)} "
            f"!= {EXPECTED_KEEP_COUNT}"
        )

    if len(cases) != EXPECTED_CASE_COUNT:
        fail(
            f"case count {len(cases)} "
            f"!= {EXPECTED_CASE_COUNT}"
        )

    if len(other) != EXPECTED_OTHER_COUNT:
        fail(
            f"unresolved product-form count {len(other)} "
            f"!= {EXPECTED_OTHER_COUNT}"
        )

    keep = sorted(
        keep,
        key=lambda row: int(
            str(row["canonical_product_id"]).split(":")[-1]
        ),
    )

    cases = sorted(
        cases,
        key=lambda row: int(
            str(row["canonical_product_id"]).split(":")[-1]
        ),
    )

    corrected_path = (
        output_root
        / "precollector_canonical_universe_v2.csv"
    )

    removed_path = (
        output_root
        / "precollector_removed_case_products_v2.csv"
    )

    summary_path = (
        output_root
        / "precollector_canonical_universe_scope_correction_v2_summary.json"
    )

    manifest_path = (
        output_root
        / "precollector_canonical_universe_scope_correction_v2_manifest.json"
    )

    write_csv(
        corrected_path,
        keep,
        fields,
    )

    removed_fields = (
        fields
        + [
            "scope_removal_reason",
            "model_exclusion",
        ]
    )

    write_csv(
        removed_path,
        cases,
        removed_fields,
    )

    corrected_identity = identity_sha(keep)

    summary = {
        "status":
            "PASS_PRECOLLECTOR_CANONICAL_UNIVERSE_SCOPE_CORRECTION_V2",

        "generated_at_utc":
            datetime.now(timezone.utc).isoformat(),

        "prior_product_count":
            186,

        "corrected_product_count":
            131,

        "removed_case_product_count":
            55,

        "unresolved_product_form_count":
            0,

        "target_commercial_unit":
            "INDIVIDUAL_SEALED_BOX_OR_DISPLAY",

        "removed_commercial_unit":
            "MULTI_BOX_CASE",

        "scope_removal_is_model_exclusion":
            False,

        "case_to_box_price_division_authorized":
            False,

        "synthetic_case_normalization_authorized":
            False,

        "corrected_identity_sha256":
            corrected_identity,

        "prior_stage9_package_sha256":
            sha256_file(package),

        "stage14_historical_authority_status":
            "REQUIRES_REBINDING_TO_CORRECTED_131_PRODUCT_UNIVERSE",

        "stage15d_fresh_market_collection_status":
            "NON_CERTIFIABLE_OVERBROAD_186_PRODUCT_SCOPE_REQUIRES_RERUN",

        "model_execution_authorized":
            False,

        "authorized_next_stage":
            "REBIND_PRECOLLECTOR_HISTORY_TO_CORRECTED_131_PRODUCT_UNIVERSE",
    }

    summary_path.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest_files = [
        corrected_path,
        removed_path,
        summary_path,
    ]

    manifest = {
        "manifest_id":
            "precollector_canonical_universe_scope_correction_v2",

        "generated_at_utc":
            datetime.now(timezone.utc).isoformat(),

        "corrected_identity_sha256":
            corrected_identity,

        "members": [
            {
                "file_name": path.name,
                "byte_length": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in manifest_files
        ],
    }

    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "PASS_PRECOLLECTOR_CANONICAL_UNIVERSE_SCOPE_CORRECTION_V2"
    )
    print("PRIOR_PRODUCT_COUNT=186")
    print("CORRECTED_PRODUCT_COUNT=131")
    print("REMOVED_CASE_PRODUCTS=55")
    print("UNRESOLVED_PRODUCT_FORMS=0")
    print(
        f"CORRECTED_IDENTITY_SHA256={corrected_identity}"
    )
    print("CASE_TO_BOX_PRICE_DIVISION_AUTHORIZED=FALSE")
    print("MODEL_EXECUTION_AUTHORIZED=FALSE")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())