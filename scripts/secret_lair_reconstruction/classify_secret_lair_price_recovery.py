from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

REGISTRY_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "secret_lair_registry_seed_2026-07-22.csv"
)

CURRENT_PRICES_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "secret_lair_current_prices_2026-07-22.csv"
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

CLASSIFICATION_PATH = (
    STAGING_ROOT
    / "secret_lair_price_recovery_candidates_2026-07-22.csv"
)

REVIEW_PATH = (
    VALIDATION_ROOT
    / "secret_lair_price_recovery_classification_review_2026-07-22.csv"
)

SUMMARY_PATH = (
    VALIDATION_ROOT
    / "secret_lair_price_recovery_classification_summary_2026-07-22.json"
)

OUTPUT_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_set_name",
    "canonical_product_name",
    "tcgcsv_group_name",
    "tcgcsv_product_name",
    "selected_subtype_name",
    "market_price",
    "low_price",
    "mid_price",
    "price_selection_state",
    "market_price_available",
    "recovery_required",
    "recovery_product_class",
    "finish_class",
    "bundle_scope",
    "component_mapping_required",
    "official_evidence_required",
    "external_market_evidence_required",
    "preferred_recovery_method",
    "classification_state",
    "classification_reason",
    "scoring_allowed",
    "universal_investable_allowed",
]

REVIEW_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_product_name",
    "recovery_product_class",
    "finish_class",
    "bundle_scope",
    "classification_state",
    "classification_reason",
    "preferred_recovery_method",
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


def normalized_text(*values: Any) -> str:
    combined = " ".join(
        clean(value)
        for value in values
        if clean(value)
    )

    return re.sub(
        r"\s+",
        " ",
        combined.lower()
        .replace("’", "'")
        .replace("–", "-")
        .replace("—", "-"),
    ).strip()


def classify_finish(text: str) -> str:
    if "raised foil" in text:
        return "raised_foil"

    if "rainbow foil" in text:
        return "rainbow_foil"

    if "galaxy foil" in text:
        return "galaxy_foil"

    if "etched foil" in text or "foil etched" in text:
        return "etched_foil"

    if "halo foil" in text:
        return "halo_foil"

    if (
        "non-foil" in text
        or "non foil" in text
        or "nonfoil" in text
    ):
        return "nonfoil"

    if "foil" in text:
        return "foil"

    return "unspecified"


def classify_product(
    text: str,
) -> tuple[str, str, str, str]:
    if any(
        phrase in text
        for phrase in (
            "festival in a box",
            "festival-in-a-box",
            "convention edition",
        )
    ):
        return (
            "festival_or_convention_box",
            "specialty_box",
            "review_required",
            "Festival or convention package detected.",
        )

    if any(
        phrase in text
        for phrase in (
            "commander deck",
            "secret lair deck",
        )
    ):
        return (
            "commander_deck",
            "standalone",
            "classified",
            "Commander deck terminology detected.",
        )

    if any(
        phrase in text
        for phrase in (
            "countdown kit",
            "countdown kit:",
        )
    ):
        return (
            "countdown_kit",
            "standalone",
            "classified",
            "Countdown kit terminology detected.",
        )

    if "playset bundle" in text:
        return (
            "playset_bundle",
            "multi_copy",
            "classified",
            "Playset bundle terminology detected.",
        )

    if "superdrop" in text and "bundle" in text:
        return (
            "superdrop_bundle",
            "multi_drop",
            "classified",
            "Superdrop bundle terminology detected.",
        )

    if "bundle" in text:
        return (
            "multi_drop_bundle",
            "multi_drop_or_multi_copy",
            "classified",
            "Bundle terminology detected.",
        )

    if any(
        phrase in text
        for phrase in (
            "deck box",
            "sleeves",
            "playmat",
            "accessory",
        )
    ):
        return (
            "accessory_or_accessory_bundle",
            "accessory",
            "review_required",
            "Accessory terminology detected.",
        )

    if any(
        phrase in text
        for phrase in (
            "drop series",
            "secret lair drop",
            "secret lair x",
        )
    ):
        return (
            "individual_sealed_drop",
            "standalone",
            "classified",
            "Individual Secret Lair drop terminology detected.",
        )

    return (
        "unresolved_product",
        "unknown",
        "review_required",
        "No governed product-class rule matched.",
    )


