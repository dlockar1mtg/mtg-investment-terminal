from __future__ import annotations

import csv
import hashlib
import json
import time
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]

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

CACHE_ROOT = (
    ROOT
    / "data"
    / "raw"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "tcgcsv_current_prices"
)

CURRENT_PRICES_PATH = (
    STAGING_ROOT
    / "secret_lair_current_prices_2026-07-22.csv"
)

ALL_SUBTYPES_PATH = (
    VALIDATION_ROOT
    / "secret_lair_current_price_subtypes_2026-07-22.csv"
)

REVIEW_QUEUE_PATH = (
    VALIDATION_ROOT
    / "secret_lair_current_price_review_queue_2026-07-22.csv"
)

FETCH_LOG_PATH = (
    VALIDATION_ROOT
    / "secret_lair_tcgcsv_price_fetch_log_2026-07-22.csv"
)

SUMMARY_PATH = (
    VALIDATION_ROOT
    / "secret_lair_current_price_summary_2026-07-22.json"
)

LAST_UPDATED_URL = "https://tcgcsv.com/last-updated.txt"

USER_AGENT = (
    "MTGInvestmentTerminal/"
    "10.5R.3.3 "
    "(Secret-Lair-Reconstruction)"
)

REQUEST_TIMEOUT_SECONDS = 60
REQUEST_DELAY_SECONDS = 0.25
MAX_ATTEMPTS = 3

PRIMARY_PRICE_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_set_name",
    "canonical_product_name",
    "canonical_product_type",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "tcgcsv_group_name",
    "tcgcsv_product_name",
    "selected_subtype_name",
    "market_price",
    "low_price",
    "mid_price",
    "high_price",
    "direct_low_price",
    "price_currency",
    "price_selection_state",
    "price_selection_reason",
    "available_subtype_count",
    "available_subtypes",
    "market_price_available",
    "tcgcsv_last_updated",
    "retrieved_at_utc",
    "source_url",
    "scoring_allowed",
    "universal_investable_allowed",
]

SUBTYPE_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_product_name",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "subtype_name",
    "market_price",
    "low_price",
    "mid_price",
    "high_price",
    "direct_low_price",
    "market_price_available",
    "source_url",
    "retrieved_at_utc",
]

REVIEW_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_product_name",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "review_state",
    "review_reason",
    "available_subtype_count",
    "available_subtypes",
    "selected_subtype_name",
    "market_price",
    "low_price",
    "mid_price",
    "source_url",
]

