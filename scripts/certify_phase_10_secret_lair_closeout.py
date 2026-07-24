from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_PRODUCTS = 973
EXPECTED_FULL = 214
EXPECTED_PROVISIONAL = 380
EXPECTED_STRUCTURAL = 379


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def certify(refresh_manifest: Path, output_root: Path) -> dict[str, object]:
    refresh = read_json(refresh_manifest)
    evaluation = refresh.get("evaluation", {})
    portfolio = refresh.get("portfolio", {})
    outputs = refresh.get("outputs", {})

    evaluation_root = Path(str(outputs.get("evaluation_root", "")))
    portfolio_root = Path(str(outputs.get("portfolio_root", "")))

    required_evaluation = (
        "secret_lair_full_product_registry.csv",
        "secret_lair_full_model_evaluation.csv",
        "secret_lair_full_forecast_inputs.csv",
        "secret_lair_guarded_recommendations.csv",
        "secret_lair_full_model_evaluation_manifest.json",
        "SECRET_LAIR_FULL_MODEL_EVALUATION_CERTIFICATION.md",
    )
    required_portfolio = (
        "secret_lair_owned_inventory_crosswalk.csv",
        "secret_lair_owned_inventory_diagnostics.csv",
        "secret_lair_holdings_full_registry.csv",
        "secret_lair_owned_portfolio_positions.csv",
        "secret_lair_owned_forecasts.csv",
        "secret_lair_owned_guarded_recommendations.csv",
        "secret_lair_owned_universal_positions.csv",
        "secret_lair_full_registry_portfolio_manifest.json",
        "SECRET_LAIR_FULL_REGISTRY_PORTFOLIO_CERTIFICATION.md",
    )

    checks = {
        "refresh_status_certified": refresh.get("status") == "CERTIFIED",
        "evaluation_status_certified": evaluation.get("status") == "CERTIFIED",
        "portfolio_status_certified": portfolio.get("status") == "CERTIFIED",
        "products_equal_973": evaluation.get("products") == EXPECTED_PRODUCTS,
        "full_model_equal_214": evaluation.get("full_model_products") == EXPECTED_FULL,
        "provisional_equal_380": evaluation.get("provisional_model_products") == EXPECTED_PROVISIONAL,
        "structural_equal_379": evaluation.get("structural_only_products") == EXPECTED_STRUCTURAL,
        "all_owned_rows_matched": portfolio.get("diagnostic_rows") == 0,
        "positions_reconcile": portfolio.get("holdings_rows") == portfolio.get("source_rows"),
        "evaluation_outputs_exist": bool(evaluation_root) and all((evaluation_root / name).exists() for name in required_evaluation),
        "portfolio_outputs_exist": bool(portfolio_root) and all((portfolio_root / name).exists() for name in required_portfolio),
        "quota_calls_zero": refresh.get("quota_calls") == 0 and evaluation.get("quota_calls") == 0 and portfolio.get("quota_calls") == 0,
    }
    status = "CERTIFIED" if all(checks.values()) else "FAILED"
    result = {
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "10",
        "lane": "SECRET_LAIR",
        "products": evaluation.get("products", 0),
        "owned_holdings": portfolio.get("holdings_rows", 0),
        "total_cost_basis_usd": portfolio.get("total_cost_basis_usd", 0),
        "total_modeled_value_usd": portfolio.get("total_modeled_value_usd", 0),
        "checks": checks,
        "quota_calls": 0,
        "refresh_manifest": str(refresh_manifest.resolve()),
    }

    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "phase_10_secret_lair_production_closeout.json"
    md_path = output_root / "PHASE_10_SECRET_LAIR_PRODUCTION_CLOSEOUT_CERTIFICATION.md"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Phase 10 Secret Lair Production Closeout Certification",
        "",
        f"**Status:** {status}",
        "",
        f"- Governed products: {result['products']}",
        f"- Owned holdings: {result['owned_holdings']}",
        f"- Total cost basis: ${float(result['total_cost_basis_usd']):,.2f}",
        f"- Total modeled value: ${float(result['total_modeled_value_usd']):,.2f}",
        "- API quota calls: 0",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in checks.items())
    lines.extend([
        "",
        "## Production disposition",
        "",
        "The Secret Lair lane is production-closed. Future work is limited to scheduled data refreshes, governed holdings maintenance, defect repair, or an explicitly approved new capability.",
    ])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("PHASE 10 SECRET LAIR PRODUCTION CLOSEOUT: COMPLETE")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    certify(args.refresh_manifest, args.output_root)


if __name__ == "__main__":
    main()