def recovery_method(
    product_class: str,
    has_market_price: bool,
) -> tuple[str, bool, bool, bool]:
    if has_market_price:
        return (
            "tcgcsv_market_price",
            False,
            False,
            False,
        )

    if product_class in {
        "superdrop_bundle",
        "multi_drop_bundle",
        "playset_bundle",
    }:
        return (
            "official_bundle_components_then_component_floor",
            True,
            True,
            True,
        )

    if product_class in {
        "festival_or_convention_box",
        "commander_deck",
        "countdown_kit",
    }:
        return (
            "official_identity_plus_external_exact_product_market",
            False,
            True,
            True,
        )

    if product_class == "individual_sealed_drop":
        return (
            "external_exact_product_market",
            False,
            True,
            True,
        )

    return (
        "manual_source_research",
        False,
        True,
        True,
    )


def main() -> int:
    registry = read_csv(REGISTRY_PATH)
    prices = read_csv(CURRENT_PRICES_PATH)

    if len(registry) != 254:
        raise RuntimeError(
            "Expected 254 registry rows, "
            f"found {len(registry)}."
        )

    if len(prices) != 254:
        raise RuntimeError(
            "Expected 254 current-price rows, "
            f"found {len(prices)}."
        )

    registry_by_id = {
        normalized_id(
            row.get("tcgplayer_product_id")
        ): row
        for row in registry
    }

    prices_by_id = {
        normalized_id(
            row.get("tcgplayer_product_id")
        ): row
        for row in prices
    }

    if len(registry_by_id) != 254:
        raise RuntimeError(
            "Registry contains duplicate or blank "
            "TCGplayer product IDs."
        )

    if len(prices_by_id) != 254:
        raise RuntimeError(
            "Current pricing contains duplicate or "
            "blank TCGplayer product IDs."
        )

    if set(registry_by_id) != set(prices_by_id):
        raise RuntimeError(
            "Registry and current-price identity sets "
            "do not match."
        )

    output_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []

    for product_id in sorted(
        registry_by_id,
        key=lambda value: int(value)
        if value.isdigit()
        else value,
    ):
        registry_row = registry_by_id[product_id]
        price_row = prices_by_id[product_id]

        text = normalized_text(
            registry_row.get(
                "canonical_product_name"
            ),
            registry_row.get(
                "canonical_product_type"
            ),
            registry_row.get(
                "tcgcsv_product_name"
            ),
            registry_row.get(
                "tcgcsv_group_name"
            ),
        )

        finish_class = classify_finish(text)

        (
            product_class,
            bundle_scope,
            classification_state,
            classification_reason,
        ) = classify_product(text)

        has_market_price = (
            clean(
                price_row.get(
                    "market_price_available"
                )
            ).lower()
            == "true"
        )

        (
            preferred_method,
            component_mapping_required,
            official_evidence_required,
            external_market_required,
        ) = recovery_method(
            product_class,
            has_market_price,
        )

        recovery_required = not has_market_price

        output_row = {
            "canonical_product_id": clean(
                registry_row.get(
                    "canonical_product_id"
                )
            ),
            "tcgplayer_product_id": product_id,
            "canonical_set_name": clean(
                registry_row.get(
                    "canonical_set_name"
                )
            ),
            "canonical_product_name": clean(
                registry_row.get(
                    "canonical_product_name"
                )
            ),
            "tcgcsv_group_name": clean(
                registry_row.get(
                    "tcgcsv_group_name"
                )
            ),
            "tcgcsv_product_name": clean(
                registry_row.get(
                    "tcgcsv_product_name"
                )
            ),
            "selected_subtype_name": clean(
                price_row.get(
                    "selected_subtype_name"
                )
            ),
            "market_price": clean(
                price_row.get("market_price")
            ),
            "low_price": clean(
                price_row.get("low_price")
            ),
            "mid_price": clean(
                price_row.get("mid_price")
            ),
            "price_selection_state": clean(
                price_row.get(
                    "price_selection_state"
                )
            ),
            "market_price_available": bool_text(
                has_market_price
            ),
            "recovery_required": bool_text(
                recovery_required
            ),
            "recovery_product_class": (
                product_class
            ),
            "finish_class": finish_class,
            "bundle_scope": bundle_scope,
            "component_mapping_required": (
                bool_text(
                    component_mapping_required
                )
            ),
            "official_evidence_required": (
                bool_text(
                    official_evidence_required
                )
            ),
            "external_market_evidence_required": (
                bool_text(
                    external_market_required
                )
            ),
            "preferred_recovery_method": (
                preferred_method
            ),
            "classification_state": (
                classification_state
            ),
            "classification_reason": (
                classification_reason
            ),
            "scoring_allowed": "false",
            "universal_investable_allowed": (
                "false"
            ),
        }

        output_rows.append(output_row)

        if (
            recovery_required
            and classification_state
            != "classified"
        ):
            review_rows.append(
                {
                    column: output_row.get(
                        column,
                        "",
                    )
                    for column in REVIEW_COLUMNS
                }
            )

    output_rows.sort(
        key=lambda row: (
            clean(
                row.get(
                    "recovery_product_class"
                )
            ),
            clean(
                row.get(
                    "canonical_product_name"
                )
            ).lower(),
        )
    )

    review_rows.sort(
        key=lambda row: (
            clean(
                row.get(
                    "recovery_product_class"
                )
            ),
            clean(
                row.get(
                    "canonical_product_name"
                )
            ).lower(),
        )
    )

    write_csv(
        CLASSIFICATION_PATH,
        output_rows,
        OUTPUT_COLUMNS,
    )

    write_csv(
        REVIEW_PATH,
        review_rows,
        REVIEW_COLUMNS,
    )

    missing_rows = [
        row
        for row in output_rows
        if row["recovery_required"] == "true"
    ]

    product_class_counts = Counter(
        row["recovery_product_class"]
        for row in missing_rows
    )

    finish_counts = Counter(
        row["finish_class"]
        for row in missing_rows
    )

    method_counts = Counter(
        row["preferred_recovery_method"]
        for row in missing_rows
    )

    classified_missing = sum(
        1
        for row in missing_rows
        if row["classification_state"]
        == "classified"
    )

    review_required = len(
        missing_rows
    ) - classified_missing

    certification_status = (
        "PASS"
        if (
            len(output_rows) == 254
            and len(missing_rows) == 183
            and review_required == 0
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
        "schema_version": "10.5R.3.4",
        "generated_at_utc": generated_at,
        "certification_status": (
            certification_status
        ),
        "registry_rows": len(registry),
        "classification_rows": len(
            output_rows
        ),
        "products_with_tcgcsv_market_price": (
            len(output_rows)
            - len(missing_rows)
        ),
        "products_requiring_price_recovery": (
            len(missing_rows)
        ),
        "classified_recovery_products": (
            classified_missing
        ),
        "classification_review_rows": (
            review_required
        ),
        "component_mapping_required_rows": (
            sum(
                1
                for row in missing_rows
                if row[
                    "component_mapping_required"
                ]
                == "true"
            )
        ),
        "product_class_counts": dict(
            sorted(
                product_class_counts.items()
            )
        ),
        "finish_class_counts": dict(
            sorted(finish_counts.items())
        ),
        "preferred_recovery_method_counts": (
            dict(sorted(method_counts.items()))
        ),
        "governance": {
            "observed_prices_overwritten": False,
            "derived_prices_created": False,
            "production_registry_changed": False,
            "final_eligibility_assigned": False,
            "scoring_enabled": False,
            "universal_investable_enabled": False,
        },
        "outputs": {
            "classification": (
                CLASSIFICATION_PATH
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
        "Phase 10.5R.3.4 Secret Lair "
        "Price-Recovery Classification"
    )
    print("=" * 76)
    print(
        f"Classification rows: "
        f"{len(output_rows)}"
    )
    print(
        "Products with TCGCSV market price: "
        f"{len(output_rows) - len(missing_rows)}"
    )
    print(
        "Products requiring recovery: "
        f"{len(missing_rows)}"
    )
    print(
        "Classified recovery products: "
        f"{classified_missing}"
    )
    print(
        "Classification review rows: "
        f"{review_required}"
    )
    print()
    print("Missing-price product classes:")

    for name, count in sorted(
        product_class_counts.items()
    ):
        print(f"  {name}: {count}")

    print()
    print("Preferred recovery methods:")

    for name, count in sorted(
        method_counts.items()
    ):
        print(f"  {name}: {count}")

    print()
    print(
        "PRICE-RECOVERY CLASSIFICATION STATUS: "
        + certification_status
    )
    print("Observed prices overwritten: NO")
    print("Derived prices created: NO")
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