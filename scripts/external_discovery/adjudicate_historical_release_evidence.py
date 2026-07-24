from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

SEALED_AUDIT_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_mtgjson_sealed_products"
    / "historical_mtgjson_sealed_product_audit_2026-07-22.csv"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_release_adjudication"
)

ADJUDICATION_PATH = (
    OUTPUT_ROOT
    / "historical_release_evidence_adjudication_2026-07-22.csv"
)

SUMMARY_PATH = (
    OUTPUT_ROOT
    / "historical_release_evidence_adjudication_summary_2026-07-22.json"
)

SCHEMA_VERSION = "10.5R.1D.2.4D.1"

OUTPUT_COLUMNS = [
    "canonical_product_id",
    "canonical_product_name",
    "sealed_match_state",
    "sealed_match_method",
    "tcgcsv_release_date",
    "mtgjson_product_release_date",
    "mtgjson_set_release_date",
    "product_vs_tcgcsv_days",
    "product_vs_set_days",
    "release_evidence_comparison_state",
    "final_release_date",
    "final_release_date_source",
    "final_release_date_assigned",
    "historical_eligibility_decision",
    "scoring_allowed",
    "universal_investable_allowed",
]

EXPECTED_STATE_COUNTS = {
    "mtgjson_set_date_only": 89,
    "product_and_tcgcsv_exact_agreement": 40,
    "mtgjson_product_date_only": 10,
    "product_and_tcgcsv_conflict": 1,
}


def clean_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).strip()

    if text.casefold() in {
        "",
        "nan",
        "nat",
        "none",
        "<na>",
    }:
        return ""

    return text


def normalized_date(value: Any) -> str:
    text = clean_text(value)

    if not text:
        return ""

    parsed = pd.to_datetime(
        text,
        errors="raise",
    )

    return parsed.strftime("%Y-%m-%d")


def absolute_day_difference(
    first_value: Any,
    second_value: Any,
) -> str:
    first_text = clean_text(first_value)
    second_text = clean_text(second_value)

    if not first_text or not second_text:
        return ""

    first_date = pd.to_datetime(
        first_text,
        errors="raise",
    )

    second_date = pd.to_datetime(
        second_text,
        errors="raise",
    )

    return str(
        abs(
            int(
                (
                    first_date - second_date
                ).days
            )
        )
    )


def comparison_state(
    *,
    tcgcsv_date: str,
    product_date: str,
    set_date: str,
) -> str:
    has_tcgcsv = bool(tcgcsv_date)
    has_product = bool(product_date)
    has_set = bool(set_date)

    if has_product and has_tcgcsv:
        if normalized_date(product_date) == normalized_date(
            tcgcsv_date
        ):
            return "product_and_tcgcsv_exact_agreement"

        return "product_and_tcgcsv_conflict"

    if has_product:
        return "mtgjson_product_date_only"

    if has_set:
        return "mtgjson_set_date_only"

    if has_tcgcsv:
        return "tcgcsv_date_only"

    return "release_date_unresolved"


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def state_counts(
    frame: pd.DataFrame,
    column: str,
) -> dict[str, int]:
    return {
        str(key): int(value)
        for key, value in (
            frame[column]
            .value_counts(dropna=False)
            .sort_index()
            .items()
        )
    }


