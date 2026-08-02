from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
MANIFEST_PATH = ROOT / "data/governance/permanence/snapshots" / SNAPSHOT_ID / "collector_snapshot_manifest.json"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_current_foundation_contract_audit"

AUTHORITY_ROLES = {
    "price": "live_price_candidates",
    "identity": "current_authority",
    "listing": "ebay_listing_ledger",
    "supply": "ebay_supply_snapshot",
    "route": "canonical_routes",
    "history": "canonical_history",
    "feature": "feature_matrix",
}

KEY_ALIASES = (
    "investment_product_id",
    "product_id",
    "collector_product_id",
    "canonical_product_id",
    "tcgplayer_product_id",
    "tcgcsv_product_id",
    "product_name",
)
PRICE_ALIASES = (
    "current_price",
    "market_price",
    "certified_current_price",
    "price",
)
PRICE_DATE_ALIASES = (
    "current_price_date",
    "latest_price_date",
    "observation_date",
    "price_observation_date",
    "source_observation_at_utc",
)
LISTING_COUNT_ALIASES = (
    "accepted_listing_count",
    "listing_count",
    "active_listing_count",
)
ROUTE_ALIASES = (
    "forecast_method",
    "method_route",
    "forecast_route",
    "route",
)

TEXT_SUFFIXES = {".py", ".json", ".yaml", ".yml", ".toml", ".md", ".sql", ".ps1", ".bat", ".sh"}
SKIP_PARTS = {".git", ".venv", "venv", "node_modules", "__pycache__"}
SEARCH_TERMS = (
    "BLOCKED_PENDING_APPROVED_EXECUTABLE_PRICE_ADAPTER",
    "current_price",
    "accepted_listing_count",
    "maximum_purchase_price",
    "purchase_recommendation",
    "analytical_score",
    "forecast_route",
)
PRODUCER_PATTERN = re.compile(r"to_csv\s*\(|write_text\s*\(|json\.dump|csv\.DictWriter", re.I)
CONSUMER_PATTERN = re.compile(r"read_csv\s*\(|read_text\s*\(|json\.load|csv\.DictReader", re.I)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Missing certified manifest: {MANIFEST_PATH}")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8-sig"))


def inspect_csv(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = list(reader)

    column_set = set(columns)
    aliases = {
        "key_candidates": [name for name in KEY_ALIASES if name in column_set],
        "price_candidates": [name for name in PRICE_ALIASES if name in column_set],
        "price_date_candidates": [name for name in PRICE_DATE_ALIASES if name in column_set],
        "listing_count_candidates": [name for name in LISTING_COUNT_ALIASES if name in column_set],
        "route_candidates": [name for name in ROUTE_ALIASES if name in column_set],
    }

    key_profiles: dict[str, object] = {}
    for key in aliases["key_candidates"]:
        values = [str(row.get(key, "")).strip() for row in rows]
        nonblank = [value for value in values if value]
        duplicates = sorted(value for value, count in Counter(nonblank).items() if count > 1)
        key_profiles[key] = {
            "nonblank_count": len(nonblank),
            "unique_count": len(set(nonblank)),
            "duplicate_count": len(duplicates),
            "duplicate_examples": duplicates[:10],
            "complete": len(nonblank) == len(rows),
            "unique": len(nonblank) == len(set(nonblank)),
        }

    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256(path),
        "row_count": len(rows),
        "columns": columns,
        "aliases": aliases,
        "key_profiles": key_profiles,
        "sample_rows": rows[:2],
    }


def scan_repository() -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_PARTS for part in path.parts) or OUT_DIR in path.parents:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        matched_terms = [term for term in SEARCH_TERMS if term in text]
        if not matched_terms:
            continue
        evidence = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            line_terms = [term for term in matched_terms if term in line]
            if line_terms:
                evidence.append({"line": line_number, "terms": line_terms, "text": line.strip()[:500]})
            if len(evidence) >= 15:
                break
        results.append({
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256(path),
            "matched_terms": matched_terms,
            "producer_candidate": bool(PRODUCER_PATTERN.search(text)),
            "consumer_candidate": bool(CONSUMER_PATTERN.search(text)),
            "evidence": evidence,
        })
    return sorted(results, key=lambda item: str(item["path"]))


