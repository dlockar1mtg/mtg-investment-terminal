from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_mtg_hosted_uip_delivery.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_mtg_hosted_uip_delivery", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_rows(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_unified_fixture(module, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    rows = []

    for key, (_registry_path, evaluation_path) in module.FILES.items():
        lane = module.LANE_NAMES[key]

        for original in read_rows(evaluation_path):
            row = dict(original)
            source = module.source_id(row)

            assert source

            row["lane"] = lane
            row["universal_mtg_product_id"] = module.universal_id(
                lane,
                source,
            )

            if lane == "SECRET_LAIR":
                row["forecast_method"] = "NATIVE_VALUATION_RANGE"
                row["valuation_method"] = "NATIVE_VALUATION_RANGE"
                row["forecast_eligible"] = "NO"
                row["forecast_status"] = "HISTORICAL_ONLY"
                row["horizon_model_certified"] = "NO"
                row["1y_downside_usd"] = ""
                row["1y_base_usd"] = ""
                row["1y_upside_usd"] = ""
                row["3y_downside_usd"] = ""
                row["3y_base_usd"] = ""
                row["3y_upside_usd"] = ""
                row["5y_downside_usd"] = ""
                row["5y_base_usd"] = ""
                row["5y_upside_usd"] = ""

            if source == "TCGCSV-22876-489207":
                row["current_market_value_usd"] = "227.18"
                row["current_unit_value_usd"] = "227.18"
                row["market_value_usd"] = "227.18"
                row["current_price"] = "227.18"
                row["evaluated_market_value_usd"] = "227.18"
                row["forecast_method"] = "NATIVE_MONTE_CARLO_RANGE"
                row["valuation_method"] = "NATIVE_MONTE_CARLO_RANGE"
                row["forecast_base_usd"] = "340.58"
                row["native_forecast_base_usd"] = "340.58"
                row["horizon_model_certified"] = "NO"
                row["1y_base_usd"] = ""
                row["3y_base_usd"] = ""
                row["5y_base_usd"] = ""

            rows.append(row)

    assert len(rows) == 1141

    universal_ids = {
        row["universal_mtg_product_id"]
        for row in rows
    }

    assert len(universal_ids) == 1141

    fields = []
    seen = set()

    for row in rows:
        for field in row:
            if field not in seen:
                seen.add(field)
                fields.append(field)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_historical_fixture(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "investment_product_id",
        "historical_performance_eligible",
        "historical_total_return_pct",
        "historical_cagr_pct",
    ]

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for index in range(973):
            eligible = index < 782
            writer.writerow(
                {
                    "investment_product_id": f"SL-TEST-{index:04d}",
                    "historical_performance_eligible": (
                        "YES" if eligible else "NO"
                    ),
                    "historical_total_return_pct": (
                        "5.0" if eligible else ""
                    ),
                    "historical_cagr_pct": (
                        "2.5" if eligible else ""
                    ),
                }
            )


def test_hosted_delivery_builds_complete_contract(tmp_path):
    module = load_module()

    historical_source = tmp_path / "source" / "historical_performance.csv"
    write_historical_fixture(historical_source)
    module.HISTORICAL_PERFORMANCE_SOURCE = historical_source

    unified_source = tmp_path / "source" / "unified_mtg_intelligence_interface.csv"
    write_unified_fixture(module, unified_source)
    module.UNIFIED_INTERFACE = unified_source

    result = module.build(tmp_path)
    assert result["status"] == "PASS"
    assert result["products"] == 1141
    latest = tmp_path / "latest"
    required = {
        "asset_master.csv",
        "forecasts.csv",
        "recommendations.csv",
        "risk_metrics.csv",
        "portfolio_positions.csv",
        "platform_status.csv",
        "diagnostics.csv",
        "historical_performance.csv",
        "export_manifest.json",
        "package_summary.json",
    }
    assert required.issubset({path.name for path in latest.iterdir()})
    assert len(read_rows(latest / "asset_master.csv")) == 1141
    assert len(read_rows(latest / "historical_performance.csv")) == 973
    assert read_rows(latest / "diagnostics.csv") == []


def test_delivery_manifest_has_expected_lanes(tmp_path):
    module = load_module()

    historical_source = tmp_path / "source" / "historical_performance.csv"
    write_historical_fixture(historical_source)
    module.HISTORICAL_PERFORMANCE_SOURCE = historical_source

    unified_source = tmp_path / "source" / "unified_mtg_intelligence_interface.csv"
    write_unified_fixture(module, unified_source)
    module.UNIFIED_INTERFACE = unified_source

    module.build(tmp_path)
    manifest = json.loads(
        (tmp_path / "latest" / "package_summary.json").read_text()
    )
    assert manifest["lane_counts"] == {
        "SECRET_LAIR": 973,
        "COLLECTOR_BOOSTER_BOX": 49,
        "PRE_COLLECTOR_BOOSTER_BOX": 119,
    }
    assert manifest["historical_performance"] == {
        "rows": 973,
        "eligible": 782,
        "suppressed": 191,
    }
    assert "historical_performance.csv" in manifest["files"]
