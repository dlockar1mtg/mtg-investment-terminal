from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parents[2]

ROUTING_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_tcgcsv_routing"
)

PRODUCT_ROUTING_PATH = (
    ROUTING_ROOT
    / "historical_tcgcsv_product_routing_2026-07-22.csv"
)

AUTHORITATIVE_HISTORICAL_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "premium_universe_eligibility"
    / "historical_booster_review_2026-07-22.csv"
)

UNROUTED_PATH = (
    ROUTING_ROOT
    / "historical_tcgcsv_unrouted_products_2026-07-22.csv"
)

RAW_CACHE_ROOT = (
    ROOT
    / "data"
    / "raw"
    / "tcgcsv"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_tcgcsv_price_enrichment"
)

SCHEMA_VERSION = "10.5R.1D.2.2D.2.1"

BASE_URL = "https://tcgcsv.com/tcgplayer"

USER_AGENT = (
    "mtg-investment-terminal/"
    "10.5R.1D.2.2D.2.1 "
    "(historical-price-enrichment)"
)

REQUEST_TIMEOUT_SECONDS = 45
REQUEST_DELAY_SECONDS = 0.25

OUTPUT_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_product_name",
    "category_id",
    "group_id",
    "price_cache_path",
    "price_cache_source",
    "price_payload_success",
    "price_record_count",
    "available_subtypes",
    "selected_subtype",
    "selection_method",
    "market_price",
    "low_price",
    "mid_price",
    "high_price",
    "direct_low_price",
    "current_price_candidate",
    "price_currency",
    "price_evidence_state",
    "historical_eligibility_decision",
    "scoring_allowed",
    "universal_investable_allowed",
]


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def clean_text(value: object) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip()


def parse_bool(value: object) -> bool:
    return clean_text(value).casefold() in {
        "true",
        "1",
        "yes",
    }


def numeric_or_blank(value: object) -> float | str:
    cleaned = clean_text(value)

    if not cleaned:
        return ""

    try:
        return float(cleaned)
    except ValueError:
        return ""


def build_session() -> requests.Session:
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=1.0,
        status_forcelist=[
            429,
            500,
            502,
            503,
            504,
        ],
        allowed_methods=[
            "GET",
        ],
        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        max_retries=retry,
    )

    session = requests.Session()

    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
    )

    session.mount(
        "https://",
        adapter,
    )

    session.mount(
        "http://",
        adapter,
    )

    return session


