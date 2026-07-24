from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

root = Path.cwd()

validation_root = (
    root
    / "data"
    / "validation"
    / "phase_10"
    / "pre_collector_booster_boxes"
)

registry_manifest_path = (
    validation_root
    / "governed_registry"
    / "pre_collector_booster_box_registry_manifest.json"
)

source_quality_manifest_path = (
    validation_root
    / "source_quality"
    / "pre_collector_source_quality_manifest.json"
)

admission_manifest_path = (
    validation_root
    / "market_value_admission"
    / "pre_collector_booster_box_market_value_admission_manifest.json"
)

plausibility_manifest_path = (
    validation_root
    / "market_value_plausibility"
    / "pre_collector_market_value_plausibility_manifest.json"
)

evaluation_manifest_path = (
    validation_root
    / "full_evaluation"
    / "pre_collector_booster_box_full_evaluation_manifest.json"
)

portfolio_manifest_path = (
    validation_root
    / "owned_portfolio"
    / "pre_collector_booster_box_portfolio_manifest.json"
)

required_paths = {
    "registry": registry_manifest_path,
    "source_quality": source_quality_manifest_path,
    "admission": admission_manifest_path,
    "plausibility": plausibility_manifest_path,
    "evaluation": evaluation_manifest_path,
    "portfolio": portfolio_manifest_path,
}

missing_paths = {
    name: str(path)
    for name, path in required_paths.items()
    if not path.exists()
}

if missing_paths:
    raise FileNotFoundError(
        "Required certification manifests are missing:\n"
        + json.dumps(missing_paths, indent=2)
    )


def read_json(path: Path) -> dict[str, object]:
    return json.loads(
        path.read_text(encoding="utf-8")
    )


registry = read_json(registry_manifest_path)
source_quality = read_json(
    source_quality_manifest_path
)
admission = read_json(admission_manifest_path)
plausibility = read_json(
    plausibility_manifest_path
)
evaluation = read_json(evaluation_manifest_path)
portfolio = read_json(portfolio_manifest_path)

checks = {
    "registry_status_certified": (
        registry.get("status") == "CERTIFIED"
    ),
    "source_quality_status_certified": (
        source_quality.get("status")
        == "CERTIFIED"
    ),
    "admission_status_certified": (
        admission.get("status") == "CERTIFIED"
    ),
    "plausibility_status_certified": (
        plausibility.get("status")
        == "CERTIFIED"
    ),
    "evaluation_status_certified": (
        evaluation.get("status")
        == "CERTIFIED"
    ),
    "portfolio_status_certified": (
        portfolio.get("status") == "CERTIFIED"
    ),
    "registry_products_equal_119": (
        registry.get("products") == 119
    ),
    "source_quality_products_equal_119": (
        source_quality.get(
            "governed_products"
        )
        == 119
    ),
    "admission_products_equal_119": (
        admission.get("products") == 119
    ),
    "plausibility_products_equal_119": (
        plausibility.get("products") == 119
    ),
    "evaluation_products_equal_119": (
        evaluation.get("products") == 119
    ),
    "portfolio_governed_products_equal_119": (
        portfolio.get("governed_products")
        == 119
    ),
    "numeric_market_values_equal_112": (
        admission.get(
            "numeric_market_values"
        )
        == 112
    ),
    "forecast_safe_products_equal_83": (
        plausibility.get(
            "forecast_safe_products"
        )
        == 83
    ),
    "review_required_products_equal_29": (
        plausibility.get(
            "review_required_products"
        )
        == 29
    ),
    "structural_only_products_equal_7": (
        plausibility.get(
            "structural_only_products"
        )
        == 7
    ),
    "numeric_forecasts_equal_83": (
        evaluation.get(
            "numeric_forecast_products"
        )
        == 83
    ),
    "recommendations_equal_65": (
        evaluation.get(
            "recommendation_eligible_products"
        )
        == 65
    ),
    "review_suppressed_equal_29": (
        evaluation.get(
            "review_suppressed_products"
        )
        == 29
    ),
    "structural_suppressed_equal_7": (
        evaluation.get(
            "structural_suppressed_products"
        )
        == 7
    ),
    "owned_positions_equal_zero": (
        portfolio.get("owned_positions") == 0
    ),
    "portfolio_diagnostics_equal_zero": (
        portfolio.get(
            "portfolio_diagnostics"
        )
        == 0
    ),
    "owned_quantity_equal_zero": (
        Decimal(
            str(
                portfolio.get(
                    "owned_quantity",
                    0,
                )
            )
        )
        == Decimal("0")
    ),
    "owned_cost_basis_equal_zero": (
        Decimal(
            str(
                portfolio.get(
                    "owned_cost_basis_usd",
                    0,
                )
            )
        )
        == Decimal("0")
    ),
    "owned_market_value_equal_zero": (
        Decimal(
            str(
                portfolio.get(
                    "owned_market_value_usd",
                    0,
                )
            )
        )
        == Decimal("0")
    ),
    "owned_unrealized_equal_zero": (
        Decimal(
            str(
                portfolio.get(
                    "owned_unrealized_gain_loss_usd",
                    0,
                )
            )
        )
        == Decimal("0")
    ),
    "all_quota_calls_zero": all(
        manifest.get("quota_calls") == 0
        for manifest in (
            registry,
            source_quality,
            admission,
            plausibility,
            evaluation,
            portfolio,
        )
    ),
}

