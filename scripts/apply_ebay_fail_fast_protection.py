from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATCHING_PATH = ROOT / "terminal2/market_sources/ebay_matching.py"
RUNNER_PATH = ROOT / "scripts/run_ebay_matching_batch.py"
RESILIENCE_TEST_PATH = ROOT / "tests/test_ebay_resilience.py"

IMPORT_OLD = '''import urllib.parse
import urllib.request
'''
IMPORT_NEW = '''import urllib.error
import urllib.parse
import urllib.request
'''

EXCEPTION_BLOCK = '''

class EbayRateLimitError(RuntimeError):
    def __init__(self, message: str, retry_after: str = ""):
        super().__init__(message)
        self.retry_after = retry_after
'''

SEARCH_OLD = '''    def search(self, query: str, limit: int = 20) -> list[dict[str, object]]:
        params = urllib.parse.urlencode({"q": query, "limit": max(1, min(limit, 200))})
        request = urllib.request.Request(
            f"https://api.ebay.com/buy/browse/v1/item_summary/search?{params}",
            headers={"Authorization": f"Bearer {self.token()}", "X-EBAY-C-MARKETPLACE-ID": self.marketplace, "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.load(response)
        return list(payload.get("itemSummaries") or [])
'''

SEARCH_NEW = '''    def search(self, query: str, limit: int = 20) -> list[dict[str, object]]:
        params = urllib.parse.urlencode({"q": query, "limit": max(1, min(limit, 200))})
        request = urllib.request.Request(
            f"https://api.ebay.com/buy/browse/v1/item_summary/search?{params}",
            headers={"Authorization": f"Bearer {self.token()}", "X-EBAY-C-MARKETPLACE-ID": self.marketplace, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
                raise EbayRateLimitError(
                    "eBay Browse API rate limit reached",
                    retry_after=retry_after,
                ) from exc
            raise
        return list(payload.get("itemSummaries") or [])
'''

EXCEPT_OLD = '''        except Exception as exc:
            matches = []
            error = f"{type(exc).__name__}: {exc}"
'''

EXCEPT_NEW = '''        except EbayRateLimitError as exc:
            matches = []
            error = f"{type(exc).__name__}: {exc}"
            results.extend(matches)
            coverage_rows.append({
                **asdict(product), "queries_used": queries_used, "results_found": 0,
                "accepted_listing_count": 0, "review_listing_count": 0,
                "rejected_listing_count": 0,
                "median_accepted_landed_price": "",
                "lowest_accepted_landed_price": "",
                "accepted_seller_count": 0,
                "coverage_state": "SOURCE_ERROR",
                "source_error": error,
            })
            print(
                f"[{index}/{len(universe)}] {product.canonical_product_name}: SOURCE_ERROR "
                f"(0 accepted, 0 found, {queries_used} queries)"
            )
            print(
                "EBAY RATE LIMIT REACHED: aborting batch immediately"
                + (f"; retry_after={exc.retry_after}" if exc.retry_after else "")
            )
            break
        except Exception as exc:
            matches = []
            error = f"{type(exc).__name__}: {exc}"
'''

SUMMARY_OLD = '''        "products": len(universe),
        "listing_rows": len(results),
'''
SUMMARY_NEW = '''        "products": len(coverage_rows),
        "expected_products": len(universe),
        "aborted_early": len(coverage_rows) < len(universe),
        "listing_rows": len(results),
'''

RUNNER_IMPORT_OLD = '''import argparse
import json
from pathlib import Path
import sys
'''
RUNNER_IMPORT_NEW = '''import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
'''

RUNNER_ROOT_OLD = '''    batch_root = base.OUTPUT_ROOT / "batches" / batch_key
    existing = sorted(batch_root.glob("ebay_matching_summary_*.json"))
'''
RUNNER_ROOT_NEW = '''    batch_root = base.OUTPUT_ROOT / "batches" / batch_key
    attempt_key = datetime.now(timezone.utc).strftime("attempt_%Y%m%dT%H%M%SZ")
    attempt_root = batch_root / "attempts" / attempt_key
    existing = sorted(batch_root.glob("ebay_matching_summary_*.json"))
'''

RUNNER_OUTPUT_OLD = '''    original_output = base.OUTPUT_ROOT
    base.OUTPUT_ROOT = batch_root
    try:
        summary = run_coverage(
            limit_per_product=args.limit_per_product,
            max_products=None,
            universe_override=subset,
        )
    finally:
        base.OUTPUT_ROOT = original_output

    if int(summary.get("products", -1)) != len(subset):
        raise RuntimeError(
            "Batch universe mismatch: "
            f"selected={len(subset)} processed={summary.get('products')}"
        )
'''

