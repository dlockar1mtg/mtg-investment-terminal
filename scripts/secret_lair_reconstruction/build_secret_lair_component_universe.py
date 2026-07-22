from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

EVIDENCE_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "external_discovery"
    / "tcgcsv"
    / "tcgcsv_secret_lair_product_evidence_2026-07-22.csv"
)

REGISTRY_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "secret_lair_registry_seed_2026-07-22.csv"
)

STAGING_ROOT = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "secret_lair_reconstruction"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "secret_lair_reconstruction"
)

CLASSIFIED_PATH = (
    VALIDATION_ROOT
    / "secret_lair_full_catalog_classification_2026-07-22.csv"
)

COMPONENT_PATH = (
    STAGING_ROOT
    / "secret_lair_component_universe_2026-07-22.csv"
)

REVIEW_PATH = (
    VALIDATION_ROOT
    / "secret_lair_component_universe_review_queue_2026-07-22.csv"
)

SUMMARY_PATH = (
    VALIDATION_ROOT
    / "secret_lair_component_universe_summary_2026-07-22.json"
)

CLASSIFIED_COLUMNS = [
    "snapshot_record_id",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "tcgplayer_product_id",
    "group_name",
    "group_published_on",
    "product_name",
    "catalog_class",
    "sealed_component_candidate",
    "finish_class",
    "classification_confidence",
    "classification_reason",
    "already_in_registry_seed",
    "requires_review",
    "mapping_allowed",
    "scoring_allowed",
    "universal_investable_allowed",
]

COMPONENT_COLUMNS = [
    "snapshot_record_id",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "tcgplayer_product_id",
    "group_name",
    "group_published_on",
    "product_name",
    "catalog_class",
    "finish_class",
    "classification_confidence",
    "classification_reason",
    "already_in_registry_seed",
    "component_identity_state",
    "component_quantity",
    "mapping_allowed",
    "scoring_allowed",
    "universal_investable_allowed",
]

REVIEW_COLUMNS = [
    "tcgplayer_product_id",
    "group_name",
    "product_name",
    "catalog_class",
    "finish_class",
    "classification_confidence",
    "classification_reason",
]


def clean(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def normalized_id(value: Any) -> str:
    text = clean(value)

    if text.endswith(".0"):
        text = text[:-2]

    return text


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def normalize_text(value: Any) -> str:
    text = (
        clean(value)
        .lower()
        .replace("’", "'")
        .replace("–", "-")
        .replace("—", "-")
        .replace("&", " and ")
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Required input is missing: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        return [
            {
                clean(key): clean(value)
                for key, value in row.items()
            }
            for row in csv.DictReader(handle)
        ]


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    columns: list[str],
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
            fieldnames=columns,
            extrasaction="ignore",
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    column: row.get(column, "")
                    for column in columns
                }
            )


def classify_finish(product_name: str) -> str:
    text = normalize_text(product_name)

    if "raised foil" in text:
        return "raised_foil"

    if "rainbow foil" in text or "double rainbow foil" in text:
        return "rainbow_foil"

    if "galaxy foil" in text:
        return "galaxy_foil"

    if "halo foil" in text:
        return "halo_foil"

    if "etched foil" in text or "foil etched" in text:
        return "etched_foil"

    if "traditional foil" in text:
        return "traditional_foil"

    if any(
        phrase in text
        for phrase in (
            "non-foil",
            "non foil",
            "nonfoil",
        )
    ):
        return "nonfoil"

    if "foil" in text:
        return "foil"

    return "unspecified"


def classify_product(
    product_name: str,
) -> tuple[str, bool, str, str]:
    text = normalize_text(product_name)

    bundle_terms = (
        "bundle",
        "goodie bag",
        "gift bag",
        "everything package",
    )

    accessory_terms = (
        "playmat",
        "deck box",
        "card sleeves",
        "sleeves",
        "accessory",
    )

    sealed_drop_prefixes = (
        "secret lair drop:",
        "secret lair drop series:",
        "secret lair x ",
    )

    if any(
        term in text
        for term in accessory_terms
    ):
        return (
            "accessory",
            False,
            "high",
            "Accessory terminology appears in product_name.",
        )

    if any(
        phrase in text
        for phrase in (
            "festival in a box",
            "festival-in-a-box",
            "convention edition",
        )
    ):
        return (
            "festival_or_convention_package",
            False,
            "high",
            "Festival or convention terminology appears in product_name.",
        )

    if any(
        term in text
        for term in bundle_terms
    ):
        return (
            "bundle_or_multi_product_package",
            False,
            "high",
            "Bundle or multi-product terminology appears in product_name.",
        )

    if (
        text.startswith(
            "secret lair commander deck:"
        )
        or text.startswith(
            "secret lair deck:"
        )
    ):
        return (
            "commander_deck",
            True,
            "high",
            "Recognized sealed-deck product prefix appears in product_name.",
        )

    if (
        text.startswith(
            "secret lair countdown kit:"
        )
        or (
            text.startswith("secret lair:")
            and "countdown kit" in text
        )
    ):
        return (
            "countdown_kit",
            True,
            "high",
            "Recognized sealed Countdown Kit name appears in product_name.",
        )

    if text.startswith(
        sealed_drop_prefixes
    ):
        return (
            "standalone_sealed_drop_candidate",
            True,
            "high",
            "Recognized sealed Secret Lair drop prefix appears in product_name.",
        )

    if text.startswith("secret lair:"):
        return (
            "other_secret_lair_sealed_candidate",
            True,
            "medium",
            "Generic Secret Lair product prefix requires confirmation.",
        )

    return (
        "likely_individual_card",
        False,
        "medium",
        "Product name lacks a recognized sealed-product prefix.",
    )


