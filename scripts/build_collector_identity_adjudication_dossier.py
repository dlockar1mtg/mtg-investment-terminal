from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TARGET_ID = "TCGCSV-2494-490512"

REGISTRY = (
    ROOT / "data" / "product_master" / "investment_products.csv"
)

MODEL = (
    ROOT / "data" / "product_master" / "product_master_model_input.csv"
)

HISTORY = (
    ROOT
    / "data"
    / "operations"
    / "mtg_universal_history_ledger"
    / "universal_mtg_daily_consolidated_ledger.csv"
)

OUTPUT = (
    ROOT
    / "data"
    / "operations"
    / "collector_booster_universe_audit"
    / "candidate_v1_0_0"
    / "mismatch_TCGCSV-2494-490512"
)


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize(value: Any) -> str:
    text = clean(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fields: list[str] = []

    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    registry = read_csv(REGISTRY)
    model = read_csv(MODEL)
    history = read_csv(HISTORY)

    exact_registry = [
        row
        for row in registry
        if clean(row.get("investment_product_id")) == TARGET_ID
    ]

    if len(exact_registry) != 1:
        raise RuntimeError(
            f"Expected one registry row for {TARGET_ID}; "
            f"found {len(exact_registry)}"
        )

    target = exact_registry[0]

    tcgplayer_id = clean(
        target.get("approved_tcgplayer_product_id")
    )
    set_name = normalize(target.get("set_name"))
    box_name = normalize(target.get("box_name"))
    approved_name = normalize(
        target.get("approved_product_name")
    )

    exact_model = [
        row
        for row in model
        if (
            clean(row.get("investment_product_id")) == TARGET_ID
            or (
                tcgplayer_id
                and clean(row.get("tcgplayer_product_id"))
                == tcgplayer_id
            )
        )
    ]

    related_registry = []

    for row in registry:
        comparison = normalize(
            f"{row.get('set_name', '')} "
            f"{row.get('box_name', '')} "
            f"{row.get('approved_product_name', '')}"
        )

        if (
            set_name and set_name in comparison
            or box_name and box_name in comparison
            or approved_name and approved_name in comparison
        ):
            related_registry.append(row)

    related_model = []

    for row in model:
        comparison = normalize(
            f"{row.get('set_name', '')} "
            f"{row.get('box_name', '')} "
            f"{row.get('product_name', '')}"
        )

        if set_name and set_name in comparison:
            related_model.append(row)

    matching_history = [
        row
        for row in history
        if (
            clean(row.get("investment_product_id")) == TARGET_ID
            or (
                tcgplayer_id
                and (
                    clean(row.get("tcgplayer_product_id"))
                    == tcgplayer_id
                    or clean(
                        row.get("approved_tcgplayer_product_id")
                    )
                    == tcgplayer_id
                )
            )
        )
    ]

    name_text = normalize(
        f"{target.get('box_name', '')} "
        f"{target.get('approved_product_name', '')}"
    )

    configuration_flags = []

    for term in (
        "master case",
        "box case",
        "display case",
        "case of",
        "mastercase",
        "booster pack",
        "single pack",
        "sample pack",
        "bundle",
    ):
        if normalize(term) in name_text:
            configuration_flags.append(term)

    possible_duplicate_ids = sorted({
        clean(row.get("investment_product_id"))
        for row in related_registry
        if clean(row.get("investment_product_id")) != TARGET_ID
    })

    history_dates = sorted({
        clean(
            row.get("observation_date")
            or row.get("date")
        )
        for row in matching_history
        if clean(
            row.get("observation_date")
            or row.get("date")
        )
    })

    if configuration_flags:
        preliminary_disposition = "EXCLUDE_CONFIGURATION"
    elif exact_model:
        preliminary_disposition = "MODEL_MAPPING_EXISTS"
    elif related_model:
        preliminary_disposition = "POSSIBLE_DUPLICATE_OR_REMAP"
    elif matching_history:
        preliminary_disposition = "MODEL_ADMISSION_REVIEW"
    else:
        preliminary_disposition = "UNSUPPORTED_REGISTRY_IDENTITY"

    manifest = {
        "status": "ADJUDICATION_REQUIRED",
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "target_id": TARGET_ID,
        "tcgplayer_product_id": tcgplayer_id,
        "set_name": clean(target.get("set_name")),
        "box_name": clean(target.get("box_name")),
        "approved_product_name": clean(
            target.get("approved_product_name")
        ),
        "investment_product_type": clean(
            target.get("investment_product_type")
        ),
        "approval_status": clean(
            target.get("approval_status")
        ),
        "approval_method": clean(
            target.get("approval_method")
        ),
        "configuration_flags": configuration_flags,
        "exact_model_rows": len(exact_model),
        "related_model_rows": len(related_model),
        "related_registry_rows": len(related_registry),
        "possible_duplicate_ids": possible_duplicate_ids,
        "history_rows": len(matching_history),
        "distinct_history_dates": len(history_dates),
        "first_history_date": (
            history_dates[0] if history_dates else None
        ),
        "latest_history_date": (
            history_dates[-1] if history_dates else None
        ),
        "preliminary_disposition": preliminary_disposition,
        "allowed_final_dispositions": [
            "ADD_TO_MODEL",
            "REMAP_TO_EXISTING_MODEL_ID",
            "EXCLUDE_CONFIGURATION",
            "RETIRE_DUPLICATE_REGISTRY_ID",
            "RETAIN_REGISTRY_HISTORY_ACCUMULATING",
            "MANUAL_IDENTITY_REVIEW",
        ],
        "production_changes_applied": False,
    }

    OUTPUT.mkdir(parents=True, exist_ok=True)

    write_csv(
        OUTPUT / "exact_registry_row.csv",
        exact_registry,
    )
    write_csv(
        OUTPUT / "exact_model_matches.csv",
        exact_model,
    )
    write_csv(
        OUTPUT / "related_registry_rows.csv",
        related_registry,
    )
    write_csv(
        OUTPUT / "related_model_rows.csv",
        related_model,
    )
    write_csv(
        OUTPUT / "matching_history_rows.csv",
        matching_history,
    )

    (
        OUTPUT / "identity_adjudication_manifest.json"
    ).write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print("IDENTITY ADJUDICATION DOSSIER COMPLETE")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()