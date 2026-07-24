from __future__ import annotations

import json
from pathlib import Path

from scripts.certify_phase_10_secret_lair_closeout import certify


def touch_all(root: Path, names: tuple[str, ...]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name in names:
        (root / name).write_text("ok\n", encoding="utf-8")


def test_closeout_certifies_complete_refresh(tmp_path: Path) -> None:
    evaluation_root = tmp_path / "evaluation"
    portfolio_root = tmp_path / "portfolio"
    touch_all(evaluation_root, (
        "secret_lair_full_product_registry.csv",
        "secret_lair_full_model_evaluation.csv",
        "secret_lair_full_forecast_inputs.csv",
        "secret_lair_guarded_recommendations.csv",
        "secret_lair_full_model_evaluation_manifest.json",
        "SECRET_LAIR_FULL_MODEL_EVALUATION_CERTIFICATION.md",
    ))
    touch_all(portfolio_root, (
        "secret_lair_owned_inventory_crosswalk.csv",
        "secret_lair_owned_inventory_diagnostics.csv",
        "secret_lair_holdings_full_registry.csv",
        "secret_lair_owned_portfolio_positions.csv",
        "secret_lair_owned_forecasts.csv",
        "secret_lair_owned_guarded_recommendations.csv",
        "secret_lair_owned_universal_positions.csv",
        "secret_lair_full_registry_portfolio_manifest.json",
        "SECRET_LAIR_FULL_REGISTRY_PORTFOLIO_CERTIFICATION.md",
    ))
    manifest = tmp_path / "refresh.json"
    manifest.write_text(json.dumps({
        "status": "CERTIFIED",
        "quota_calls": 0,
        "evaluation": {
            "status": "CERTIFIED", "products": 973, "full_model_products": 214,
            "provisional_model_products": 380, "structural_only_products": 379, "quota_calls": 0,
        },
        "portfolio": {
            "status": "CERTIFIED", "source_rows": 12, "holdings_rows": 12,
            "diagnostic_rows": 0, "total_cost_basis_usd": 471.9,
            "total_modeled_value_usd": 962.83, "quota_calls": 0,
        },
        "outputs": {"evaluation_root": str(evaluation_root), "portfolio_root": str(portfolio_root)},
    }), encoding="utf-8")
    result = certify(manifest, tmp_path / "closeout")
    assert result["status"] == "CERTIFIED"
    assert all(result["checks"].values())


def test_closeout_fails_when_portfolio_has_diagnostics(tmp_path: Path) -> None:
    manifest = tmp_path / "refresh.json"
    manifest.write_text(json.dumps({
        "status": "CERTIFIED", "quota_calls": 0,
        "evaluation": {"status": "CERTIFIED", "products": 973, "full_model_products": 214, "provisional_model_products": 380, "structural_only_products": 379, "quota_calls": 0},
        "portfolio": {"status": "CERTIFIED", "source_rows": 1, "holdings_rows": 0, "diagnostic_rows": 1, "quota_calls": 0},
        "outputs": {"evaluation_root": str(tmp_path / "missing-evaluation"), "portfolio_root": str(tmp_path / "missing-portfolio")},
    }), encoding="utf-8")
    result = certify(manifest, tmp_path / "closeout")
    assert result["status"] == "FAILED"
    assert result["checks"]["all_owned_rows_matched"] is False
