from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
MANIFEST_PATH = (
    ROOT
    / "data"
    / "governance"
    / "permanence"
    / "snapshots"
    / EXPECTED_SNAPSHOT_ID
    / "collector_snapshot_manifest.json"
)
EVIDENCE_DIR = (
    ROOT
    / "data"
    / "governance"
    / "permanence"
    / "certification"
    / "collector_v1_snapshot_bound_authority_verification"
)

REQUIRED_AUTHORITY_ROLES = {
    "price": "live_price_candidates",
    "identity": "current_authority",
    "listing": "ebay_listing_ledger",
    "supply": "ebay_supply_snapshot",
    "route": "canonical_routes",
    "history": "canonical_history",
    "feature": "feature_matrix",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Certified snapshot manifest not found: {MANIFEST_PATH}")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8-sig"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    generated_at_utc = datetime.now(timezone.utc).isoformat()
    checks: dict[str, bool] = {}
    manifest = load_manifest()

    checks["snapshot_id_matches"] = manifest.get("snapshot_id") == EXPECTED_SNAPSHOT_ID
    checks["snapshot_certified_for_model_input"] = manifest.get("certified_for_model_input") is True
    checks["snapshot_model_rebuild_authorized"] = manifest.get("model_rebuild_authorized") is True
    checks["purchase_recommendations_remain_unauthorized"] = (
        manifest.get("purchase_recommendations_authorized") is False
    )

    files_by_role = {
        str(item.get("role")): item
        for item in manifest.get("files", [])
        if isinstance(item, dict)
    }

    authorities: dict[str, dict[str, object]] = {}
    for authority_name, role in REQUIRED_AUTHORITY_ROLES.items():
        item = files_by_role.get(role)
        present = item is not None
        checks[f"{authority_name}_authority_registered"] = present
        if not present:
            continue

        relative_path = str(item.get("path", ""))
        expected_hash = str(item.get("sha256", ""))
        path = ROOT / relative_path
        exists = path.exists()
        checks[f"{authority_name}_authority_exists"] = exists
        actual_hash = sha256(path) if exists else None
        checks[f"{authority_name}_authority_hash_matches"] = (
            exists and bool(expected_hash) and actual_hash == expected_hash
        )
        authorities[authority_name] = {
            "role": role,
            "path": relative_path,
            "expected_sha256": expected_hash,
            "actual_sha256": actual_hash,
            "hash_matches": checks[f"{authority_name}_authority_hash_matches"],
            "rows": item.get("rows"),
        }

    source_hashes = sorted(
        str(item.get("sha256"))
        for item in manifest.get("files", [])
        if isinstance(item, dict)
        and item.get("role")
        in {
            "tcgcsv_products",
            "tcgcsv_groups",
            "live_price_observations",
            "current_authority",
            "live_price_candidates",
            "ebay_listing_ledger",
            "ebay_supply_snapshot",
        }
    )
    bundle_digest = hashlib.sha256("".join(source_hashes).encode("utf-8")).hexdigest()
    checks["source_bundle_sha256_matches"] = (
        bundle_digest == manifest.get("source_bundle_sha256")
    )

    failures = [name for name, passed in checks.items() if not passed]
    passed = not failures
    summary = {
        "block_name": "Collector V1 Snapshot-Bound Authority Verification",
        "block_version": "1.0.0",
        "generated_at_utc": generated_at_utc,
        "source_snapshot_id": EXPECTED_SNAPSHOT_ID,
        "source_bundle_sha256": manifest.get("source_bundle_sha256"),
        "source_price_authority_sha256": authorities.get("price", {}).get("actual_sha256"),
        "source_listing_authority_sha256": authorities.get("listing", {}).get("actual_sha256"),
        "source_feature_authority_sha256": authorities.get("feature", {}).get("actual_sha256"),
        "authorities": authorities,
        "checks": checks,
        "critical_failures": failures,
        "verified_for_snapshot_bound_model_rebuild": passed,
        "purchase_recommendations_authorized": False,
        "status": (
            "PASS_COLLECTOR_V1_SNAPSHOT_BOUND_AUTHORITY_VERIFICATION"
            if passed
            else "FAIL_COLLECTOR_V1_SNAPSHOT_BOUND_AUTHORITY_VERIFICATION"
        ),
    }

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    output = EVIDENCE_DIR / "collector_v1_snapshot_bound_authority_verification_summary.json"
    output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
