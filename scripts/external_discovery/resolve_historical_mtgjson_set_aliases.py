from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[2]

ROUTING_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_mtgjson_set_routing"
    / "historical_mtgjson_set_routing_2026-07-22.csv"
)

SET_LIST_PATH = (
    ROOT
    / "data"
    / "raw"
    / "mtgjson"
    / "SetList.json"
)

ALIAS_CONFIG_PATH = (
    ROOT
    / "config"
    / "historical_mtgjson_set_aliases.yaml"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_mtgjson_set_alias_resolution"
)

SCHEMA_VERSION = "10.5R.1D.2.4C.2"

OUTPUT_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_product_name",
    "canonical_set_name",
    "governed_candidate_cohort",
    "tcgcsv_release_date_candidate",
    "mtgjson_set_code",
    "mtgjson_set_name",
    "mtgjson_set_release_date",
    "mtgjson_set_type",
    "mtgjson_parent_code",
    "mtgjson_tcgplayer_group_id",
    "set_route_state",
    "set_route_method",
    "alias_basis",
    "candidate_set_codes",
    "family_review_reason",
    "release_date_comparison_state",
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


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(
        "r",
        encoding="utf-8-sig",
    ) as handle:
        value = yaml.safe_load(handle)

    if not isinstance(value, dict):
        raise RuntimeError(
            f"YAML file must contain an object: {path}"
        )

    return value


def load_set_list() -> dict[str, dict[str, Any]]:
    with SET_LIST_PATH.open(
        "r",
        encoding="utf-8-sig",
    ) as handle:
        payload = json.load(handle)

    records = payload.get("data")

    if not isinstance(records, list):
        raise RuntimeError(
            "SetList data must be a list."
        )

    result: dict[str, dict[str, Any]] = {}

    for record in records:
        if not isinstance(record, dict):
            continue

        code = clean_text(
            record.get("code")
        )

        if code:
            result[code] = record

    return result


