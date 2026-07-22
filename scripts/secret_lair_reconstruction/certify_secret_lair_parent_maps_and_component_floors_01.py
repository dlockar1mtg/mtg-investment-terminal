from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

CONFIRMED_MAP_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "secret_lair_confirmed_component_map_01_2026-07-22.csv"
)

PARENT_COVERAGE_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "secret_lair_official_bundle_parent_coverage_01_2026-07-22.csv"
)

COMPONENT_PRICES_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "secret_lair_component_current_prices_2026-07-22.csv"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "secret_lair_reconstruction"
)

CERTIFIED_PARENT_MAP_PATH = (
    VALIDATION_ROOT
    / "secret_lair_certified_parent_map_01_2026-07-22.csv"
)

COMPONENT_FLOOR_PATH = (
    VALIDATION_ROOT
    / "secret_lair_bundle_component_floor_01_2026-07-22.csv"
)

COMPONENT_FLOOR_REVIEW_PATH = (
    VALIDATION_ROOT
    / "secret_lair_bundle_component_floor_review_01_2026-07-22.csv"
)

SUMMARY_PATH = (
    VALIDATION_ROOT
    / "secret_lair_bundle_component_floor_01_summary_2026-07-22.json"
)

CERTIFIED_PARENT_COLUMNS = [
    "evidence_batch",
    "parent_tcgplayer_product_id",
    "parent_canonical_product_id",
    "local_parent_product_name",
    "official_parent_product_name",
    "official_source_url",
    "official_component_rows",
    "resolved_component_rows",
    "official_total_component_quantity",
    "resolved_total_component_quantity",
    "unique_component_product_ids",
    "duplicate_component_ordinals",
    "official_evidence_complete",
    "component_resolution_complete",
    "quantity_reconciliation_complete",
    "parent_mapping_certified",
    "parent_mapping_state",
    "derived_component_floor_allowed",
    "observed_parent_price_overwritten",
    "production_registry_changed",
    "final_eligibility_assigned",
    "scoring_allowed",
    "universal_investable_allowed",
]

COMPONENT_FLOOR_COLUMNS = [
    "evidence_batch",
    "parent_tcgplayer_product_id",
    "parent_canonical_product_id",
    "local_parent_product_name",
    "official_parent_product_name",
    "official_source_url",
    "component_rows",
    "total_component_quantity",
    "market_priced_component_rows",
    "proxy_priced_component_rows",
    "missing_priced_component_rows",
    "market_priced_component_quantity",
    "proxy_priced_component_quantity",
    "missing_priced_component_quantity",
    "quantity_weighted_market_total",
    "quantity_weighted_low_total",
    "quantity_weighted_mid_total",
    "quantity_weighted_selected_total",
    "component_floor_price_basis",
    "component_floor_coverage_state",
    "component_floor_complete",
    "component_floor_is_observed_parent_price",
    "parent_mapping_certified",
    "derived_component_floor_allowed",
    "production_registry_changed",
    "final_eligibility_assigned",
    "scoring_allowed",
    "universal_investable_allowed",
]

REVIEW_COLUMNS = [
    "parent_tcgplayer_product_id",
    "local_parent_product_name",
    "component_tcgplayer_product_id",
    "component_product_name",
    "component_quantity",
    "market_price",
    "low_price",
    "mid_price",
    "selected_price",
    "price_selection_state",
    "review_reason",
]


