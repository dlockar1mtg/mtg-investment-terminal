from __future__ import annotations

import csv
import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_ARTIFACTS = (
    "universal_mtg_consumption_interface.csv",
    "dashboard.csv",
    "forecasts.csv",
    "recommendations.csv",
    "rankings.csv",
    "exclusions.csv",
    "market_provenance.csv",
    "consumption_summary.json",
    "valuation_summary.json",
)


@dataclass(frozen=True)
class ActivationResult:
    status: str
    package_id: str
    source_package: str
    active_root: str
    used_fallback: bool
    artifact_count: int
    interface_rows: int
    dashboard_rows: int
    forecast_rows: int
    recommendation_rows: int
    ranking_rows: int
    exclusion_rows: int
    current_asking_is_sold_history: bool
    current_asking_model_eligible: bool


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_package(package_root: Path) -> dict[str, Any]:
    manifest_path = package_root / "delivery_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(str(manifest_path))

    manifest = read_json(manifest_path)
    if manifest.get("status") != "PASS":
        raise ValueError("Delivery manifest is not PASS")
    if manifest.get("interface_name") != "mtg-governed-terminal-delivery":
        raise ValueError("Unsupported delivery interface")
    if manifest.get("interface_version") != "1.0":
        raise ValueError("Unsupported delivery interface version")
    if manifest.get("governed_product_count") != 1141:
        raise ValueError("Governed product count must equal 1,141")
    if manifest.get("current_asking_is_sold_history") is not False:
        raise ValueError("Current asking references cannot be sold history")
    if manifest.get("current_asking_model_eligible") is not False:
        raise ValueError("Current asking references cannot be model eligible")

    by_name = {
        row.get("filename"): row
        for row in manifest.get("artifacts", [])
        if row.get("filename")
    }
    for filename in REQUIRED_ARTIFACTS:
        path = package_root / filename
        if not path.is_file():
            raise FileNotFoundError(str(path))
        expected = by_name.get(filename, {}).get("sha256")
        if expected and sha256(path) != expected:
            raise ValueError(f"Checksum mismatch: {filename}")

    counts = {
        "interface_rows": csv_rows(
            package_root / "universal_mtg_consumption_interface.csv"
        ),
        "dashboard_rows": csv_rows(package_root / "dashboard.csv"),
        "forecast_rows": csv_rows(package_root / "forecasts.csv"),
        "recommendation_rows": csv_rows(
            package_root / "recommendations.csv"
        ),
        "ranking_rows": csv_rows(package_root / "rankings.csv"),
        "exclusion_rows": csv_rows(package_root / "exclusions.csv"),
        "provenance_rows": csv_rows(
            package_root / "market_provenance.csv"
        ),
    }
    if counts["interface_rows"] != 1141:
        raise ValueError("Universal interface must contain 1,141 rows")
    if counts["provenance_rows"] != 1141:
        raise ValueError("Market provenance must contain 1,141 rows")
    return {"manifest": manifest, "counts": counts}


def _replace_directory(source: Path, destination: Path) -> None:
    staging = destination.parent / f".{destination.name}-next"
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(source, staging)
    if destination.exists():
        shutil.rmtree(destination)
    staging.rename(destination)


def activate_delivery(
    delivery_root: Path,
    active_root: Path,
    state_root: Path,
) -> ActivationResult:
    latest = delivery_root / "latest"
    last_known_good = state_root / "last_known_good"
    state_root.mkdir(parents=True, exist_ok=True)

    used_fallback = False
    source = latest
    try:
        validated = validate_package(source)
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        source = last_known_good
        used_fallback = True
        validated = validate_package(source)

    _replace_directory(source, active_root)
    if not used_fallback:
        _replace_directory(source, last_known_good)

    manifest = validated["manifest"]
    counts = validated["counts"]
    status = {
        "status": "PASS",
        "activated_at_utc": datetime.now(timezone.utc).isoformat(),
        "package_id": manifest["package_id"],
        "source_package": str(source),
        "active_root": str(active_root),
        "used_fallback": used_fallback,
        "interface_version": manifest["interface_version"],
        "artifact_count": len(REQUIRED_ARTIFACTS),
        **counts,
        "current_asking_is_sold_history": False,
        "current_asking_model_eligible": False,
    }
    (state_root / "terminal_activation_status.json").write_text(
        json.dumps(status, indent=2) + "\n",
        encoding="utf-8",
    )

    return ActivationResult(
        status="PASS",
        package_id=manifest["package_id"],
        source_package=str(source),
        active_root=str(active_root),
        used_fallback=used_fallback,
        artifact_count=len(REQUIRED_ARTIFACTS),
        interface_rows=counts["interface_rows"],
        dashboard_rows=counts["dashboard_rows"],
        forecast_rows=counts["forecast_rows"],
        recommendation_rows=counts["recommendation_rows"],
        ranking_rows=counts["ranking_rows"],
        exclusion_rows=counts["exclusion_rows"],
        current_asking_is_sold_history=False,
        current_asking_model_eligible=False,
    )
