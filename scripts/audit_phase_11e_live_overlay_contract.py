from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.apply_mtg_live_uip_overlay import build_asset_aliases, identifiers, read_csv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    package = args.package.resolve()
    market = args.market_root.resolve()
    required = {
        "assets": package / "asset_master.csv",
        "forecasts": package / "forecasts.csv",
        "recommendations": package / "recommendations.csv",
        "risks": package / "risk_metrics.csv",
        "prices": market / "consolidated_marketplace_prices.csv",
        "decisions": market / "certified_marketplace_decisions.csv",
    }
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        payload = {
            "status": "FAILED",
            "reason_codes": ["PHASE_11E_REQUIRED_FILE_MISSING"],
            "missing_files": missing,
        }
    else:
        assets = read_csv(required["assets"])
        forecasts = read_csv(required["forecasts"])
        recommendations = read_csv(required["recommendations"])
        risks = read_csv(required["risks"])
        prices = read_csv(required["prices"])
        decisions = read_csv(required["decisions"])

        aliases = build_asset_aliases(assets)
        package_ids = {i for values in aliases.values() for i in values}
        price_ids = {i for row in prices for i in identifiers(row)}
        decision_ids = {i for row in decisions for i in identifiers(row)}
        asset_ids = {
            str(row.get("asset_id", "") or "").strip()
            for row in assets
            if str(row.get("asset_id", "") or "").strip()
        }

        orphan_counts = {}
        for name, rows in (
            ("forecasts", forecasts),
            ("recommendations", recommendations),
            ("risks", risks),
        ):
            row_asset_ids = {
                str(row.get("asset_id", "") or "").strip()
                for row in rows
                if str(row.get("asset_id", "") or "").strip()
            }
            orphan_counts[name] = len(row_asset_ids.difference(asset_ids))

        price_matches = sorted(price_ids.intersection(package_ids))
        decision_matches = sorted(decision_ids.intersection(package_ids))
        reasons = []
        if len(assets) != 1141:
            reasons.append("PHASE_11E_PACKAGE_PRODUCT_COUNT_NOT_1141")
        if not prices or not decisions:
            reasons.append("PHASE_11E_LIVE_SOURCE_ROWS_EMPTY")
        if not price_matches:
            reasons.append("PHASE_11E_PRICE_JOIN_ZERO")
        if not decision_matches:
            reasons.append("PHASE_11E_DECISION_JOIN_ZERO")
        if any(orphan_counts.values()):
            reasons.append("PHASE_11E_ORPHAN_UNIVERSAL_ROWS")

        payload = {
            "status": "PASS" if not reasons else "FAILED",
            "reason_codes": reasons,
            "counts": {
                "assets": len(assets),
                "forecasts": len(forecasts),
                "recommendations": len(recommendations),
                "risks": len(risks),
                "certified_prices": len(prices),
                "certified_decisions": len(decisions),
                "joinable_price_identifiers": len(price_matches),
                "joinable_decision_identifiers": len(decision_matches),
            },
            "orphan_asset_id_counts": orphan_counts,
            "sample_joinable_price_identifiers": price_matches[:10],
            "sample_joinable_decision_identifiers": decision_matches[:10],
            "sample_unmatched_price_identifiers": sorted(price_ids.difference(package_ids))[:10],
            "sample_unmatched_decision_identifiers": sorted(decision_ids.difference(package_ids))[:10],
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
