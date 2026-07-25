from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "data" / "validation" / "phase_10" / "universal_export" / "latest"


def read_csv(name: str) -> list[dict[str, str]]:
    with (PACKAGE / name).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_required_export_files_exist() -> None:
    for name in (
        "asset_master.csv",
        "forecasts.csv",
        "recommendations.csv",
        "risk_metrics.csv",
        "portfolio_summary.csv",
        "platform_status.csv",
        "diagnostics.csv",
        "package_summary.json",
        "export_manifest.json",
    ):
        assert (PACKAGE / name).exists(), name


def test_export_row_counts_and_identity_reconciliation() -> None:
    assets = read_csv("asset_master.csv")
    forecasts = read_csv("forecasts.csv")
    recommendations = read_csv("recommendations.csv")
    risks = read_csv("risk_metrics.csv")
    assert len(assets) == len(forecasts) == len(recommendations) == len(risks) == 1141
    ids = {row["asset_id"] for row in assets}
    assert len(ids) == 1141
    assert {row["asset_id"] for row in forecasts} == ids
    assert {row["asset_id"] for row in recommendations} == ids
    assert {row["asset_id"] for row in risks} == ids


def test_export_excludes_private_position_detail() -> None:
    forbidden = {
        "acquisition_date",
        "acquisition_cost_total",
        "total_cost_basis_usd",
        "unit_cost_usd",
        "quantity",
        "holding_id",
        "source_holding_id",
        "notes",
    }
    headers: set[str] = set()
    for name in (
        "asset_master.csv",
        "forecasts.csv",
        "recommendations.csv",
        "risk_metrics.csv",
        "portfolio_summary.csv",
        "platform_status.csv",
    ):
        with (PACKAGE / name).open("r", encoding="utf-8-sig", newline="") as handle:
            headers.update(csv.DictReader(handle).fieldnames or [])
    assert not (forbidden & headers)


def test_package_summary_is_validated() -> None:
    summary = json.loads((PACKAGE / "package_summary.json").read_text(encoding="utf-8"))
    assert summary["validation_status"] == "PASS"
    assert summary["product_count"] == 1141
    assert summary["portfolio_summary_only"] is True
    assert summary["private_position_details_included"] is False
    assert summary["quota_calls"] == 0
