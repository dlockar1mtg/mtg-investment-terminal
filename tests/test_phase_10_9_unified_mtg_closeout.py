from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "certify_phase_10_9_unified_mtg_closeout.py"


def load_module():
    spec = importlib.util.spec_from_file_location("phase_10_9_closeout", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_closeout_certifies_all_artifacts() -> None:
    result = load_module().certify()
    assert result["status"] == "PRODUCTION_CLOSED"
    assert all(result["checks"].values())


def test_closeout_counts_are_exact() -> None:
    result = load_module().certify()
    assert result["products"] == 1141
    assert result["owned_positions"] == 14
    assert result["lane_counts"] == {
        "COLLECTOR_BOOSTER_BOX": 49,
        "PRE_COLLECTOR_BOOSTER_BOX": 119,
        "SECRET_LAIR": 973,
    }


def test_closeout_portfolio_reconciles() -> None:
    result = load_module().certify()
    assert result["cost_basis_usd"] == 923.39
    assert result["market_value_usd"] == 1914.43
    assert result["unrealized_gain_loss_usd"] == 991.04
    assert result["checks"]["portfolio_gain_reconciles"]


def test_closeout_allowlist_excludes_generated_data() -> None:
    result = load_module().certify()
    allowlist = result["tracked_commit_allowlist"]
    assert allowlist
    assert all(not path.startswith("data/") for path in allowlist)
    assert "scripts/discover_full_secret_lair_catalog.py" not in allowlist