def common_unique_keys(authorities: dict[str, dict[str, object]]) -> list[str]:
    candidates = set(KEY_ALIASES)
    for role in ("price", "identity", "supply", "route", "feature"):
        profile = authorities[role]
        valid = {
            key
            for key, details in profile["key_profiles"].items()
            if details["complete"] and details["unique"]
        }
        candidates &= valid
    return [key for key in KEY_ALIASES if key in candidates]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    manifest = load_manifest()
    files_by_role = {
        str(item.get("role")): item
        for item in manifest.get("files", [])
        if isinstance(item, dict)
    }

    authorities: dict[str, dict[str, object]] = {}
    checks: dict[str, bool] = {}
    for authority_name, manifest_role in AUTHORITY_ROLES.items():
        item = files_by_role.get(manifest_role)
        checks[f"{authority_name}_registered"] = item is not None
        if item is None:
            continue
        path = ROOT / str(item.get("path", ""))
        checks[f"{authority_name}_exists"] = path.exists()
        if not path.exists():
            continue
        profile = inspect_csv(path)
        authorities[authority_name] = profile
        checks[f"{authority_name}_hash_matches_manifest"] = profile["sha256"] == item.get("sha256")

    expected = set(AUTHORITY_ROLES)
    checks["all_authorities_profiled"] = set(authorities) == expected

    common_keys = common_unique_keys(authorities) if checks["all_authorities_profiled"] else []
    checks["exactly_one_common_complete_unique_product_key"] = len(common_keys) == 1

    if "price" in authorities:
        aliases = authorities["price"]["aliases"]
        checks["exactly_one_price_column"] = len(aliases["price_candidates"]) == 1
        checks["price_observation_lineage_present"] = len(aliases["price_date_candidates"]) >= 1
    else:
        checks["exactly_one_price_column"] = False
        checks["price_observation_lineage_present"] = False

    if "supply" in authorities:
        checks["supply_listing_count_present"] = len(authorities["supply"]["aliases"]["listing_count_candidates"]) >= 1
    else:
        checks["supply_listing_count_present"] = False

    if "route" in authorities:
        checks["route_column_present"] = len(authorities["route"]["aliases"]["route_candidates"]) >= 1
    else:
        checks["route_column_present"] = False

    row_checks = {
        "price": 50,
        "identity": 50,
        "supply": 50,
        "feature": 50,
    }
    for role, expected_rows in row_checks.items():
        checks[f"{role}_has_{expected_rows}_rows"] = authorities.get(role, {}).get("row_count") == expected_rows

    repository_matches = scan_repository()
    governance_matches = [
        item for item in repository_matches
        if "BLOCKED_PENDING_APPROVED_EXECUTABLE_PRICE_ADAPTER" in item["matched_terms"]
    ]
    producer_candidates = [item for item in repository_matches if item["producer_candidate"]]
    checks["blocked_authority_record_located"] = len(governance_matches) >= 1
    checks["downstream_producer_candidates_located"] = len(producer_candidates) >= 1

    critical_failures = [name for name, passed in checks.items() if not passed]
    passed = not critical_failures
    summary = {
        "block_name": "Collector V1 Current Foundation Contract and Execution Discovery",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_snapshot_id": SNAPSHOT_ID,
        "source_bundle_sha256": manifest.get("source_bundle_sha256"),
        "common_complete_unique_product_keys": common_keys,
        "authorities": authorities,
        "governance_record_candidates": governance_matches,
        "downstream_producer_candidates": producer_candidates,
        "repository_matches": repository_matches,
        "checks": checks,
        "critical_failures": critical_failures,
        "current_foundation_contract_unambiguous": passed,
        "model_rebuild_authorized": bool(passed and manifest.get("model_rebuild_authorized") is True),
        "purchase_recommendations_authorized": False,
        "status": (
            "PASS_COLLECTOR_V1_CURRENT_FOUNDATION_CONTRACT_DISCOVERY"
            if passed
            else "BLOCKED_COLLECTOR_V1_CURRENT_FOUNDATION_CONTRACT_DISCOVERY"
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "collector_v1_current_foundation_contract_audit_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "collector_v1_current_foundation_authority_schemas.json").write_text(
        json.dumps(authorities, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "collector_v1_current_foundation_execution_inventory.json").write_text(
        json.dumps(repository_matches, indent=2), encoding="utf-8"
    )

    print(json.dumps({
        "status": summary["status"],
        "source_snapshot_id": SNAPSHOT_ID,
        "common_complete_unique_product_keys": common_keys,
        "authority_row_counts": {name: item["row_count"] for name, item in authorities.items()},
        "governance_record_candidates": [item["path"] for item in governance_matches],
        "downstream_producer_candidates": [item["path"] for item in producer_candidates],
        "critical_failures": critical_failures,
        "model_rebuild_authorized": summary["model_rebuild_authorized"],
        "purchase_recommendations_authorized": False,
        "evidence_directory": str(OUT_DIR.relative_to(ROOT)),
    }, indent=2))
    return 0 if passed or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
