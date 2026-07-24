from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

COHORT_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_cohort_policy"
    / "historical_governed_candidate_cohorts_2026-07-22.csv"
)

ROUTING_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_tcgcsv_routing"
    / "historical_tcgcsv_product_routing_2026-07-22.csv"
)

RAW_TCGCSV_ROOT = (
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
    / "historical_release_timing"
)

SCHEMA_VERSION = "10.5R.1D.2.4A.1"

REVIEW_COHORTS = {
    "traditional_historical_review",
    "explicit_specialty_draft_review",
    "commander_draft_policy_review",
}

OUTPUT_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_set_name",
    "canonical_product_name",
    "governed_candidate_cohort",
    "category_id",
    "group_id",
    "product_cache_path",
    "product_cache_exists",
    "product_record_found",
    "cached_product_name",
    "presale_is_presale",
    "presale_released_on",
    "presale_note",
    "product_modified_on",
    "release_date_candidate",
    "release_date_source",
    "release_timing_evidence_state",
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


def load_json_payload(
    path: Path,
) -> dict[str, Any]:
    with path.open(
        "r",
        encoding="utf-8-sig",
    ) as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise RuntimeError(
            "Cached TCGCSV product payload must be "
            f"a JSON object: {path}"
        )

    results = payload.get("results")

    if not isinstance(results, list):
        raise RuntimeError(
            "Cached TCGCSV product payload has no "
            f"results list: {path}"
        )

    return payload


def find_product_record(
    payload: dict[str, Any],
    product_id: str,
) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []

    for record in payload.get(
        "results",
        [],
    ):
        if not isinstance(record, dict):
            continue

        if clean_text(
            record.get("productId")
        ) == product_id:
            matches.append(record)

    if len(matches) > 1:
        raise RuntimeError(
            "Multiple cached product records found for "
            f"TCGplayer product {product_id}."
        )

    return matches[0] if matches else None


def presale_values(
    product_record: dict[str, Any] | None,
) -> tuple[str, str, str]:
    if product_record is None:
        return "", "", ""

    presale = product_record.get(
        "presaleInfo"
    )

    if not isinstance(presale, dict):
        return "", "", ""

    is_presale = clean_text(
        presale.get("isPresale")
    )

    released_on = clean_text(
        presale.get("releasedOn")
    )

    note = clean_text(
        presale.get("note")
    )

    return (
        is_presale,
        released_on,
        note,
    )


