from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_SOURCE_ID = "20260801T211201Z"
REQUIRED = {
    "tcgcsv_manifest": "data/operations/mtg_source_discovery/tcgcsv_snapshots/20260801T211201Z/tcgcsv_snapshot_manifest.json",
    "tcgcsv_products": "data/operations/mtg_source_discovery/tcgcsv_snapshots/20260801T211201Z/tcgcsv_magic_products.csv",
    "tcgcsv_groups": "data/operations/mtg_source_discovery/tcgcsv_snapshots/20260801T211201Z/tcgcsv_magic_groups.csv",
    "live_price_observations": "data/operations/tcgcsv/collector_live_price_observations.csv",
    "current_authority": "data/governance/permanence/certification/collector_current_authority/collector_current_authority_authorized.csv",
    "current_authority_summary": "data/governance/permanence/certification/collector_current_authority/collector_current_authority_summary.json",
    "live_price_candidates": "data/governance/permanence/certification/collector_live_current_prices/collector_live_current_price_certified_candidates.csv",
    "live_price_summary": "data/governance/permanence/certification/collector_live_current_prices/collector_live_current_price_summary.json",
    "ebay_listing_ledger": "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline/collector_ebay_day_one_accepted_listing_ledger.csv",
    "ebay_supply_snapshot": "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline/collector_ebay_day_one_product_supply_snapshot.csv",
    "ebay_baseline_summary": "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline/collector_ebay_day_one_supply_baseline_summary.json",
    "canonical_routes": "data/governance/permanence/certification/collector_v1_canonical_inputs/collector_v1_canonical_forecast_routes.csv",
    "canonical_history": "data/governance/permanence/certification/collector_v1_canonical_inputs/collector_v1_canonical_daily_price_history.csv",
    "feature_matrix": "data/governance/permanence/certification/collector_v1_feature_matrix/collector_v1_feature_matrix.csv",
    "feature_manifest": "data/governance/permanence/certification/collector_v1_feature_matrix/collector_v1_feature_matrix_manifest.json",
    "feature_certification": "data/governance/permanence/certification/collector_v1_feature_matrix/collector_v1_feature_matrix_certification.json",
}

PASS_WORDS = {"PASS", "CERTIFIED", "READY", "COMPLETE", "AUTHORIZED", "TRUE"}
DATE_PATTERN = re.compile(r"2026-08-01|20260801T")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def row_count(path: Path) -> int | None:
    if path.suffix.lower() != ".csv":
        return None
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return max(sum(1 for _ in csv.reader(f)) - 1, 0)


def json_pass_like(path: Path) -> bool:
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return False
    text = json.dumps(obj, sort_keys=True).upper()
    return any(word in text for word in PASS_WORDS) and "FAIL" not in text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    checks: dict[str, bool] = {}
    files = []
    for role, rel in REQUIRED.items():
        path = ROOT / rel
        exists = path.exists()
        checks[f"{role}_exists"] = exists
        if not exists:
            continue
        modified_utc = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        files.append({
            "role": role,
            "path": rel,
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
            "rows": row_count(path),
            "last_modified_utc": modified_utc.isoformat(),
        })
        checks[f"{role}_is_august_1_artifact"] = bool(DATE_PATTERN.search(rel) or modified_utc.date().isoformat() == "2026-08-01")

    summary_roles = [r for r in REQUIRED if r.endswith("summary") or r.endswith("certification") or r.endswith("manifest")]
    for role in summary_roles:
        p = ROOT / REQUIRED[role]
        if p.exists() and p.suffix.lower() == ".json":
            checks[f"{role}_pass_like"] = json_pass_like(p)

    source_files = [x for x in files if x["role"] in {"tcgcsv_products", "tcgcsv_groups", "live_price_observations", "current_authority", "live_price_candidates", "ebay_listing_ledger", "ebay_supply_snapshot"}]
    digest = hashlib.sha256("".join(sorted(x["sha256"] for x in source_files)).encode()).hexdigest()
    snapshot_id = f"collector-20260801T211201Z-{digest[:8]}"
    out_dir = ROOT / "data/governance/permanence/snapshots" / snapshot_id
    out_dir.mkdir(parents=True, exist_ok=True)

    all_required_exist = all(checks.get(f"{role}_exists", False) for role in REQUIRED)
    all_aug1 = all(checks.get(f"{role}_is_august_1_artifact", False) for role in REQUIRED)
    all_json_pass = all(v for k, v in checks.items() if k.endswith("_pass_like"))
    checks["all_required_authorities_present"] = all_required_exist
    checks["all_registered_artifacts_from_august_1"] = all_aug1
    checks["all_declared_json_controls_pass_like"] = all_json_pass
    checks["source_hash_bundle_created"] = bool(digest)

    certified = all(checks.values())
    manifest = {
        "snapshot_id": snapshot_id,
        "snapshot_source_id": SNAPSHOT_SOURCE_ID,
        "captured_at_utc": "2026-08-01T21:12:01Z",
        "registered_at_utc": now.isoformat(),
        "provider_authorities": ["TCGCSV", "eBay"],
        "price_authority": REQUIRED["live_price_candidates"],
        "listing_authority": REQUIRED["ebay_listing_ledger"],
        "feature_authority": REQUIRED["feature_matrix"],
        "source_bundle_sha256": digest,
        "files": files,
        "checks": checks,
        "certified_for_model_input": certified,
        "fresh_snapshot_capture_authorized": certified,
        "model_rebuild_authorized": certified,
        "purchase_recommendations_authorized": False,
        "status": "PASS_COLLECTOR_V1_AUGUST_1_GOVERNED_SNAPSHOT_REGISTRATION" if certified else "FAIL_COLLECTOR_V1_AUGUST_1_GOVERNED_SNAPSHOT_REGISTRATION",
    }
    manifest_path = out_dir / "collector_snapshot_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    evidence_dir = ROOT / "data/governance/permanence/certification/collector_v1_august_1_snapshot_registration"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "collector_v1_august_1_snapshot_registration_summary.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(json.dumps(manifest, indent=2))
    if certified:
        print("PASS_COLLECTOR_V1_AUGUST_1_GOVERNED_SNAPSHOT_REGISTRATION")
        return 0
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
