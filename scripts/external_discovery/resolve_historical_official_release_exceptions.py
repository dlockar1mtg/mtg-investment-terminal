from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[2]

GOVERNANCE_AUDIT_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_release_date_governance"
    / "historical_release_date_governance_audit_2026-07-22.csv"
)

POLICY_PATH = (
    ROOT
    / "config"
    / "historical_official_release_date_exceptions.yaml"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_final_release_dates"
)

SCHEMA_VERSION = "10.5R.1D.2.4H.1"

EXPECTED_EXCEPTION_IDS = {
    "MTG-CANON-TCGPLAYER-246935",
    "MTG-CANON-TCGPLAYER-563752",
}

EXPECTED_REMAINING_UNRESOLVED_IDS = {
    "MTG-CANON-TCGPLAYER-245972",
}

EXPECTED_PRIOR_UNRESOLVED_IDS = (
    EXPECTED_EXCEPTION_IDS
    | EXPECTED_REMAINING_UNRESOLVED_IDS
)

OUTPUT_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_product_name",
    "canonical_set_name",
    "governed_candidate_cohort",
    "release_evidence_comparison_state",
    "tcgcsv_release_date",
    "mtgjson_product_release_date",
    "mtgjson_set_release_date",
    "governed_release_date",
    "governed_release_date_source",
    "governed_release_date_state",
    "release_date_governance_reason",
    "official_exception_applied",
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


def repository_relative_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def normalize_date(value: object) -> str:
    cleaned = clean_text(value)

    if not cleaned:
        return ""

    parsed = pd.to_datetime(
        cleaned,
        errors="coerce",
        utc=True,
    )

    if pd.isna(parsed):
        raise RuntimeError(
            f"Invalid governed release date: {cleaned}"
        )

    return parsed.strftime("%Y-%m-%d")


def load_policy() -> dict[str, Any]:
    with POLICY_PATH.open(
        "r",
        encoding="utf-8-sig",
    ) as handle:
        value = yaml.safe_load(handle)

    if not isinstance(value, dict):
        raise RuntimeError(
            "Official release policy must be a YAML object."
        )

    return value