status = (
    "CERTIFIED"
    if all(checks.values())
    else "FAILED"
)

output_root = (
    validation_root
    / "production_closeout"
)

output_root.mkdir(
    parents=True,
    exist_ok=True,
)

manifest = {
    "status": status,
    "generated_at_utc": datetime.now(
        timezone.utc
    ).isoformat(),
    "phase": "10.8.7",
    "lane": "PRE_COLLECTOR_BOOSTER_BOX",
    "production_disposition": (
        "PRODUCTION_CLOSED"
        if status == "CERTIFIED"
        else "NOT_CLOSED"
    ),
    "products": 119,
    "numeric_market_values": 112,
    "forecast_safe_products": 83,
    "numeric_forecast_products": 83,
    "recommendation_eligible_products": 65,
    "review_suppressed_products": 29,
    "structural_suppressed_products": 7,
    "owned_positions": 0,
    "owned_quantity": 0.0,
    "owned_cost_basis_usd": 0.0,
    "owned_market_value_usd": 0.0,
    "owned_unrealized_gain_loss_usd": 0.0,
    "checks": checks,
    "quota_calls": 0,
    "future_work_policy": [
        "scheduled data refreshes",
        "governed holdings maintenance",
        "evidence remediation for review-required products",
        "defect repair",
        "explicitly approved new capabilities",
    ],
}

manifest_path = (
    output_root
    / "pre_collector_booster_box_production_closeout_manifest.json"
)

manifest_path.write_text(
    json.dumps(manifest, indent=2),
    encoding="utf-8",
)

certification_path = (
    output_root
    / "PHASE_10_8_7_PRE_COLLECTOR_PRODUCTION_CLOSEOUT_CERTIFICATION.md"
)

lines = [
    "# Phase 10.8.7 Pre-Collector Booster Box Production Closeout",
    "",
    f"**Status:** {status}",
    "",
    (
        "**Production disposition:** "
        f"{manifest['production_disposition']}"
    ),
    "",
    "- Governed products: 119",
    "- Numeric market values: 112",
    "- Forecast-safe products: 83",
    "- Numeric forecast products: 83",
    "- Recommendation-eligible products: 65",
    "- Review-suppressed products: 29",
    "- Structural-suppressed products: 7",
    "- Owned positions: 0",
    "- Cost basis: $0.00",
    "- Modeled market value: $0.00",
    "- API quota calls: 0",
    "",
    "## Checks",
    "",
]

lines.extend(
    f"- {name}: {'PASS' if passed else 'FAIL'}"
    for name, passed in checks.items()
)

lines.extend(
    [
        "",
        "## Production policy",
        "",
        (
            "The Pre-Collector Booster Box lane is "
            "production-closed. Future work is limited "
            "to scheduled data refreshes, governed "
            "holdings maintenance, evidence remediation "
            "for review-required products, defect repair, "
            "or an explicitly approved new capability."
        ),
        "",
    ]
)

certification_path.write_text(
    "\n".join(lines),
    encoding="utf-8",
)

print(
    "PHASE 10.8.7 PRE-COLLECTOR "
    f"PRODUCTION CLOSEOUT: {status}"
)

print(json.dumps(manifest, indent=2))

raise SystemExit(
    0 if status == "CERTIFIED" else 1
)
