from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parents[2]

ALIAS_RESOLUTION_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_mtgjson_set_alias_resolution"
    / "historical_mtgjson_set_alias_resolution_2026-07-22.csv"
)

TARGET_SCOPE_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_mtgjson_set_alias_resolution"
    / "historical_mtgjson_targeted_set_scope_2026-07-22.csv"
)

CACHE_ROOT = (
    ROOT
    / "data"
    / "raw"
    / "mtgjson"
    / "sets"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_mtgjson_sealed_products"
)

SCHEMA_VERSION = "10.5R.1D.2.4D"

USER_AGENT = (
    "mtg-investment-terminal/"
    "10.5R.1D.2.4D "
    "(historical-sealed-product-discovery)"
)

REQUEST_TIMEOUT_SECONDS = 90
REQUEST_DELAY_SECONDS = 0.15

OUTPUT_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_product_name",
    "canonical_set_name",
    "governed_candidate_cohort",
    "set_route_state",
    "set_route_method",
    "candidate_set_codes",
    "searched_set_codes",
    "sealed_candidate_count",
    "selected_set_code",
    "selected_set_name",
    "selected_sealed_uuid",
    "selected_sealed_name",
    "selected_sealed_category",
    "selected_sealed_subtype",
    "selected_sealed_release_date",
    "selected_sealed_tcgplayer_product_id",
    "sealed_match_method",
    "sealed_match_score",
    "sealed_match_state",
    "set_release_date",
    "tcgcsv_release_date_candidate",
    "product_release_date_candidate",
    "release_evidence_state",
    "final_release_date_assigned",
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


