from __future__ import annotations

import csv
import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

COMPONENT_UNIVERSE_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "secret_lair_component_universe_2026-07-22.csv"
)

CACHE_ROOT = (
    ROOT
    / "data"
    / "raw"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "tcgcsv_current_prices"
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

CURRENT_PRICES_PATH = (
    STAGING_ROOT
    / "secret_lair_component_current_prices_2026-07-22.csv"
)

SUBTYPES_PATH = (
    VALIDATION_ROOT
    / "secret_lair_component_price_subtypes_2026-07-22.csv"
)

REVIEW_PATH = (
    VALIDATION_ROOT
    / "secret_lair_component_price_review_queue_2026-07-22.csv"
)

SUMMARY_PATH = (
    VALIDATION_ROOT
    / "secret_lair_component_price_summary_2026-07-22.json"
)

CURRENT_PRICE_COLUMNS = [
    "tcgplayer_product_id",
    "product_name",
    "catalog_class",
    "finish_class",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "selected_subtype_name",
    "market_price",
    "low_price",
    "mid_price",
    "high_price",
    "direct_low_price",
    "available_subtype_count",
    "available_subtypes",
    "market_price_available",
    "low_price_available",
    "mid_price_available",
    "price_selection_state",
    "price_selection_reason",
    "price_source",
    "component_identity_state",
    "mapping_allowed",
    "scoring_allowed",
    "universal_investable_allowed",
]

SUBTYPE_COLUMNS = [
    "tcgplayer_product_id",
    "product_name",
    "catalog_class",
    "finish_class",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "subtype_name",
    "market_price",
    "low_price",
    "mid_price",
    "high_price",
    "direct_low_price",
    "market_price_available",
    "low_price_available",
    "mid_price_available",
    "price_source",
]

REVIEW_COLUMNS = [
    "tcgplayer_product_id",
    "product_name",
    "catalog_class",
    "finish_class",
    "price_selection_state",
    "price_selection_reason",
    "available_subtype_count",
    "available_subtypes",
    "selected_subtype_name",
    "market_price",
    "low_price",
    "mid_price",
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


def parse_decimal(value: Any) -> Decimal | None:
    text = clean(value)

    if not text:
        return None

    try:
        parsed = Decimal(text)
    except InvalidOperation:
        return None

    if parsed <= 0:
        return None

    return parsed


def decimal_text(value: Any) -> str:
    parsed = parse_decimal(value)

    if parsed is None:
        return ""

    return format(parsed, "f")


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def normalize_subtype(value: Any) -> str:
    return (
        clean(value)
        .lower()
        .replace("-", " ")
        .replace("_", " ")
    )


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


def subtype_rank(
    finish_class: str,
    subtype_name: str,
) -> int:
    finish = clean(finish_class)
    subtype = normalize_subtype(subtype_name)

    if finish == "nonfoil":
        if subtype in {
            "normal",
            "non foil",
            "nonfoil",
        }:
            return 0

        if "foil" not in subtype:
            return 1

        return 50

    if finish == "traditional_foil":
        if subtype in {
            "foil",
            "holofoil",
        }:
            return 0

        if "foil" in subtype:
            return 1

        return 50

    if finish == "foil":
        if subtype in {
            "foil",
            "holofoil",
        }:
            return 0

        if "foil" in subtype:
            return 1

        return 50

    if finish == "rainbow_foil":
        if "rainbow" in subtype:
            return 0

        if "foil" in subtype:
            return 1

        return 50

    if finish == "raised_foil":
        if "raised" in subtype:
            return 0

        if "foil" in subtype:
            return 1

        return 50

    if finish == "galaxy_foil":
        if "galaxy" in subtype:
            return 0

        if "foil" in subtype:
            return 1

        return 50

    if finish == "halo_foil":
        if "halo" in subtype:
            return 0

        if "foil" in subtype:
            return 1

        return 50

    if finish == "etched_foil":
        if "etched" in subtype:
            return 0

        if "foil" in subtype:
            return 1

        return 50

    if subtype == "normal":
        return 10

    if subtype in {
        "foil",
        "holofoil",
    }:
        return 11

    return 20


def select_primary_price(
    component: dict[str, str],
    price_rows: list[dict[str, Any]],
) -> tuple[
    dict[str, Any] | None,
    str,
    str,
]:
    if not price_rows:
        return (
            None,
            "missing_price_record",
            "No cached TCGCSV price row matched the product ID.",
        )

    finish_class = clean(
        component.get("finish_class")
    )

    if len(price_rows) == 1:
        selected = price_rows[0]

        market_available = (
            parse_decimal(
                selected.get("marketPrice")
            )
            is not None
        )

        low_available = (
            parse_decimal(
                selected.get("lowPrice")
            )
            is not None
        )

        mid_available = (
            parse_decimal(
                selected.get("midPrice")
            )
            is not None
        )

        if market_available:
            return (
                selected,
                "exact_product_market_selected",
                "One cached price row matched the exact "
                "TCGplayer product ID. Product finish is "
                "encoded in the sealed-product identity.",
            )

        if low_available or mid_available:
            return (
                selected,
                "exact_product_proxy_only",
                "One cached price row matched the exact "
                "TCGplayer product ID, but no market price "
                "was available.",
            )

        return (
            selected,
            "exact_product_no_usable_price",
            "One cached price row matched the exact "
            "TCGplayer product ID but contained no usable "
            "market, low, or mid price.",
        )

    ranked = sorted(
        price_rows,
        key=lambda row: (
            subtype_rank(
                finish_class,
                clean(row.get("subTypeName")),
            ),
            0
            if parse_decimal(
                row.get("marketPrice")
            )
            is not None
            else 1,
            0
            if parse_decimal(
                row.get("lowPrice")
            )
            is not None
            else 1,
            normalize_subtype(
                row.get("subTypeName")
            ),
        ),
    )

    selected = ranked[0]

    selected_rank = subtype_rank(
        finish_class,
        clean(selected.get("subTypeName")),
    )

    same_rank_count = sum(
        1
        for row in ranked
        if subtype_rank(
            finish_class,
            clean(row.get("subTypeName")),
        )
        == selected_rank
    )

    market_available = (
        parse_decimal(
            selected.get("marketPrice")
        )
        is not None
    )

    low_available = (
        parse_decimal(
            selected.get("lowPrice")
        )
        is not None
    )

    mid_available = (
        parse_decimal(
            selected.get("midPrice")
        )
        is not None
    )

    if finish_class == "unspecified":
        if len(price_rows) == 1:
            if market_available:
                return (
                    selected,
                    "single_subtype_market_selected",
                    "Only one subtype was available and it had a market price.",
                )

            if low_available or mid_available:
                return (
                    selected,
                    "single_subtype_proxy_only",
                    "Only one subtype was available, but no market price existed.",
                )

            return (
                selected,
                "single_subtype_no_usable_price",
                "Only one subtype was available with no usable market, low, or mid price.",
            )

        return (
            selected,
            "unspecified_finish_multiple_subtypes",
            "The product finish is unspecified and multiple subtypes are available.",
        )

    if selected_rank >= 50:
        return (
            selected,
            "finish_subtype_mismatch",
            "No cached subtype matched the classified product finish.",
        )

    if same_rank_count > 1:
        return (
            selected,
            "multiple_matching_subtypes",
            "More than one cached subtype matched the product finish.",
        )

    if market_available:
        return (
            selected,
            "exact_finish_market_selected",
            "The selected subtype matched the product finish and had a market price.",
        )

    if low_available or mid_available:
        return (
            selected,
            "exact_finish_proxy_only",
            "The selected subtype matched the finish but lacked a market price.",
        )

    return (
        selected,
        "exact_finish_no_usable_price",
        "The selected subtype matched the finish but had no usable price fields.",
    )


def load_cached_prices() -> tuple[
    dict[str, list[dict[str, Any]]],
    list[str],
]:
    cache_files = sorted(
        CACHE_ROOT.rglob("prices.json")
    )

    if not cache_files:
        raise FileNotFoundError(
            f"No cached TCGCSV price files found under: {CACHE_ROOT}"
        )

    prices_by_product_id: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    cache_paths: list[str] = []

    for cache_path in cache_files:
        payload = json.loads(
            cache_path.read_text(
                encoding="utf-8"
            )
        )

        results = payload.get(
            "results",
            [],
        )

        if not isinstance(results, list):
            raise RuntimeError(
                f"Invalid cached results array: {cache_path}"
            )

        cache_paths.append(
            cache_path
            .relative_to(ROOT)
            .as_posix()
        )

        for price_row in results:
            product_id = normalized_id(
                price_row.get("productId")
            )

            if not product_id:
                continue

            prices_by_product_id.setdefault(
                product_id,
                [],
            ).append(price_row)

    return prices_by_product_id, cache_paths


def main() -> int:
    components = read_csv(
        COMPONENT_UNIVERSE_PATH
    )

    if len(components) != 733:
        raise RuntimeError(
            "Expected 733 component-universe rows, "
            f"found {len(components)}."
        )

    component_ids = [
        normalized_id(
            row.get("tcgplayer_product_id")
        )
        for row in components
    ]

    if any(not value for value in component_ids):
        raise RuntimeError(
            "Component universe contains blank TCGplayer product IDs."
        )

    if len(component_ids) != len(
        set(component_ids)
    ):
        raise RuntimeError(
            "Component universe contains duplicate TCGplayer product IDs."
        )

    (
        prices_by_product_id,
        cache_paths,
    ) = load_cached_prices()

    current_rows: list[dict[str, Any]] = []
    subtype_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []

    for component in components:
        product_id = normalized_id(
            component.get(
                "tcgplayer_product_id"
            )
        )

        price_rows = prices_by_product_id.get(
            product_id,
            [],
        )

        selected, state, reason = (
            select_primary_price(
                component,
                price_rows,
            )
        )

        selected = selected or {}

        subtype_names = sorted(
            {
                clean(
                    row.get("subTypeName")
                )
                or "blank"
                for row in price_rows
            }
        )

        for price_row in sorted(
            price_rows,
            key=lambda row: normalize_subtype(
                row.get("subTypeName")
            ),
        ):
            market_price = decimal_text(
                price_row.get("marketPrice")
            )

            low_price = decimal_text(
                price_row.get("lowPrice")
            )

            mid_price = decimal_text(
                price_row.get("midPrice")
            )

            subtype_rows.append(
                {
                    "tcgplayer_product_id": (
                        product_id
                    ),
                    "product_name": clean(
                        component.get(
                            "product_name"
                        )
                    ),
                    "catalog_class": clean(
                        component.get(
                            "catalog_class"
                        )
                    ),
                    "finish_class": clean(
                        component.get(
                            "finish_class"
                        )
                    ),
                    "tcgcsv_category_id": clean(
                        component.get(
                            "tcgcsv_category_id"
                        )
                    ),
                    "tcgcsv_group_id": clean(
                        component.get(
                            "tcgcsv_group_id"
                        )
                    ),
                    "subtype_name": clean(
                        price_row.get(
                            "subTypeName"
                        )
                    ),
                    "market_price": (
                        market_price
                    ),
                    "low_price": low_price,
                    "mid_price": mid_price,
                    "high_price": decimal_text(
                        price_row.get(
                            "highPrice"
                        )
                    ),
                    "direct_low_price": (
                        decimal_text(
                            price_row.get(
                                "directLowPrice"
                            )
                        )
                    ),
                    "market_price_available": (
                        bool_text(
                            bool(market_price)
                        )
                    ),
                    "low_price_available": (
                        bool_text(
                            bool(low_price)
                        )
                    ),
                    "mid_price_available": (
                        bool_text(
                            bool(mid_price)
                        )
                    ),
                    "price_source": (
                        "tcgcsv_cached_current"
                    ),
                }
            )

        market_price = decimal_text(
            selected.get("marketPrice")
        )

        low_price = decimal_text(
            selected.get("lowPrice")
        )

        mid_price = decimal_text(
            selected.get("midPrice")
        )

        current_row = {
            "tcgplayer_product_id": product_id,
            "product_name": clean(
                component.get("product_name")
            ),
            "catalog_class": clean(
                component.get("catalog_class")
            ),
            "finish_class": clean(
                component.get("finish_class")
            ),
            "tcgcsv_category_id": clean(
                component.get(
                    "tcgcsv_category_id"
                )
            ),
            "tcgcsv_group_id": clean(
                component.get(
                    "tcgcsv_group_id"
                )
            ),
            "selected_subtype_name": clean(
                selected.get("subTypeName")
            ),
            "market_price": market_price,
            "low_price": low_price,
            "mid_price": mid_price,
            "high_price": decimal_text(
                selected.get("highPrice")
            ),
            "direct_low_price": (
                decimal_text(
                    selected.get(
                        "directLowPrice"
                    )
                )
            ),
            "available_subtype_count": len(
                price_rows
            ),
            "available_subtypes": "|".join(
                subtype_names
            ),
            "market_price_available": (
                bool_text(
                    bool(market_price)
                )
            ),
            "low_price_available": (
                bool_text(
                    bool(low_price)
                )
            ),
            "mid_price_available": (
                bool_text(
                    bool(mid_price)
                )
            ),
            "price_selection_state": state,
            "price_selection_reason": reason,
            "price_source": (
                "tcgcsv_cached_current"
            ),
            "component_identity_state": clean(
                component.get(
                    "component_identity_state"
                )
            ),
            "mapping_allowed": "false",
            "scoring_allowed": "false",
            "universal_investable_allowed": (
                "false"
            ),
        }

        current_rows.append(current_row)

        if state not in {
            "exact_product_market_selected",
            "exact_finish_market_selected",
            "single_subtype_market_selected",
        }:
            review_rows.append(
                {
                    "tcgplayer_product_id": (
                        product_id
                    ),
                    "product_name": (
                        current_row[
                            "product_name"
                        ]
                    ),
                    "catalog_class": (
                        current_row[
                            "catalog_class"
                        ]
                    ),
                    "finish_class": (
                        current_row[
                            "finish_class"
                        ]
                    ),
                    "price_selection_state": (
                        state
                    ),
                    "price_selection_reason": (
                        reason
                    ),
                    "available_subtype_count": (
                        len(price_rows)
                    ),
                    "available_subtypes": (
                        "|".join(
                            subtype_names
                        )
                    ),
                    "selected_subtype_name": (
                        current_row[
                            "selected_subtype_name"
                        ]
                    ),
                    "market_price": (
                        market_price
                    ),
                    "low_price": low_price,
                    "mid_price": mid_price,
                }
            )

    current_rows.sort(
        key=lambda row: (
            row["catalog_class"],
            row["product_name"].lower(),
            row["tcgplayer_product_id"],
        )
    )

    subtype_rows.sort(
        key=lambda row: (
            row["product_name"].lower(),
            row["tcgplayer_product_id"],
            normalize_subtype(
                row["subtype_name"]
            ),
        )
    )

    review_rows.sort(
        key=lambda row: (
            row["price_selection_state"],
            row["product_name"].lower(),
        )
    )

    write_csv(
        CURRENT_PRICES_PATH,
        current_rows,
        CURRENT_PRICE_COLUMNS,
    )

    write_csv(
        SUBTYPES_PATH,
        subtype_rows,
        SUBTYPE_COLUMNS,
    )

    write_csv(
        REVIEW_PATH,
        review_rows,
        REVIEW_COLUMNS,
    )

    state_counts = Counter(
        row["price_selection_state"]
        for row in current_rows
    )

    market_price_rows = sum(
        1
        for row in current_rows
        if row[
            "market_price_available"
        ]
        == "true"
    )

    low_price_rows = sum(
        1
        for row in current_rows
        if row["low_price_available"]
        == "true"
    )

    mid_price_rows = sum(
        1
        for row in current_rows
        if row["mid_price_available"]
        == "true"
    )

    no_price_record_rows = sum(
        1
        for row in current_rows
        if row["price_selection_state"]
        == "missing_price_record"
    )

    direct_market_rows = sum(
        1
        for row in current_rows
        if row["price_selection_state"]
        in {
            "exact_product_market_selected",
            "exact_finish_market_selected",
            "single_subtype_market_selected",
        }
    )

    certification_status = (
        "PASS"
        if (
            len(current_rows) == 733
            and len(set(component_ids)) == 733
            and len(cache_paths) >= 3
        )
        else "PARTIAL"
    )

    summary = {
        "schema_version": "10.5R.3.5B",
        "certification_status": (
            certification_status
        ),
        "component_universe_rows": len(
            components
        ),
        "current_price_rows": len(
            current_rows
        ),
        "subtype_price_rows": len(
            subtype_rows
        ),
        "cached_price_files_read": len(
            cache_paths
        ),
        "cached_price_files": cache_paths,
        "components_with_market_price": (
            market_price_rows
        ),
        "components_with_low_price": (
            low_price_rows
        ),
        "components_with_mid_price": (
            mid_price_rows
        ),
        "components_with_no_price_record": (
            no_price_record_rows
        ),
        "direct_market_selection_rows": (
            direct_market_rows
        ),
        "review_queue_rows": len(
            review_rows
        ),
        "price_selection_state_counts": dict(
            sorted(state_counts.items())
        ),
        "governance": {
            "network_requests_performed": False,
            "component_identity_finalized": False,
            "bundle_mappings_created": False,
            "component_quantities_assigned": False,
            "derived_bundle_values_created": False,
            "observed_prices_overwritten": False,
            "production_registry_changed": False,
            "final_eligibility_assigned": False,
            "scoring_enabled": False,
            "universal_investable_enabled": False,
        },
        "outputs": {
            "current_prices": (
                CURRENT_PRICES_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "subtype_prices": (
                SUBTYPES_PATH
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
        "Phase 10.5R.3.5B Secret Lair "
        "Component Pricing from Cache"
    )
    print("=" * 76)
    print(
        f"Component rows: {len(components)}"
    )
    print(
        f"Cached price files read: "
        f"{len(cache_paths)}"
    )
    print(
        f"Current-price rows: "
        f"{len(current_rows)}"
    )
    print(
        f"Subtype-price rows: "
        f"{len(subtype_rows)}"
    )
    print(
        "Components with market price: "
        f"{market_price_rows}"
    )
    print(
        "Components with low price: "
        f"{low_price_rows}"
    )
    print(
        "Components with mid price: "
        f"{mid_price_rows}"
    )
    print(
        "Components with no price record: "
        f"{no_price_record_rows}"
    )
    print(
        f"Review queue rows: "
        f"{len(review_rows)}"
    )
    print()
    print("Price-selection states:")

    for state, count in sorted(
        state_counts.items()
    ):
        print(f"  {state}: {count}")

    print()
    print(
        "COMPONENT PRICING STATUS: "
        + certification_status
    )
    print("Network requests performed: NO")
    print("Bundle mappings created: NO")
    print("Derived bundle values created: NO")
    print("Observed prices overwritten: NO")
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