def exact_alias_index(
    policy: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    for record in policy.get(
        "exact_aliases",
        [],
    ):
        if not isinstance(record, dict):
            continue

        canonical_id = clean_text(
            record.get(
                "canonical_product_id"
            )
        )

        if not canonical_id:
            continue

        if canonical_id in result:
            raise RuntimeError(
                "Duplicate exact alias ID: "
                f"{canonical_id}"
            )

        result[canonical_id] = record

    return result


def family_review_index(
    policy: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    for record in policy.get(
        "set_family_reviews",
        [],
    ):
        if not isinstance(record, dict):
            continue

        canonical_id = clean_text(
            record.get(
                "canonical_product_id"
            )
        )

        if not canonical_id:
            continue

        if canonical_id in result:
            raise RuntimeError(
                "Duplicate family-review ID: "
                f"{canonical_id}"
            )

        result[canonical_id] = record

    return result


def main() -> int:
    for path in (
        ROUTING_PATH,
        SET_LIST_PATH,
        ALIAS_CONFIG_PATH,
    ):
        if not path.is_file():
            raise FileNotFoundError(
                f"Required input missing: {path}"
            )

    routing = pd.read_csv(
        ROUTING_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    if len(routing) != 140:
        raise RuntimeError(
            "Expected 140 MTGJSON routing rows; "
            f"found {len(routing)}."
        )

    policy = load_yaml(
        ALIAS_CONFIG_PATH
    )

    sets_by_code = load_set_list()

    aliases = exact_alias_index(
        policy
    )

    families = family_review_index(
        policy
    )

    if len(aliases) != 9:
        raise RuntimeError(
            "Expected 9 exact aliases; "
            f"found {len(aliases)}."
        )

    if len(families) != 3:
        raise RuntimeError(
            "Expected 3 family reviews; "
            f"found {len(families)}."
        )

    overlap = set(aliases) & set(families)

    if overlap:
        raise RuntimeError(
            "Alias and family-review IDs overlap: "
            + ", ".join(sorted(overlap))
        )

    output_rows: list[
        dict[str, Any]
    ] = []

    target_scope_rows: list[
        dict[str, Any]
    ] = []

    for _, row in routing.iterrows():
        canonical_id = clean_text(
            row.get(
                "canonical_product_id"
            )
        )

        current_state = clean_text(
            row.get(
                "set_match_state"
            )
        )

        alias = aliases.get(
            canonical_id
        )

        family = families.get(
            canonical_id
        )

        set_record: dict[
            str,
            Any,
        ] | None = None

        alias_basis = ""
        candidate_codes: list[str] = []
        family_reason = ""

        if current_state == "matched":
            set_code = clean_text(
                row.get(
                    "mtgjson_set_code"
                )
            )

            set_record = sets_by_code.get(
                set_code
            )

            route_state = "matched"
            route_method = clean_text(
                row.get(
                    "set_match_method"
                )
            )

        elif alias is not None:
            set_code = clean_text(
                alias.get(
                    "mtgjson_set_code"
                )
            )

            set_record = sets_by_code.get(
                set_code
            )

            if set_record is None:
                raise RuntimeError(
                    "Alias references unknown MTGJSON set: "
                    f"{set_code}"
                )

            expected_name = clean_text(
                alias.get(
                    "mtgjson_set_name"
                )
            )

            actual_name = clean_text(
                set_record.get("name")
            )

            if expected_name != actual_name:
                raise RuntimeError(
                    "Alias set-name mismatch for "
                    f"{canonical_id}: expected "
                    f"{expected_name!r}; found "
                    f"{actual_name!r}."
                )

            route_state = "matched"
            route_method = (
                "governed_exact_alias"
            )

            alias_basis = clean_text(
                alias.get(
                    "alias_basis"
                )
            )

        elif family is not None:
            raw_codes = family.get(
                "candidate_set_codes",
                [],
            )

            candidate_codes = [
                clean_text(value)
                for value in raw_codes
                if clean_text(value)
            ]

            if not candidate_codes:
                raise RuntimeError(
                    "Family review has no candidate codes: "
                    f"{canonical_id}"
                )

            unknown_codes = [
                code
                for code in candidate_codes
                if code not in sets_by_code
            ]

            if unknown_codes:
                raise RuntimeError(
                    "Family review references unknown sets: "
                    + ", ".join(unknown_codes)
                )

            set_code = ""
            route_state = (
                "set_family_review_required"
            )
            route_method = (
                "governed_multi_set_family"
            )

            family_reason = clean_text(
                family.get(
                    "family_review_reason"
                )
            )

        else:
            set_code = ""
            route_state = "unresolved"
            route_method = "no_governed_route"

        if set_record is not None:
            set_name = clean_text(
                set_record.get("name")
            )

            set_release_date = clean_text(
                set_record.get(
                    "releaseDate"
                )
            )

            set_type = clean_text(
                set_record.get("type")
            )

            parent_code = clean_text(
                set_record.get(
                    "parentCode"
                )
            )

            group_id = clean_text(
                set_record.get(
                    "tcgplayerGroupId"
                )
            )
        else:
            set_name = ""
            set_release_date = ""
            set_type = ""
            parent_code = ""
            group_id = ""

        output_rows.append(
            {
                "canonical_product_id": canonical_id,
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
                "canonical_set_name": clean_text(
                    row.get(
                        "canonical_set_name"
                    )
                ),
                "governed_candidate_cohort": clean_text(
                    row.get(
                        "governed_candidate_cohort"
                    )
                ),
                "tcgcsv_release_date_candidate": clean_text(
                    row.get(
                        "tcgcsv_release_date_candidate"
                    )
                ),
                "mtgjson_set_code": set_code,
                "mtgjson_set_name": set_name,
                "mtgjson_set_release_date": (
                    set_release_date
                ),
                "mtgjson_set_type": set_type,
                "mtgjson_parent_code": (
                    parent_code
                ),
                "mtgjson_tcgplayer_group_id": (
                    group_id
                ),
                "set_route_state": route_state,
                "set_route_method": route_method,
                "alias_basis": alias_basis,
                "candidate_set_codes": "|".join(
                    candidate_codes
                ),
                "family_review_reason": (
                    family_reason
                ),
                "release_date_comparison_state": clean_text(
                    row.get(
                        "release_date_comparison_state"
                    )
                ),
                "final_release_date_assigned": False,
                "historical_eligibility_decision": (
                    "not_decided"
                ),
                "scoring_allowed": False,
                "universal_investable_allowed": False,
            }
        )

        target_codes = (
            [set_code]
            if set_code
            else candidate_codes
        )

        for target_code in target_codes:
            target_set = sets_by_code[
                target_code
            ]

            target_scope_rows.append(
                {
                    "mtgjson_set_code": (
                        target_code
                    ),
                    "mtgjson_set_name": clean_text(
                        target_set.get(
                            "name"
                        )
                    ),
                    "mtgjson_set_release_date": clean_text(
                        target_set.get(
                            "releaseDate"
                        )
                    ),
                    "target_set_file_url": (
                        "https://mtgjson.com/api/v5/"
                        f"{target_code}.json"
                    ),
                    "target_set_cache_path": str(
                        (
                            ROOT
                            / "data"
                            / "raw"
                            / "mtgjson"
                            / "sets"
                            / f"{target_code}.json"
                        ).relative_to(ROOT)
                    ),
                    "canonical_product_id": (
                        canonical_id
                    ),
                    "route_method": (
                        route_method
                    ),
                }
            )

    output = (
        pd.DataFrame(
            output_rows,
            columns=OUTPUT_COLUMNS,
        )
        .sort_values(
            [
                "set_route_state",
                "canonical_product_name",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    target_scope_detail = pd.DataFrame(
        target_scope_rows
    )

    target_scope = (
        target_scope_detail
        .groupby(
            [
                "mtgjson_set_code",
                "mtgjson_set_name",
                "mtgjson_set_release_date",
                "target_set_file_url",
                "target_set_cache_path",
            ],
            as_index=False,
            sort=True,
        )
        .agg(
            routed_product_count=(
                "canonical_product_id",
                "nunique",
            ),
            route_methods=(
                "route_method",
                lambda values: "|".join(
                    sorted(
                        set(values)
                    )
                ),
            ),
        )
    )

    state_counts = {
        str(key): int(value)
        for key, value in (
            output[
                "set_route_state"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    expected_states = {
        "matched": 137,
        "set_family_review_required": 3,
    }

    if state_counts != expected_states:
        raise RuntimeError(
            "Unexpected route-state counts. "
            f"Expected {expected_states}; "
            f"found {state_counts}."
        )

    if len(target_scope) != 138:
        raise RuntimeError(
            "Expected 138 unique targeted set files; "
            f"found {len(target_scope)}."
        )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    resolution_path = (
        OUTPUT_ROOT
        / "historical_mtgjson_set_alias_resolution_2026-07-22.csv"
    )

    family_path = (
        OUTPUT_ROOT
        / "historical_mtgjson_set_family_review_2026-07-22.csv"
    )

    scope_path = (
        OUTPUT_ROOT
        / "historical_mtgjson_targeted_set_scope_2026-07-22.csv"
    )

    summary_path = (
        OUTPUT_ROOT
        / "historical_mtgjson_set_alias_resolution_summary_2026-07-22.json"
    )

    output.to_csv(
        resolution_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    output[
        output[
            "set_route_state"
        ].eq(
            "set_family_review_required"
        )
    ].to_csv(
        family_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    target_scope.to_csv(
        scope_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "resolution_status": "PASS",
        "review_product_rows": int(
            len(output)
        ),
        "prior_matched_rows": 128,
        "governed_exact_alias_rows": 9,
        "set_family_review_rows": 3,
        "fully_unresolved_rows": int(
            output[
                "set_route_state"
            ].eq("unresolved").sum()
        ),
        "set_route_state_counts": (
            state_counts
        ),
        "unique_targeted_set_files": int(
            len(target_scope)
        ),
        "targeted_set_files_downloaded": 0,
        "final_release_dates_assigned": 0,
        "final_eligibility_assigned": False,
        "scoring_allowed_rows": 0,
        "universal_investable_allowed_rows": 0,
        "production_registry_changed": False,
        "universal_database_changed": False,
        "output_files": {
            "resolution": str(
                resolution_path
            ),
            "family_review": str(
                family_path
            ),
            "targeted_set_scope": str(
                scope_path
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
        "Phase 10.5R.1D.2.4C.2 "
        "Governed MTGJSON Alias Resolution"
    )
    print("=" * 76)
    print(
        f"Review products: {len(output)}"
    )
    print(
        "Prior matched routes: 128"
    )
    print(
        "Governed exact aliases: 9"
    )
    print(
        "Set-family reviews: 3"
    )
    print(
        "Fully unresolved routes: "
        + str(
            summary[
                "fully_unresolved_rows"
            ]
        )
    )
    print(
        "Unique targeted set files: "
        + str(
            len(target_scope)
        )
    )
    print()
    print(
        "RESOLUTION STATUS: PASS"
    )
    print(
        "Targeted set files downloaded: NO"
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