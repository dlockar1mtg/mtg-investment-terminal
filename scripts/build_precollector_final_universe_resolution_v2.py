from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = ROOT / "scripts/build_precollector_final_universe_resolution.py"
SPEC = importlib.util.spec_from_file_location("final_universe_resolution_impl", IMPLEMENTATION)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("FINAL_UNIVERSE_RESOLUTION_IMPORT_FAILED")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def strict_validate(resolved: pd.DataFrame, fresh_resolution: pd.DataFrame) -> None:
    # The implementation passes a temporary frame that may contain the legacy
    # owner_review_status plus the final owner_decision_status under the same
    # label. Select the final status deterministically and preserve fail-closed
    # validation of dates, configurations, and fresh-only exclusions.
    status_columns = [index for index, name in enumerate(resolved.columns) if name == "owner_review_status"]
    if not status_columns:
        raise RuntimeError("OWNER_DECISION_STATUS_MISSING")
    final_status = resolved.iloc[:, status_columns[-1]].astype(str)
    names = resolved["product_name_august1"].fillna("").str.casefold()
    ready_mask = final_status.eq("OWNER_APPROVAL_READY")
    ready = resolved.loc[ready_mask]
    if ready.empty:
        raise RuntimeError("OWNER_APPROVAL_READY_UNIVERSE_EMPTY")
    if names.loc[ready_mask].str.contains(r"\bcase\b", regex=True).any():
        raise RuntimeError("CASE_IN_OWNER_APPROVAL_READY")
    if ready["governed_release_date"].fillna("").str.strip().eq("").any():
        raise RuntimeError("BLANK_RELEASE_DATE_IN_OWNER_APPROVAL_READY")
    prohibited = fresh_resolution[
        fresh_resolution["fresh_resolution_status"].ne("OWNER_EXCLUSION_RECOMMENDED")
        & fresh_resolution["fresh_resolution_reason"].isin([
            "COLLECTOR_BOOSTER_PRODUCT",
            "DRAFT_BOOSTER_PRODUCT",
            "PLAY_BOOSTER_PRODUCT",
            "BOOSTER_BOX_CASE",
            "NON_BOOSTER_DISPLAY",
            "RELEASE_HAS_COLLECTOR_OPTION",
        ])
    ]
    if not prohibited.empty:
        raise RuntimeError("PROHIBITED_FRESH_PRODUCT_NOT_EXCLUDED")


MODULE.validate = strict_validate

if __name__ == "__main__":
    raise SystemExit(MODULE.main())