def clean(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def normalize_id(value: Any) -> str:
    text = clean(value)

    if text.endswith(".0"):
        text = text[:-2]

    return text


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def decimal_or_none(
    value: Any,
) -> Decimal | None:
    text = clean(value)

    if not text:
        return None

    text = (
        text
        .replace("$", "")
        .replace(",", "")
    )

    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def decimal_text(
    value: Decimal | None,
) -> str:
    if value is None:
        return ""

    return format(
        value.quantize(Decimal("0.01")),
        "f",
    )


def read_csv(
    path: Path,
) -> list[dict[str, str]]:
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


def first_available(
    row: dict[str, str],
    names: tuple[str, ...],
) -> str:
    for name in names:
        value = clean(row.get(name))

        if value:
            return value

    return ""


def classify_price_state(
    price_row: dict[str, str],
) -> str:
    raw_state = first_available(
        price_row,
        (
            "price_selection_state",
            "pricing_state",
            "price_state",
            "selected_price_state",
        ),
    ).lower()

    if "market" in raw_state:
        return "market"

    if (
        "proxy" in raw_state
        or "low" in raw_state
        or "mid" in raw_state
    ):
        return "proxy"

    market_price = decimal_or_none(
        price_row.get("market_price")
    )

    selected_price = decimal_or_none(
        first_available(
            price_row,
            (
                "selected_price",
                "current_price",
                "reconstructed_price",
                "price",
            ),
        )
    )

    low_price = decimal_or_none(
        price_row.get("low_price")
    )

    mid_price = decimal_or_none(
        price_row.get("mid_price")
    )

    if market_price is not None:
        return "market"

    if (
        selected_price is not None
        or low_price is not None
        or mid_price is not None
    ):
        return "proxy"

    return "missing"


def selected_component_price(
    price_row: dict[str, str],
) -> tuple[Decimal | None, str]:
    market_price = decimal_or_none(
        price_row.get("market_price")
    )

    if market_price is not None:
        return market_price, "market_price"

    selected_price = decimal_or_none(
        first_available(
            price_row,
            (
                "selected_price",
                "current_price",
                "reconstructed_price",
                "price",
            ),
        )
    )

    if selected_price is not None:
        return selected_price, "selected_proxy_price"

    low_price = decimal_or_none(
        price_row.get("low_price")
    )

    if low_price is not None:
        return low_price, "low_price_proxy"

    mid_price = decimal_or_none(
        price_row.get("mid_price")
    )

    if mid_price is not None:
        return mid_price, "mid_price_proxy"

    return None, "missing"


def main() -> int:
    confirmed_map = read_csv(
        CONFIRMED_MAP_PATH
    )

    parent_coverage = read_csv(
        PARENT_COVERAGE_PATH
    )

    component_prices = read_csv(
        COMPONENT_PRICES_PATH
    )

    if len(confirmed_map) != 17:
        raise RuntimeError(
            "Expected 17 confirmed component rows, "
            f"found {len(confirmed_map)}."
        )

    if len(parent_coverage) != 10:
        raise RuntimeError(
            "Expected 10 parent-coverage rows, "
            f"found {len(parent_coverage)}."
        )

    if len(component_prices) != 733:
        raise RuntimeError(
            "Expected 733 component-price rows, "
            f"found {len(component_prices)}."
        )

    prices_by_id = {
        normalize_id(
            row.get("tcgplayer_product_id")
        ): row
        for row in component_prices
    }

    if len(prices_by_id) != 733:
        raise RuntimeError(
            "Component-price registry contains "
            "duplicate or blank product IDs."
        )

    coverage_by_parent_id = {
        normalize_id(
            row.get(
                "parent_tcgplayer_product_id"
            )
        ): row
        for row in parent_coverage
    }

    if len(coverage_by_parent_id) != 10:
        raise RuntimeError(
            "Parent-coverage registry contains "
            "duplicate or blank parent IDs."
        )

    map_rows_by_parent: dict[
        str,
        list[dict[str, str]],
    ] = {}

    for row in confirmed_map:
        parent_id = normalize_id(
            row.get(
                "parent_tcgplayer_product_id"
            )
        )

        map_rows_by_parent.setdefault(
            parent_id,
            [],
        ).append(row)

    if set(map_rows_by_parent) != set(
        coverage_by_parent_id
    ):
        raise RuntimeError(
            "Confirmed-map parent identity set "
            "does not match parent coverage."
        )

    certified_parent_rows: list[
        dict[str, Any]
    ] = []

    component_floor_rows: list[
        dict[str, Any]
    ] = []

    review_rows: list[
        dict[str, Any]
    ] = []

    for parent_id in sorted(
        map_rows_by_parent,
        key=lambda value: clean(
            coverage_by_parent_id[value].get(
                "local_parent_product_name"
            )
        ).lower(),
    ):
        coverage = coverage_by_parent_id[
            parent_id
        ]

        component_rows = sorted(
            map_rows_by_parent[parent_id],
            key=lambda row: int(
                clean(
                    row.get(
                        "official_component_ordinal"
                    )
                )
                or "0"
            ),
        )

        official_component_rows = int(
            clean(
                coverage.get(
                    "official_component_rows"
                )
            )
            or "0"
        )

        official_total_quantity = int(
            clean(
                coverage.get(
                    "official_total_component_quantity"
                )
            )
            or "0"
        )

        resolved_component_rows = len(
            component_rows
        )

        resolved_total_quantity = sum(
            int(
                clean(
                    row.get(
                        "component_quantity"
                    )
                )
                or "0"
            )
            for row in component_rows
        )

        ordinals = [
            clean(
                row.get(
                    "official_component_ordinal"
                )
            )
            for row in component_rows
        ]

        component_ids = [
            normalize_id(
                row.get(
                    "component_tcgplayer_product_id"
                )
            )
            for row in component_rows
        ]

        duplicate_ordinals = (
            len(ordinals)
            - len(set(ordinals))
        )

        official_complete = (
            clean(
                coverage.get(
                    "official_evidence_complete"
                )
            ).lower()
            == "true"
        )

        resolution_complete = (
            resolved_component_rows
            == official_component_rows
            and all(component_ids)
            and duplicate_ordinals == 0
        )

        quantity_complete = (
            resolved_total_quantity
            == official_total_quantity
            and official_total_quantity > 0
        )

        parent_mapping_certified = (
            official_complete
            and resolution_complete
            and quantity_complete
        )

        certified_parent_rows.append(
            {
                "evidence_batch": clean(
                    coverage.get(
                        "evidence_batch"
                    )
                ),
                "parent_tcgplayer_product_id": (
                    parent_id
                ),
                "parent_canonical_product_id": clean(
                    coverage.get(
                        "parent_canonical_product_id"
                    )
                ),
                "local_parent_product_name": clean(
                    coverage.get(
                        "local_parent_product_name"
                    )
                ),
                "official_parent_product_name": clean(
                    coverage.get(
                        "official_parent_product_name"
                    )
                ),
                "official_source_url": clean(
                    coverage.get(
                        "official_source_url"
                    )
                ),
                "official_component_rows": (
                    official_component_rows
                ),
                "resolved_component_rows": (
                    resolved_component_rows
                ),
                "official_total_component_quantity": (
                    official_total_quantity
                ),
                "resolved_total_component_quantity": (
                    resolved_total_quantity
                ),
                "unique_component_product_ids": (
                    len(set(component_ids))
                ),
                "duplicate_component_ordinals": (
                    duplicate_ordinals
                ),
                "official_evidence_complete": (
                    bool_text(official_complete)
                ),
                "component_resolution_complete": (
                    bool_text(
                        resolution_complete
                    )
                ),
                "quantity_reconciliation_complete": (
                    bool_text(quantity_complete)
                ),
                "parent_mapping_certified": (
                    bool_text(
                        parent_mapping_certified
                    )
                ),
                "parent_mapping_state": (
                    "certified_official_component_map"
                    if parent_mapping_certified
                    else "mapping_certification_failed"
                ),
                "derived_component_floor_allowed": (
                    bool_text(
                        parent_mapping_certified
                    )
                ),
                "observed_parent_price_overwritten": (
                    "false"
                ),
                "production_registry_changed": (
                    "false"
                ),
                "final_eligibility_assigned": (
                    "false"
                ),
                "scoring_allowed": "false",
                "universal_investable_allowed": (
                    "false"
                ),
            }
        )

        market_total = Decimal("0")
        low_total = Decimal("0")
        mid_total = Decimal("0")
        selected_total = Decimal("0")

        market_rows = 0
        proxy_rows = 0
        missing_rows = 0

        market_quantity = 0
        proxy_quantity = 0
        missing_quantity = 0

        selected_basis_counts: Counter[
            str
        ] = Counter()

        for component in component_rows:
            component_id = normalize_id(
                component.get(
                    "component_tcgplayer_product_id"
                )
            )

            quantity = int(
                clean(
                    component.get(
                        "component_quantity"
                    )
                )
                or "0"
            )

            price_row = prices_by_id.get(
                component_id,
                {},
            )

            market_price = decimal_or_none(
                price_row.get("market_price")
            )

            low_price = decimal_or_none(
                price_row.get("low_price")
            )

            mid_price = decimal_or_none(
                price_row.get("mid_price")
            )

            selected_price, selected_basis = (
                selected_component_price(
                    price_row
                )
            )

            price_state = classify_price_state(
                price_row
            )

            if market_price is not None:
                market_total += (
                    market_price * quantity
                )

            if low_price is not None:
                low_total += (
                    low_price * quantity
                )

            if mid_price is not None:
                mid_total += (
                    mid_price * quantity
                )

            if selected_price is not None:
                selected_total += (
                    selected_price * quantity
                )

                selected_basis_counts[
                    selected_basis
                ] += 1

            if price_state == "market":
                market_rows += 1
                market_quantity += quantity
            elif price_state == "proxy":
                proxy_rows += 1
                proxy_quantity += quantity
            else:
                missing_rows += 1
                missing_quantity += quantity

                review_rows.append(
                    {
                        "parent_tcgplayer_product_id": (
                            parent_id
                        ),
                        "local_parent_product_name": clean(
                            coverage.get(
                                "local_parent_product_name"
                            )
                        ),
                        "component_tcgplayer_product_id": (
                            component_id
                        ),
                        "component_product_name": clean(
                            component.get(
                                "component_product_name"
                            )
                        ),
                        "component_quantity": (
                            quantity
                        ),
                        "market_price": clean(
                            price_row.get(
                                "market_price"
                            )
                        ),
                        "low_price": clean(
                            price_row.get(
                                "low_price"
                            )
                        ),
                        "mid_price": clean(
                            price_row.get(
                                "mid_price"
                            )
                        ),
                        "selected_price": first_available(
                            price_row,
                            (
                                "selected_price",
                                "current_price",
                                "reconstructed_price",
                                "price",
                            ),
                        ),
                        "price_selection_state": (
                            first_available(
                                price_row,
                                (
                                    "price_selection_state",
                                    "pricing_state",
                                    "price_state",
                                    "selected_price_state",
                                ),
                            )
                        ),
                        "review_reason": (
                            "confirmed_component_has_no_usable_price"
                        ),
                    }
                )

        if not parent_mapping_certified:
            coverage_state = (
                "mapping_not_certified"
            )
            floor_complete = False
        elif missing_rows > 0:
            coverage_state = (
                "incomplete_component_pricing"
            )
            floor_complete = False
        elif proxy_rows > 0:
            coverage_state = (
                "complete_with_governed_proxy"
            )
            floor_complete = True
        else:
            coverage_state = (
                "complete_market_pricing"
            )
            floor_complete = True

        if not floor_complete:
            selected_total_output = ""
            price_basis = (
                "incomplete_no_certified_floor"
            )
        else:
            selected_total_output = decimal_text(
                selected_total
            )

            if proxy_rows > 0:
                price_basis = (
                    "quantity_weighted_market_and_proxy_prices"
                )
            else:
                price_basis = (
                    "quantity_weighted_market_prices"
                )

        component_floor_rows.append(
            {
                "evidence_batch": clean(
                    coverage.get(
                        "evidence_batch"
                    )
                ),
                "parent_tcgplayer_product_id": (
                    parent_id
                ),
                "parent_canonical_product_id": clean(
                    coverage.get(
                        "parent_canonical_product_id"
                    )
                ),
                "local_parent_product_name": clean(
                    coverage.get(
                        "local_parent_product_name"
                    )
                ),
                "official_parent_product_name": clean(
                    coverage.get(
                        "official_parent_product_name"
                    )
                ),
                "official_source_url": clean(
                    coverage.get(
                        "official_source_url"
                    )
                ),
                "component_rows": len(
                    component_rows
                ),
                "total_component_quantity": (
                    resolved_total_quantity
                ),
                "market_priced_component_rows": (
                    market_rows
                ),
                "proxy_priced_component_rows": (
                    proxy_rows
                ),
                "missing_priced_component_rows": (
                    missing_rows
                ),
                "market_priced_component_quantity": (
                    market_quantity
                ),
                "proxy_priced_component_quantity": (
                    proxy_quantity
                ),
                "missing_priced_component_quantity": (
                    missing_quantity
                ),
                "quantity_weighted_market_total": (
                    decimal_text(market_total)
                    if market_rows > 0
                    else ""
                ),
                "quantity_weighted_low_total": (
                    decimal_text(low_total)
                    if low_total > 0
                    else ""
                ),
                "quantity_weighted_mid_total": (
                    decimal_text(mid_total)
                    if mid_total > 0
                    else ""
                ),
                "quantity_weighted_selected_total": (
                    selected_total_output
                ),
                "component_floor_price_basis": (
                    price_basis
                ),
                "component_floor_coverage_state": (
                    coverage_state
                ),
                "component_floor_complete": (
                    bool_text(floor_complete)
                ),
                "component_floor_is_observed_parent_price": (
                    "false"
                ),
                "parent_mapping_certified": (
                    bool_text(
                        parent_mapping_certified
                    )
                ),
                "derived_component_floor_allowed": (
                    bool_text(floor_complete)
                ),
                "production_registry_changed": (
                    "false"
                ),
                "final_eligibility_assigned": (
                    "false"
                ),
                "scoring_allowed": "false",
                "universal_investable_allowed": (
                    "false"
                ),
            }
        )

    certified_parent_rows.sort(
        key=lambda row: (
            row[
                "local_parent_product_name"
            ].lower()
        )
    )

    component_floor_rows.sort(
        key=lambda row: (
            row[
                "local_parent_product_name"
            ].lower()
        )
    )

    review_rows.sort(
        key=lambda row: (
            row[
                "local_parent_product_name"
            ].lower(),
            row[
                "component_product_name"
            ].lower(),
        )
    )

    write_csv(
        CERTIFIED_PARENT_MAP_PATH,
        certified_parent_rows,
        CERTIFIED_PARENT_COLUMNS,
    )

    write_csv(
        COMPONENT_FLOOR_PATH,
        component_floor_rows,
        COMPONENT_FLOOR_COLUMNS,
    )

    write_csv(
        COMPONENT_FLOOR_REVIEW_PATH,
        review_rows,
        REVIEW_COLUMNS,
    )

    certified_parent_count = sum(
        row["parent_mapping_certified"]
        == "true"
        for row in certified_parent_rows
    )

    complete_floor_count = sum(
        row["component_floor_complete"]
        == "true"
        for row in component_floor_rows
    )

    coverage_state_counts = Counter(
        row[
            "component_floor_coverage_state"
        ]
        for row in component_floor_rows
    )

    certification_status = (
        "PASS"
        if (
            len(certified_parent_rows) == 10
            and len(component_floor_rows) == 10
            and certified_parent_count == 10
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
        "schema_version": "10.5R.3.6B.4",
        "generated_at_utc": generated_at,
        "certification_status": (
            certification_status
        ),
        "certified_parent_map_rows": len(
            certified_parent_rows
        ),
        "certified_parent_rows": (
            certified_parent_count
        ),
        "component_floor_rows": len(
            component_floor_rows
        ),
        "complete_component_floor_rows": (
            complete_floor_count
        ),
        "incomplete_component_floor_rows": (
            len(component_floor_rows)
            - complete_floor_count
        ),
        "component_floor_review_rows": len(
            review_rows
        ),
        "coverage_state_counts": dict(
            sorted(
                coverage_state_counts.items()
            )
        ),
        "governance": {
            "official_evidence_preserved": True,
            "parent_mappings_certified": (
                certified_parent_count == 10
            ),
            "derived_component_floors_created": (
                complete_floor_count > 0
            ),
            "component_floor_treated_as_observed_parent_price": (
                False
            ),
            "observed_parent_prices_overwritten": (
                False
            ),
            "production_registry_changed": False,
            "final_eligibility_assigned": False,
            "scoring_enabled": False,
            "universal_investable_enabled": False,
        },
        "outputs": {
            "certified_parent_map": (
                CERTIFIED_PARENT_MAP_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "bundle_component_floor": (
                COMPONENT_FLOOR_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "bundle_component_floor_review": (
                COMPONENT_FLOOR_REVIEW_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
        },
    }

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
        "Phase 10.5R.3.6B.4 Secret Lair "
        "Parent Mapping Certification and "
        "Component-Floor Valuation 01"
    )
    print("=" * 76)
    print(
        f"Certified parent-map rows: "
        f"{len(certified_parent_rows)}"
    )
    print(
        f"Certified parents: "
        f"{certified_parent_count}"
    )
    print(
        f"Component-floor rows: "
        f"{len(component_floor_rows)}"
    )
    print(
        f"Complete component floors: "
        f"{complete_floor_count}"
    )
    print(
        "Incomplete component floors: "
        f"{len(component_floor_rows) - complete_floor_count}"
    )
    print(
        f"Component-floor review rows: "
        f"{len(review_rows)}"
    )
    print()
    print("Coverage states:")

    for state, count in sorted(
        coverage_state_counts.items()
    ):
        print(f"  {state}: {count}")

    print()
    print(
        "PARENT MAPPING AND COMPONENT-FLOOR "
        "STATUS: "
        + certification_status
    )
    print(
        "Component floors are observed "
        "parent prices: NO"
    )
    print(
        "Observed parent prices overwritten: NO"
    )
    print("Production registry changed: NO")
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