from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_early_peer_feature_recovery"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()

    summary_path = OUT_DIR / "collector_v1_early_peer_feature_recovery_summary.json"
    required = [
        summary_path,
        OUT_DIR / "collector_v1_release_age_cutoffs_with_recovered_peer_features.csv",
        OUT_DIR / "collector_v1_recovered_peer_lineage.csv",
        OUT_DIR / "collector_v1_recovered_peer_product_diagnostics.csv",
    ]
    failures = []
    for path in required:
        if not path.exists():
            failures.append({"check": f"required output exists: {path.name}", "severity": "CRITICAL"})

    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    checks = {
        "recovery ready": summary.get("peer_feature_recovery_ready") is True,
        "sources not mutated": summary.get("certified_sources_mutated") is False,
        "all cutoff rows preserved": int(summary.get("cutoff_rows", 0)) == 280,
        "products profiled": int(summary.get("products_profiled", 0)) == 40,
        "lineage present": int(summary.get("peer_lineage_rows_with_realized_returns", 0)) > 0,
        "fixed source paths recorded": len(summary.get("source_paths", {})) == 3,
        "production remains blocked": summary.get("production_forecasting_authorized") is False,
        "purchase remains blocked": summary.get("purchase_recommendations_authorized") is False,
    }
    for name, passed in checks.items():
        if not passed:
            failures.append({"check": name, "severity": "CRITICAL"})

    result = {
        "block_name": "Collector V1 Early Peer Feature Recovery Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks) + len(required),
        "critical_failures": failures,
        "early_peer_feature_recovery_certified": not failures,
        "early_tournament_rebuild_authorized": bool(not failures and summary.get("promotion_scale_reached")),
        "model_promotion_authorized": False,
        "long_horizon_simulation_authorized": False,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Rebuild early-opportunity tournament with recovered peer features if promotion scale is reached; otherwise adjudicate remaining source gap.",
        "status": "PASS_COLLECTOR_V1_EARLY_PEER_FEATURE_RECOVERY_CERTIFIED" if not failures else "FAIL_COLLECTOR_V1_EARLY_PEER_FEATURE_RECOVERY_CERTIFICATION",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "collector_v1_early_peer_feature_recovery_certification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
