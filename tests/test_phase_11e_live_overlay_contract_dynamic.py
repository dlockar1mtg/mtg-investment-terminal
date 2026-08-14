from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_phase_11e_live_overlay_contract.py"


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_overlay_audit_uses_dynamic_native_authority_population(tmp_path: Path) -> None:
    package = tmp_path / "package"
    market = tmp_path / "market"
    output = tmp_path / "audit.json"

    assets = [
        {
            "asset_id": "COLLECTOR_V1|MTG-CANON-TCGPLAYER-100",
            "source_product_id": "MTG-CANON-TCGPLAYER-100",
        },
        {
            "asset_id": "SECRET_LAIR_V1_1|SL-TEST-200",
            "source_product_id": "SL-TEST-200",
        },
    ]
    dependent = [{"asset_id": row["asset_id"], "source_product_id": row["source_product_id"]} for row in assets]
    native = [
        {"mtg_asset_id": assets[0]["asset_id"], "mtg_lane": "COLLECTOR_V1"},
        {"mtg_asset_id": assets[1]["asset_id"], "mtg_lane": "SECRET_LAIR_V1_1"},
    ]

    write_csv(package / "asset_master.csv", assets)
    write_csv(package / "forecasts.csv", dependent)
    write_csv(package / "recommendations.csv", dependent)
    write_csv(package / "risk_metrics.csv", dependent)
    write_csv(package / "mtg_native_authority.csv", native)
    write_csv(
        market / "consolidated_marketplace_prices.csv",
        [{"source_product_id": "MTG-CANON-TCGPLAYER-100", "current_price_usd": "10"}],
    )
    write_csv(
        market / "certified_marketplace_decisions.csv",
        [{"source_product_id": "MTG-CANON-TCGPLAYER-100", "signal": "WATCH"}],
    )

    (package / "package_summary.json").write_text(
        json.dumps(
            {
                "products": 2,
                "lane_counts": {"COLLECTOR_V1": 1, "SECRET_LAIR_V1_1": 1},
                "snapshot_population_is_permanent": False,
                "generic_surfaces_are_semantic_authority": False,
                "automatic_purchase_execution": False,
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--package",
            str(package),
            "--market-root",
            str(market),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["population_contract"] == "DYNAMIC_CERTIFIED_NATIVE_AUTHORITY"
    assert payload["counts"]["assets"] == 2
    assert payload["counts"]["native_authority"] == 2
    assert "PHASE_11E_PACKAGE_PRODUCT_COUNT_NOT_1141" not in payload["reason_codes"]
