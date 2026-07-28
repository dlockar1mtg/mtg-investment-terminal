from __future__ import annotations

import csv
import hashlib
import json
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


def validate_delivery_package(package_root: Path) -> dict[str, Any]:
    manifest_path = package_root / "delivery_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(str(manifest_path))

    manifest = read_json(manifest_path)
    checks = {
        "manifest_status_pass": manifest.get("status") == "PASS",
        "interface_name_supported": (
            manifest.get("interface_name")
            == "mtg-governed-terminal-delivery"
        ),
        "interface_version_supported": (
            manifest.get("interface_version") == "1.0"
        ),
        "governed_product_count_1141": (
            manifest.get("governed_product_count") == 1141
        ),
        "current_asking_not_sold_history": (
            manifest.get("current_asking_is_sold_history") is False
        ),
        "current_asking_not_model_eligible": (
            manifest.get("current_asking_model_eligible") is False
        ),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError(f"Delivery contract checks failed: {failed}")

    manifest_artifacts = {
        row.get("filename"): row
        for row in manifest.get("artifacts", [])
        if row.get("filename")
    }
    artifacts: list[dict[str, Any]] = []

    for filename in REQUIRED_ARTIFACTS:
        path = package_root / filename
        if not path.is_file():
            raise FileNotFoundError(str(path))

        expected_sha = manifest_artifacts.get(filename, {}).get("sha256")
        actual_sha = sha256(path)
        if expected_sha and actual_sha != expected_sha:
            raise ValueError(f"Checksum mismatch: {filename}")

        row: dict[str, Any] = {
            "filename": filename,
            "relative_path": filename,
            "size_bytes": path.stat().st_size,
            "sha256": actual_sha,
        }
        if path.suffix.casefold() == ".csv":
            row["row_count"] = csv_rows(path)
        artifacts.append(row)

    counts = {
        row["filename"]: row.get("row_count")
        for row in artifacts
        if "row_count" in row
    }
    if counts["universal_mtg_consumption_interface.csv"] != 1141:
        raise ValueError("Universal interface must contain 1,141 rows")
    if counts["market_provenance.csv"] != 1141:
        raise ValueError("Market provenance must contain 1,141 rows")

    return {
        "manifest": manifest,
        "checks": checks,
        "artifacts": artifacts,
        "row_counts": counts,
    }


def build_uip_handoff(
    repository_root: Path,
    delivery_root: Path,
    handoff_root: Path,
) -> dict[str, Any]:
    latest_pointer = delivery_root / "latest_package.json"
    if not latest_pointer.is_file():
        raise FileNotFoundError(str(latest_pointer))

    pointer = read_json(latest_pointer)
    package_id = str(pointer["package_id"])
    package_root = delivery_root / "packages" / package_id
    validated = validate_delivery_package(package_root)
    manifest = validated["manifest"]

    payload = {
        "status": "READY_FOR_UIP_IMPORT",
        "handoff_contract": "mtg-to-uip-manual-production-v1",
        "handoff_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_platform": "mtg",
        "source_repository": "mtg-investment-terminal",
        "source_repository_root": str(repository_root.resolve()),
        "manual_production_command": (
            "python scripts/run_phase_11e_17_manual_uip_handoff.py"
        ),
        "package_id": package_id,
        "package_relative_path": str(
            package_root.relative_to(repository_root)
        ).replace("\\", "/"),
        "delivery_manifest_relative_path": str(
            (package_root / "delivery_manifest.json").relative_to(
                repository_root
            )
        ).replace("\\", "/"),
        "interface_name": manifest["interface_name"],
        "interface_version": manifest["interface_version"],
        "currency": manifest.get("currency", "USD"),
        "governed_product_count": manifest["governed_product_count"],
        "current_asking_is_sold_history": False,
        "current_asking_model_eligible": False,
        "row_counts": validated["row_counts"],
        "artifacts": validated["artifacts"],
        "quality_checks": validated["checks"],
        "ownership": {
            "mtg_repository": [
                "source collection",
                "MTG-specific governance",
                "valuation",
                "forecast and recommendation production",
                "versioned package publication",
                "UIP handoff publication",
            ],
            "universal_investment_platform": [
                "refresh scheduling",
                "package invocation or discovery",
                "package import",
                "last-known-good import state",
                "cross-asset intelligence",
                "semantic layer",
                "dashboard publication and refresh",
            ],
        },
    }

    handoff_root.mkdir(parents=True, exist_ok=True)
    handoff_path = handoff_root / "latest_mtg_uip_handoff.json"
    handoff_path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload
