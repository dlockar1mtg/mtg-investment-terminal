from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


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

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_set_date_fallback"
)

SCHEMA_VERSION = "10.5R.1D.2.4F.1"

OUTPUT_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_product_name",
    "canonical_set_name",
    "governed_candidate_cohort",
    "set_route_state",
    "set_route_method",
    "selected_set_code",
    "selected_set_name",
    "selected_sealed_name",
    "selected_sealed_tcgplayer_product_id",
    "sealed_match_method",
    "sealed_match_state",
    "mtgjson_set_release_date",
    "canonical_name_years",
    "sealed_name_years",
    "set_release_year",
    "year_conflict_detected",
    "family_route_review_detected",
    "edition_review_detected",
    "identity_review_detected",
    "set_date_valid",
    "set_date_fallback_state",
    "set_date_fallback_review_reasons",
    "proposed_release_date",
    "proposed_release_date_source",
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


def extract_years(value: object) -> list[int]:
    text = clean_text(value)

    years = {
        int(match)
        for match in re.findall(
            r"\b(?:19|20)\d{2}\b",
            text,
        )
    }

    return sorted(years)


def main() -> int:
    for path in (
        AUTHORITATIVE_REVIEW_PATH,
        AUTHORITATIVE_ADJUDICATION_PATH,
    ):
        if not path.is_file():
            raise FileNotFoundError(
                f"Required input missing: {path}"
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

    if len(active) != 140:
        raise RuntimeError(
            "Expected 140 authoritative historical-review rows; "
            f"found {len(active)}."
        )

    if len(adjudication) != 140:
        raise RuntimeError(
            "Expected 140 authoritative adjudication rows; "
            f"found {len(adjudication)}."
        )

    set_only_ids = set(
        adjudication.loc[
            adjudication[
                "release_evidence_comparison_state"
            ].eq("mtgjson_set_date_only"),
            "canonical_product_id",
        ].tolist()
    )

    if len(set_only_ids) != 89:
        raise RuntimeError(
            "Expected 89 set-date-only products; "
            f"found {len(set_only_ids)}."
        )

    population = active[
        active[
            "canonical_product_id"
        ].isin(set_only_ids)
    ].copy()

    if len(population) != 89:
        raise RuntimeError(
            "Authoritative review and adjudication set-only "
            "populations do not align."
        )

    output_rows: list[dict[str, Any]] = []

    for _, row in population.iterrows():
        canonical_name = clean_text(
            row.get("canonical_product_name")
        )

        sealed_name = clean_text(
            row.get("selected_sealed_name")
        )

        set_date_text = clean_text(
            row.get("set_release_date")
        )

        set_date = parse_date(
            set_date_text
        )

        set_year = (
            int(set_date.year)
            if set_date is not None
            else None
        )

        canonical_years = extract_years(
            canonical_name
        )

        sealed_years = extract_years(
            sealed_name
        )

        product_years = sorted(
            set(canonical_years + sealed_years)
        )

        year_conflict = bool(
            set_year is not None
            and product_years
            and any(
                year != set_year
                for year in product_years
            )
        )

        set_route_state = clean_text(
            row.get("set_route_state")
        )

        set_route_method = clean_text(
            row.get("set_route_method")
        )

        family_review = (
            set_route_state
            == "set_family_review_required"
            or set_route_method
            == "governed_multi_set_family"
        )

        edition_review = bool(
            re.search(
                (
                    r"\b(?:convention|retail|exclusive|"
                    r"edition|language|japanese|french|"
                    r"german|italian)\b"
                ),
                (
                    canonical_name
                    + " "
                    + sealed_name
                ),
                flags=re.IGNORECASE,
            )
        )

        identity_review = (
            clean_text(
                row.get("sealed_match_method")
            )
            != "exact_tcgplayer_product_id"
            or clean_text(
                row.get("sealed_match_state")
            )
            != "matched"
        )

        reasons: list[str] = []

        if set_date is None:
            reasons.append(
                "set_release_date_missing_or_invalid"
            )

        if family_review:
            reasons.append(
                "governed_multi_set_family_route"
            )

        if year_conflict:
            reasons.append(
                "product_name_year_conflicts_with_set_year"
            )

        if edition_review:
            reasons.append(
                "product_edition_or_language_marker"
            )

        if identity_review:
            reasons.append(
                "product_identity_not_exactly_matched"
            )

        if reasons:
            fallback_state = (
                "set_date_fallback_review_required"
            )

            proposed_date = ""
            proposed_source = ""

        else:
            fallback_state = (
                "set_date_fallback_candidate"
            )

            proposed_date = set_date.strftime(
                "%Y-%m-%d"
            )

            proposed_source = (
                "mtgjson_set_release_date_fallback_candidate"
            )

        output_rows.append(
            {
                "canonical_product_id": clean_text(
                    row.get("canonical_product_id")
                ),
                "tcgplayer_product_id": clean_text(
                    row.get("tcgplayer_product_id")
                ),
                "canonical_product_name": canonical_name,
                "canonical_set_name": clean_text(
                    row.get("canonical_set_name")
                ),
                "governed_candidate_cohort": clean_text(
                    row.get(
                        "governed_candidate_cohort"
                    )
                ),
                "set_route_state": set_route_state,
                "set_route_method": set_route_method,
                "selected_set_code": clean_text(
                    row.get("selected_set_code")
                ),
                "selected_set_name": clean_text(
                    row.get("selected_set_name")
                ),
                "selected_sealed_name": sealed_name,
                "selected_sealed_tcgplayer_product_id": clean_text(
                    row.get(
                        "selected_sealed_tcgplayer_product_id"
                    )
                ),
                "sealed_match_method": clean_text(
                    row.get("sealed_match_method")
                ),
                "sealed_match_state": clean_text(
                    row.get("sealed_match_state")
                ),
                "mtgjson_set_release_date": set_date_text,
                "canonical_name_years": "|".join(
                    str(value)
                    for value in canonical_years
                ),
                "sealed_name_years": "|".join(
                    str(value)
                    for value in sealed_years
                ),
                "set_release_year": (
                    set_year
                    if set_year is not None
                    else ""
                ),
                "year_conflict_detected": year_conflict,
                "family_route_review_detected": (
                    family_review
                ),
                "edition_review_detected": (
                    edition_review
                ),
                "identity_review_detected": (
                    identity_review
                ),
                "set_date_valid": (
                    set_date is not None
                ),
                "set_date_fallback_state": (
                    fallback_state
                ),
                "set_date_fallback_review_reasons": (
                    "|".join(reasons)
                ),
                "proposed_release_date": (
                    proposed_date
                ),
                "proposed_release_date_source": (
                    proposed_source
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
                "set_date_fallback_state",
                "canonical_product_name",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    if len(output) != 89:
        raise RuntimeError(
            "Set-date fallback audit did not preserve "
            "all 89 records."
        )

    candidates = output[
        output[
            "set_date_fallback_state"
        ].eq(
            "set_date_fallback_candidate"
        )
    ].copy()

    review = output[
        output[
            "set_date_fallback_state"
        ].eq(
            "set_date_fallback_review_required"
        )
    ].copy()

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit_path = (
        OUTPUT_ROOT
        / "historical_set_date_fallback_audit_2026-07-22.csv"
    )

    candidate_path = (
        OUTPUT_ROOT
        / "historical_set_date_fallback_candidates_2026-07-22.csv"
    )

    review_path = (
        OUTPUT_ROOT
        / "historical_set_date_fallback_review_queue_2026-07-22.csv"
    )

    summary_path = (
        OUTPUT_ROOT
        / "historical_set_date_fallback_summary_2026-07-22.json"
    )

    output.to_csv(
        audit_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    candidates.to_csv(
        candidate_path,
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

    state_counts = {
        str(key): int(value)
        for key, value in (
            output[
                "set_date_fallback_state"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    reason_counts: dict[str, int] = {}

    for reasons in output[
        "set_date_fallback_review_reasons"
    ].tolist():
        for reason in clean_text(
            reasons
        ).split("|"):
            if not reason:
                continue

            reason_counts[reason] = (
                reason_counts.get(
                    reason,
                    0,
                )
                + 1
            )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "audit_status": "PASS",
        "authoritative_historical_review_rows": 140,
        "set_date_only_rows": int(len(output)),
        "set_date_fallback_candidate_rows": int(
            len(candidates)
        ),
        "set_date_fallback_review_rows": int(
            len(review)
        ),
        "set_date_fallback_state_counts": (
            state_counts
        ),
        "review_reason_counts": (
            reason_counts
        ),
        "final_release_dates_assigned": 0,
        "final_eligibility_assigned": False,
        "scoring_allowed_rows": 0,
        "universal_investable_allowed_rows": 0,
        "production_registry_changed": False,
        "universal_database_changed": False,
        "output_files": {
            "audit": str(audit_path),
            "fallback_candidates": str(
                candidate_path
            ),
            "review_queue": str(
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
        "Phase 10.5R.1D.2.4F.1 "
        "Set-Date Fallback Safety Audit"
    )
    print("=" * 76)
    print(
        f"Set-date-only products: {len(output)}"
    )
    print(
        "Fallback candidates: "
        f"{len(candidates)}"
    )
    print(
        "Fallback review required: "
        f"{len(review)}"
    )
    print()
    print("AUDIT STATUS: PASS")
    print("Final release dates assigned: 0")
    print("Final eligibility: NOT ASSIGNED")
    print("Scoring: DISABLED")
    print("Production registry: UNCHANGED")
    print("Universal database: UNCHANGED")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())