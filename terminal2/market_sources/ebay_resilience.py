from __future__ import annotations

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