def main() -> int:
    for required_path in (
        COHORT_PATH,
        ROUTING_PATH,
    ):
        if not required_path.is_file():
            raise FileNotFoundError(
                f"Required input missing: {required_path}"
            )

    cohorts = pd.read_csv(
        COHORT_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    routing = pd.read_csv(
        ROUTING_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    if len(cohorts) != 140:
        raise RuntimeError(
            "Expected 140 governed cohort rows; "
            f"found {len(cohorts)}."
        )

    if cohorts[
        "canonical_product_id"
    ].duplicated().any():
        raise RuntimeError(
            "Governed cohort input contains duplicate "
            "canonical product IDs."
        )

    review = cohorts[
        cohorts[
            "governed_candidate_cohort"
        ].isin(REVIEW_COHORTS)
    ].copy()

    if len(review) != 140:
        raise RuntimeError(
            "Expected 140 products remaining in review; "
            f"found {len(review)}."
        )

    authoritative_ids = set(
        review[
            "canonical_product_id"
        ]
        .astype(str)
        .str.strip()
    )

    routing_ids = set(
        routing[
            "canonical_product_id"
        ]
        .astype(str)
        .str.strip()
    )

    missing_routing_ids = sorted(
        authoritative_ids - routing_ids
    )

    if missing_routing_ids:
        raise RuntimeError(
            "Authoritative products missing from TCGCSV "
            "routing: "
            + ", ".join(missing_routing_ids)
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
            "Expected 140 authoritative routing rows "
            "after filtering; "
            f"found {len(routing)}."
        )

    if routing[
        "canonical_product_id"
    ].duplicated().any():
        raise RuntimeError(
            "Filtered TCGCSV routing contains duplicate "
            "canonical product IDs."
        )

    filtered_routing_ids = set(
        routing[
            "canonical_product_id"
        ]
        .astype(str)
        .str.strip()
    )

    if filtered_routing_ids != authoritative_ids:
        raise RuntimeError(
            "Filtered TCGCSV routing does not exactly match "
            "the authoritative cohort identity boundary."
        )

    routing_by_id = (
        routing
        .set_index(
            "canonical_product_id",
            drop=False,
        )
    )

    output_rows: list[
        dict[str, Any]
    ] = []

    errors: list[dict[str, str]] = []

    for _, cohort_row in review.iterrows():
        canonical_id = clean_text(
            cohort_row.get(
                "canonical_product_id"
            )
        )

        product_id = clean_text(
            cohort_row.get(
                "tcgplayer_product_id"
            )
        )

        routing_row: pd.Series | None = None

        if canonical_id in routing_by_id.index:
            candidate = routing_by_id.loc[
                canonical_id
            ]

            if isinstance(
                candidate,
                pd.DataFrame,
            ):
                routing_row = candidate.iloc[0]
            else:
                routing_row = candidate

        category_id = (
            clean_text(
                routing_row.get(
                    "category_id"
                )
            )
            if routing_row is not None
            else ""
        )

        group_id = (
            clean_text(
                routing_row.get(
                    "group_id"
                )
            )
            if routing_row is not None
            else ""
        )

        route_is_valid = (
            bool(category_id)
            and bool(group_id)
            and (
                parse_bool(
                    routing_row.get(
                        "product_id_matches"
                    )
                )
                if routing_row is not None
                else False
            )
        )

        if route_is_valid:
            cache_path = (
                RAW_TCGCSV_ROOT
                / (
                    f"products_"
                    f"{category_id}_"
                    f"{group_id}.json"
                )
            )
        else:
            cache_path = None

        product_record: dict[
            str,
            Any,
        ] | None = None

        if (
            cache_path is not None
            and cache_path.is_file()
        ):
            try:
                payload = load_json_payload(
                    cache_path
                )

                product_record = find_product_record(
                    payload,
                    product_id,
                )

            except Exception as exc:
                errors.append(
                    {
                        "canonical_product_id": canonical_id,
                        "tcgplayer_product_id": product_id,
                        "category_id": category_id,
                        "group_id": group_id,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )

        (
            presale_is_presale,
            presale_released_on,
            presale_note,
        ) = presale_values(
            product_record
        )

        modified_on = (
            clean_text(
                product_record.get(
                    "modifiedOn"
                )
            )
            if product_record is not None
            else ""
        )

        if presale_released_on:
            release_date_candidate = (
                presale_released_on
            )

            release_date_source = (
                "tcgcsv_product_presale_info"
            )

            evidence_state = (
                "cached_release_date_available"
            )

        elif product_record is not None:
            release_date_candidate = ""
            release_date_source = ""
            evidence_state = (
                "cached_product_found_release_date_blank"
            )

        elif (
            cache_path is not None
            and cache_path.is_file()
        ):
            release_date_candidate = ""
            release_date_source = ""
            evidence_state = (
                "cached_group_found_product_missing"
            )

        elif route_is_valid:
            release_date_candidate = ""
            release_date_source = ""
            evidence_state = (
                "product_cache_missing"
            )

        else:
            release_date_candidate = ""
            release_date_source = ""
            evidence_state = (
                "valid_tcgcsv_route_missing"
            )

        if cache_path is None:
            relative_cache_path = ""
        else:
            try:
                relative_cache_path = str(
                    cache_path.relative_to(
                        ROOT
                    )
                )
            except ValueError:
                relative_cache_path = str(
                    cache_path
                )

        output_rows.append(
            {
                "canonical_product_id": canonical_id,
                "tcgplayer_product_id": product_id,
                "canonical_set_name": clean_text(
                    cohort_row.get(
                        "canonical_set_name"
                    )
                ),
                "canonical_product_name": clean_text(
                    cohort_row.get(
                        "canonical_product_name"
                    )
                ),
                "governed_candidate_cohort": clean_text(
                    cohort_row.get(
                        "governed_candidate_cohort"
                    )
                ),
                "category_id": category_id,
                "group_id": group_id,
                "product_cache_path": (
                    relative_cache_path
                ),
                "product_cache_exists": (
                    cache_path is not None
                    and cache_path.is_file()
                ),
                "product_record_found": (
                    product_record is not None
                ),
                "cached_product_name": (
                    clean_text(
                        product_record.get(
                            "name"
                        )
                    )
                    if product_record is not None
                    else ""
                ),
                "presale_is_presale": (
                    presale_is_presale
                ),
                "presale_released_on": (
                    presale_released_on
                ),
                "presale_note": (
                    presale_note
                ),
                "product_modified_on": (
                    modified_on
                ),
                "release_date_candidate": (
                    release_date_candidate
                ),
                "release_date_source": (
                    release_date_source
                ),
                "release_timing_evidence_state": (
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
                "release_timing_evidence_state",
                "governed_candidate_cohort",
                "canonical_product_name",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    if len(output) != 140:
        raise RuntimeError(
            "Release-timing audit did not produce "
            "exactly 140 rows."
        )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit_path = (
        OUTPUT_ROOT
        / "historical_cached_release_timing_audit_2026-07-22.csv"
    )

    available_path = (
        OUTPUT_ROOT
        / "historical_cached_release_dates_available_2026-07-22.csv"
    )

    unresolved_path = (
        OUTPUT_ROOT
        / "historical_external_release_timing_queue_2026-07-22.csv"
    )

    errors_path = (
        OUTPUT_ROOT
        / "historical_cached_release_timing_errors_2026-07-22.csv"
    )

    summary_path = (
        OUTPUT_ROOT
        / "historical_cached_release_timing_summary_2026-07-22.json"
    )

    available = output[
        output[
            "release_timing_evidence_state"
        ].eq(
            "cached_release_date_available"
        )
    ].copy()

    unresolved = output[
        ~output[
            "release_timing_evidence_state"
        ].eq(
            "cached_release_date_available"
        )
    ].copy()

    error_frame = pd.DataFrame(
        errors,
        columns=[
            "canonical_product_id",
            "tcgplayer_product_id",
            "category_id",
            "group_id",
            "error_type",
            "error_message",
        ],
    )

    output.to_csv(
        audit_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    available.to_csv(
        available_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    unresolved.to_csv(
        unresolved_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    error_frame.to_csv(
        errors_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    evidence_counts = {
        str(key): int(value)
        for key, value in (
            output[
                "release_timing_evidence_state"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    cohort_coverage = {}

    for cohort_name, group in output.groupby(
        "governed_candidate_cohort",
        sort=True,
    ):
        cohort_coverage[
            str(cohort_name)
        ] = {
            "rows": int(len(group)),
            "release_dates_available": int(
                group[
                    "release_date_candidate"
                ]
                .astype(str)
                .str.strip()
                .ne("")
                .sum()
            ),
            "release_dates_unresolved": int(
                group[
                    "release_date_candidate"
                ]
                .astype(str)
                .str.strip()
                .eq("")
                .sum()
            ),
        }

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "audit_status": (
            "PASS"
            if not errors
            else "PARTIAL"
        ),
        "review_product_rows": int(
            len(output)
        ),
        "unique_canonical_product_ids": int(
            output[
                "canonical_product_id"
            ].nunique()
        ),
        "valid_tcgcsv_route_rows": int(
            output[
                "category_id"
            ]
            .astype(str)
            .str.strip()
            .ne("")
            .sum()
        ),
        "cached_product_file_rows": int(
            output[
                "product_cache_exists"
            ]
            .astype(str)
            .str.casefold()
            .eq("true")
            .sum()
        ),
        "cached_product_record_rows": int(
            output[
                "product_record_found"
            ]
            .astype(str)
            .str.casefold()
            .eq("true")
            .sum()
        ),
        "cached_release_date_rows": int(
            len(available)
        ),
        "external_release_timing_required_rows": int(
            len(unresolved)
        ),
        "release_timing_evidence_state_counts": (
            evidence_counts
        ),
        "cohort_release_timing_coverage": (
            cohort_coverage
        ),
        "error_rows": int(
            len(error_frame)
        ),
        "modified_on_used_as_release_date": False,
        "final_eligibility_assigned": False,
        "scoring_allowed_rows": 0,
        "universal_investable_allowed_rows": 0,
        "production_registry_changed": False,
        "universal_database_changed": False,
        "output_files": {
            "audit": str(audit_path),
            "cached_dates_available": str(
                available_path
            ),
            "external_timing_queue": str(
                unresolved_path
            ),
            "errors": str(errors_path),
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

    print("=" * 76)
    print(
        "Phase 10.5R.1D.2.4A "
        "Cached Product Release-Timing Audit"
    )
    print("=" * 76)
    print(
        f"Review products: {len(output)}"
    )
    print(
        "Cached product records: "
        + str(
            summary[
                "cached_product_record_rows"
            ]
        )
    )
    print(
        "Cached release dates available: "
        + str(
            summary[
                "cached_release_date_rows"
            ]
        )
    )
    print(
        "External release timing required: "
        + str(
            summary[
                "external_release_timing_required_rows"
            ]
        )
    )
    print(
        f"Errors: {len(error_frame)}"
    )
    print()
    print(
        "AUDIT STATUS: "
        + summary["audit_status"]
    )
    print(
        "modifiedOn used as release date: NO"
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

    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())