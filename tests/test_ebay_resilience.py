from terminal2.market_sources.ebay_resilience import (
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
