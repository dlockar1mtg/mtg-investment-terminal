from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESILIENCE_PATH = ROOT / "terminal2/market_sources/ebay_resilience.py"
RUNNER_PATH = ROOT / "scripts/run_ebay_matching_batch.py"
TEST_PATH = ROOT / "tests/test_ebay_resilience.py"

RESILIENCE_CONTENT = '''from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import urllib.request


ANALYTICS_URL = "https://api.ebay.com/developer/analytics/v1_beta/rate_limit/"


@dataclass(frozen=True)
class BrowseQuota:
    count: int
    limit: int
    remaining: int
    reset: str
    time_window: int

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0

    def supports(self, required_calls: int, reserve_calls: int = 0) -> bool:
        return self.remaining >= max(0, required_calls) + max(0, reserve_calls)


def parse_browse_quota(payload: dict[str, object]) -> BrowseQuota:
    for group in payload.get("rateLimits", []):
        if not isinstance(group, dict):
            continue
        context = str(group.get("apiContext", "")).strip().lower()
        name = str(group.get("apiName", "")).strip().lower()
        if context != "buy" or name != "browse":
            continue
        for resource in group.get("resources", []):
            if not isinstance(resource, dict):
                continue
            if str(resource.get("name", "")).strip().lower() != "buy.browse":
                continue
            rates = resource.get("rates", [])
            if not rates:
                break
            rate = rates[0]
            if not isinstance(rate, dict):
                break
            return BrowseQuota(
                count=int(rate.get("count", 0)),
                limit=int(rate.get("limit", 0)),
                remaining=int(rate.get("remaining", 0)),
                reset=str(rate.get("reset", "")),
                time_window=int(rate.get("timeWindow", 0)),
            )
    raise RuntimeError("eBay Browse quota was not present in the Analytics response")


def get_browse_quota(client, timeout: int = 30) -> BrowseQuota:
    request = urllib.request.Request(
        ANALYTICS_URL,
        headers={
            "Authorization": f"Bearer {client.token()}",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    return parse_browse_quota(payload)


def estimate_batch_calls(product_count: int, maximum_queries_per_product: int = 3) -> int:
    if product_count < 0:
        raise ValueError("product_count must be nonnegative")
    if maximum_queries_per_product < 1:
        raise ValueError("maximum_queries_per_product must be at least 1")
    return product_count * maximum_queries_per_product


def format_reset_local(reset_value: str) -> str:
    if not reset_value:
        return "unknown"
    reset = datetime.fromisoformat(reset_value.replace("Z", "+00:00"))
    return reset.astimezone().isoformat()
'''

TEST_CONTENT = '''from terminal2.market_sources.ebay_resilience import (
    estimate_batch_calls,
    parse_browse_quota,
)


def payload(remaining=5000, count=0, limit=5000):
    return {
        "rateLimits": [
            {
                "apiContext": "buy",
                "apiName": "Browse",
                "apiVersion": "v1",
                "resources": [
                    {
                        "name": "buy.browse",
                        "rates": [
                            {
                                "count": count,
                                "limit": limit,
                                "remaining": remaining,
                                "reset": "2026-07-24T07:00:00.000Z",
                                "timeWindow": 86400,
                            }
                        ],
                    }
                ],
            }
        ]
    }


def test_parse_browse_quota_is_case_tolerant():
    quota = parse_browse_quota(payload(remaining=120, count=4880))
    assert quota.limit == 5000
    assert quota.count == 4880
    assert quota.remaining == 120
    assert quota.reset == "2026-07-24T07:00:00.000Z"


def test_quota_supports_required_calls_and_reserve():
    quota = parse_browse_quota(payload(remaining=700))
    assert quota.supports(600, reserve_calls=100)
    assert not quota.supports(601, reserve_calls=100)


def test_estimate_batch_calls_uses_three_query_ceiling():
    assert estimate_batch_calls(200) == 600
'''

RUNNER_IMPORT_OLD = '''from terminal2.market_sources import ebay_matching as base
from terminal2.market_sources.ebay_precision import run_coverage
from terminal2.market_sources.ebay_universe import build_complete_universe
'''

RUNNER_IMPORT_NEW = '''from terminal2.market_sources import ebay_matching as base
from terminal2.market_sources.ebay_matching import EbayBrowseClient
from terminal2.market_sources.ebay_precision import run_coverage
from terminal2.market_sources.ebay_resilience import (
    estimate_batch_calls,
    format_reset_local,
    get_browse_quota,
)
from terminal2.market_sources.ebay_universe import build_complete_universe
'''

ARG_OLD = '''    parser.add_argument("--limit-per-product", type=int, default=20)
    parser.add_argument("--force", action="store_true")
'''

ARG_NEW = '''    parser.add_argument("--limit-per-product", type=int, default=20)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-quota-check", action="store_true")
    parser.add_argument("--quota-reserve", type=int, default=100)
'''

PREFLIGHT_ANCHOR = '''    end = args.offset + len(subset) - 1
    batch_key = f"{args.product_class.lower()}_{args.offset:04d}_{end:04d}"
'''

PREFLIGHT_BLOCK = '''    if args.quota_reserve < 0:
        raise SystemExit("--quota-reserve must be zero or greater")

    if not args.skip_quota_check:
        client = EbayBrowseClient()
        quota = get_browse_quota(client)
        estimated_calls = estimate_batch_calls(len(subset))
        print("EBAY BROWSE QUOTA PREFLIGHT")
        print(f"  limit: {quota.limit}")
        print(f"  used: {quota.count}")
        print(f"  remaining: {quota.remaining}")
        print(f"  estimated maximum calls: {estimated_calls}")
        print(f"  reserve: {args.quota_reserve}")
        print(f"  reset UTC: {quota.reset or 'unknown'}")
        print(f"  reset local: {format_reset_local(quota.reset)}")
        if not quota.supports(estimated_calls, reserve_calls=args.quota_reserve):
            raise SystemExit(
                "INSUFFICIENT EBAY BROWSE QUOTA: "
                f"remaining={quota.remaining}, required={estimated_calls}, "
                f"reserve={args.quota_reserve}, reset={quota.reset or 'unknown'}"
            )

'''


def apply() -> None:
    RESILIENCE_PATH.write_text(RESILIENCE_CONTENT, encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    runner = RUNNER_PATH.read_text(encoding="utf-8")
    if "from terminal2.market_sources.ebay_resilience import" not in runner:
        if RUNNER_IMPORT_OLD not in runner:
            raise RuntimeError("Expected runner import block was not found")
        runner = runner.replace(RUNNER_IMPORT_OLD, RUNNER_IMPORT_NEW, 1)

    if '--skip-quota-check' not in runner:
        if ARG_OLD not in runner:
            raise RuntimeError("Expected runner argument block was not found")
        runner = runner.replace(ARG_OLD, ARG_NEW, 1)

    if "EBAY BROWSE QUOTA PREFLIGHT" not in runner:
        if PREFLIGHT_ANCHOR not in runner:
            raise RuntimeError("Expected runner preflight anchor was not found")
        runner = runner.replace(
            PREFLIGHT_ANCHOR,
            PREFLIGHT_BLOCK + PREFLIGHT_ANCHOR,
            1,
        )

    RUNNER_PATH.write_text(runner, encoding="utf-8")

    print("PHASE 10.6A1 EBAY QUOTA PREFLIGHT: APPLIED")
    print(f"Created: {RESILIENCE_PATH.relative_to(ROOT)}")
    print(f"Updated: {RUNNER_PATH.relative_to(ROOT)}")
    print(f"Created: {TEST_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    apply()
