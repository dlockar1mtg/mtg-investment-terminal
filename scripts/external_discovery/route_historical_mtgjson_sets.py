from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parents[2]

COHORT_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_cohort_policy"
    / "historical_governed_candidate_cohorts_2026-07-22.csv"
)

RELEASE_AUDIT_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_release_timing"
    / "historical_cached_release_timing_audit_2026-07-22.csv"
)

CACHE_ROOT = (
    ROOT
    / "data"
    / "raw"
    / "mtgjson"
)

SET_LIST_PATH = (
    CACHE_ROOT
    / "SetList.json"
)

SET_LIST_SHA256_PATH = (
    CACHE_ROOT
    / "SetList.json.sha256"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_mtgjson_set_routing"
)

SCHEMA_VERSION = "10.5R.1D.2.4C"

SET_LIST_URL = (
    "https://mtgjson.com/api/v5/SetList.json"
)

SET_LIST_SHA256_URL = (
    "https://mtgjson.com/api/v5/SetList.json.sha256"
)

USER_AGENT = (
    "mtg-investment-terminal/"
    "10.5R.1D.2.4C "
    "(historical-release-routing)"
)

REVIEW_COHORTS = {
    "traditional_historical_review",
    "explicit_specialty_draft_review",
    "commander_draft_policy_review",
}

OUTPUT_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_product_name",
    "canonical_set_name",
    "governed_candidate_cohort",
    "tcgcsv_release_date_candidate",
    "normalized_product_set_name",
    "mtgjson_set_code",
    "mtgjson_set_name",
    "mtgjson_set_release_date",
    "mtgjson_set_type",
    "mtgjson_parent_code",
    "mtgjson_tcgplayer_group_id",
    "set_match_method",
    "set_match_score",
    "set_match_state",
    "release_date_comparison_state",
    "release_date_day_difference",
    "target_set_file_url",
    "target_set_cache_path",
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


def parse_date(value: object) -> pd.Timestamp | None:
    cleaned = clean_text(value)

    if not cleaned:
        return None

    parsed = pd.to_datetime(
        cleaned,
        errors="coerce",
        utc=True,
    )

    if pd.isna(parsed):
        return None

    return parsed


def normalized_name(value: object) -> str:
    text = clean_text(value).casefold()

    suffixes = [
        " - draft booster box",
        " - draft booster display",
        " - booster box",
        " - booster display",
        " draft booster box",
        " draft booster display",
        " booster box",
        " booster display",
        " - box",
    ]

    for suffix in suffixes:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break

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
    }

    for source, target in replacements.items():
        text = text.replace(
            source,
            target,
        )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


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
            "Accept": "application/json,text/plain",
        }
    )

    session.mount(
        "https://",
        adapter,
    )

    return session


def download_file(
    *,
    session: requests.Session,
    url: str,
    destination: Path,
) -> str:
    if destination.is_file():
        return "existing_cache"

    response = session.get(
        url,
        timeout=90,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Download failed with HTTP "
            f"{response.status_code}: {url}"
        )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = destination.with_suffix(
        destination.suffix + ".tmp"
    )

    temporary_path.write_bytes(
        response.content
    )

    temporary_path.replace(
        destination
    )

    return "downloaded"


def sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def expected_sha256(
    path: Path,
) -> str:
    text = path.read_text(
        encoding="utf-8-sig",
    ).strip()

    if not text:
        raise RuntimeError(
            "MTGJSON SHA256 file is blank."
        )

    return text.split()[0].strip()


def load_set_list() -> list[dict[str, Any]]:
    with SET_LIST_PATH.open(
        "r",
        encoding="utf-8-sig",
    ) as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise RuntimeError(
            "SetList payload must be an object."
        )

    data = payload.get("data")

    if not isinstance(data, list):
        raise RuntimeError(
            "SetList payload data must be a list."
        )

    return [
        record
        for record in data
        if isinstance(record, dict)
    ]


