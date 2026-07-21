from __future__ import annotations

import importlib
from pathlib import Path


PRODUCTION_MODULES = [
    "terminal2_run_all",
    "terminal2_module2_run_all",
    "terminal2_export",
    "terminal2.db.schema",
    "terminal2.db.module1_migration",
    "terminal2.db.module2_migration",
    "terminal2.db.loaders",
    "terminal2.features.price_features",
    "terminal2.analytics.scoring",
    "terminal2.warehouse.dashboard_mart",
    "terminal2.market.analytics.intelligence",
    "terminal2.market.analytics.health",
    "terminal2.market.exports",
    "terminal2.history",
    "terminal2.portfolio",
    "terminal2.forecast",
    "terminal2.intelligence",
    "terminal2.calibration",
    "terminal2.semantic",
    "terminal2.return_analytics",
    "terminal2.secret_lair",
]


def test_primary_production_modules_import() -> None:
    for module_name in PRODUCTION_MODULES:
        imported = importlib.import_module(module_name)
        assert imported is not None


def test_orchestrators_do_not_reference_removed_exports_package() -> None:
    repository_root = Path(__file__).resolve().parents[1]

    scripts = [
        repository_root / "terminal2_run_all.py",
        repository_root / "terminal2_module2_run_all.py",
        repository_root / "terminal2_export.py",
    ]

    for script in scripts:
        content = script.read_text(encoding="utf-8")

        assert "terminal2.exports" not in content
        assert "export_all()" not in content