def main() -> int:
    if not SEALED_AUDIT_PATH.is_file():
        raise FileNotFoundError(
            f"Required sealed audit missing: "
            f"{SEALED_AUDIT_PATH}"
        )

    sealed = pd.read_csv(
        SEALED_AUDIT_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    if len(sealed) != 140:
        raise RuntimeError(
            "Expected 140 sealed-product audit rows; "
            f"found {len(sealed)}."
        )

    canonical_ids = (
        sealed["canonical_product_id"]
        .map(clean_text)
    )

    if canonical_ids.nunique() != 140:
        raise RuntimeError(
            "Expected 140 unique canonical product IDs; "
            f"found {canonical_ids.nunique()}."
        )

    output_rows: list[dict[str, Any]] = []

    for _, row in sealed.iterrows():
        tcgcsv_date = clean_text(
            row.get(
                "tcgcsv_release_date_candidate"
            )
        )

        product_date = clean_text(
            row.get(
                "product_release_date_candidate"
            )
        )

        set_date = clean_text(
            row.get("set_release_date")
        )

        evidence_state = comparison_state(
            tcgcsv_date=tcgcsv_date,
            product_date=product_date,
            set_date=set_date,
        )

        output_rows.append(
            {
                "canonical_product_id": clean_text(
                    row.get("canonical_product_id")
                ),
                "canonical_product_name": clean_text(
                    row.get("canonical_product_name")
                ),
                "sealed_match_state": clean_text(
                    row.get("sealed_match_state")
                ),
                "sealed_match_method": clean_text(
                    row.get("sealed_match_method")
                ),
                "tcgcsv_release_date": tcgcsv_date,
                "mtgjson_product_release_date": (
                    product_date
                ),
                "mtgjson_set_release_date": set_date,
                "product_vs_tcgcsv_days": (
                    absolute_day_difference(
                        product_date,
                        tcgcsv_date,
                    )
                ),
                "product_vs_set_days": (
                    absolute_day_difference(
                        product_date,
                        set_date,
                    )
                ),
                "release_evidence_comparison_state": (
                    evidence_state
                ),
                "final_release_date": "",
                "final_release_date_source": "",
                "final_release_date_assigned": False,
                "historical_eligibility_decision": (
                    "not_decided"
                ),
                "scoring_allowed": False,
                "universal_investable_allowed": False,
            }
        )

    output = pd.DataFrame(
        output_rows,
        columns=OUTPUT_COLUMNS,
    )

    if len(output) != 140:
        raise RuntimeError(
            "Expected 140 adjudication rows; "
            f"found {len(output)}."
        )

    if (
        output["canonical_product_id"].nunique()
        != 140
    ):
        raise RuntimeError(
            "Adjudication output does not contain "
            "140 unique canonical IDs."
        )

    output_states = state_counts(
        output,
        "release_evidence_comparison_state",
    )

    if output_states != EXPECTED_STATE_COUNTS:
        raise RuntimeError(
            "Unexpected evidence-comparison states. "
            f"Expected {EXPECTED_STATE_COUNTS}; "
            f"found {output_states}."
        )

    if output["mtgjson_set_release_date"].eq("").any():
        raise RuntimeError(
            "Every authoritative row must retain an "
            "MTGJSON set release date."
        )

    disabled_control_checks = {
        "final_release_date_populated": int(
            output["final_release_date"]
            .ne("")
            .sum()
        ),
        "final_release_date_source_populated": int(
            output["final_release_date_source"]
            .ne("")
            .sum()
        ),
        "final_release_date_assigned_true": int(
            output["final_release_date_assigned"]
            .eq(True)
            .sum()
        ),
        "eligibility_decided": int(
            output[
                "historical_eligibility_decision"
            ]
            .ne("not_decided")
            .sum()
        ),
        "scoring_allowed_true": int(
            output["scoring_allowed"]
            .eq(True)
            .sum()
        ),
        "universal_investable_true": int(
            output["universal_investable_allowed"]
            .eq(True)
            .sum()
        ),
    }

    if any(disabled_control_checks.values()):
        raise RuntimeError(
            "Decision controls were unexpectedly enabled: "
            f"{disabled_control_checks}"
        )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.to_csv(
        ADJUDICATION_PATH,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "adjudication_status": "PASS",
        "review_product_rows": int(
            len(output)
        ),
        "unique_canonical_product_ids": int(
            output[
                "canonical_product_id"
            ].nunique()
        ),
        "tcgcsv_release_date_rows": int(
            output["tcgcsv_release_date"]
            .ne("")
            .sum()
        ),
        "mtgjson_product_release_date_rows": int(
            output[
                "mtgjson_product_release_date"
            ]
            .ne("")
            .sum()
        ),
        "mtgjson_set_release_date_rows": int(
            output[
                "mtgjson_set_release_date"
            ]
            .ne("")
            .sum()
        ),
        "release_evidence_comparison_state_counts": (
            output_states
        ),
        "final_release_dates_assigned": 0,
        "final_eligibility_assigned": False,
        "scoring_allowed_rows": 0,
        "universal_investable_allowed_rows": 0,
        "production_registry_changed": False,
        "universal_database_changed": False,
        "output_files": {
            "adjudication": str(
                ADJUDICATION_PATH
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
        newline="\n",
    )

    print("=" * 76)
    print(
        "Phase 10.5R.1D.2.4D.1 "
        "Historical Release-Evidence Adjudication"
    )
    print("=" * 76)
    print(
        f"Authoritative review products: "
        f"{len(output)}"
    )
    print(
        "TCGCSV release-date rows: "
        f"{output['tcgcsv_release_date'].ne('').sum()}"
    )
    print(
        "MTGJSON product-date rows: "
        f"{output['mtgjson_product_release_date'].ne('').sum()}"
    )
    print(
        "MTGJSON set-date rows: "
        f"{output['mtgjson_set_release_date'].ne('').sum()}"
    )
    print()
    print("ADJUDICATION STATUS: PASS")
    print("Final release dates assigned: 0")
    print("Final eligibility: NOT ASSIGNED")
    print("Scoring: DISABLED")
    print("Production registry: UNCHANGED")
    print("Universal database: UNCHANGED")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())