def normalize_name(value: object) -> str:
    text = clean_text(value).casefold()

    replacements = {
        "&": " and ",
        ":": " ",
        "-": " ",
        "'": "",
        "’": "",
        "(": " ",
        ")": " ",
        "[": " ",
        "]": " ",
        "/": " ",
    }

    for source, target in replacements.items():
        text = text.replace(source, target)

    noise_terms = [
        "sealed",
        "display",
        "box",
        "booster",
        "draft",
        "traditional",
        "retail exclusive",
        "convention edition",
    ]

    text = re.sub(
        r"\b(?:"
        + "|".join(
            re.escape(term)
            for term in noise_terms
        )
        + r")\b",
        " ",
        text,
    )

    text = re.sub(
        r"\b20(?:19|21)\b",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


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
        allowed_methods=["GET"],
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

    return session


def download_set_file(
    *,
    session: requests.Session,
    url: str,
    cache_path: Path,
) -> str:
    if cache_path.is_file():
        return "existing_cache"

    response = session.get(
        url,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"HTTP {response.status_code}: {url}"
        )

    cache_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = cache_path.with_suffix(
        ".json.tmp"
    )

    temporary_path.write_bytes(
        response.content
    )

    temporary_path.replace(
        cache_path
    )

    time.sleep(
        REQUEST_DELAY_SECONDS
    )

    return "downloaded"


def load_set_payload(
    path: Path,
) -> dict[str, Any]:
    with path.open(
        "r",
        encoding="utf-8-sig",
    ) as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise RuntimeError(
            f"MTGJSON set payload is not an object: {path}"
        )

    data = payload.get("data")

    if not isinstance(data, dict):
        raise RuntimeError(
            f"MTGJSON set payload has no data object: {path}"
        )

    return data


def sealed_products(
    set_data: dict[str, Any],
) -> list[dict[str, Any]]:
    for field in (
        "sealedProduct",
        "sealedProducts",
    ):
        value = set_data.get(field)

        if isinstance(value, list):
            return [
                record
                for record in value
                if isinstance(record, dict)
            ]

    return []


def identifiers(
    record: dict[str, Any],
) -> dict[str, str]:
    value = record.get("identifiers")

    if not isinstance(value, dict):
        return {}

    return {
        clean_text(key): clean_text(child)
        for key, child in value.items()
        if clean_text(child)
    }


def tcgplayer_id(
    record: dict[str, Any],
) -> str:
    values = identifiers(record)

    for key in (
        "tcgplayerProductId",
        "tcgplayerEtchedProductId",
    ):
        if values.get(key):
            return values[key]

    return ""


def select_candidate(
    *,
    product_name: str,
    product_id: str,
    candidates: list[dict[str, Any]],
) -> tuple[
    dict[str, Any] | None,
    str,
    float,
    str,
]:
    exact_id_matches = [
        candidate
        for candidate in candidates
        if tcgplayer_id(candidate) == product_id
    ]

    if len(exact_id_matches) == 1:
        return (
            exact_id_matches[0],
            "exact_tcgplayer_product_id",
            1.0,
            "matched",
        )

    if len(exact_id_matches) > 1:
        return (
            None,
            "ambiguous_tcgplayer_product_id",
            1.0,
            "review_required",
        )

    normalized_target = normalize_name(
        product_name
    )

    scored: list[
        tuple[
            float,
            dict[str, Any],
        ]
    ] = []

    for candidate in candidates:
        candidate_name = normalize_name(
            candidate.get("name")
        )

        if not candidate_name:
            continue

        score = SequenceMatcher(
            None,
            normalized_target,
            candidate_name,
        ).ratio()

        scored.append(
            (
                score,
                candidate,
            )
        )

    scored.sort(
        key=lambda item: (
            item[0],
            clean_text(
                item[1].get("uuid")
            ),
        ),
        reverse=True,
    )

    if not scored:
        return (
            None,
            "no_sealed_candidates",
            0.0,
            "unmatched",
        )

    top_score = scored[0][0]

    if top_score < 0.72:
        return (
            None,
            "no_confident_name_match",
            top_score,
            "unmatched",
        )

    tied = [
        item
        for item in scored
        if abs(item[0] - top_score) < 0.000001
    ]

    if len(tied) > 1:
        return (
            None,
            "ambiguous_name_match",
            top_score,
            "review_required",
        )

    state = (
        "matched"
        if top_score >= 0.90
        else "review_required"
    )

    return (
        scored[0][1],
        "sealed_name_similarity",
        top_score,
        state,
    )


def main() -> int:
    for required_path in (
        ALIAS_RESOLUTION_PATH,
        TARGET_SCOPE_PATH,
    ):
        if not required_path.is_file():
            raise FileNotFoundError(
                f"Required input missing: {required_path}"
            )

    resolution = pd.read_csv(
        ALIAS_RESOLUTION_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    scope = pd.read_csv(
        TARGET_SCOPE_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    if len(resolution) != 140:
        raise RuntimeError(
            "Expected 140 alias-resolution rows; "
            f"found {len(resolution)}."
        )

    if len(scope) != 138:
        raise RuntimeError(
            "Expected 138 targeted set files; "
            f"found {len(scope)}."
        )

    session = build_session()

    set_data_by_code: dict[
        str,
        dict[str, Any],
    ] = {}

    cache_sources: dict[
        str,
        str,
    ] = {}

    download_errors: list[
        dict[str, str]
    ] = []

    for position, row in scope.iterrows():
        set_code = clean_text(
            row.get("mtgjson_set_code")
        )

        url = clean_text(
            row.get("target_set_file_url")
        )

        cache_path = (
            ROOT
            / clean_text(
                row.get("target_set_cache_path")
            )
        )

        print(
            "["
            f"{position + 1:03d}/"
            f"{len(scope):03d}"
            "] "
            f"{set_code}"
        )

        try:
            cache_source = download_set_file(
                session=session,
                url=url,
                cache_path=cache_path,
            )

            set_data_by_code[set_code] = (
                load_set_payload(cache_path)
            )

            cache_sources[set_code] = (
                cache_source
            )

        except Exception as exc:
            download_errors.append(
                {
                    "mtgjson_set_code": set_code,
                    "target_set_file_url": url,
                    "error_type": (
                        type(exc).__name__
                    ),
                    "error_message": str(exc),
                }
            )

    output_rows: list[
        dict[str, Any]
    ] = []

    candidate_detail_rows: list[
        dict[str, Any]
    ] = []

    for _, row in resolution.iterrows():
        canonical_id = clean_text(
            row.get("canonical_product_id")
        )

        product_name = clean_text(
            row.get("canonical_product_name")
        )

        product_id = clean_text(
            row.get("tcgplayer_product_id")
        )

        direct_set_code = clean_text(
            row.get("mtgjson_set_code")
        )

        family_codes = [
            clean_text(value)
            for value in clean_text(
                row.get("candidate_set_codes")
            ).split("|")
            if clean_text(value)
        ]

        searched_codes = (
            [direct_set_code]
            if direct_set_code
            else family_codes
        )

        all_candidates: list[
            dict[str, Any]
        ] = []

        set_release_dates: dict[
            str,
            str,
        ] = {}

        set_names: dict[
            str,
            str,
        ] = {}

        for set_code in searched_codes:
            set_data = set_data_by_code.get(
                set_code
            )

            if set_data is None:
                continue

            set_release_dates[set_code] = (
                clean_text(
                    set_data.get("releaseDate")
                )
            )

            set_names[set_code] = clean_text(
                set_data.get("name")
            )

            for sealed in sealed_products(
                set_data
            ):
                enriched = dict(sealed)
                enriched["_set_code"] = (
                    set_code
                )
                enriched["_set_name"] = (
                    set_names[set_code]
                )

                all_candidates.append(
                    enriched
                )

                candidate_detail_rows.append(
                    {
                        "canonical_product_id": canonical_id,
                        "canonical_product_name": product_name,
                        "searched_set_code": set_code,
                        "sealed_uuid": clean_text(
                            sealed.get("uuid")
                        ),
                        "sealed_name": clean_text(
                            sealed.get("name")
                        ),
                        "sealed_category": clean_text(
                            sealed.get("category")
                        ),
                        "sealed_subtype": clean_text(
                            sealed.get("subtype")
                        ),
                        "sealed_release_date": clean_text(
                            sealed.get("releaseDate")
                        ),
                        "sealed_tcgplayer_product_id": (
                            tcgplayer_id(sealed)
                        ),
                    }
                )

        (
            selected,
            match_method,
            match_score,
            match_state,
        ) = select_candidate(
            product_name=product_name,
            product_id=product_id,
            candidates=all_candidates,
        )

        selected_set_code = (
            clean_text(
                selected.get("_set_code")
            )
            if selected is not None
            else ""
        )

        product_release_date = (
            clean_text(
                selected.get("releaseDate")
            )
            if selected is not None
            else ""
        )

        set_release_date = (
            set_release_dates.get(
                selected_set_code,
                "",
            )
            if selected_set_code
            else ""
        )

        if product_release_date:
            release_state = (
                "product_level_release_candidate"
            )
        elif (
            selected is not None
            and set_release_date
        ):
            release_state = (
                "matched_product_set_date_only"
            )
        elif all_candidates:
            release_state = (
                "sealed_product_review_required"
            )
        else:
            release_state = (
                "no_sealed_product_records"
            )

        output_rows.append(
            {
                "canonical_product_id": canonical_id,
                "tcgplayer_product_id": product_id,
                "canonical_product_name": product_name,
                "canonical_set_name": clean_text(
                    row.get("canonical_set_name")
                ),
                "governed_candidate_cohort": clean_text(
                    row.get(
                        "governed_candidate_cohort"
                    )
                ),
                "set_route_state": clean_text(
                    row.get("set_route_state")
                ),
                "set_route_method": clean_text(
                    row.get("set_route_method")
                ),
                "candidate_set_codes": clean_text(
                    row.get("candidate_set_codes")
                ),
                "searched_set_codes": "|".join(
                    searched_codes
                ),
                "sealed_candidate_count": len(
                    all_candidates
                ),
                "selected_set_code": (
                    selected_set_code
                ),
                "selected_set_name": (
                    clean_text(
                        selected.get("_set_name")
                    )
                    if selected is not None
                    else ""
                ),
                "selected_sealed_uuid": (
                    clean_text(
                        selected.get("uuid")
                    )
                    if selected is not None
                    else ""
                ),
                "selected_sealed_name": (
                    clean_text(
                        selected.get("name")
                    )
                    if selected is not None
                    else ""
                ),
                "selected_sealed_category": (
                    clean_text(
                        selected.get("category")
                    )
                    if selected is not None
                    else ""
                ),
                "selected_sealed_subtype": (
                    clean_text(
                        selected.get("subtype")
                    )
                    if selected is not None
                    else ""
                ),
                "selected_sealed_release_date": (
                    product_release_date
                ),
                "selected_sealed_tcgplayer_product_id": (
                    tcgplayer_id(selected)
                    if selected is not None
                    else ""
                ),
                "sealed_match_method": (
                    match_method
                ),
                "sealed_match_score": round(
                    match_score,
                    6,
                ),
                "sealed_match_state": (
                    match_state
                ),
                "set_release_date": (
                    set_release_date
                ),
                "tcgcsv_release_date_candidate": clean_text(
                    row.get(
                        "tcgcsv_release_date_candidate"
                    )
                ),
                "product_release_date_candidate": (
                    product_release_date
                ),
                "release_evidence_state": (
                    release_state
                ),
                "final_release_date_assigned": False,
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
                "sealed_match_state",
                "release_evidence_state",
                "canonical_product_name",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    if len(output) != 140:
        raise RuntimeError(
            "Expected 140 sealed-product audit rows; "
            f"found {len(output)}."
        )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit_path = (
        OUTPUT_ROOT
        / "historical_mtgjson_sealed_product_audit_2026-07-22.csv"
    )

    review_path = (
        OUTPUT_ROOT
        / "historical_mtgjson_sealed_product_review_queue_2026-07-22.csv"
    )

    candidates_path = (
        OUTPUT_ROOT
        / "historical_mtgjson_sealed_product_candidates_2026-07-22.csv"
    )

    errors_path = (
        OUTPUT_ROOT
        / "historical_mtgjson_set_download_errors_2026-07-22.csv"
    )

    summary_path = (
        OUTPUT_ROOT
        / "historical_mtgjson_sealed_product_summary_2026-07-22.json"
    )

    review = output[
        ~output[
            "sealed_match_state"
        ].eq("matched")
    ].copy()

    candidates = pd.DataFrame(
        candidate_detail_rows
    )

    error_frame = pd.DataFrame(
        download_errors,
        columns=[
            "mtgjson_set_code",
            "target_set_file_url",
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

    review.to_csv(
        review_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    candidates.to_csv(
        candidates_path,
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

    match_counts = {
        str(key): int(value)
        for key, value in (
            output[
                "sealed_match_state"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    evidence_counts = {
        str(key): int(value)
        for key, value in (
            output[
                "release_evidence_state"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "audit_status": (
            "PASS"
            if not download_errors
            else "PARTIAL"
        ),
        "review_product_rows": int(
            len(output)
        ),
        "targeted_set_files": int(
            len(scope)
        ),
        "successful_set_files": int(
            len(set_data_by_code)
        ),
        "failed_set_files": int(
            len(download_errors)
        ),
        "existing_cache_files": int(
            sum(
                source == "existing_cache"
                for source in cache_sources.values()
            )
        ),
        "downloaded_set_files": int(
            sum(
                source == "downloaded"
                for source in cache_sources.values()
            )
        ),
        "sealed_match_state_counts": (
            match_counts
        ),
        "release_evidence_state_counts": (
            evidence_counts
        ),
        "product_level_release_candidates": int(
            output[
                "product_release_date_candidate"
            ]
            .astype(str)
            .str.strip()
            .ne("")
            .sum()
        ),
        "sealed_product_review_rows": int(
            len(review)
        ),
        "final_release_dates_assigned": 0,
        "final_eligibility_assigned": False,
        "scoring_allowed_rows": 0,
        "universal_investable_allowed_rows": 0,
        "production_registry_changed": False,
        "universal_database_changed": False,
        "output_files": {
            "audit": str(audit_path),
            "review_queue": str(
                review_path
            ),
            "candidate_records": str(
                candidates_path
            ),
            "download_errors": str(
                errors_path
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

    print("=" * 76)
    print(
        "Phase 10.5R.1D.2.4D "
        "MTGJSON Targeted Sealed-Product Discovery"
    )
    print("=" * 76)
    print(
        f"Review products: {len(output)}"
    )
    print(
        f"Targeted set files: {len(scope)}"
    )
    print(
        "Successful set files: "
        f"{len(set_data_by_code)}"
    )
    print(
        "Failed set files: "
        f"{len(download_errors)}"
    )
    print(
        "Matched sealed products: "
        + str(
            match_counts.get(
                "matched",
                0,
            )
        )
    )
    print(
        "Sealed-product review rows: "
        f"{len(review)}"
    )
    print(
        "Product-level release candidates: "
        + str(
            summary[
                "product_level_release_candidates"
            ]
        )
    )
    print()
    print(
        "AUDIT STATUS: "
        + summary["audit_status"]
    )
    print(
        "Final release dates assigned: 0"
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
        if not download_errors
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())