RUNNER_OUTPUT_NEW = '''    original_output = base.OUTPUT_ROOT
    base.OUTPUT_ROOT = attempt_root
    try:
        summary = run_coverage(
            limit_per_product=args.limit_per_product,
            max_products=None,
            universe_override=subset,
        )
    finally:
        base.OUTPUT_ROOT = original_output

    processed = int(summary.get("products", -1))
    source_errors = int(summary.get("coverage_states", {}).get("SOURCE_ERROR", 0))
    aborted_early = bool(summary.get("aborted_early", False))
    if processed != len(subset) or source_errors or aborted_early:
        print("\nEBAY MATCHING BATCH: INCOMPLETE")
        print(f"Attempt preserved at: {attempt_root}")
        print(
            f"selected={len(subset)} processed={processed} "
            f"source_errors={source_errors} aborted_early={aborted_early}"
        )
        raise SystemExit(2)

    batch_root.mkdir(parents=True, exist_ok=True)
    for path in attempt_root.iterdir():
        if path.is_file():
            shutil.copy2(path, batch_root / path.name)
'''

TEST_APPEND = '''


def test_browse_quota_exhausted_property():
    quota = parse_browse_quota(payload(remaining=0, count=5000))
    assert quota.exhausted is True
'''


def apply() -> None:
    matching = MATCHING_PATH.read_text(encoding="utf-8")
    if "import urllib.error" not in matching:
        if IMPORT_OLD not in matching:
            raise RuntimeError("Expected urllib import block not found")
        matching = matching.replace(IMPORT_OLD, IMPORT_NEW, 1)
    if "class EbayRateLimitError" not in matching:
        anchor = "class EbayBrowseClient:\n"
        if anchor not in matching:
            raise RuntimeError("Expected EbayBrowseClient anchor not found")
        matching = matching.replace(anchor, EXCEPTION_BLOCK + "\n\n" + anchor, 1)
    if "eBay Browse API rate limit reached" not in matching:
        if SEARCH_OLD not in matching:
            raise RuntimeError("Expected search method not found")
        matching = matching.replace(SEARCH_OLD, SEARCH_NEW, 1)
    if "EBAY RATE LIMIT REACHED: aborting batch immediately" not in matching:
        if EXCEPT_OLD not in matching:
            raise RuntimeError("Expected coverage exception block not found")
        matching = matching.replace(EXCEPT_OLD, EXCEPT_NEW, 1)
    if '"expected_products": len(universe)' not in matching:
        if SUMMARY_OLD not in matching:
            raise RuntimeError("Expected summary block not found")
        matching = matching.replace(SUMMARY_OLD, SUMMARY_NEW, 1)
    MATCHING_PATH.write_text(matching, encoding="utf-8")

    runner = RUNNER_PATH.read_text(encoding="utf-8")
    if "from datetime import datetime, timezone" not in runner:
        if RUNNER_IMPORT_OLD not in runner:
            raise RuntimeError("Expected runner import block not found")
        runner = runner.replace(RUNNER_IMPORT_OLD, RUNNER_IMPORT_NEW, 1)
    if "attempt_key = datetime.now" not in runner:
        if RUNNER_ROOT_OLD not in runner:
            raise RuntimeError("Expected runner batch-root block not found")
        runner = runner.replace(RUNNER_ROOT_OLD, RUNNER_ROOT_NEW, 1)
    if "EBAY MATCHING BATCH: INCOMPLETE" not in runner:
        if RUNNER_OUTPUT_OLD not in runner:
            raise RuntimeError("Expected runner output block not found")
        runner = runner.replace(RUNNER_OUTPUT_OLD, RUNNER_OUTPUT_NEW, 1)
    RUNNER_PATH.write_text(runner, encoding="utf-8")

    tests = RESILIENCE_TEST_PATH.read_text(encoding="utf-8")
    if "test_browse_quota_exhausted_property" not in tests:
        tests = tests.rstrip() + TEST_APPEND + "\n"
    RESILIENCE_TEST_PATH.write_text(tests, encoding="utf-8")

    print("PHASE 10.6A2 EBAY FAIL-FAST PROTECTION: APPLIED")
    print(f"Updated: {MATCHING_PATH.relative_to(ROOT)}")
    print(f"Updated: {RUNNER_PATH.relative_to(ROOT)}")
    print(f"Updated: {RESILIENCE_TEST_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    apply()