def validate_payload(
    payload: object,
    *,
    path_or_url: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError(
            "TCGCSV payload must be a JSON object: "
            f"{path_or_url}"
        )

    results = payload.get(
        "results"
    )

    if not isinstance(results, list):
        raise RuntimeError(
            "TCGCSV payload is missing a results list: "
            f"{path_or_url}"
        )

    return payload


def load_cached_payload(
    path: Path,
) -> dict[str, Any]:
    with path.open(
        "r",
        encoding="utf-8-sig",
    ) as handle:
        payload = json.load(handle)

    return validate_payload(
        payload,
        path_or_url=str(path),
    )


def download_payload(
    *,
    session: requests.Session,
    category_id: str,
    group_id: str,
    cache_path: Path,
) -> dict[str, Any]:
    url = (
        f"{BASE_URL}/"
        f"{category_id}/"
        f"{group_id}/prices"
    )

    response = session.get(
        url,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        raise RuntimeError(
            "TCGCSV price request failed: "
            f"HTTP {response.status_code} "
            f"for {url}"
        )

    payload = validate_payload(
        response.json(),
        path_or_url=url,
    )

    cache_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = cache_path.with_suffix(
        ".json.tmp"
    )

    temporary_path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    temporary_path.replace(
        cache_path
    )

    return payload


def get_group_payload(
    *,
    session: requests.Session,
    category_id: str,
    group_id: str,
) -> tuple[dict[str, Any], Path, str]:
    cache_path = (
        RAW_CACHE_ROOT
        / (
            f"prices_"
            f"{category_id}_"
            f"{group_id}.json"
        )
    )

    if cache_path.is_file():
        return (
            load_cached_payload(
                cache_path
            ),
            cache_path,
            "existing_cache",
        )

    payload = download_payload(
        session=session,
        category_id=category_id,
        group_id=group_id,
        cache_path=cache_path,
    )

    time.sleep(
        REQUEST_DELAY_SECONDS
    )

    return (
        payload,
        cache_path,
        "downloaded",
    )


def records_for_product(
    payload: dict[str, Any],
    product_id: str,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []

    for record in payload.get(
        "results",
        [],
    ):
        if not isinstance(
            record,
            dict,
        ):
            continue

        if clean_text(
            record.get(
                "productId"
            )
        ) == product_id:
            matches.append(record)

    return matches


def subtype_name(
    record: dict[str, Any],
) -> str:
    return clean_text(
        record.get(
            "subTypeName"
        )
    )


def select_price_record(
    records: list[dict[str, Any]],
) -> tuple[
    dict[str, Any] | None,
    str,
]:
    if not records:
        return None, "no_price_records"

    normal_records = [
        record
        for record in records
        if subtype_name(
            record
        ).casefold() == "normal"
    ]

    if len(normal_records) == 1:
        return (
            normal_records[0],
            "normal_subtype",
        )

    if len(normal_records) > 1:
        normal_with_market = [
            record
            for record in normal_records
            if record.get(
                "marketPrice"
            )
            is not None
        ]

        if len(normal_with_market) == 1:
            return (
                normal_with_market[0],
                "normal_subtype_unique_market_price",
            )

        return (
            None,
            "ambiguous_normal_records",
        )

    if len(records) == 1:
        return (
            records[0],
            "single_price_record",
        )

    nonblank_market_records = [
        record
        for record in records
        if record.get(
            "marketPrice"
        )
        is not None
    ]

    if len(nonblank_market_records) == 1:
        return (
            nonblank_market_records[0],
            "unique_market_price_record",
        )

    return (
        None,
        "ambiguous_multiple_subtypes",
    )


def price_value(
    record: dict[str, Any] | None,
    field: str,
) -> float | str:
    if record is None:
        return ""

    return numeric_or_blank(
        record.get(field)
    )


def current_price_candidate(
    selected: dict[str, Any] | None,
) -> float | str:
    if selected is None:
        return ""

    for field in (
        "marketPrice",
        "midPrice",
        "lowPrice",
    ):
        value = numeric_or_blank(
            selected.get(field)
        )

        if value != "":
            return value

    return ""


def main() -> int:
    if not PRODUCT_ROUTING_PATH.is_file():
        raise FileNotFoundError(
            "Historical routing file not found: "
            f"{PRODUCT_ROUTING_PATH}"
        )

    if not AUTHORITATIVE_HISTORICAL_PATH.is_file():
        raise FileNotFoundError(
            "Authoritative historical source not found: "
            f"{AUTHORITATIVE_HISTORICAL_PATH}"
        )

    routing = pd.read_csv(
        PRODUCT_ROUTING_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    authoritative = pd.read_csv(
        AUTHORITATIVE_HISTORICAL_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    if len(authoritative) != 140:
        raise RuntimeError(
            "Expected 140 authoritative historical rows; "
            f"found {len(authoritative)}."
        )

    authoritative_ids = set(
        authoritative[
            "canonical_product_id"
        ]
        .astype(str)
        .str.strip()
        .tolist()
    )

    if len(authoritative_ids) != 140:
        raise RuntimeError(
            "Authoritative historical IDs are not unique."
        )

    routing_ids = set(
        routing[
            "canonical_product_id"
        ]
        .astype(str)
        .str.strip()
        .tolist()
    )

    missing_ids = (
        authoritative_ids
        - routing_ids
    )

    if missing_ids:
        raise RuntimeError(
            "Authoritative historical IDs are missing "
            "from TCGCSV routing: "
            + ", ".join(
                sorted(missing_ids)
            )
        )

    routing = routing[
        routing[
            "canonical_product_id"
        ]
        .astype(str)
        .str.strip()
        .isin(authoritative_ids)
    ].copy()

    if len(routing) != 140:
        raise RuntimeError(
            "Expected 140 filtered routing rows; "
            f"found {len(routing)}."
        )

    routed = routing[
        routing["category_id"]
        .astype(str)
        .str.strip()
        .ne("")
        & routing["group_id"]
        .astype(str)
        .str.strip()
        .ne("")
        & routing["product_id_matches"]
        .apply(parse_bool)
    ].copy()

    unrouted = routing[
        ~routing.index.isin(
            routed.index
        )
    ].copy()

    if len(routed) != 140:
        raise RuntimeError(
            "Expected all 140 authoritative products "
            "to be routed; "
            f"found {len(routed)}."
        )

    if len(unrouted) != 0:
        raise RuntimeError(
            "Expected zero unrouted authoritative products; "
            f"found {len(unrouted)}."
        )

    group_routes = (
        routed[
            [
                "category_id",
                "group_id",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            [
                "category_id",
                "group_id",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    if group_routes.empty:
        raise RuntimeError(
            "No TCGCSV groups were resolved for the "
            "authoritative historical population."
        )

    session = build_session()

    group_payloads: dict[
        tuple[str, str],
        dict[str, Any],
    ] = {}

    group_cache_paths: dict[
        tuple[str, str],
        Path,
    ] = {}

    group_cache_sources: dict[
        tuple[str, str],
        str,
    ] = {}

    group_errors: list[dict[str, str]] = []

    for position, group_row in (
        group_routes.iterrows()
    ):
        category_id = clean_text(
            group_row.get(
                "category_id"
            )
        )

        group_id = clean_text(
            group_row.get(
                "group_id"
            )
        )

        key = (
            category_id,
            group_id,
        )

        print(
            "["
            f"{position + 1:03d}/"
            f"{len(group_routes):03d}"
            "] "
            f"category={category_id} "
            f"group={group_id}"
        )

        try:
            (
                payload,
                cache_path,
                cache_source,
            ) = get_group_payload(
                session=session,
                category_id=category_id,
                group_id=group_id,
            )

            group_payloads[key] = payload
            group_cache_paths[key] = (
                cache_path
            )
            group_cache_sources[key] = (
                cache_source
            )

        except Exception as exc:
            group_errors.append(
                {
                    "category_id": category_id,
                    "group_id": group_id,
                    "error_type": (
                        type(exc).__name__
                    ),
                    "error_message": str(exc),
                }
            )

    output_rows: list[
        dict[str, Any]
    ] = []

    for _, row in routed.iterrows():
        category_id = clean_text(
            row.get(
                "category_id"
            )
        )

        group_id = clean_text(
            row.get(
                "group_id"
            )
        )

        product_id = clean_text(
            row.get(
                "tcgplayer_product_id"
            )
        )

        key = (
            category_id,
            group_id,
        )

        payload = group_payloads.get(
            key
        )

        cache_path = group_cache_paths.get(
            key
        )

        cache_source = (
            group_cache_sources.get(
                key,
                ""
            )
        )

        if payload is None:
            records: list[
                dict[str, Any]
            ] = []

            payload_success = False
        else:
            records = records_for_product(
                payload,
                product_id,
            )

            payload_success = bool(
                payload.get(
                    "success",
                    False,
                )
            )

        selected, selection_method = (
            select_price_record(
                records
            )
        )

        available_subtypes = sorted(
            {
                subtype_name(record)
                for record in records
                if subtype_name(record)
            }
        )

        candidate = (
            current_price_candidate(
                selected
            )
        )

        if selected is not None and candidate != "":
            evidence_state = (
                "current_price_available"
            )
        elif records:
            evidence_state = (
                "price_records_require_review"
            )
        elif payload is None:
            evidence_state = (
                "group_fetch_failed"
            )
        else:
            evidence_state = (
                "product_price_not_found"
            )

        try:
            relative_cache_path = (
                str(
                    cache_path.relative_to(
                        ROOT
                    )
                )
                if cache_path is not None
                else ""
            )
        except ValueError:
            relative_cache_path = (
                str(cache_path)
                if cache_path is not None
                else ""
            )

        output_rows.append(
            {
                "canonical_product_id": clean_text(
                    row.get(
                        "canonical_product_id"
                    )
                ),
                "tcgplayer_product_id": (
                    product_id
                ),
                "canonical_product_name": clean_text(
                    row.get(
                        "canonical_product_name"
                    )
                ),
                "category_id": category_id,
                "group_id": group_id,
                "price_cache_path": (
                    relative_cache_path
                ),
                "price_cache_source": (
                    cache_source
                ),
                "price_payload_success": (
                    payload_success
                ),
                "price_record_count": len(
                    records
                ),
                "available_subtypes": "|".join(
                    available_subtypes
                ),
                "selected_subtype": (
                    subtype_name(selected)
                    if selected is not None
                    else ""
                ),
                "selection_method": (
                    selection_method
                ),
                "market_price": price_value(
                    selected,
                    "marketPrice",
                ),
                "low_price": price_value(
                    selected,
                    "lowPrice",
                ),
                "mid_price": price_value(
                    selected,
                    "midPrice",
                ),
                "high_price": price_value(
                    selected,
                    "highPrice",
                ),
                "direct_low_price": price_value(
                    selected,
                    "directLowPrice",
                ),
                "current_price_candidate": (
                    candidate
                ),
                "price_currency": "USD",
                "price_evidence_state": (
                    evidence_state
                ),
                "historical_eligibility_decision": (
                    "not_decided"
                ),
                "scoring_allowed": False,
                "universal_investable_allowed": False,
            }
        )

    output = (
        pd.DataFrame(
            output_rows,
            columns=OUTPUT_COLUMNS,
        )
        .sort_values(
            [
                "price_evidence_state",
                "canonical_product_name",
                "tcgplayer_product_id",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    enrichment_path = (
        OUTPUT_ROOT
        / "historical_tcgcsv_current_price_enrichment_2026-07-22.csv"
    )

    review_path = (
        OUTPUT_ROOT
        / "historical_tcgcsv_price_review_queue_2026-07-22.csv"
    )

    fetch_errors_path = (
        OUTPUT_ROOT
        / "historical_tcgcsv_group_fetch_errors_2026-07-22.csv"
    )

    summary_path = (
        OUTPUT_ROOT
        / "historical_tcgcsv_current_price_summary_2026-07-22.json"
    )

    review = output[
        ~output[
            "price_evidence_state"
        ].eq(
            "current_price_available"
        )
    ].copy()

    fetch_errors = pd.DataFrame(
        group_errors,
        columns=[
            "category_id",
            "group_id",
            "error_type",
            "error_message",
        ],
    )

    output.to_csv(
        enrichment_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    review.to_csv(
        review_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    fetch_errors.to_csv(
        fetch_errors_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    evidence_counts = {
        str(key): int(value)
        for key, value in (
            output[
                "price_evidence_state"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    selection_counts = {
        str(key): int(value)
        for key, value in (
            output[
                "selection_method"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "adapter_status": (
            "PASS"
            if not group_errors
            else "PARTIAL"
        ),
        "historical_routing_rows": int(
            len(routing)
        ),
        "routed_product_rows": int(
            len(routed)
        ),
        "unrouted_product_rows": int(
            len(unrouted)
        ),
        "unique_routed_groups": int(
            len(group_routes)
        ),
        "successful_group_payloads": int(
            len(group_payloads)
        ),
        "failed_group_payloads": int(
            len(group_errors)
        ),
        "existing_cache_groups": int(
            sum(
                source
                == "existing_cache"
                for source in (
                    group_cache_sources.values()
                )
            )
        ),
        "downloaded_groups": int(
            sum(
                source
                == "downloaded"
                for source in (
                    group_cache_sources.values()
                )
            )
        ),
        "price_enrichment_rows": int(
            len(output)
        ),
        "rows_with_current_price_candidate": int(
            output[
                "current_price_candidate"
            ]
            .astype(str)
            .str.strip()
            .ne("")
            .sum()
        ),
        "rows_requiring_price_review": int(
            len(review)
        ),
        "price_evidence_state_counts": (
            evidence_counts
        ),
        "selection_method_counts": (
            selection_counts
        ),
        "final_eligibility_assigned": False,
        "scoring_allowed_rows": 0,
        "universal_investable_allowed_rows": 0,
        "production_registry_changed": False,
        "universal_database_changed": False,
        "output_files": {
            "price_enrichment": str(
                enrichment_path
            ),
            "price_review_queue": str(
                review_path
            ),
            "group_fetch_errors": str(
                fetch_errors_path
            ),
        },
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

    print()
    print("=" * 76)
    print(
        "Phase 10.5R.1D.2.2D.2 "
        "TCGCSV Current Price Cache Adapter"
    )
    print("=" * 76)
    print(
        f"Historical routing rows: {len(routing)}"
    )
    print(
        f"Routed products: {len(routed)}"
    )
    print(
        f"Unrouted products: {len(unrouted)}"
    )
    print(
        f"Unique routed groups: {len(group_routes)}"
    )
    print(
        "Successful group payloads: "
        f"{len(group_payloads)}"
    )
    print(
        "Failed group payloads: "
        f"{len(group_errors)}"
    )
    print(
        "Rows with current price: "
        + str(
            summary[
                "rows_with_current_price_candidate"
            ]
        )
    )
    print(
        "Rows requiring price review: "
        + str(
            summary[
                "rows_requiring_price_review"
            ]
        )
    )
    print()
    print(
        "ADAPTER STATUS: "
        + summary[
            "adapter_status"
        ]
    )
    print(
        "Final eligibility: NOT ASSIGNED"
    )
    print(
        "Scoring: DISABLED"
    )
    print(
        "Production registry: UNCHANGED"
    )
    print(
        "Universal database: UNCHANGED"
    )

    return (
        0
        if not group_errors
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())