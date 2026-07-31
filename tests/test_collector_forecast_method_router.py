from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.route_collector_forecast_methods import (
    route_product,
)


POLICY = {
    "policy_name": "collector_forecast_method_router",
    "policy_version": "1.0.0",
    "standard_name": "MTG Forecasting and Decision Standard",
    "standard_version": "1.0.0",
    "lane": "COLLECTOR_BOOSTER",
    "identity_valid_statuses": [
        "VERIFIED",
        "APPROVED",
        "GOVERNED",
        "ACTIVE",
    ],
    "purchase_recommendation_authorized": False,
    "routing_rules": {
        "CERTIFIED": {
            "forecast_method": (
                "DIRECT_HISTORY_CALIBRATED"
            ),
            "direct_history_method_allowed": True,
            "comparable_method_allowed": True,
            "forecast_output_allowed": True,
            "purchase_analysis_allowed": True,
        },
        "CERTIFIED_LIMITED": {
            "forecast_method": (
                "DIRECT_HISTORY_LIMITED"
            ),
            "direct_history_method_allowed": True,
            "comparable_method_allowed": True,
            "forecast_output_allowed": True,
            "purchase_analysis_allowed": True,
        },
        "QUARANTINED": {
            "forecast_method": (
                "COMPARABLE_PRODUCT_ADJUSTED"
            ),
            "direct_history_method_allowed": False,
            "comparable_method_allowed": True,
            "forecast_output_allowed": True,
            "purchase_analysis_allowed": True,
        },
        "HISTORY_ACCUMULATING": {
            "forecast_method": (
                "COMPARABLE_PRODUCT_ADJUSTED"
            ),
            "direct_history_method_allowed": False,
            "comparable_method_allowed": True,
            "forecast_output_allowed": True,
            "purchase_analysis_allowed": True,
        },
    },
    "fail_closed_rules": {
        "identity_invalid_method": (
            "DEFERRED_IDENTITY"
        ),
        "missing_or_nonpositive_current_price_method": (
            "DEFERRED_MISSING_PRICE"
        ),
        "missing_history_certification_method": (
            "DEFERRED_INSUFFICIENT_EVIDENCE"
        ),
        "unknown_history_status_method": (
            "DEFERRED_INSUFFICIENT_EVIDENCE"
        ),
    },
}


def registry_row(
    identity_status: str = "VERIFIED",
) -> dict[str, str]:
    return {
        "investment_product_id": "MTG:TEST:1",
        "box_name": (
            "Test Collector Booster Display"
        ),
        "identity_status": identity_status,
    }


def model_row(
    current_price: str = "200.00",
) -> dict[str, str]:
    return {
        "investment_product_id": "MTG:TEST:1",
        "current_price": current_price,
    }


def history_row(
    status: str,
    band: str = "STRONG",
) -> dict[str, str]:
    return {
        "investment_product_id": "MTG:TEST:1",
        "product_name": (
            "Test Collector Booster Display"
        ),
        "history_certification_status": status,
        "history_quality_band": band,
    }


def route(
    *,
    status: str,
    band: str = "STRONG",
    identity_status: str = "VERIFIED",
    current_price: str = "200.00",
):
    return route_product(
        investment_product_id="MTG:TEST:1",
        registry_row=registry_row(
            identity_status
        ),
        model_row=model_row(
            current_price
        ),
        history_row=history_row(
            status,
            band,
        ),
        policy=POLICY,
    )


def test_certified_routes_to_direct_calibrated() -> None:
    result = route(
        status="CERTIFIED"
    )

    assert (
        result["forecast_method"]
        == "DIRECT_HISTORY_CALIBRATED"
    )
    assert (
        result[
            "direct_history_method_allowed"
        ]
        is True
    )
    assert (
        result["forecast_output_allowed"]
        is True
    )


def test_certified_limited_routes_to_limited() -> None:
    result = route(
        status="CERTIFIED_LIMITED",
        band="MODERATE",
    )

    assert (
        result["forecast_method"]
        == "DIRECT_HISTORY_LIMITED"
    )
    assert (
        result[
            "direct_history_method_allowed"
        ]
        is True
    )


