import csv
import hashlib
import json
from pathlib import Path

from terminal2.delivery.uip_handoff import (
    REQUIRED_ARTIFACTS,
    build_uip_handoff,
)


def write_csv(path: Path, rows: int) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["canonical_product_id", "valuation_state"],
        )
        writer.writeheader()
        for index in range(rows):
            writer.writerow({
                "canonical_product_id": f"P{index:04d}",
                "valuation_state": "DIRECT_HISTORY_VALUATION",
            })


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_package(root: Path) -> None:
    delivery = root / "data/operations/mtg_terminal_delivery"
    package_id = "mtg-governed-test"
    package = delivery / "packages" / package_id
    package.mkdir(parents=True)

    counts = {
        "universal_mtg_consumption_interface.csv": 1141,
        "dashboard.csv": 1001,
        "forecasts.csv": 955,
        "recommendations.csv": 567,
        "rankings.csv": 130,
        "exclusions.csv": 186,
        "market_provenance.csv": 1141,
    }
    for name, rows in counts.items():
        write_csv(package / name, rows)
    (package / "consumption_summary.json").write_text("{}")
    (package / "valuation_summary.json").write_text("{}")

    artifacts = [
        {"filename": name, "sha256": sha(package / name)}
        for name in REQUIRED_ARTIFACTS
    ]
    (package / "delivery_manifest.json").write_text(json.dumps({
        "status": "PASS",
        "package_id": package_id,
        "interface_name": "mtg-governed-terminal-delivery",
        "interface_version": "1.0",
        "governed_product_count": 1141,
        "currency": "USD",
        "current_asking_is_sold_history": False,
        "current_asking_model_eligible": False,
        "artifacts": artifacts,
    }))
    (delivery / "latest_package.json").write_text(json.dumps({
        "package_id": package_id,
    }))


def test_builds_manual_uip_handoff(tmp_path: Path):
    build_package(tmp_path)
    payload = build_uip_handoff(
        tmp_path,
        tmp_path / "data/operations/mtg_terminal_delivery",
        tmp_path / "data/operations/mtg_uip_handoff",
    )
    assert payload["status"] == "READY_FOR_UIP_IMPORT"
    assert payload["package_id"] == "mtg-governed-test"
    assert payload["row_counts"][
        "universal_mtg_consumption_interface.csv"
    ] == 1141
    assert payload["current_asking_is_sold_history"] is False
    assert payload["current_asking_model_eligible"] is False
