from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_CODE_REGISTRY = ROOT / "config/mtg/standards/mtg_active_code_registry_v1.json"
EVIDENCE_SOURCE_MAP = ROOT / "config/mtg/evidence/collector_evidence_source_map_v1.json"
CURRENT_DATA_AUTHORITY = ROOT / "config/mtg/governance/collector_current_data_authority_v1.json"
PURCHASE_AUTHORITY_STATE = ROOT / "data/governance/permanence/certification/collector_v1_purchase_authorization_state.json"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_current_data_authority_gate"

DOWNSTREAM_SCRIPTS = [
    "scripts/run_collector_v1_current_product_application_foundation_v2.py",
    "scripts/run_collector_v1_product_level_forecast_ranking_tournament.py",
    "scripts/run_collector_v1_final_purchase_adequacy_tournament_v2.py",
]


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    registry = load_json(ACTIVE_CODE_REGISTRY)
    source_map = load_json(EVIDENCE_SOURCE_MAP)
    authority = load_json(CURRENT_DATA_AUTHORITY)
    purchase_state = load_json(PURCHASE_AUTHORITY_STATE)

    active_scripts = set(registry.get("authoritative_scripts", []))
    primary_source = source_map.get("primary_source", {})
    source_rules = source_map.get("rules", {})
    required = authority.get("required_authority_before_activation", {})
    current_authorization = authority.get("current_authorization", {})

    downstream_registration = {
        script: script in active_scripts for script in DOWNSTREAM_SCRIPTS
    }

    checks = {
        "active_code_registry_is_active": registry.get("status") == "ACTIVE_BASELINE",
        "current_data_authority_exists": bool(authority),
        "current_data_authority_is_activated": authority.get("status") == "ACTIVE_AUTHORITATIVE_SOURCE",
        "approved_market_provider_registered": bool(required.get("approved_market_provider")),
        "approved_adapter_registered": bool(required.get("approved_adapter_path")),
        "approved_execution_command_registered": bool(required.get("approved_execution_command")),
        "raw_snapshot_path_registered": bool(required.get("approved_raw_snapshot_path_pattern")),
        "normalized_price_authority_registered": bool(required.get("approved_normalized_price_authority_path_pattern")),
        "listing_authority_registered": bool(required.get("approved_listing_authority_path_pattern")),
        "documented_primary_source_is_authoritative": primary_source.get("source_status") == "ACTIVE_AUTHORITATIVE_SOURCE",
        "source_map_allows_purchase_recommendations": source_rules.get("purchase_recommendation_authorized") is True,
        "all_downstream_scripts_registered": all(downstream_registration.values()),
        "purchase_authority_not_suspended": purchase_state.get("purchase_recommendations_authorized") is True,
        "authority_allows_snapshot_capture": current_authorization.get("fresh_snapshot_capture_authorized") is True,
        "authority_allows_model_rebuild": all(
            current_authorization.get(key) is True
            for key in [
                "current_state_feature_build_authorized",
                "forecast_rebuild_authorized",
                "ranking_rebuild_authorized",
            ]
        ),
    }

    critical_failures = [name for name, passed in checks.items() if not passed]
    authority_activated = not critical_failures

    summary = {
        "block_name": "Collector V1 Current Data Authority Gate",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "governing_registry_status": registry.get("status"),
        "current_data_authority_status": authority.get("status"),
        "documented_primary_source": primary_source,
        "downstream_script_registration": downstream_registration,
        "checks": checks,
        "critical_failures": critical_failures,
        "current_data_authority_activated": authority_activated,
        "fresh_snapshot_capture_authorized": authority_activated,
        "model_rebuild_authorized": authority_activated,
        "purchase_recommendations_authorized": False,
        "next_authorized_action": (
            "EXECUTE_APPROVED_CURRENT_MARKET_SNAPSHOT"
            if authority_activated
            else "APPROVE_AND_REGISTER_EXECUTABLE_PRICE_ADAPTER"
        ),
        "status": (
            "PASS_COLLECTOR_V1_CURRENT_DATA_AUTHORITY_GATE"
            if authority_activated
            else "BLOCKED_COLLECTOR_V1_CURRENT_DATA_AUTHORITY_GATE"
        ),
    }

    output_path = OUT_DIR / "collector_v1_current_data_authority_gate_summary.json"
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))

    return 0 if (authority_activated or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
