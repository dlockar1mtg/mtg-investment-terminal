import csv
import hashlib
import json
from pathlib import Path

from terminal2.delivery.governed_loader import (
    REQUIRED_ARTIFACTS,
    activate_delivery,
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


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package(root: Path, package_id: str) -> Path:
    latest = root / "latest"
    latest.mkdir(parents=True)
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
        write_csv(latest / name, rows)
    (latest / "consumption_summary.json").write_text("{}")
    (latest / "valuation_summary.json").write_text("{}")
    artifacts = [
        {"filename": name, "sha256": digest(latest / name)}
        for name in REQUIRED_ARTIFACTS
    ]
    (latest / "delivery_manifest.json").write_text(json.dumps({
        "status": "PASS",
        "package_id": package_id,
        "interface_name": "mtg-governed-terminal-delivery",
        "interface_version": "1.0",
        "governed_product_count": 1141,
        "current_asking_is_sold_history": False,
        "current_asking_model_eligible": False,
        "artifacts": artifacts,
    }))
    return latest


def test_activation_copies_valid_package(tmp_path: Path):
    delivery = tmp_path / "delivery"
    package(delivery, "test-package")
    result = activate_delivery(
        delivery,
        tmp_path / "active",
        tmp_path / "state",
    )
    assert result.package_id == "test-package"
    assert result.interface_rows == 1141
    assert result.used_fallback is False
