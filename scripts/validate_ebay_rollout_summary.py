from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_MATCHER = "precision-v2"
REQUIRED_SELECTION_MODE = "PRODUCT_MAP_TARGETED"


def validate_summary(
    summary: dict[str, object],
    expected_products: int,
    limit_per_product: int,
) -> list[str]:
    errors: list[str] = []
    max_rows = expected_products * limit_per_product

    if summary.get("status") != "PASS":
        errors.append("status must be PASS")
    if summary.get("live_api_called") is not True:
        errors.append("live_api_called must be true")
    if summary.get("matcher_version") != REQUIRED_MATCHER:
        errors.append(f"matcher_version must be {REQUIRED_MATCHER}")
    if summary.get("matcher_fail_closed") is not True:
        errors.append("matcher_fail_closed must be true")
    if summary.get("selection_mode") != REQUIRED_SELECTION_MODE:
        errors.append(f"selection_mode must be {REQUIRED_SELECTION_MODE}")
    if summary.get("products") != expected_products:
        errors.append(f"products must equal {expected_products}")
    if summary.get("expected_products") != expected_products:
        errors.append(f"expected_products must equal {expected_products}")
    if summary.get("aborted_early") is not False:
        errors.append("aborted_early must be false")
    if summary.get("credentials_printed") is not False:
        errors.append("credentials_printed must be false")

    listing_rows = summary.get("listing_rows")
    if not isinstance(listing_rows, int):
        errors.append("listing_rows must be an integer")
    elif listing_rows > max_rows:
        errors.append(f"listing_rows exceeds bounded maximum {max_rows}")

    missing = summary.get("missing_tcgplayer_product_ids")
    if missing not in ([], None):
        errors.append("missing_tcgplayer_product_ids must be empty")

    progress_log = summary.get("progress_log")
    if not isinstance(progress_log, list):
        errors.append("progress_log must be a list")
    elif any("SOURCE_ERROR" in str(line) for line in progress_log):
        errors.append("progress_log contains SOURCE_ERROR")
    elif any("RATE LIMIT" in str(line).upper() for line in progress_log):
        errors.append("progress_log contains rate-limit evidence")

    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed validation for bounded precision-v2 eBay rollout"
    )
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--expected-products", type=int, required=True)
    parser.add_argument("--limit-per-product", type=int, required=True)
    parser.add_argument("--result-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    errors = validate_summary(
        summary=summary,
        expected_products=args.expected_products,
        limit_per_product=args.limit_per_product,
    )

    result = {
        "status": "PASS" if not errors else "FAIL",
        "mode": "BOUNDED_ROLLOUT_VALIDATION",
        "summary": str(args.summary.resolve()),
        "expected_products": args.expected_products,
        "limit_per_product": args.limit_per_product,
        "maximum_listing_rows": args.expected_products * args.limit_per_product,
        "errors": errors,
    }

    rendered = json.dumps(result, indent=2)
    if args.result_output:
        args.result_output.parent.mkdir(parents=True, exist_ok=True)
        args.result_output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