def determine_product_set_name(
    row: pd.Series,
) -> str:
    canonical_set_name = clean_text(
        row.get(
            "canonical_set_name"
        )
    )

    if canonical_set_name:
        return canonical_set_name

    return clean_text(
        row.get(
            "canonical_product_name"
        )
    )


def exact_name_index(
    sets: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    index: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for record in sets:
        normalized = normalized_name(
            record.get("name")
        )

        if not normalized:
            continue

        index.setdefault(
            normalized,
            [],
        ).append(record)

    return index


def select_set_match(
    *,
    normalized_target: str,
    target_group_id: str,
    sets: list[dict[str, Any]],
    exact_index: dict[
        str,
        list[dict[str, Any]],
    ],
) -> tuple[
    dict[str, Any] | None,
    str,
    float,
    str,
]:
    exact_matches = exact_index.get(
        normalized_target,
        [],
    )

    if len(exact_matches) == 1:
        return (
            exact_matches[0],
            "exact_normalized_set_name",
            1.0,
            "matched",
        )

    if len(exact_matches) > 1:
        group_matches = [
            record
            for record in exact_matches
            if clean_text(
                record.get(
                    "tcgplayerGroupId"
                )
            ) == target_group_id
        ]

        if len(group_matches) == 1:
            return (
                group_matches[0],
                "exact_name_and_tcgplayer_group",
                1.0,
                "matched",
            )

        return (
            None,
            "ambiguous_exact_set_name",
            1.0,
            "review_required",
        )

    if target_group_id:
        group_matches = [
            record
            for record in sets
            if clean_text(
                record.get(
                    "tcgplayerGroupId"
                )
            ) == target_group_id
        ]

        if len(group_matches) == 1:
            return (
                group_matches[0],
                "exact_tcgplayer_group_id",
                1.0,
                "matched",
            )

    scored: list[
        tuple[
            float,
            dict[str, Any],
        ]
    ] = []

    for record in sets:
        candidate_name = normalized_name(
            record.get("name")
        )

        if not candidate_name:
            continue

        score = SequenceMatcher(
            None,
            normalized_target,
            candidate_name,
        ).ratio()

        if score >= 0.88:
            scored.append(
                (
                    score,
                    record,
                )
            )

    scored.sort(
        key=lambda item: (
            item[0],
            clean_text(
                item[1].get("code")
            ),
        ),
        reverse=True,
    )

    if not scored:
        return (
            None,
            "no_set_match",
            0.0,
            "unmatched",
        )

    top_score = scored[0][0]

    tied = [
        item
        for item in scored
        if abs(
            item[0] - top_score
        ) < 0.000001
    ]

    if len(tied) > 1:
        return (
            None,
            "ambiguous_fuzzy_set_name",
            top_score,
            "review_required",
        )

    return (
        scored[0][1],
        "fuzzy_set_name",
        top_score,
        "review_required",
    )


def main() -> int:
    for required_path in (
        COHORT_PATH,
        RELEASE_AUDIT_PATH,
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

    release_audit = pd.read_csv(
        RELEASE_AUDIT_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    review = cohorts[
        cohorts[
            "governed_candidate_cohort"
        ].isin(REVIEW_COHORTS)
    ].copy()

    if len(review) != 140:
        raise RuntimeError(
            "Expected 140 review products; "
            f"found {len(review)}."
        )

    if len(release_audit) != 140:
        raise RuntimeError(
            "Expected 140 cached release-audit rows; "
            f"found {len(release_audit)}."
        )

    session = build_session()

    set_list_source = download_file(
        session=session,
        url=SET_LIST_URL,
        destination=SET_LIST_PATH,
    )

    sha_source = download_file(
        session=session,
        url=SET_LIST_SHA256_URL,
        destination=SET_LIST_SHA256_PATH,
    )

    actual_hash = sha256_file(
        SET_LIST_PATH
    )

    expected_hash = expected_sha256(
        SET_LIST_SHA256_PATH
    )

    if actual_hash.casefold() != (
        expected_hash.casefold()
    ):
        raise RuntimeError(
            "SetList SHA256 validation failed."
        )

    sets = load_set_list()

    if not sets:
        raise RuntimeError(
            "MTGJSON SetList contains no sets."
        )

    name_index = exact_name_index(
        sets
    )

    release_by_id = (
        release_audit
        .drop_duplicates(
            subset=[
                "canonical_product_id",
            ],
            keep="first",
        )
        .set_index(
            "canonical_product_id",
            drop=False,
        )
    )

    output_rows: list[
        dict[str, Any]
    ] = []

    for _, row in review.iterrows():
        canonical_id = clean_text(
            row.get(
                "canonical_product_id"
            )
        )

        release_row = (
            release_by_id.loc[
                canonical_id
            ]
            if canonical_id
            in release_by_id.index
            else None
        )

        target_group_id = (
            clean_text(
                release_row.get(
                    "group_id"
                )
            )
            if release_row is not None
            else ""
        )

        product_set_name = (
            determine_product_set_name(
                row
            )
        )

        normalized_target = (
            normalized_name(
                product_set_name
            )
        )

        (
            matched_set,
            match_method,
            match_score,
            match_state,
        ) = select_set_match(
            normalized_target=normalized_target,
            target_group_id=target_group_id,
            sets=sets,
            exact_index=name_index,
        )

        set_code = (
            clean_text(
                matched_set.get("code")
            )
            if matched_set is not None
            else ""
        )

        set_name = (
            clean_text(
                matched_set.get("name")
            )
            if matched_set is not None
            else ""
        )

        set_release_date = (
            clean_text(
                matched_set.get(
                    "releaseDate"
                )
            )
            if matched_set is not None
            else ""
        )

        tcgcsv_release = (
            clean_text(
                release_row.get(
                    "release_date_candidate"
                )
            )
            if release_row is not None
            else ""
        )

        tcg_date = parse_date(
            tcgcsv_release
        )

        mtgjson_date = parse_date(
            set_release_date
        )

        if (
            tcg_date is not None
            and mtgjson_date is not None
        ):
            day_difference = abs(
                (
                    tcg_date.normalize()
                    - mtgjson_date.normalize()
                ).days
            )

            if day_difference == 0:
                comparison_state = (
                    "exact_date_agreement"
                )
            elif day_difference <= 7:
                comparison_state = (
                    "near_date_agreement"
                )
            else:
                comparison_state = (
                    "date_conflict_review_required"
                )

        elif mtgjson_date is not None:
            day_difference = ""
            comparison_state = (
                "mtgjson_set_date_available"
            )

        elif tcg_date is not None:
            day_difference = ""
            comparison_state = (
                "tcgcsv_date_only"
            )

        else:
            day_difference = ""
            comparison_state = (
                "release_date_unresolved"
            )

        if set_code:
            set_file_url = (
                "https://mtgjson.com/api/v5/"
                f"{set_code}.json"
            )

            set_cache_path = (
                CACHE_ROOT
                / "sets"
                / f"{set_code}.json"
            )

            relative_set_cache_path = str(
                set_cache_path.relative_to(
                    ROOT
                )
            )
        else:
            set_file_url = ""
            relative_set_cache_path = ""

        output_rows.append(
            {
                "canonical_product_id": (
                    canonical_id
                ),
                "tcgplayer_product_id": clean_text(
                    row.get(
                        "tcgplayer_product_id"
                    )
                ),
                "canonical_product_name": clean_text(
                    row.get(
                        "canonical_product_name"
                    )
                ),
                "canonical_set_name": (
                    product_set_name
                ),
                "governed_candidate_cohort": clean_text(
                    row.get(
                        "governed_candidate_cohort"
                    )
                ),
                "tcgcsv_release_date_candidate": (
                    tcgcsv_release
                ),
                "normalized_product_set_name": (
                    normalized_target
                ),
                "mtgjson_set_code": set_code,
                "mtgjson_set_name": set_name,
                "mtgjson_set_release_date": (
                    set_release_date
                ),
                "mtgjson_set_type": (
                    clean_text(
                        matched_set.get("type")
                    )
                    if matched_set is not None
                    else ""
                ),
                "mtgjson_parent_code": (
                    clean_text(
                        matched_set.get(
                            "parentCode"
                        )
                    )
                    if matched_set is not None
                    else ""
                ),
                "mtgjson_tcgplayer_group_id": (
                    clean_text(
                        matched_set.get(
                            "tcgplayerGroupId"
                        )
                    )
                    if matched_set is not None
                    else ""
                ),
                "set_match_method": (
                    match_method
                ),
                "set_match_score": (
                    round(
                        match_score,
                        6,
                    )
                ),
                "set_match_state": (
                    match_state
                ),
                "release_date_comparison_state": (
                    comparison_state
                ),
                "release_date_day_difference": (
                    day_difference
                ),
                "target_set_file_url": (
                    set_file_url
                ),
                "target_set_cache_path": (
                    relative_set_cache_path
                ),
                "final_release_date_assigned": (
                    False
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
                "set_match_state",
                "release_date_comparison_state",
                "canonical_product_name",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    routing_path = (
        OUTPUT_ROOT
        / "historical_mtgjson_set_routing_2026-07-22.csv"
    )

    matched_path = (
        OUTPUT_ROOT
        / "historical_mtgjson_matched_sets_2026-07-22.csv"
    )

    review_path = (
        OUTPUT_ROOT
        / "historical_mtgjson_set_match_review_2026-07-22.csv"
    )

    summary_path = (
        OUTPUT_ROOT
        / "historical_mtgjson_set_routing_summary_2026-07-22.json"
    )

    matched = output[
        output[
            "set_match_state"
        ].eq("matched")
    ].copy()

    review_required = output[
        ~output[
            "set_match_state"
        ].eq("matched")
    ].copy()

    output.to_csv(
        routing_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    matched.to_csv(
        matched_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    review_required.to_csv(
        review_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    match_counts = {
        str(key): int(value)
        for key, value in (
            output[
                "set_match_state"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    comparison_counts = {
        str(key): int(value)
        for key, value in (
            output[
                "release_date_comparison_state"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "routing_status": "PASS",
        "set_list_source": set_list_source,
        "sha256_source": sha_source,
        "set_list_sha256_verified": True,
        "mtgjson_set_records": int(
            len(sets)
        ),
        "review_product_rows": int(
            len(output)
        ),
        "matched_set_rows": int(
            len(matched)
        ),
        "set_match_review_rows": int(
            len(review_required)
        ),
        "set_match_state_counts": (
            match_counts
        ),
        "release_date_comparison_counts": (
            comparison_counts
        ),
        "unique_target_set_codes": int(
            output[
                "mtgjson_set_code"
            ]
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .nunique()
        ),
        "targeted_set_files_downloaded": 0,
        "all_printings_downloaded": False,
        "final_release_dates_assigned": 0,
        "final_eligibility_assigned": False,
        "scoring_allowed_rows": 0,
        "universal_investable_allowed_rows": 0,
        "production_registry_changed": False,
        "universal_database_changed": False,
        "output_files": {
            "routing": str(
                routing_path
            ),
            "matched_sets": str(
                matched_path
            ),
            "set_match_review": str(
                review_path
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
        "Phase 10.5R.1D.2.4C "
        "MTGJSON Set-List Routing Adapter"
    )
    print("=" * 76)
    print(
        f"Review products: {len(output)}"
    )
    print(
        f"MTGJSON sets loaded: {len(sets)}"
    )
    print(
        f"Matched set rows: {len(matched)}"
    )
    print(
        "Set-match review rows: "
        f"{len(review_required)}"
    )
    print(
        "Unique targeted set codes: "
        + str(
            summary[
                "unique_target_set_codes"
            ]
        )
    )
    print()
    print(
        "SetList SHA256 verified: YES"
    )
    print(
        "Targeted set files downloaded: NO"
    )
    print(
        "AllPrintings downloaded: NO"
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())