from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

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

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "operations"
    / "collector_booster_universe_audit"
    / "candidate_v1_0_0"
)

DISPLAY_TYPE = "Collector Booster Display"

EXCLUDED_CONFIGURATION_TERMS = (
    "master case",
    "box case",
    "display case",
    "collector booster case",
    "booster case",
    "case of",
    "mastercase",
    "booster pack",
    "single pack",
    "sample pack",
    "collector sample",
    "bundle",
)


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize(value: Any) -> str:
    text = clean(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fields: list[str] = []

    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)

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


def main() -> None:
    registry = read_csv(REGISTRY_PATH)
    model = read_csv(MODEL_PATH)

    model_ids = {
        clean(row.get("investment_product_id"))
        for row in model
        if clean(row.get("investment_product_id"))
    }

    registry_candidates = [
        row
        for row in registry
        if clean(row.get("investment_product_type"))
        == DISPLAY_TYPE
    ]

    results: list[dict[str, Any]] = []

    for row in registry_candidates:
        investment_id = clean(
            row.get("investment_product_id")
        )

        box_name = clean(row.get("box_name"))
        approved_name = clean(
            row.get("approved_product_name")
        )

        combined_name = normalize(
            f"{box_name} {approved_name}"
        )

        matched_exclusions = [
            term
            for term in EXCLUDED_CONFIGURATION_TERMS
            if normalize(term) in combined_name
        ]

        contains_collector_booster = (
            "collector booster" in combined_name
        )

        contains_display = "display" in combined_name

        in_model = investment_id in model_ids

        if matched_exclusions:
            classification = "EXCLUDE_CONFIGURATION"
            reason = "|".join(matched_exclusions)
        elif not contains_collector_booster:
            classification = "REVIEW_NAME_MISMATCH"
            reason = "collector booster term absent"
        elif not contains_display:
            classification = "REVIEW_DISPLAY_UNCONFIRMED"
            reason = "display term absent"
        else:
            classification = "INCLUDE_DISPLAY"
            reason = "display identity confirmed"

        results.append({
            "investment_product_id": investment_id,
            "set_name": clean(row.get("set_name")),
            "box_name": box_name,
            "approved_product_name": approved_name,
            "approved_tcgplayer_product_id": clean(
                row.get(
                    "approved_tcgplayer_product_id"
                )
            ),
            "investment_product_type": clean(
                row.get("investment_product_type")
            ),
            "in_model_input": str(in_model).lower(),
            "contains_collector_booster": str(
                contains_collector_booster
            ).lower(),
            "contains_display": str(
                contains_display
            ).lower(),
            "matched_exclusion_terms": "|".join(
                matched_exclusions
            ),
            "universe_classification": classification,
            "classification_reason": reason,
        })

    included = [
        row
        for row in results
        if row["universe_classification"]
        == "INCLUDE_DISPLAY"
    ]

    excluded = [
        row
        for row in results
        if row["universe_classification"]
        == "EXCLUDE_CONFIGURATION"
    ]

    review = [
        row
        for row in results
        if row["universe_classification"].startswith(
            "REVIEW_"
        )
    ]

    included_ids = {
        row["investment_product_id"]
        for row in included
    }

    missing_from_registry = sorted(
        model_ids - included_ids
    )

    included_not_in_model = sorted(
        included_ids - model_ids
    )

    write_csv(
        OUTPUT_ROOT
        / "collector_registry_universe_classification.csv",
        results,
    )

    write_csv(
        OUTPUT_ROOT
        / "collector_display_included.csv",
        included,
    )

    write_csv(
        OUTPUT_ROOT
        / "collector_configuration_excluded.csv",
        excluded,
    )

    write_csv(
        OUTPUT_ROOT
        / "collector_universe_manual_review.csv",
        review,
    )

    mismatch_rows = [
        {
            "mismatch_type": (
                "MODEL_ID_MISSING_FROM_FILTERED_REGISTRY"
            ),
            "investment_product_id": value,
        }
        for value in missing_from_registry
    ]

    mismatch_rows.extend(
        {
            "mismatch_type": (
                "FILTERED_REGISTRY_ID_NOT_IN_MODEL"
            ),
            "investment_product_id": value,
        }
        for value in included_not_in_model
    )

    write_csv(
        OUTPUT_ROOT
        / "collector_universe_reconciliation_mismatches.csv",
        mismatch_rows,
    )

    counts = Counter(
        row["universe_classification"]
        for row in results
    )

    manifest = {
        "status": (
            "PASS"
            if (
                not review
                and not missing_from_registry
                and not included_not_in_model
            )
            else "REVIEW_REQUIRED"
        ),
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "registry_display_type_rows": len(
            registry_candidates
        ),
        "filtered_display_rows": len(included),
        "excluded_configuration_rows": len(excluded),
        "manual_review_rows": len(review),
        "model_identity_rows": len(model_ids),
        "model_ids_missing_from_filtered_registry": (
            len(missing_from_registry)
        ),
        "filtered_registry_ids_missing_from_model": (
            len(included_not_in_model)
        ),
        "classification_counts": dict(counts),
        "required_equation": (
            "filtered_display_ids == model_input_ids"
        ),
    }

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    (
        OUTPUT_ROOT
        / "collector_universe_audit_manifest.json"
    ).write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print("COLLECTOR UNIVERSE AUDIT COMPLETE")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()