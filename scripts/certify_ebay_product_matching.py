from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.market_sources.ebay_matching import OUTPUT_ROOT
from terminal2.market_sources.ebay_universe import build_complete_universe


def newest(pattern: str) -> Path | None:
    matches = sorted(OUTPUT_ROOT.glob(pattern))
    return matches[-1] if matches else None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description="Certify governed MTG-to-eBay matching coverage artifacts.")
    parser.add_argument("--minimum-product-coverage", type=float, default=0.0)
    parser.add_argument("--minimum-products-observed", type=int, default=10)
    args = parser.parse_args()

    universe = build_complete_universe()
    coverage_path = newest("ebay_product_coverage_*.csv")
    results_path = newest("ebay_listing_match_results_*.csv")
    summary_path = newest("ebay_matching_summary_*.json")

    checks: list[tuple[str, bool, str]] = []
    checks.append(("governed_universe_nonempty", bool(universe), f"products={len(universe)}"))
    checks.append(("coverage_artifact_exists", coverage_path is not None, str(coverage_path or "")))
    checks.append(("results_artifact_exists", results_path is not None, str(results_path or "")))
    checks.append(("summary_artifact_exists", summary_path is not None, str(summary_path or "")))

    coverage_rows: list[dict[str, str]] = read_csv(coverage_path) if coverage_path else []
    result_rows: list[dict[str, str]] = read_csv(results_path) if results_path else []
    checks.append((
        "minimum_products_observed",
        len(coverage_rows) >= args.minimum_products_observed,
        f"products={len(coverage_rows)}",
    ))

    ids = {row.canonical_product_id for row in universe}
    coverage_ids = {row.get("canonical_product_id", "") for row in coverage_rows}
    ratio = len(ids & coverage_ids) / len(ids) if ids else 0.0
    checks.append(("universe_coverage_ratio", ratio >= args.minimum_product_coverage, f"ratio={ratio:.3f}"))
    unknown_ids = sorted(coverage_ids - ids - {""})
    checks.append(("coverage_ids_governed", not unknown_ids, f"unknown_ids={len(unknown_ids)}"))

    allowed_classes = {"COLLECTOR_BOOSTER_BOX", "PRE_COLLECTOR_BOOSTER_BOX", "SEALED_SECRET_LAIR"}
    actual_classes = {row.product_class for row in universe}
    checks.append(("premium_classes_only", actual_classes <= allowed_classes, f"classes={sorted(actual_classes)}"))
    checks.append((
        "collector_booster_lane_present",
        "COLLECTOR_BOOSTER_BOX" in actual_classes,
        f"collector_products={sum(row.product_class == 'COLLECTOR_BOOSTER_BOX' for row in universe)}",
    ))

    forbidden_names = ("set booster box", "play booster box", "jumpstart booster box")
    bad_universe = [row.canonical_product_name for row in universe if any(value in row.canonical_product_name.lower() for value in forbidden_names)]
    checks.append(("nonpremium_boxes_excluded", not bad_universe, f"violations={len(bad_universe)}"))

    bad_states = [row for row in result_rows if row.get("match_state") not in {"ACCEPTED", "REVIEW", "REJECTED"}]
    checks.append(("match_states_valid", not bad_states, f"violations={len(bad_states)}"))

    accepted = [row for row in result_rows if row.get("match_state") == "ACCEPTED"]
    accepted_with_exclusions = [row for row in accepted if row.get("exclusion_reasons")]
    checks.append(("excluded_listings_not_accepted", not accepted_with_exclusions, f"violations={len(accepted_with_exclusions)}"))

    source_errors = [row for row in coverage_rows if row.get("coverage_state") == "SOURCE_ERROR"]
    checks.append(("source_errors_below_10_percent", len(source_errors) <= max(1, int(len(coverage_rows) * 0.10)), f"errors={len(source_errors)}"))

    passed = all(value for _, value, _ in checks)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if passed else "FAIL",
        "checks": [{"name": name, "passed": value, "detail": detail} for name, value, detail in checks],
        "universe_products": len(universe),
        "coverage_rows": len(coverage_rows),
        "listing_rows": len(result_rows),
        "accepted_rows": len(accepted),
        "credentials_printed": False,
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_ROOT / f"ebay_matching_certification_{datetime.now(timezone.utc).date().isoformat()}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=" * 72)
    print("MTG GOVERNED PRODUCT TO EBAY MATCHING CERTIFICATION")
    print("=" * 72)
    for name, value, detail in checks:
        print(f"{'PASS' if value else 'FAIL'}  {name}: {detail}")
    print(f"\nEBAY PRODUCT MATCHING CERTIFICATION: {report['status']}")
    print(f"Report: {report_path.relative_to(ROOT).as_posix()}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
