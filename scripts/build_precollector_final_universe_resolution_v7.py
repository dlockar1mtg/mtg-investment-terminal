from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
V6_PATH = ROOT / "scripts/build_precollector_final_universe_resolution_v6.py"
SPEC = importlib.util.spec_from_file_location("precollector_final_resolution_v6", V6_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("FINAL_UNIVERSE_V6_IMPORT_FAILED")
V6 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(V6)

ORIGINAL_RESOLVE_MYSTERY_PRODUCT_DATES = V6.resolve_mystery_product_dates


def resolve_product_specific_and_final_tcgcsv_date(
    owner: pd.DataFrame,
    fresh: pd.DataFrame,
) -> pd.DataFrame:
    frame = ORIGINAL_RESOLVE_MYSTERY_PRODUCT_DATES(owner, fresh)

    required = {"canonical_product_id", "presaleInfo"}
    if not required.issubset(fresh.columns):
        raise RuntimeError("TCGCSV_PRODUCT_RELEASE_EVIDENCE_FIELDS_MISSING")

    release_evidence = fresh[["canonical_product_id", "presaleInfo"]].copy()
    release_evidence["tcgcsv_product_release_date"] = release_evidence["presaleInfo"].map(
        V6.MODULE.parse_product_release_date
    )
    release_evidence = release_evidence[
        release_evidence["tcgcsv_product_release_date"].str.match(
            r"^\d{4}-\d{2}-\d{2}$", na=False
        )
    ].drop_duplicates("canonical_product_id")

    frame = frame.merge(
        release_evidence[["canonical_product_id", "tcgcsv_product_release_date"]],
        on="canonical_product_id",
        how="left",
    )

    unresolved = (
        frame["owner_review_status"].eq("REQUIRES_RELEASE_DATE_REVIEW")
        & frame["governed_release_date"].fillna("").str.strip().eq("")
        & frame["tcgcsv_product_release_date"].fillna("").str.match(
            r"^\d{4}-\d{2}-\d{2}$"
        )
    )

    frame.loc[unresolved, "release_date_authority"] = (
        "TCGCSV_PRODUCT_RELEASE_SECONDARY"
    )
    frame.loc[unresolved, "governed_release_date"] = frame.loc[
        unresolved, "tcgcsv_product_release_date"
    ]
    frame.loc[unresolved, "owner_review_status"] = "READY_FOR_OWNER_REVIEW"

    remaining = frame[
        frame["owner_review_status"].eq("REQUIRES_RELEASE_DATE_REVIEW")
        | frame["governed_release_date"].fillna("").str.strip().eq("")
    ]
    if not remaining.empty:
        columns = [
            column
            for column in (
                "canonical_product_id",
                "product_name_august1",
                "reconciliation_group_name",
                "owner_review_status",
                "release_date_authority",
                "governed_release_date",
            )
            if column in remaining.columns
        ]
        print("UNRESOLVED_FINAL_PRODUCT_ROWS")
        print(remaining[columns].to_string(index=False))
        raise RuntimeError(
            f"FINAL_RELEASE_DATE_UNRESOLVED_AFTER_ALL_AUTHORITIES: {len(remaining)}"
        )

    return frame


V6.MODULE.resolve_mystery_product_dates = resolve_product_specific_and_final_tcgcsv_date

# Governed compatibility export used by downstream builders that dynamically
# import this script and invoke MODULE.main().
MODULE = V6.MODULE

if __name__ == "__main__":
    raise SystemExit(MODULE.main())
