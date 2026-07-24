from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COLLECTOR_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "collector_booster_boxes"
)

REGISTRY_MANIFEST = (
    COLLECTOR_ROOT
    / "governed_registry"
    / "collector_booster_box_registry_manifest.json"
)

ADMISSION_MANIFEST = (
    COLLECTOR_ROOT
    / "market_value_admission"
    / "collector_booster_box_market_value_admission_manifest.json"
)

EVALUATION_MANIFEST = (
    COLLECTOR_ROOT
    / "full_evaluation"
    / "collector_booster_box_full_evaluation_manifest.json"
)

PORTFOLIO_MANIFEST = (
    COLLECTOR_ROOT
    / "owned_portfolio"
    / "collector_booster_box_portfolio_manifest.json"
)

CLOSEOUT_ROOT = (
    COLLECTOR_ROOT
    / "production_closeout"
)

REPORT_PATH = (
    CLOSEOUT_ROOT
    / "collector_booster_box_production_closeout_manifest.json"
)

CERTIFICATION_PATH = (
    CLOSEOUT_ROOT
    / "PHASE_10_7_7_COLLECTOR_BOX_PRODUCTION_CLOSEOUT_CERTIFICATION.md"
)


def read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(
            f"Required certification manifest not found: {path}"
        )

    return json.loads(
        path.read_text(encoding="utf-8")
    )


def main() -> int:
    registry = read_json(REGISTRY_MANIFEST)
    admission = read_json(ADMISSION_MANIFEST)
    evaluation = read_json(EVALUATION_MANIFEST)
    portfolio = read_json(PORTFOLIO_MANIFEST)

    checks = {
        "registry_status_certified": (
            registry.get("status") == "CERTIFIED"
        ),
        "admission_status_certified": (
            admission.get("status") == "CERTIFIED"
        ),
        "evaluation_status_certified": (
            evaluation.get("status") == "CERTIFIED"
        ),
        "portfolio_status_certified": (
            portfolio.get("status") == "CERTIFIED"
        ),
        "registry_products_equal_49": (
            int(registry.get("products", 0)) == 49
        ),
        "admission_products_equal_49": (
            int(admission.get("products", 0)) == 49
        ),
        "evaluation_products_equal_49": (
            int(evaluation.get("products", 0)) == 49
        ),
        "numeric_forecasts_equal_47": (
            int(
                evaluation.get(
                    "numeric_forecast_products",
                    0,
                )
            )
            == 47
        ),
        "recommendation_eligible_equal_36": (
            int(
                evaluation.get(
                    "recommendation_eligible_products",
                    0,
                )
            )
            == 36
        ),
        "portfolio_positions_equal_2": (
            int(portfolio.get("positions", 0)) == 2
        ),
        "portfolio_diagnostics_zero": (
            int(portfolio.get("diagnostics", -1)) == 0
        ),
        "portfolio_quantity_equal_2": (
            float(portfolio.get("quantity", 0)) == 2.0
        ),
        "portfolio_cost_basis_equal_451_49": (
            float(
                portfolio.get(
                    "total_cost_basis_usd",
                    0,
                )
            )
            == 451.49
        ),
        "portfolio_value_equal_951_60": (
            float(
                portfolio.get(
                    "total_market_value_usd",
                    0,
                )
            )
            == 951.60
        ),
        "portfolio_unrealized_equal_500_11": (
            float(
                portfolio.get(
                    "unrealized_gain_loss_usd",
                    0,
                )
            )
            == 500.11
        ),
        "all_quota_calls_zero": all(
            int(manifest.get("quota_calls", -1)) == 0
            for manifest in (
                registry,
                admission,
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

    report = {
        "status": status,
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "phase": "10.7.7",
        "lane": "COLLECTOR_BOOSTER_BOX",
        "production_disposition": (
            "PRODUCTION_CLOSED"
            if status == "CERTIFIED"
            else "NOT_CLOSED"
        ),
        "products": 49,
        "numeric_forecast_products": 47,
        "recommendation_eligible_products": 36,
        "owned_positions": 2,
        "owned_quantity": 2.0,
        "owned_cost_basis_usd": 451.49,
        "owned_market_value_usd": 951.60,
        "owned_unrealized_gain_loss_usd": 500.11,
        "checks": checks,
        "quota_calls": 0,
        "future_work_policy": [
            "scheduled data refreshes",
            "governed holdings maintenance",
            "defect repair",
            "explicitly approved new capabilities",
        ],
    }

    CLOSEOUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_PATH.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    certification_lines = [
        "# Phase 10.7.7 Collector Booster Box Production Closeout Certification",
        "",
        f"**Status:** {status}",
        "",
        f"**Production disposition:** {report['production_disposition']}",
        "",
        "- Governed products: 49",
        "- Numeric forecast products: 47",
        "- Recommendation-eligible products: 36",
        "- Owned positions: 2",
        "- Owned quantity: 2",
        "- Owned cost basis: $451.49",
        "- Owned modeled value: $951.60",
        "- Owned unrealized gain/loss: $500.11",
        "- API quota calls: 0",
        "",
        "## Checks",
        "",
    ]

    certification_lines.extend(
        f"- {name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in checks.items()
    )

    certification_lines.extend(
        [
            "",
            "## Production disposition",
            "",
            (
                "The Collector Booster Box lane is production-closed. "
                "Future work is limited to scheduled data refreshes, "
                "governed holdings maintenance, defect repair, or an "
                "explicitly approved new capability."
            ),
            "",
        ]
    )

    CERTIFICATION_PATH.write_text(
        "\n".join(certification_lines),
        encoding="utf-8",
    )

    print(
        "PHASE 10.7.7 COLLECTOR BOX PRODUCTION "
        f"CLOSEOUT: {status}"
    )
    print(json.dumps(report, indent=2))

    return 0 if status == "CERTIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