def build_exception_index(
    policy: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    for record in policy.get(
        "official_release_date_exceptions",
        [],
    ):
        if not isinstance(record, dict):
            continue

        canonical_id = clean_text(
            record.get("canonical_product_id")
        )

        if not canonical_id:
            continue

        if canonical_id in result:
            raise RuntimeError(
                "Duplicate official release exception: "
                f"{canonical_id}"
            )

        result[canonical_id] = record

    return result


def main() -> int:
    for required_path in (
        GOVERNANCE_AUDIT_PATH,
        POLICY_PATH,
    ):
        if not required_path.is_file():
            raise FileNotFoundError(
                f"Required input missing: {required_path}"
            )

    governance = pd.read_csv(
        GOVERNANCE_AUDIT_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    if len(governance) != 140:
        raise RuntimeError(
            "Expected 140 governance rows; "
            f"found {len(governance)}."
        )

    policy = load_policy()
    exceptions = build_exception_index(policy)

    if set(exceptions) != EXPECTED_EXCEPTION_IDS:
        raise RuntimeError(
            "Official exception IDs do not match the expected "
            "two-product official-exception population."
        )

    prior_governed = governance[
        governance[
            "governed_release_date_state"
        ].eq("governed_release_date")
    ]

    prior_unresolved = governance[
        ~governance[
            "governed_release_date_state"
        ].eq("governed_release_date")
    ]

    if len(prior_governed) != 137:
        raise RuntimeError(
            "Expected 137 previously governed dates; "
            f"found {len(prior_governed)}."
        )

    if len(prior_unresolved) != 3:
        raise RuntimeError(
            "Expected three prior unresolved release dates; "
            f"found {len(prior_unresolved)}."
        )

    if set(
        prior_unresolved["canonical_product_id"]
    ) != EXPECTED_PRIOR_UNRESOLVED_IDS:
        raise RuntimeError(
            "Prior unresolved products do not match the "
            "governed three-product unresolved population."
        )

    output_rows: list[dict[str, Any]] = []

    for _, row in governance.iterrows():
        canonical_id = clean_text(
            row.get("canonical_product_id")
        )

        exception = exceptions.get(canonical_id)

        governed_date = clean_text(
            row.get("governed_release_date")
        )

        governed_source = clean_text(
            row.get("governed_release_date_source")
        )

        governance_state = clean_text(
            row.get("governed_release_date_state")
        )

        governance_reason = clean_text(
            row.get("release_date_governance_reason")
        )

        exception_applied = False

        if exception is not None:
            if governed_date:
                raise RuntimeError(
                    "Official exception product was already assigned "
                    f"a release date: {canonical_id}"
                )

            governed_date = normalize_date(
                exception.get("governed_release_date")
            )

            governed_source = clean_text(
                exception.get(
                    "governed_release_date_source"
                )
            )

            governance_state = (
                "governed_release_date"
            )

            governance_reason = clean_text(
                exception.get("resolution_basis")
            )

            exception_applied = True

        if (
            not governed_date
            and canonical_id
            not in EXPECTED_REMAINING_UNRESOLVED_IDS
        ):
            raise RuntimeError(
                "Unexpected final governed release date remains "
                f"blank for {canonical_id}."
            )

        output_rows.append(
            {
                "canonical_product_id": canonical_id,
                "tcgplayer_product_id": clean_text(
                    row.get("tcgplayer_product_id")
                ),
                "canonical_product_name": clean_text(
                    row.get("canonical_product_name")
                ),
                "canonical_set_name": clean_text(
                    row.get("canonical_set_name")
                ),
                "governed_candidate_cohort": clean_text(
                    row.get(
                        "governed_candidate_cohort"
                    )
                ),
                "release_evidence_comparison_state": clean_text(
                    row.get(
                        "release_evidence_comparison_state"
                    )
                ),
                "tcgcsv_release_date": clean_text(
                    row.get("tcgcsv_release_date")
                ),
                "mtgjson_product_release_date": clean_text(
                    row.get(
                        "mtgjson_product_release_date"
                    )
                ),
                "mtgjson_set_release_date": clean_text(
                    row.get("mtgjson_set_release_date")
                ),
                "governed_release_date": governed_date,
                "governed_release_date_source": (
                    governed_source
                ),
                "governed_release_date_state": (
                    governance_state
                ),
                "release_date_governance_reason": (
                    governance_reason
                ),
                "official_exception_applied": (
                    exception_applied
                ),
                "final_release_date_assigned": bool(governed_date),
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
            "canonical_product_name",
            kind="stable",
        )
        .reset_index(drop=True)
    )

    if len(output) != 140:
        raise RuntimeError(
            "Final release output did not preserve 140 rows."
        )

    final_unresolved = output[
        output[
            "governed_release_date"
        ].astype(str).str.strip().eq("")
    ].copy()

    if len(final_unresolved) != 1:
        raise RuntimeError(
            "Expected one final unresolved release date; "
            f"found {len(final_unresolved)}."
        )

    if set(
        final_unresolved["canonical_product_id"]
    ) != EXPECTED_REMAINING_UNRESOLVED_IDS:
        raise RuntimeError(
            "Unexpected final unresolved release-date products."
        )

    exception_rows = output[
        output[
            "official_exception_applied"
        ].eq(True)
    ]

    if len(exception_rows) != 2:
        raise RuntimeError(
            "Expected two applied official exceptions; "
            f"found {len(exception_rows)}."
        )

    mystery_2021 = output[
        output[
            "canonical_product_id"
        ].eq("MTG-CANON-TCGPLAYER-246935")
    ].iloc[0]

    mystery_2 = output[
        output[
            "canonical_product_id"
        ].eq("MTG-CANON-TCGPLAYER-563752")
    ].iloc[0]

    if mystery_2021["governed_release_date"] != "2021-08-20":
        raise RuntimeError(
            "Mystery Booster Convention Edition 2021 "
            "date is incorrect."
        )

    if mystery_2["governed_release_date"] != "2024-10-25":
        raise RuntimeError(
            "Mystery Booster 2 date is incorrect."
        )

    renaissance = output[
        output[
            "canonical_product_id"
        ].eq("MTG-CANON-TCGPLAYER-245972")
    ].iloc[0]

    if clean_text(
        renaissance["governed_release_date"]
    ):
        raise RuntimeError(
            "Renaissance Italian received an unsupported "
            "final release date."
        )

    if bool(
        renaissance["official_exception_applied"]
    ):
        raise RuntimeError(
            "Renaissance Italian incorrectly received an "
            "official release-date exception."
        )

    if bool(
        renaissance["final_release_date_assigned"]
    ):
        raise RuntimeError(
            "Renaissance Italian was incorrectly marked as "
            "having a final release date."
        )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    final_path = (
        OUTPUT_ROOT
        / "historical_final_governed_release_dates_2026-07-22.csv"
    )

    exceptions_path = (
        OUTPUT_ROOT
        / "historical_official_release_date_exceptions_2026-07-22.csv"
    )

    summary_path = (
        OUTPUT_ROOT
        / "historical_final_release_date_summary_2026-07-22.json"
    )

    output.to_csv(
        final_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    exception_rows.to_csv(
        exceptions_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    source_counts = {
        str(key): int(value)
        for key, value in (
            output.loc[
                output[
                    "governed_release_date_source"
                ].astype(str).str.strip().ne(""),
                "governed_release_date_source",
            ]
            .value_counts()
            .sort_index()
            .items()
        )
    }

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "resolution_status": "PASS",
        "authoritative_historical_products": 140,
        "prior_governed_release_dates": 137,
        "official_release_exception_rows": 2,
        "final_governed_release_dates": 139,
        "unresolved_release_dates": 1,
        "governed_release_date_source_counts": (
            source_counts
        ),
        "final_eligibility_assigned": False,
        "scoring_allowed_rows": 0,
        "universal_investable_allowed_rows": 0,
        "production_registry_changed": False,
        "universal_database_changed": False,
        "output_files": {
            "final_governed_release_dates": (
                repository_relative_path(final_path)
            ),
            "official_exceptions": (
                repository_relative_path(exceptions_path)
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
        "Phase 10.5R.1D.2.4H.1 "
        "Official Release-Date Exception Resolution"
    )
    print("=" * 76)
    print("Authoritative historical products: 140")
    print("Previously governed release dates: 137")
    print("Official release-date exceptions: 2")
    print("Final governed release dates: 139")
    print("Unresolved release dates: 1")
    print()
    print("RESOLUTION STATUS: PASS")
    print("Final eligibility: NOT ASSIGNED")
    print("Scoring: DISABLED")
    print("Production registry: UNCHANGED")
    print("Universal database: UNCHANGED")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())