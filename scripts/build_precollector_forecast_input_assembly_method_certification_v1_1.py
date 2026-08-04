from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_BUILDER = ROOT / "scripts/build_precollector_forecast_input_assembly_method_certification.py"

OLD_ROUTE_SUBSET = '''    route_subset = routes[[
        "canonical_product_id", "forecast_method", "historical_rows", "history_span_days",
        "accepted_listing_count", "accepted_seller_count", "coverage_state",
        "confidence_penalty_required", "route_version"
    ]].copy()
    product_input = selected.merge(route_subset, on="canonical_product_id", how="left", validate="one_to_one")
'''

NEW_ROUTE_SUBSET = '''    # The selected-universe artifact is the canonical source for evidence fields such as
    # historical_rows, history_span_days, listing counts, and coverage state.  Only
    # route-owned columns are merged here so pandas cannot suffix overlapping evidence
    # columns and silently remove their canonical names.
    route_subset = routes[[
        "canonical_product_id", "forecast_method",
        "confidence_penalty_required", "route_version"
    ]].copy()
    product_input = selected.merge(route_subset, on="canonical_product_id", how="left", validate="one_to_one")
'''


def main() -> int:
    source = BASE_BUILDER.read_text(encoding="utf-8")
    if OLD_ROUTE_SUBSET not in source:
        raise RuntimeError("FORECAST_INPUT_BASE_SCHEMA_PATCH_TARGET_NOT_FOUND")

    patched = source.replace(OLD_ROUTE_SUBSET, NEW_ROUTE_SUBSET, 1)
    namespace: dict[str, object] = {
        "__name__": "precollector_forecast_input_assembly_method_certification_v1_1",
        "__file__": str(BASE_BUILDER),
    }
    exec(compile(patched, str(BASE_BUILDER), "exec"), namespace)

    builder_main = namespace.get("main")
    if not callable(builder_main):
        raise RuntimeError("FORECAST_INPUT_PATCHED_BUILDER_MAIN_NOT_CALLABLE")

    result = int(builder_main())
    if result == 0:
        print("PASS_PRECOLLECTOR_FORECAST_INPUT_SCHEMA_OVERLAP_CORRECTION_V1_1")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
