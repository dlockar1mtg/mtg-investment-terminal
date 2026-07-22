from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[2]

AUTHORITATIVE_REVIEW_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_mtgjson_sealed_products"
    / "historical_mtgjson_sealed_product_audit_2026-07-22.csv"
)

AUTHORITATIVE_ADJUDICATION_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_release_adjudication"
    / "historical_release_evidence_adjudication_2026-07-22.csv"
)

SET_FALLBACK_AUDIT_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_set_date_fallback"
    / "historical_set_date_fallback_audit_2026-07-22.csv"
)

POLICY_PATH = (
    ROOT
    / "config"
    / "historical_release_date_policy.yaml"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_release_date_governance"
)

SCHEMA_VERSION = "10.5R.1D.2.4G.1"

UNRESOLVED_IDS = {
    "MTG-CANON-TCGPLAYER-245972",
    "MTG-CANON-TCGPLAYER-246935",
    "MTG-CANON-TCGPLAYER-563752",
}

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
    "set_date_fallback_state",
    "governed_release_date",
    "governed_release_date_source",
    "governed_release_date_state",
    "release_date_governance_reason",
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


def normalized_date(value: object) -> str:
    cleaned = clean_text(value)

    if not cleaned:
        return ""

    parsed = pd.to_datetime(
        cleaned,
        errors="coerce",
        utc=True,
    )

    if pd.isna(parsed):
        return ""

    return parsed.strftime("%Y-%m-%d")


def load_policy() -> dict[str, Any]:
    with POLICY_PATH.open(
        "r",
        encoding="utf-8-sig",
    ) as handle:
        value = yaml.safe_load(handle)

    if not isinstance(value, dict):
        raise RuntimeError(
            "Release-date policy must contain a YAML object."
        )

    return value