def test_quarantined_routes_to_comparable() -> None:
    result = route(
        status="QUARANTINED"
    )

    assert (
        result["forecast_method"]
        == "COMPARABLE_PRODUCT_ADJUSTED"
    )
    assert (
        result[
            "direct_history_method_allowed"
        ]
        is False
    )
    assert (
        result["comparable_method_allowed"]
        is True
    )
    assert (
        result["forecast_output_allowed"]
        is True
    )


def test_accumulating_routes_to_comparable() -> None:
    result = route(
        status="HISTORY_ACCUMULATING",
        band="NONE",
    )

    assert (
        result["forecast_method"]
        == "COMPARABLE_PRODUCT_ADJUSTED"
    )
    assert (
        result["comparable_group_required"]
        is True
    )


def test_invalid_identity_fails_closed() -> None:
    result = route(
        status="CERTIFIED",
        identity_status="REVIEW_REQUIRED",
    )

    assert (
        result["forecast_method"]
        == "DEFERRED_IDENTITY"
    )
    assert (
        result["forecast_output_allowed"]
        is False
    )
    assert (
        result["comparable_method_allowed"]
        is False
    )


def test_missing_price_fails_closed() -> None:
    result = route(
        status="CERTIFIED",
        current_price="",
    )

    assert (
        result["forecast_method"]
        == "DEFERRED_MISSING_PRICE"
    )
    assert (
        result["forecast_output_allowed"]
        is False
    )


def test_purchase_authorization_always_false() -> None:
    statuses = [
        "CERTIFIED",
        "CERTIFIED_LIMITED",
        "QUARANTINED",
        "HISTORY_ACCUMULATING",
    ]

    for status in statuses:
        result = route(
            status=status
        )

        assert (
            result[
                "purchase_recommendation_authorized"
            ]
            is False
        )


def test_unknown_status_fails_closed() -> None:
    result = route(
        status="UNKNOWN_STATUS"
    )

    assert (
        result["forecast_method"]
        == "DEFERRED_INSUFFICIENT_EVIDENCE"
    )
    assert (
        result["forecast_output_allowed"]
        is False
    )

def test_router_applies_japanese_hybrid_override(
    tmp_path,
) -> None:
    import csv
    import json
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]

    script = (
        root
        / "scripts"
        / "route_collector_forecast_methods.py"
    )

    override_path = (
        root
        / "data"
        / "governance"
        / "mtg"
        / "collector_comparables"
        / "collector_japanese_edition_hybrid_override_v1.json"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--override",
            str(override_path),
            "--output-root",
            str(tmp_path),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        result.stdout + result.stderr
    )

    routes_path = (
        tmp_path
        / "collector_forecast_method_routes.csv"
    )

    with routes_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        rows = list(
            csv.DictReader(handle)
        )

    override_rows = [
        row
        for row in rows
        if row["override_applied"] == "True"
    ]

    assert len(override_rows) == 1

    override_row = override_rows[0]

    assert (
        override_row["investment_product_id"]
        == "TCGCSV-24219-628315"
    )

    assert (
        override_row["base_forecast_method"]
        == "COMPARABLE_PRODUCT_ADJUSTED"
    )

    assert (
        override_row["forecast_method"]
        == "FUNDAMENTAL_COMPARABLE_HYBRID"
    )

    assert (
        override_row["override_reason_code"]
        == "INSUFFICIENT_EXACT_SEMANTIC_COMPARABLES"
    )

    assert (
        override_row[
            "purchase_recommendation_authorized"
        ]
        == "False"
    )

    manifest_path = (
        tmp_path
        / "collector_forecast_method_router_manifest.json"
    )

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8-sig"
        )
    )

    assert manifest["status"] == "PASS"
    assert manifest["override_applied_count"] == 1

    assert manifest["method_counts"] == {
        "COMPARABLE_PRODUCT_ADJUSTED": 24,
        "DIRECT_HISTORY_CALIBRATED": 19,
        "DIRECT_HISTORY_LIMITED": 7,
        "FUNDAMENTAL_COMPARABLE_HYBRID": 1,
    }

    assert (
        manifest[
            "purchase_recommendations_authorized"
        ]
        is False
    )