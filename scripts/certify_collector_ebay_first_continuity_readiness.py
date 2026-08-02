"""Certify readiness for the first comparable post-baseline Collector eBay observation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline"
SUMMARY = BASE / "collector_ebay_day_one_supply_baseline_summary.json"
MANIFEST = BASE / "collector_ebay_day_one_supply_baseline_manifest.json"
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_first_continuity_readiness"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Certify first post-baseline continuity readiness")
    p.add_argument("--minimum-hours", type=float, default=24.0)
    p.add_argument("--strict", action="store_true")
    return p


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def main() -> int:
    args = parser().parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    missing = [str(p) for p in (SUMMARY, MANIFEST) if not p.is_file()]
    if missing:
        result = {"status": "REQUIRED_INPUT_MISSING", "missing_inputs": missing, "authorized": False}
        (OUT / "collector_ebay_first_continuity_readiness_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    baseline_time = parse_time(summary.get("generated_at", summary.get("baseline_observed_at_utc", "")))
    elapsed_hours = (now - baseline_time).total_seconds() / 3600.0
    interval_passed = elapsed_hours >= args.minimum_hours

    artifact_hash_results = {}
    all_hashes_match = True
    for name, rel in manifest.get("artifacts", {}).items():
        path = ROOT / rel
        expected = manifest.get("hashes", {}).get(f"{name}_sha256") or manifest.get("hashes", {}).get(name + "_sha256")
        if not path.is_file() or not expected:
            artifact_hash_results[name] = {"exists": path.is_file(), "expected_hash_present": bool(expected), "matches": False}
            all_hashes_match = False
            continue
        actual = sha256_file(path)
        matches = actual == expected
        artifact_hash_results[name] = {"exists": True, "expected": expected, "actual": actual, "matches": matches}
        all_hashes_match = all_hashes_match and matches

    baseline_promoted = summary.get("baseline_promoted") is True and summary.get("continuity_accumulation_authorized") is True
    credentials_ready = bool(os.getenv("EBAY_CLIENT_ID")) and bool(os.getenv("EBAY_CLIENT_SECRET"))
    authorized = baseline_promoted and all_hashes_match and interval_passed and credentials_ready
    if not interval_passed:
        state = "DAILY_INTERVAL_NOT_REACHED"
    elif not credentials_ready:
        state = "CREDENTIALS_REQUIRED"
    elif not all_hashes_match:
        state = "BASELINE_HASH_MISMATCH"
    elif not baseline_promoted:
        state = "BASELINE_NOT_AUTHORIZED"
    else:
        state = "AUTHORIZED_ONE_CONTINUITY_RUN"

    result = {
        "block_name": "Collector eBay First Continuity Readiness",
        "block_version": "1.0.0",
        "generated_at": now.isoformat(),
        "offline_only": True,
        "quota_calls": 0,
        "minimum_interval_hours": args.minimum_hours,
        "baseline_time_utc": baseline_time.isoformat(),
        "elapsed_hours": round(elapsed_hours, 6),
        "interval_passed": interval_passed,
        "baseline_promoted": baseline_promoted,
        "baseline_artifact_hashes_match": all_hashes_match,
        "credentials_ready": credentials_ready,
        "authorization_state": state,
        "authorized": authorized,
        "artifact_hash_results": artifact_hash_results,
        "forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_FIRST_CONTINUITY_READINESS_AUTHORIZED" if authorized else state,
    }
    (OUT / "collector_ebay_first_continuity_readiness_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if authorized or state == "DAILY_INTERVAL_NOT_REACHED" else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