def main() -> int:
    for required_path in (
        AUTHORITATIVE_REVIEW_PATH,
        AUTHORITATIVE_ADJUDICATION_PATH,
        SET_FALLBACK_AUDIT_PATH,
        POLICY_PATH,
    ):
        if not required_path.is_file():
            raise FileNotFoundError(
                f"Required input missing: {required_path}"
            )

    active = pd.read_csv(
        AUTHORITATIVE_REVIEW_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    adjudication = pd.read_csv(
        AUTHORITATIVE_ADJUDICATION_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    fallback = pd.read_csv(
        SET_FALLBACK_AUDIT_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    policy = load_policy()

    if len(active) != 140:
        raise RuntimeError(
            f"Expected 140 authoritative products; found {len(active)}."
        )

    if len(adjudication) != 140:
        raise RuntimeError(
            "Expected 140 authoritative adjudication rows; "
            f"found {len(adjudication)}."
        )

    if len(fallback) != 89:
        raise RuntimeError(
            "Expected 89 set-fallback rows; "
            f"found {len(fallback)}."
        )

    configured_unresolved = {
        clean_text(record.get("canonical_product_id"))
        for record in policy.get("unresolved_products", [])
        if isinstance(record, dict)
    }

    if configured_unresolved != UNRESOLVED_IDS:
        raise RuntimeError(
            "Configured unresolved products do not match "
            "the governed two-product exception set."
        )

    active_by_id = (
        active
        .drop_duplicates(
            subset=["canonical_product_id"],
            keep="first",
        )
        .set_index("canonical_product_id")
    )

    fallback_by_id = (
        fallback
        .drop_duplicates(
            subset=["canonical_product_id"],
            keep="first",
        )
        .set_index("canonical_product_id")
    )

    output_rows: list[dict[str, Any]] = []

    for _, row in adjudication.iterrows():
        canonical_id = clean_text(
            row.get("canonical_product_id")
        )

        if canonical_id not in active_by_id.index:
            raise RuntimeError(
                f"Adjudication row is not active: {canonical_id}"
            )

        active_row = active_by_id.loc[canonical_id]

        evidence_state = clean_text(
            row.get("release_evidence_comparison_state")
        )

        tcgcsv_date = normalized_date(
            row.get("tcgcsv_release_date")
        )

        product_date = normalized_date(
            row.get("mtgjson_product_release_date")
        )

        set_date = normalized_date(
            row.get("mtgjson_set_release_date")
        )

        fallback_state = ""

        if canonical_id in fallback_by_id.index:
            fallback_state = clean_text(
                fallback_by_id.loc[
                    canonical_id
                ].get("set_date_fallback_state")
            )

        if canonical_id in UNRESOLVED_IDS:
            governed_date = ""
            governed_source = ""

            if canonical_id == (
                "MTG-CANON-TCGPLAYER-245972"
            ):
                governance_state = (
                    "sealed_product_identity_review_required"
                )

                governance_reason = (
                    "The Italian Renaissance booster box is not "
                    "exactly matched to the selected German sealed "
                    "product and cannot inherit the generic set date."
                )

            elif canonical_id == (
                "MTG-CANON-TCGPLAYER-246935"
            ):
                governance_state = (
                    "edition_specific_release_date_required"
                )

                governance_reason = (
                    "The 2021 Convention Edition cannot inherit "
                    "the 2019 Mystery Booster parent-set date."
                )

            elif canonical_id == (
                "MTG-CANON-TCGPLAYER-563752"
            ):
                governance_state = (
                    "product_date_conflict_unresolved"
                )

                governance_reason = (
                    "TCGCSV and MTGJSON product dates conflict."
                )

            else:
                raise RuntimeError(
                    "Unexpected governed unresolved product: "
                    f"{canonical_id}"
                )

        elif evidence_state == (
            "product_and_tcgcsv_exact_agreement"
        ):
            if not product_date or product_date != tcgcsv_date:
                raise RuntimeError(
                    "Exact-agreement evidence is internally "
                    f"inconsistent for {canonical_id}."
                )

            governed_date = product_date
            governed_source = (
                "mtgjson_product_and_tcgcsv_exact_agreement"
            )
            governance_state = "governed_release_date"
            governance_reason = (
                "Independent product-level sources agree exactly."
            )

        elif evidence_state == "mtgjson_product_date_only":
            if not product_date:
                raise RuntimeError(
                    "MTGJSON product-date-only row has no date: "
                    f"{canonical_id}"
                )

            governed_date = product_date
            governed_source = (
                "mtgjson_product_release_date"
            )
            governance_state = "governed_release_date"
            governance_reason = (
                "Exact sealed-product identity with an MTGJSON "
                "product-level release date."
            )

        elif evidence_state == "mtgjson_set_date_only":
            if not set_date:
                raise RuntimeError(
                    "Set-date-only row has no valid set date: "
                    f"{canonical_id}"
                )

            governed_date = set_date
            governed_source = (
                "mtgjson_set_release_date_fallback"
            )
            governance_state = "governed_release_date"
            governance_reason = (
                "Exact sealed-product identity with no product-level "
                "date and no substantive edition-specific conflict."
            )

        else:
            raise RuntimeError(
                "Unexpected unresolved evidence state for "
                f"{canonical_id}: {evidence_state}"
            )

        assigned = bool(governed_date)

        output_rows.append(
            {
                "canonical_product_id": canonical_id,
                "tcgplayer_product_id": clean_text(
                    active_row.get("tcgplayer_product_id")
                ),
                "canonical_product_name": clean_text(
                    active_row.get("canonical_product_name")
                ),
                "canonical_set_name": clean_text(
                    active_row.get("canonical_set_name")
                ),
                "governed_candidate_cohort": clean_text(
                    active_row.get(
                        "governed_candidate_cohort"
                    )
                ),
                "release_evidence_comparison_state": (
                    evidence_state
                ),
                "tcgcsv_release_date": tcgcsv_date,
                "mtgjson_product_release_date": (
                    product_date
                ),
                "mtgjson_set_release_date": set_date,
                "set_date_fallback_state": fallback_state,
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
                "final_release_date_assigned": assigned,
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
                "governed_release_date_state",
                "canonical_product_name",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    if len(output) != 140:
        raise RuntimeError(
            "Release governance did not preserve 140 rows."
        )

    governed = output[
        output[
            "governed_release_date_state"
        ].eq("governed_release_date")
    ].copy()

    unresolved = output[
        ~output[
            "governed_release_date_state"
        ].eq("governed_release_date")
    ].copy()

    if len(governed) != 137:
        raise RuntimeError(
            "Expected 137 governed release dates; "
            f"found {len(governed)}."
        )

    if len(unresolved) != 3:
        raise RuntimeError(
            "Expected three unresolved release dates; "
            f"found {len(unresolved)}."
        )

    if set(
        unresolved["canonical_product_id"]
    ) != UNRESOLVED_IDS:
        raise RuntimeError(
            "Unexpected unresolved release-date products."
        )

    source_counts = {
        str(key): int(value)
        for key, value in (
            governed[
                "governed_release_date_source"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    expected_sources = {
        "mtgjson_set_release_date_fallback": 87,
        "mtgjson_product_and_tcgcsv_exact_agreement": 40,
        "mtgjson_product_release_date": 10,
    }

    if source_counts != expected_sources:
        raise RuntimeError(
            "Unexpected governed source counts. "
            f"Expected {expected_sources}; "
            f"found {source_counts}."
        )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit_path = (
        OUTPUT_ROOT
        / "historical_release_date_governance_audit_2026-07-22.csv"
    )

    governed_path = (
        OUTPUT_ROOT
        / "historical_governed_release_dates_2026-07-22.csv"
    )

    unresolved_path = (
        OUTPUT_ROOT
        / "historical_unresolved_release_dates_2026-07-22.csv"
    )

    summary_path = (
        OUTPUT_ROOT
        / "historical_release_date_governance_summary_2026-07-22.json"
    )

    output.to_csv(
        audit_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    governed.to_csv(
        governed_path,
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

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "governance_status": "PASS",
        "authoritative_historical_review_rows": 140,
        "governed_release_date_rows": 137,
        "unresolved_release_date_rows": 3,
        "governed_release_date_source_counts": (
            source_counts
        ),
        "unresolved_canonical_product_ids": sorted(
            UNRESOLVED_IDS
        ),
        "final_eligibility_assigned": False,
        "scoring_allowed_rows": 0,
        "universal_investable_allowed_rows": 0,
        "production_registry_changed": False,
        "universal_database_changed": False,
        "output_files": {
            "audit": str(audit_path),
            "governed_release_dates": str(
                governed_path
            ),
            "unresolved_release_dates": str(
                unresolved_path
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
        "Phase 10.5R.1D.2.4G.1 "
        "Historical Release-Date Governance"
    )
    print("=" * 76)
    print("Authoritative historical products: 140")
    print("Governed release dates: 137")
    print("Unresolved release dates: 3")
    print()
    print("Release-date sources:")
    print("  Exact product-source agreement: 40")
    print("  MTGJSON product date only: 10")
    print("  MTGJSON set-date fallback: 87")
    print()
    print("GOVERNANCE STATUS: PASS")
    print("Final eligibility: NOT ASSIGNED")
    print("Scoring: DISABLED")
    print("Production registry: UNCHANGED")
    print("Universal database: UNCHANGED")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())