FETCH_LOG_COLUMNS = [
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "source_url",
    "fetch_state",
    "http_status",
    "attempts",
    "result_rows",
    "cache_path",
    "response_sha256",
    "error",
    "retrieved_at_utc",
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


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
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


def normalize_subtype(value: Any) -> str:
    return (
        clean(value)
        .lower()
        .replace("-", " ")
        .replace("_", " ")
    )


def product_finish_hint(
    registry_row: dict[str, str],
) -> str:
    combined = " ".join(
        [
            clean(
                registry_row.get(
                    "canonical_product_name"
                )
            ),
            clean(
                registry_row.get(
                    "canonical_product_type"
                )
            ),
            clean(
                registry_row.get(
                    "tcgcsv_product_name"
                )
            ),
        ]
    ).lower()

    if "etched" in combined:
        return "etched"

    if "rainbow foil" in combined:
        return "rainbow foil"

    if "galaxy foil" in combined:
        return "galaxy foil"

    if "foil" in combined:
        return "foil"

    if (
        "non-foil" in combined
        or "nonfoil" in combined
        or "non foil" in combined
    ):
        return "nonfoil"

    return "unknown"


def subtype_rank(
    finish_hint: str,
    subtype_name: str,
) -> int:
    subtype = normalize_subtype(subtype_name)

    if finish_hint == "etched":
        if "etched" in subtype:
            return 0

    if finish_hint == "rainbow foil":
        if "rainbow" in subtype:
            return 0
        if "foil" in subtype:
            return 1

    if finish_hint == "galaxy foil":
        if "galaxy" in subtype:
            return 0
        if "foil" in subtype:
            return 1

    if finish_hint == "foil":
        if subtype in {
            "foil",
            "holofoil",
        }:
            return 0

        if "foil" in subtype:
            return 1

    if finish_hint == "nonfoil":
        if subtype in {
            "normal",
            "non foil",
            "nonfoil",
        }:
            return 0

        if "foil" not in subtype:
            return 1

    if subtype == "normal":
        return 10

    if subtype in {
        "foil",
        "holofoil",
    }:
        return 11

    return 20


def choose_primary_price(
    registry_row: dict[str, str],
    prices: list[dict[str, Any]],
) -> tuple[
    dict[str, Any] | None,
    str,
    str,
]:
    if not prices:
        return (
            None,
            "missing_price",
            "No TCGCSV price rows matched the product ID.",
        )

    finish_hint = product_finish_hint(
        registry_row
    )

    ranked = sorted(
        prices,
        key=lambda row: (
            subtype_rank(
                finish_hint,
                clean(row.get("subTypeName")),
            ),
            0
            if parse_decimal(
                row.get("marketPrice")
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
        finish_hint,
        clean(selected.get("subTypeName")),
    )

    matching_rank_count = sum(
        1
        for row in ranked
        if subtype_rank(
            finish_hint,
            clean(row.get("subTypeName")),
        )
        == selected_rank
    )

    if finish_hint == "unknown":
        if len(prices) == 1:
            return (
                selected,
                "single_subtype_selected",
                "Only one TCGCSV subtype was available.",
            )

        return (
            selected,
            "ambiguous_finish_review",
            "Multiple price subtypes exist but the "
            "registry name does not identify a finish.",
        )

    if matching_rank_count > 1:
        return (
            selected,
            "multiple_matching_subtypes_review",
            "More than one subtype matched the "
            f"registry finish hint '{finish_hint}'.",
        )

    if selected_rank >= 20:
        return (
            selected,
            "finish_subtype_mismatch_review",
            "No TCGCSV subtype matched the "
            f"registry finish hint '{finish_hint}'.",
        )

    if parse_decimal(
        selected.get("marketPrice")
    ) is None:
        return (
            selected,
            "market_price_missing_review",
            "A matching subtype was found, but its "
            "market price was null, zero, or invalid.",
        )

    return (
        selected,
        "exact_finish_subtype_selected",
        "The selected TCGCSV subtype matched the "
        f"registry finish hint '{finish_hint}'.",
    )


def request_json(
    session: requests.Session,
    url: str,
) -> tuple[
    dict[str, Any] | None,
    int | None,
    int,
    str,
]:
    error = ""

    for attempt in range(
        1,
        MAX_ATTEMPTS + 1,
    ):
        try:
            response = session.get(
                url,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

            status = response.status_code

            if status == 200:
                payload = response.json()

                if not isinstance(payload, dict):
                    raise RuntimeError(
                        "TCGCSV response was not a JSON object."
                    )

                return payload, status, attempt, ""

            error = (
                f"HTTP {status}: "
                + response.text[:500]
            )

        except Exception as exc:
            status = None
            error = (
                f"{type(exc).__name__}: {exc}"
            )

        if attempt < MAX_ATTEMPTS:
            time.sleep(
                REQUEST_DELAY_SECONDS * attempt
            )

    return None, status, MAX_ATTEMPTS, error


def main() -> int:
    registry = read_csv(REGISTRY_PATH)

    if len(registry) != 254:
        raise RuntimeError(
            "Expected 254 registry seed rows, "
            f"found {len(registry)}."
        )

    required_columns = {
        "canonical_product_id",
        "tcgplayer_product_id",
        "canonical_product_name",
        "tcgcsv_category_id",
        "tcgcsv_group_id",
        "scoring_allowed",
        "universal_investable_allowed",
    }

    missing_columns = sorted(
        required_columns - set(registry[0])
    )

    if missing_columns:
        raise RuntimeError(
            "Registry seed is missing columns: "
            + ", ".join(missing_columns)
        )

    product_ids = [
        normalized_id(
            row.get("tcgplayer_product_id")
        )
        for row in registry
    ]

    if any(not value for value in product_ids):
        raise RuntimeError(
            "Registry seed contains blank "
            "TCGplayer product IDs."
        )

    if len(product_ids) != len(set(product_ids)):
        raise RuntimeError(
            "Registry seed contains duplicate "
            "TCGplayer product IDs."
        )

    groups = sorted(
        {
            (
                normalized_id(
                    row.get("tcgcsv_category_id")
                ),
                normalized_id(
                    row.get("tcgcsv_group_id")
                ),
            )
            for row in registry
        }
    )

    if any(
        not category_id or not group_id
        for category_id, group_id in groups
    ):
        raise RuntimeError(
            "Registry seed contains blank TCGCSV "
            "category or group IDs."
        )

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
    )

    retrieved_at = utc_now()

    try:
        last_updated_response = session.get(
            LAST_UPDATED_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        if last_updated_response.status_code == 200:
            tcgcsv_last_updated = (
                last_updated_response.text.strip()
            )
        else:
            tcgcsv_last_updated = ""

    except requests.RequestException:
        tcgcsv_last_updated = ""

    prices_by_product_id: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    fetch_log_rows: list[dict[str, Any]] = []

    CACHE_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    for index, (
        category_id,
        group_id,
    ) in enumerate(groups, start=1):
        url = (
            "https://tcgcsv.com/tcgplayer/"
            f"{category_id}/{group_id}/prices"
        )

        payload, status, attempts, error = (
            request_json(
                session,
                url,
            )
        )

        cache_path = (
            CACHE_ROOT
            / category_id
            / group_id
            / "prices.json"
        )

        result_rows: list[dict[str, Any]] = []
        response_sha256 = ""
        fetch_state = "failed"

        if payload is not None:
            result_rows = payload.get(
                "results",
                [],
            )

            if not isinstance(result_rows, list):
                raise RuntimeError(
                    f"Invalid results collection: {url}"
                )

            cache_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            serialized = (
                json.dumps(
                    payload,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )

            cache_path.write_text(
                serialized,
                encoding="utf-8",
            )

            response_sha256 = hashlib.sha256(
                serialized.encode("utf-8")
            ).hexdigest()

            fetch_state = "success"

            for price_row in result_rows:
                product_id = normalized_id(
                    price_row.get("productId")
                )

                if not product_id:
                    continue

                prices_by_product_id.setdefault(
                    product_id,
                    [],
                ).append(price_row)

        fetch_log_rows.append(
            {
                "tcgcsv_category_id": category_id,
                "tcgcsv_group_id": group_id,
                "source_url": url,
                "fetch_state": fetch_state,
                "http_status": (
                    status
                    if status is not None
                    else ""
                ),
                "attempts": attempts,
                "result_rows": len(result_rows),
                "cache_path": (
                    cache_path
                    .relative_to(ROOT)
                    .as_posix()
                    if payload is not None
                    else ""
                ),
                "response_sha256": response_sha256,
                "error": error,
                "retrieved_at_utc": retrieved_at,
            }
        )

        print(
            f"[{index}/{len(groups)}] "
            f"category={category_id} "
            f"group={group_id} "
            f"state={fetch_state} "
            f"rows={len(result_rows)}"
        )

        if index < len(groups):
            time.sleep(REQUEST_DELAY_SECONDS)

    primary_rows: list[dict[str, Any]] = []
    subtype_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []

    for registry_row in registry:
        product_id = normalized_id(
            registry_row.get(
                "tcgplayer_product_id"
            )
        )

        prices = prices_by_product_id.get(
            product_id,
            [],
        )

        selected, state, reason = (
            choose_primary_price(
                registry_row,
                prices,
            )
        )

        subtype_names = sorted(
            {
                clean(
                    price.get("subTypeName")
                )
                or "blank"
                for price in prices
            }
        )

        source_url = (
            "https://tcgcsv.com/tcgplayer/"
            f"{normalized_id(registry_row.get('tcgcsv_category_id'))}/"
            f"{normalized_id(registry_row.get('tcgcsv_group_id'))}/"
            "prices"
        )

        for price in sorted(
            prices,
            key=lambda row: normalize_subtype(
                row.get("subTypeName")
            ),
        ):
            market_price = decimal_text(
                price.get("marketPrice")
            )

            subtype_rows.append(
                {
                    "canonical_product_id": clean(
                        registry_row.get(
                            "canonical_product_id"
                        )
                    ),
                    "tcgplayer_product_id": product_id,
                    "canonical_product_name": clean(
                        registry_row.get(
                            "canonical_product_name"
                        )
                    ),
                    "tcgcsv_category_id": clean(
                        registry_row.get(
                            "tcgcsv_category_id"
                        )
                    ),
                    "tcgcsv_group_id": clean(
                        registry_row.get(
                            "tcgcsv_group_id"
                        )
                    ),
                    "subtype_name": clean(
                        price.get("subTypeName")
                    ),
                    "market_price": market_price,
                    "low_price": decimal_text(
                        price.get("lowPrice")
                    ),
                    "mid_price": decimal_text(
                        price.get("midPrice")
                    ),
                    "high_price": decimal_text(
                        price.get("highPrice")
                    ),
                    "direct_low_price": decimal_text(
                        price.get("directLowPrice")
                    ),
                    "market_price_available": (
                        bool_text(bool(market_price))
                    ),
                    "source_url": source_url,
                    "retrieved_at_utc": retrieved_at,
                }
            )

        selected = selected or {}

        selected_market_price = decimal_text(
            selected.get("marketPrice")
        )

        primary_row = {
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
            "canonical_product_type": clean(
                registry_row.get(
                    "canonical_product_type"
                )
            ),
            "tcgcsv_category_id": clean(
                registry_row.get(
                    "tcgcsv_category_id"
                )
            ),
            "tcgcsv_group_id": clean(
                registry_row.get(
                    "tcgcsv_group_id"
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
                selected.get("subTypeName")
            ),
            "market_price": selected_market_price,
            "low_price": decimal_text(
                selected.get("lowPrice")
            ),
            "mid_price": decimal_text(
                selected.get("midPrice")
            ),
            "high_price": decimal_text(
                selected.get("highPrice")
            ),
            "direct_low_price": decimal_text(
                selected.get("directLowPrice")
            ),
            "price_currency": "USD",
            "price_selection_state": state,
            "price_selection_reason": reason,
            "available_subtype_count": len(prices),
            "available_subtypes": "|".join(
                subtype_names
            ),
            "market_price_available": bool_text(
                bool(selected_market_price)
            ),
            "tcgcsv_last_updated": (
                tcgcsv_last_updated
            ),
            "retrieved_at_utc": retrieved_at,
            "source_url": source_url,
            "scoring_allowed": "false",
            "universal_investable_allowed": "false",
        }

        primary_rows.append(primary_row)

        if state not in {
            "exact_finish_subtype_selected",
            "single_subtype_selected",
        }:
            review_rows.append(
                {
                    "canonical_product_id": (
                        primary_row[
                            "canonical_product_id"
                        ]
                    ),
                    "tcgplayer_product_id": product_id,
                    "canonical_product_name": (
                        primary_row[
                            "canonical_product_name"
                        ]
                    ),
                    "tcgcsv_category_id": (
                        primary_row[
                            "tcgcsv_category_id"
                        ]
                    ),
                    "tcgcsv_group_id": (
                        primary_row[
                            "tcgcsv_group_id"
                        ]
                    ),
                    "review_state": state,
                    "review_reason": reason,
                    "available_subtype_count": (
                        len(prices)
                    ),
                    "available_subtypes": (
                        "|".join(subtype_names)
                    ),
                    "selected_subtype_name": (
                        primary_row[
                            "selected_subtype_name"
                        ]
                    ),
                    "market_price": (
                        primary_row["market_price"]
                    ),
                    "low_price": (
                        primary_row["low_price"]
                    ),
                    "mid_price": (
                        primary_row["mid_price"]
                    ),
                    "source_url": source_url,
                }
            )

    primary_rows.sort(
        key=lambda row: (
            clean(
                row.get("canonical_product_name")
            ).lower(),
            normalized_id(
                row.get("tcgplayer_product_id")
            ),
        )
    )

    subtype_rows.sort(
        key=lambda row: (
            clean(
                row.get("canonical_product_name")
            ).lower(),
            normalized_id(
                row.get("tcgplayer_product_id")
            ),
            normalize_subtype(
                row.get("subtype_name")
            ),
        )
    )

    review_rows.sort(
        key=lambda row: (
            clean(
                row.get("review_state")
            ),
            clean(
                row.get("canonical_product_name")
            ).lower(),
        )
    )

    write_csv(
        CURRENT_PRICES_PATH,
        primary_rows,
        PRIMARY_PRICE_COLUMNS,
    )

    write_csv(
        ALL_SUBTYPES_PATH,
        subtype_rows,
        SUBTYPE_COLUMNS,
    )

    write_csv(
        REVIEW_QUEUE_PATH,
        review_rows,
        REVIEW_COLUMNS,
    )

    write_csv(
        FETCH_LOG_PATH,
        fetch_log_rows,
        FETCH_LOG_COLUMNS,
    )

    state_counts = Counter(
        clean(row.get("price_selection_state"))
        for row in primary_rows
    )

    priced_rows = sum(
        1
        for row in primary_rows
        if row.get("market_price_available")
        == "true"
    )

    successful_fetches = sum(
        1
        for row in fetch_log_rows
        if row.get("fetch_state") == "success"
    )

    failed_fetches = (
        len(fetch_log_rows)
        - successful_fetches
    )

    certification_status = (
        "PASS"
        if (
            failed_fetches == 0
            and len(primary_rows) == 254
            and not review_rows
        )
        else "PARTIAL"
    )

    summary = {
        "schema_version": "10.5R.3.3",
        "generated_at_utc": retrieved_at,
        "certification_status": (
            certification_status
        ),
        "tcgcsv_last_updated": (
            tcgcsv_last_updated
        ),
        "registry_rows": len(registry),
        "unique_groups_requested": len(groups),
        "successful_group_fetches": (
            successful_fetches
        ),
        "failed_group_fetches": failed_fetches,
        "current_price_rows": len(primary_rows),
        "all_subtype_price_rows": (
            len(subtype_rows)
        ),
        "products_with_market_price": priced_rows,
        "products_without_market_price": (
            len(primary_rows) - priced_rows
        ),
        "review_queue_rows": len(review_rows),
        "price_selection_state_counts": dict(
            sorted(state_counts.items())
        ),
        "governance": {
            "production_registry_changed": False,
            "universal_database_changed": False,
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
            "all_subtypes": (
                ALL_SUBTYPES_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "review_queue": (
                REVIEW_QUEUE_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "fetch_log": (
                FETCH_LOG_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "raw_cache_root": (
                CACHE_ROOT
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
        "Phase 10.5R.3.3 Secret Lair "
        "Current TCGCSV Pricing"
    )
    print("=" * 76)
    print(
        f"Registry rows: {len(registry)}"
    )
    print(
        f"Unique groups requested: {len(groups)}"
    )
    print(
        "Successful group fetches: "
        f"{successful_fetches}"
    )
    print(
        f"Failed group fetches: {failed_fetches}"
    )
    print(
        f"Current price rows: {len(primary_rows)}"
    )
    print(
        "All subtype price rows: "
        f"{len(subtype_rows)}"
    )
    print(
        "Products with market price: "
        f"{priced_rows}"
    )
    print(
        "Products without market price: "
        f"{len(primary_rows) - priced_rows}"
    )
    print(
        f"Review queue rows: {len(review_rows)}"
    )
    print()
    print("Price selection states:")

    for state, count in sorted(
        state_counts.items()
    ):
        print(f"  {state}: {count}")

    print()
    print(
        "CURRENT PRICING STATUS: "
        + certification_status
    )
    print("Final eligibility: NOT ASSIGNED")
    print("Scoring: DISABLED")
    print("Universal investable: DISABLED")
    print("Production registry changed: NO")
    print("Universal database changed: NO")
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