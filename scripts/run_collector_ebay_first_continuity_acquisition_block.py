"""Run exactly one governed first post-baseline eBay continuity acquisition.

This block is fail closed. It verifies the 24-hour readiness gate, runs the existing
50-product acquisition contract, and immediately archives the resulting acquisition
artifacts into an immutable timestamped continuity-observation directory. Raw output
is not authorized for continuity metrics until later hardening and adjudication pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READINESS = ROOT / "data/governance/permanence/certification/collector_ebay_first_continuity_readiness/collector_ebay_first_continuity_readiness_summary.json"
ACQ_DIR = ROOT / "data/governance/permanence/certification/collector_ebay_full_universe_acquisition"
ACQ_SUMMARY = ACQ_DIR / "collector_ebay_full_universe_acquisition_summary.json"
OUT_ROOT = ROOT / "data/governance/permanence/certification/collector_ebay_continuity_observations"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run first governed post-baseline eBay continuity acquisition")
    p.add_argument("--minimum-hours", type=float, default=24.0)
    p.add_argument("--limit-per-product", type=int, default=200)
    p.add_argument("--strict", action="store_true")
    return p


def run(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, env=env, check=False, text=True)


def main() -> int:
    args = parser().parse_args()
    generated = datetime.now(timezone.utc)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    readiness_command = [
        sys.executable,
        "scripts/certify_collector_ebay_first_continuity_readiness.py",
        "--minimum-hours",
        str(args.minimum_hours),
        "--strict",
    ]
    readiness_result = run(readiness_command, env)
    readiness = json.loads(READINESS.read_text(encoding="utf-8")) if READINESS.is_file() else {}
    authorized = (
        readiness_result.returncode == 0
        and readiness.get("authorization_state") == "AUTHORIZED_ONE_CONTINUITY_RUN"
        and readiness.get("authorized") is True
        and readiness.get("baseline_artifact_hashes_match") is True
    )

    if not authorized:
        summary = {
            "block_name": "Collector eBay First Continuity Acquisition",
            "block_version": "1.0.0",
            "generated_at": generated.isoformat(),
            "live_collection_executed": False,
            "readiness_authorization_state": readiness.get("authorization_state", "MISSING"),
            "readiness_authorized": bool(readiness.get("authorized")),
            "observation_archived": False,
            "continuity_metrics_authorized": False,
            "status": "CONTINUITY_ACQUISITION_NOT_AUTHORIZED",
        }
        print(json.dumps(summary, indent=2))
        return 1 if args.strict and readiness.get("authorization_state") not in {"DAILY_INTERVAL_NOT_REACHED", "CREDENTIALS_REQUIRED"} else 0

    acquisition_command = [
        sys.executable,
        "scripts/run_collector_ebay_full_universe_acquisition_certification_block.py",
        "--limit-per-product",
        str(args.limit_per_product),
        "--strict",
    ]
    acquisition_result = run(acquisition_command, env)
    acquisition = json.loads(ACQ_SUMMARY.read_text(encoding="utf-8")) if ACQ_SUMMARY.is_file() else {}
    acquisition_passed = (
        acquisition_result.returncode == 0
        and acquisition.get("acquisition_recall_certified") is True
        and acquisition.get("live_collection_executed") is True
        and int(acquisition.get("governed_products", 0)) == 50
        and int(acquisition.get("coverage_rows", 0)) == 50
        and int(acquisition.get("source_errors", -1)) == 0
        and not acquisition.get("candidate_ceiling_products")
    )

    observation_id = "collector-ebay-continuity-" + generated.strftime("%Y%m%dT%H%M%SZ")
    observation_dir = OUT_ROOT / observation_id
    archived_files: list[dict[str, object]] = []
    if acquisition_passed:
        observation_dir.mkdir(parents=True, exist_ok=False)
        for source in sorted(ACQ_DIR.iterdir()):
            if source.is_file():
                target = observation_dir / source.name
                shutil.copy2(source, target)
                archived_files.append({
                    "path": str(target.relative_to(ROOT)),
                    "sha256": sha256_file(target),
                    "bytes": target.stat().st_size,
                })

    summary = {
        "block_name": "Collector eBay First Continuity Acquisition",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "observation_id": observation_id if acquisition_passed else "",
        "baseline_id": readiness.get("baseline_id", "collector-ebay-day-one-20260802"),
        "readiness_authorization_state": readiness.get("authorization_state"),
        "readiness_authorized": authorized,
        "live_collection_executed": bool(acquisition.get("live_collection_executed")),
        "acquisition_recall_certified": bool(acquisition.get("acquisition_recall_certified")),
        "governed_products": acquisition.get("governed_products", 0),
        "coverage_rows": acquisition.get("coverage_rows", 0),
        "source_errors": acquisition.get("source_errors", -1),
        "candidate_ceiling_products": acquisition.get("candidate_ceiling_products", []),
        "raw_listing_rows": acquisition.get("raw_listing_rows", 0),
        "deduplicated_listing_rows": acquisition.get("deduplicated_listing_rows", 0),
        "observation_archived": acquisition_passed,
        "observation_directory": str(observation_dir.relative_to(ROOT)) if acquisition_passed else "",
        "archived_files": archived_files,
        "raw_observation_only": True,
        "matcher_hardening_required": True,
        "cross_product_adjudication_required": True,
        "continuity_metrics_authorized": False,
        "scarcity_features_authorized": False,
        "forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_FIRST_CONTINUITY_ACQUISITION_ARCHIVED_HARDENING_REQUIRED" if acquisition_passed else "FAIL_FIRST_CONTINUITY_ACQUISITION",
    }
    if acquisition_passed:
        (observation_dir / "collector_ebay_first_continuity_acquisition_manifest.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(summary, indent=2))
    return 0 if acquisition_passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
