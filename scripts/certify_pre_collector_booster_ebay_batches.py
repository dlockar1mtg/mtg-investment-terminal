from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.market_sources import ebay_matching as base
from terminal2.market_sources.ebay_universe import build_complete_universe

PRODUCT_CLASS = "PRE_COLLECTOR_BOOSTER_BOX"
BATCH_ROOT = base.OUTPUT_ROOT / "batches"
REPORT_PATH = base.OUTPUT_ROOT / "pre_collector_booster_ebay_certification.json"
HARD_EXCLUSION_REASONS = {
    "unrelated_game",
    "missing_mtg_identity",
    "missing_booster_box_form",
    "excluded_product_form",
    "loose_packs",
    "multi_box_case",
    "multi_unit_lot",
    "incomplete_pack_box_lot",
    "incomplete_product",
    "deprecated_catalog_placeholder",
    "mixed_product_listing",
    "damaged_or_uncertain_seal",
    "single_pack_collector_product",
    "conflicting_set_identity",
    "insufficient_product_identity",
    "non_english",
    "presale",
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _latest(directory: Path, pattern: str) -> Path | None:
    matches = sorted(directory.glob(pattern), key=lambda value: value.stat().st_mtime)
    return matches[-1] if matches else None


def _check(name: str, passed: bool, detail: str) -> dict[str, object]:
    print(f"{'PASS' if passed else 'FAIL'}  {name}: {detail}")
    return {"name": name, "passed": passed, "detail": detail}


def main() -> int:
    governed = [
        product
        for product in build_complete_universe()
        if product.product_class == PRODUCT_CLASS
    ]
    governed_ids = {product.canonical_product_id for product in governed}

    manifests: list[dict[str, object]] = []
    result_rows: list[dict[str, str]] = []
    coverage_rows: list[dict[str, str]] = []
    batch_dirs: list[Path] = []

    for directory in sorted(BATCH_ROOT.glob("pre_collector_booster_box_*")):
        manifest_path = directory / "batch_manifest.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("product_class") != PRODUCT_CLASS:
            continue
        results_path = _latest(directory, "ebay_listing_match_results_*.csv")
        coverage_path = _latest(directory, "ebay_product_coverage_*.csv")
        if results_path is None or coverage_path is None:
            continue
        manifests.append(manifest)
        result_rows.extend(_read_csv(results_path))
        coverage_rows.extend(_read_csv(coverage_path))
        batch_dirs.append(directory)

    observed_ids = {
        row.get("canonical_product_id", "")
        for row in coverage_rows
        if row.get("canonical_product_id")
    }
    accepted_rows = [row for row in result_rows if row.get("match_state") == "ACCEPTED"]
    review_rows = [row for row in result_rows if row.get("match_state") == "REVIEW"]
    rejected_rows = [row for row in result_rows if row.get("match_state") == "REJECTED"]
    source_error_rows = [row for row in coverage_rows if row.get("coverage_state") == "SOURCE_ERROR"]

    accepted_hard_violations: list[dict[str, str]] = []
    for row in accepted_rows:
        reasons = {
            value
            for value in row.get("exclusion_reasons", "").split("|")
            if value
        }
        if reasons & HARD_EXCLUSION_REASONS:
            accepted_hard_violations.append(row)

    manifest_ids: list[str] = []
    for manifest in manifests:
        manifest_ids.extend(str(value) for value in manifest.get("product_ids", []))

    checks = [
        _check("governed_pre_collector_universe", bool(governed_ids), f"products={len(governed_ids)}"),
        _check("expected_universe_size", len(governed_ids) == 119, f"products={len(governed_ids)}"),
        _check("batch_manifests_found", len(manifests) == 5, f"batches={len(manifests)}"),
        _check("manifest_ids_unique", len(manifest_ids) == len(set(manifest_ids)), f"ids={len(manifest_ids)}"),
        _check("all_governed_products_batched", set(manifest_ids) == governed_ids, f"batched={len(set(manifest_ids))}, governed={len(governed_ids)}"),
        _check("all_products_observed", observed_ids == governed_ids, f"observed={len(observed_ids)}, governed={len(governed_ids)}"),
        _check("coverage_ids_governed", observed_ids <= governed_ids, f"unknown={len(observed_ids - governed_ids)}"),
        _check("no_source_errors", not source_error_rows, f"errors={len(source_error_rows)}"),
        _check("accepted_hard_exclusions_absent", not accepted_hard_violations, f"violations={len(accepted_hard_violations)}"),
        _check("no_manual_reviews", not review_rows, f"review_rows={len(review_rows)}"),
        _check("credentials_not_printed", all(not bool((manifest.get("summary") or {}).get("credentials_printed")) for manifest in manifests), f"batches={len(manifests)}"),
    ]

    passed = all(bool(check["passed"]) for check in checks)
    report = {
        "certification": "PRE_COLLECTOR_BOOSTER_EBAY_BATCHES",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if passed else "FAIL",
        "governed_products": len(governed_ids),
        "batch_directories": [str(path.relative_to(ROOT)) for path in batch_dirs],
        "observed_products": len(observed_ids),
        "accepted_rows": len(accepted_rows),
        "review_rows": len(review_rows),
        "rejected_rows": len(rejected_rows),
        "source_error_rows": len(source_error_rows),
        "accepted_hard_violations": len(accepted_hard_violations),
        "checks": checks,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print()
    print(f"PRE-COLLECTOR BOOSTER EBAY CERTIFICATION: {'PASS' if passed else 'FAIL'}")
    print(f"Report: {REPORT_PATH.relative_to(ROOT)}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
