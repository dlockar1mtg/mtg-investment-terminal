from __future__ import annotations

from pathlib import Path

FILES = {
    "scripts/run_secret_lair_production_refresh.py": r'''from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.build_full_secret_lair_model_evaluation import build as build_full_evaluation
from terminal2.portfolio.secret_lair_full_registry import build_owned_portfolio


def run_refresh(
    admission_ledger: Path,
    owned_source: Path,
    output_root: Path,
    default_unspecified_finish: str = "NONFOIL",
) -> dict[str, object]:
    evaluation_root = output_root / "full_model_evaluation"
    portfolio_root = output_root / "owned_portfolio"

    evaluation = build_full_evaluation(admission_ledger, evaluation_root)
    if evaluation.get("status") != "CERTIFIED":
        result = {
            "status": "FAILED",
            "stage": "FULL_MODEL_EVALUATION",
            "evaluation": evaluation,
            "quota_calls": 0,
        }
    else:
        portfolio = build_owned_portfolio(
            registry_path=evaluation_root / "secret_lair_full_product_registry.csv",
            evaluation_path=evaluation_root / "secret_lair_full_model_evaluation.csv",
            owned_source_path=owned_source,
            output_root=portfolio_root,
            default_unspecified_finish=default_unspecified_finish,
        )
        result = {
            "status": "CERTIFIED" if portfolio.get("status") == "CERTIFIED" else "FAILED",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "evaluation": evaluation,
            "portfolio": portfolio,
            "quota_calls": 0,
            "outputs": {
                "evaluation_root": str(evaluation_root.resolve()),
                "portfolio_root": str(portfolio_root.resolve()),
            },
        }

    output_root.mkdir(parents=True, exist_ok=True)
    manifest = output_root / "secret_lair_production_refresh_manifest.json"
    manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("SECRET LAIR PRODUCTION REFRESH: COMPLETE")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admission-ledger", type=Path, required=True)
    parser.add_argument("--owned-source", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--default-unspecified-finish",
        default="NONFOIL",
        choices=("NONFOIL", "FOIL", "RAINBOW_FOIL", "GALAXY_FOIL", "ETCHED_FOIL", "RAISED_FOIL"),
    )
    args = parser.parse_args()
    run_refresh(
        admission_ledger=args.admission_ledger,
        owned_source=args.owned_source,
        output_root=args.output_root,
        default_unspecified_finish=args.default_unspecified_finish,
    )


if __name__ == "__main__":
    main()
''',
    "scripts/certify_phase_10_secret_lair_closeout.py": r'''from __future__ import annotations

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
''',
    "tests/test_phase_10_secret_lair_production_closeout.py": r'''from __future__ import annotations

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
''',
    "docs/phase_10/PHASE_10_SECRET_LAIR_PRODUCTION_CLOSEOUT.md": r'''# Phase 10 Secret Lair Production Closeout

## Production scope

The Secret Lair lane contains a governed 973-product identity registry, complete three-tier model evaluation, finish-aware owned-inventory matching, portfolio valuation, owned-product forecasts, guarded recommendations, and Universal Investment Platform exports.

## Evaluation tiers

- `FULL_MODEL`: governed observed valuation and normal recommendation safeguards.
- `PROVISIONAL_MODEL`: provisional valuation with reduced confidence and watch-only recommendations.
- `STRUCTURAL_ONLY`: comparable-based structural estimate with data-needed recommendations.

## Standard production refresh

Run `scripts/run_secret_lair_production_refresh.py` with the current admission ledger and the local owned-inventory CSV. The command rebuilds the full evaluation and owned portfolio in one deterministic operation and writes a combined refresh manifest.

Then run `scripts/certify_phase_10_secret_lair_closeout.py` against that refresh manifest. Production closeout requires exact reconciliation to 973 products, the 214/380/379 tier split, zero unmatched holdings, complete output publication, and zero API quota calls.

## Data governance

Personal holdings and acquisition costs remain local. Generated validation, portfolio, forecast, recommendation, and certification outputs are reproducible artifacts and are not committed.

## Change-control rule

After certification, the Secret Lair lane is considered production-closed. Reopening development requires one of:

1. A reproducible defect or regression.
2. A source-contract or marketplace change.
3. An approved new capability with a separate milestone.
4. A governed model-policy revision.

Routine price refreshes and holdings updates do not reopen the lane.
''',
}

GITIGNORE_BLOCK = '''
# Phase 10 Secret Lair local holdings and generated production artifacts
data/portfolio/
data/validation/phase_10/ebay_matching/
data/validation/phase_10/premium_universe_eligibility/
'''


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    created: list[str] = []
    for relative, content in FILES.items():
        path = root / relative
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite existing file: {relative}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(relative)

    gitignore = root / ".gitignore"
    current = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    marker = "# Phase 10 Secret Lair local holdings and generated production artifacts"
    if marker not in current:
        gitignore.write_text(current.rstrip() + "\n\n" + GITIGNORE_BLOCK.strip() + "\n", encoding="utf-8")
        created.append(".gitignore (updated)")

    for item in created:
        print(f"Created: {item}")
    print("PHASE 10 SECRET LAIR PRODUCTION CLOSEOUT BUNDLE: APPLIED")


if __name__ == "__main__":
    main()