def main() -> int:
    evidence = read_csv(EVIDENCE_PATH)
    registry = read_csv(REGISTRY_PATH)

    if len(evidence) != 4347:
        raise RuntimeError(
            "Expected 4,347 TCGCSV evidence rows, "
            f"found {len(evidence)}."
        )

    if len(registry) != 254:
        raise RuntimeError(
            "Expected 254 registry rows, "
            f"found {len(registry)}."
        )

    registry_ids = {
        normalized_id(
            row.get("tcgplayer_product_id")
        )
        for row in registry
    }

    classified_rows: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []

    for row in evidence:
        product_id = normalized_id(
            row.get("tcgplayer_product_id")
        )

        product_name = clean(
            row.get("product_name")
        )

        (
            catalog_class,
            sealed_candidate,
            confidence,
            reason,
        ) = classify_product(product_name)

        already_in_registry = (
            product_id in registry_ids
        )

        requires_review = (
            confidence != "high"
            and catalog_class
            != "likely_individual_card"
        )

        classified_row = {
            "snapshot_record_id": clean(
                row.get("snapshot_record_id")
            ),
            "tcgcsv_category_id": clean(
                row.get("tcgcsv_category_id")
            ),
            "tcgcsv_group_id": clean(
                row.get("tcgcsv_group_id")
            ),
            "tcgplayer_product_id": product_id,
            "group_name": clean(
                row.get("group_name")
            ),
            "group_published_on": clean(
                row.get("group_published_on")
            ),
            "product_name": product_name,
            "catalog_class": catalog_class,
            "sealed_component_candidate": (
                bool_text(sealed_candidate)
            ),
            "finish_class": classify_finish(
                product_name
            ),
            "classification_confidence": confidence,
            "classification_reason": reason,
            "already_in_registry_seed": (
                bool_text(already_in_registry)
            ),
            "requires_review": bool_text(
                requires_review
            ),
            "mapping_allowed": "false",
            "scoring_allowed": "false",
            "universal_investable_allowed": "false",
        }

        classified_rows.append(classified_row)

        if (
            sealed_candidate
            and not already_in_registry
        ):
            component_rows.append(
                {
                    "snapshot_record_id": (
                        classified_row[
                            "snapshot_record_id"
                        ]
                    ),
                    "tcgcsv_category_id": (
                        classified_row[
                            "tcgcsv_category_id"
                        ]
                    ),
                    "tcgcsv_group_id": (
                        classified_row[
                            "tcgcsv_group_id"
                        ]
                    ),
                    "tcgplayer_product_id": (
                        product_id
                    ),
                    "group_name": (
                        classified_row[
                            "group_name"
                        ]
                    ),
                    "group_published_on": (
                        classified_row[
                            "group_published_on"
                        ]
                    ),
                    "product_name": product_name,
                    "catalog_class": catalog_class,
                    "finish_class": (
                        classified_row[
                            "finish_class"
                        ]
                    ),
                    "classification_confidence": (
                        confidence
                    ),
                    "classification_reason": reason,
                    "already_in_registry_seed": (
                        "false"
                    ),
                    "component_identity_state": (
                        "candidate_pending_official_confirmation"
                    ),
                    "component_quantity": "",
                    "mapping_allowed": "false",
                    "scoring_allowed": "false",
                    "universal_investable_allowed": (
                        "false"
                    ),
                }
            )

        if requires_review:
            review_rows.append(
                {
                    column: classified_row.get(
                        column,
                        "",
                    )
                    for column in REVIEW_COLUMNS
                }
            )

    classified_rows.sort(
        key=lambda row: (
            row["catalog_class"],
            row["product_name"].lower(),
            row["tcgplayer_product_id"],
        )
    )

    component_rows.sort(
        key=lambda row: (
            row["catalog_class"],
            row["product_name"].lower(),
            row["tcgplayer_product_id"],
        )
    )

    review_rows.sort(
        key=lambda row: (
            row["catalog_class"],
            row["product_name"].lower(),
        )
    )

    write_csv(
        CLASSIFIED_PATH,
        classified_rows,
        CLASSIFIED_COLUMNS,
    )

    write_csv(
        COMPONENT_PATH,
        component_rows,
        COMPONENT_COLUMNS,
    )

    write_csv(
        REVIEW_PATH,
        review_rows,
        REVIEW_COLUMNS,
    )

    class_counts = Counter(
        row["catalog_class"]
        for row in classified_rows
    )

    component_class_counts = Counter(
        row["catalog_class"]
        for row in component_rows
    )

    component_ids = [
        row["tcgplayer_product_id"]
        for row in component_rows
    ]

    duplicate_component_ids = (
        len(component_ids)
        - len(set(component_ids))
    )

    suspicious_kit_rows = [
        row
        for row in component_rows
        if (
            row["catalog_class"]
            == "countdown_kit"
            and "countdown kit"
            not in normalize_text(
                row["product_name"]
            )
        )
    ]

    suspicious_deck_rows = [
        row
        for row in component_rows
        if (
            row["catalog_class"]
            == "commander_deck"
            and not (
                normalize_text(
                    row["product_name"]
                ).startswith(
                    "secret lair commander deck:"
                )
                or normalize_text(
                    row["product_name"]
                ).startswith(
                    "secret lair deck:"
                )
            )
        )
    ]

    certification_status = (
        "PASS"
        if (
            len(classified_rows) == 4347
            and duplicate_component_ids == 0
            and not suspicious_kit_rows
            and not suspicious_deck_rows
            and len(component_rows) > 100
        )
        else "PARTIAL"
    )

    generated_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    summary = {
        "schema_version": "10.5R.3.5A.1",
        "generated_at_utc": generated_at,
        "certification_status": (
            certification_status
        ),
        "tcgcsv_evidence_rows": len(evidence),
        "registry_seed_rows": len(registry),
        "classified_catalog_rows": len(
            classified_rows
        ),
        "component_universe_rows": len(
            component_rows
        ),
        "component_universe_unique_product_ids": (
            len(set(component_ids))
        ),
        "duplicate_component_product_ids": (
            duplicate_component_ids
        ),
        "suspicious_countdown_kit_rows": len(
            suspicious_kit_rows
        ),
        "suspicious_commander_deck_rows": len(
            suspicious_deck_rows
        ),
        "review_queue_rows": len(
            review_rows
        ),
        "catalog_class_counts": dict(
            sorted(class_counts.items())
        ),
        "component_class_counts": dict(
            sorted(component_class_counts.items())
        ),
        "governance": {
            "component_identity_finalized": False,
            "bundle_mappings_created": False,
            "component_quantities_assigned": False,
            "derived_bundle_values_created": False,
            "production_registry_changed": False,
            "final_eligibility_assigned": False,
            "scoring_enabled": False,
            "universal_investable_enabled": False,
        },
        "outputs": {
            "full_classification": (
                CLASSIFIED_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "component_universe": (
                COMPONENT_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "review_queue": (
                REVIEW_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
        },
    }

    SUMMARY_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    SUMMARY_PATH.write_text(
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
        "Phase 10.5R.3.5A.1 Corrected "
        "Secret Lair Component Universe"
    )
    print("=" * 76)
    print(
        f"TCGCSV evidence rows: {len(evidence)}"
    )
    print(
        f"Classified catalog rows: "
        f"{len(classified_rows)}"
    )
    print(
        f"Component-universe rows: "
        f"{len(component_rows)}"
    )
    print(
        "Duplicate component IDs: "
        f"{duplicate_component_ids}"
    )
    print(
        "Suspicious Countdown Kit rows: "
        f"{len(suspicious_kit_rows)}"
    )
    print(
        "Suspicious Commander Deck rows: "
        f"{len(suspicious_deck_rows)}"
    )
    print(
        f"Review queue rows: "
        f"{len(review_rows)}"
    )
    print()
    print("Catalog classes:")

    for name, count in sorted(
        class_counts.items()
    ):
        print(f"  {name}: {count}")

    print()
    print("Component classes:")

    for name, count in sorted(
        component_class_counts.items()
    ):
        print(f"  {name}: {count}")

    print()
    print(
        "COMPONENT UNIVERSE STATUS: "
        + certification_status
    )
    print("Component identity finalized: NO")
    print("Bundle mappings created: NO")
    print("Derived bundle values created: NO")
    print("Final eligibility: NOT ASSIGNED")
    print("Scoring: DISABLED")
    print("Universal investable: DISABLED")
    print()
    print(
        "Summary: "
        + SUMMARY_PATH
        .relative_to(ROOT)
        .as_posix()
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())