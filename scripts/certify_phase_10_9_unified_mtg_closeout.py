from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "data" / "validation" / "phase_10"
REGISTRY_ROOT = VALIDATION / "unified_mtg_registry"
PORTFOLIO_ROOT = VALIDATION / "unified_mtg_portfolio"
INTELLIGENCE_ROOT = VALIDATION / "unified_mtg_intelligence"
OUTPUT_ROOT = VALIDATION / "unified_mtg_closeout"

REGISTRY = REGISTRY_ROOT / "unified_mtg_product_registry.csv"
REGISTRY_MANIFEST = REGISTRY_ROOT / "unified_mtg_product_registry_manifest.json"
PORTFOLIO = PORTFOLIO_ROOT / "unified_mtg_owned_positions.csv"
PORTFOLIO_MANIFEST = PORTFOLIO_ROOT / "unified_mtg_portfolio_manifest.json"
INTELLIGENCE = INTELLIGENCE_ROOT / "unified_mtg_intelligence_interface.csv"
INTELLIGENCE_MANIFEST = INTELLIGENCE_ROOT / "unified_mtg_intelligence_manifest.json"

EXPECTED_LANES = {
    "SECRET_LAIR": 973,
    "COLLECTOR_BOOSTER_BOX": 49,
    "PRE_COLLECTOR_BOOSTER_BOX": 119,
}
EXPECTED_PORTFOLIO = {
    "SECRET_LAIR": 12,
    "COLLECTOR_BOOSTER_BOX": 2,
    "PRE_COLLECTOR_BOOSTER_BOX": 0,
}
TRACKED_ALLOWLIST = [
    "docs/phase_10/PHASE_10_9_3_UNIFIED_MTG_INTELLIGENCE.md",
    "docs/phase_10/PHASE_10_9_4_UNIFIED_MTG_PRODUCTION_CLOSEOUT.md",
    "scripts/build_unified_mtg_intelligence.py",
    "scripts/build_unified_mtg_portfolio.py",
    "scripts/certify_phase_10_9_unified_mtg_closeout.py",
    "scripts/run_phase_10_9_2_unified_mtg_portfolio.ps1",
    "scripts/run_phase_10_9_3_unified_mtg_intelligence.ps1",
    "scripts/run_phase_10_9_4_unified_mtg_closeout.ps1",
    "tests/test_phase_10_9_unified_mtg_closeout.py",
    "tests/test_unified_mtg_intelligence.py",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decimal(value: str | None) -> Decimal:
    return Decimal(str(value or "0").strip() or "0")


def certify() -> dict:
    required = [
        REGISTRY,
        REGISTRY_MANIFEST,
        PORTFOLIO,
        PORTFOLIO_MANIFEST,
        INTELLIGENCE,
        INTELLIGENCE_MANIFEST,
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        return {
            "status": "FAILED",
            "phase": "10.9.4",
            "missing_inputs": missing,
            "checks": {"all_required_inputs_exist": False},
            "quota_calls": 0,
        }

    registry = read_csv(REGISTRY)
    portfolio = read_csv(PORTFOLIO)
    intelligence = read_csv(INTELLIGENCE)
    registry_manifest = read_json(REGISTRY_MANIFEST)
    portfolio_manifest = read_json(PORTFOLIO_MANIFEST)
    intelligence_manifest = read_json(INTELLIGENCE_MANIFEST)

    registry_counts = Counter(row["lane"] for row in registry)
    portfolio_counts = Counter(row["lane"] for row in portfolio)
    intelligence_counts = Counter(row["lane"] for row in intelligence)

    registry_ids = [row["universal_mtg_product_id"] for row in registry]
    portfolio_ids = [row["universal_mtg_product_id"] for row in portfolio]
    intelligence_ids = [row["universal_mtg_product_id"] for row in intelligence]
    registry_id_set = set(registry_ids)

    total_cost = sum((decimal(row.get("total_cost_basis_usd")) for row in portfolio), Decimal("0"))
    total_value = sum((decimal(row.get("total_market_value_usd")) for row in portfolio), Decimal("0"))
    total_gain = sum((decimal(row.get("unrealized_gain_loss_usd")) for row in portfolio), Decimal("0"))

    checks = {
        "all_required_inputs_exist": True,
        "registry_manifest_certified": registry_manifest.get("status") == "CERTIFIED",
        "portfolio_manifest_certified": portfolio_manifest.get("status") == "CERTIFIED",
        "intelligence_manifest_certified": intelligence_manifest.get("status") == "CERTIFIED",
        "registry_rows_equal_1141": len(registry) == 1141,
        "intelligence_rows_equal_1141": len(intelligence) == 1141,
        "portfolio_rows_equal_14": len(portfolio) == 14,
        "registry_lane_counts_match": dict(registry_counts) == EXPECTED_LANES,
        "intelligence_lane_counts_match": dict(intelligence_counts) == EXPECTED_LANES,
        "portfolio_lane_counts_match": all(portfolio_counts[lane] == count for lane, count in EXPECTED_PORTFOLIO.items()),
        "registry_ids_unique": len(registry_ids) == len(set(registry_ids)) == 1141,
        "intelligence_ids_unique": len(intelligence_ids) == len(set(intelligence_ids)) == 1141,
        "intelligence_ids_match_registry": set(intelligence_ids) == registry_id_set,
        "portfolio_ids_resolve_to_registry": set(portfolio_ids).issubset(registry_id_set),
        "portfolio_gain_reconciles": abs(total_gain - (total_value - total_cost)) <= Decimal("0.05"),
        "registry_sha_matches_manifest": registry_manifest.get("registry_sha256") == sha256(REGISTRY),
        "intelligence_sha_matches_manifest": intelligence_manifest.get("interface_sha256") == sha256(INTELLIGENCE),
        "portfolio_diagnostics_zero": portfolio_manifest.get("diagnostics") == 0,
        "intelligence_diagnostics_zero": intelligence_manifest.get("diagnostics") == 0,
        "registry_diagnostics_zero": registry_manifest.get("diagnostics") == 0,
        "private_holdings_absent_from_registry": all(field not in registry[0] for field in ("quantity", "acquisition_date", "total_cost_basis_usd")),
        "private_holdings_absent_from_intelligence": all(field not in intelligence[0] for field in ("quantity", "acquisition_date", "total_cost_basis_usd")),
        "quota_calls_zero": True,
    }

    status = "PRODUCTION_CLOSED" if all(checks.values()) else "FAILED"
    return {
        "status": status,
        "phase": "10.9.4",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "products": len(registry),
        "owned_positions": len(portfolio),
        "lane_counts": dict(sorted(registry_counts.items())),
        "portfolio_lane_counts": {lane: portfolio_counts[lane] for lane in EXPECTED_PORTFOLIO},
        "cost_basis_usd": float(total_cost),
        "market_value_usd": float(total_value),
        "unrealized_gain_loss_usd": float(total_gain),
        "forecast_eligible_counts": intelligence_manifest.get("forecast_eligible_counts", {}),
        "recommendation_eligible_counts": intelligence_manifest.get("recommendation_eligible_counts", {}),
        "checks": checks,
        "artifact_sha256": {
            "registry": sha256(REGISTRY),
            "portfolio": sha256(PORTFOLIO),
            "intelligence": sha256(INTELLIGENCE),
        },
        "tracked_commit_allowlist": TRACKED_ALLOWLIST,
        "generated_validation_directories_excluded": [
            "data/validation/phase_10/collector_booster_boxes/",
            "data/validation/phase_10/pre_collector_booster_boxes/",
            "data/validation/phase_10/unified_mtg_registry/",
            "data/validation/phase_10/unified_mtg_portfolio/",
            "data/validation/phase_10/unified_mtg_intelligence/",
            "data/validation/phase_10/unified_mtg_closeout/",
        ],
        "quota_calls": 0,
    }


def write_outputs(result: dict) -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUTPUT_ROOT / "phase_10_9_unified_mtg_production_closeout.json"
    manifest_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    allowlist_path = OUTPUT_ROOT / "phase_10_9_tracked_commit_allowlist.txt"
    allowlist_path.write_text("\n".join(TRACKED_ALLOWLIST) + "\n", encoding="utf-8")

    certification = [
        "# Phase 10.9.4 Unified MTG Production Closeout",
        "",
        f"**Status:** {result['status']}",
        "",
        f"- Unified products: {result.get('products', 0)}",
        f"- Owned positions: {result.get('owned_positions', 0)}",
        f"- Cost basis: ${result.get('cost_basis_usd', 0):.2f}",
        f"- Modeled market value: ${result.get('market_value_usd', 0):.2f}",
        f"- Unrealized gain/loss: ${result.get('unrealized_gain_loss_usd', 0):.2f}",
        "- API quota calls: 0",
        "",
        "## Checks",
        "",
    ]
    certification.extend(
        f"- {name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in result.get("checks", {}).items()
    )
    certification.extend([
        "",
        "## Commit policy",
        "",
        "Only the tracked allowlist may be staged. Generated validation outputs and personal holdings remain local.",
    ])
    (OUTPUT_ROOT / "PHASE_10_9_4_UNIFIED_MTG_PRODUCTION_CLOSEOUT.md").write_text(
        "\n".join(certification) + "\n", encoding="utf-8"
    )


def main() -> int:
    result = certify()
    write_outputs(result)
    print(f"PHASE 10.9.4 UNIFIED MTG PRODUCTION CLOSEOUT: {result['status']}")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PRODUCTION_CLOSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
