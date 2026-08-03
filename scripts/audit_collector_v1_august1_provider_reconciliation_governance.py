from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_august1_provider_package_reconciliation_contract_v1.json"
SCRIPT = ROOT / "scripts/reconcile_collector_v1_august1_provider_package.py"
SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
OPERATING_DATE = "2026-08-01"
BUNDLE_SHA = "7688afbd6dfb4483c0a316dad6a2a05458944434a91a3f714568e5f4a10c7890"
PRODUCT_COUNT = 50


def main() -> int:
    failures: list[str] = []
    for path, label in ((CONTRACT, "CONTRACT"), (SCRIPT, "SCRIPT")):
        if not path.is_file():
            failures.append(f"{label}_MISSING")
    if failures:
        print(json.dumps({"status": "FAIL_AUGUST1_PROVIDER_RECONCILIATION_GOVERNANCE", "failures": failures}, indent=2))
        return 2

    contract_text = CONTRACT.read_text(encoding="utf-8")
    script_text = SCRIPT.read_text(encoding="utf-8")
    required_script_tokens = (
        SNAPSHOT_ID,
        OPERATING_DATE,
        BUNDLE_SHA,
        str(PRODUCT_COUNT),
        'SNAPSHOT_MANIFEST = ROOT / "data/governance/permanence/snapshots/',
        '"snapshot_manifest_only_discovery": True',
        '"historical_source_reconstruction_authorized": False',
        '"historical_observation_ledger_build_authorized": False',
        '"model_tournament_authorized": False',
        '"purchase_recommendations_authorized": False',
    )
    for token in required_script_tokens:
        if token not in script_text:
            failures.append(f"SCRIPT_REQUIRED_TOKEN_MISSING:{token}")

    prohibited_script_tokens = (
        "FROZEN_MANIFEST",
        "rglob(",
        ".glob(",
        "datetime.now",
        '"historical_source_reconstruction_authorized": True',
        '"historical_observation_ledger_build_authorized": True',
        '"model_tournament_authorized": True',
        '"purchase_recommendations_authorized": True',
    )
    for token in prohibited_script_tokens:
        if token in script_text:
            failures.append(f"SCRIPT_PROHIBITED_TOKEN_PRESENT:{token}")

    required_contract_tokens = (
        '"snapshot_manifest_is_only_discovery_authority": true',
        '"historical_rows_inside_august_1_artifact_allowed": true',
        '"older_uncertified_artifact_prohibited": true',
        '"broad_repository_scan_prohibited": true',
        '"reconstruction_requires_separate_certification": true',
        '"historical_source_reconstruction_authorized": false',
        '"historical_observation_ledger_build_authorized": false',
        '"model_tournament_authorized": false',
        '"purchase_recommendations_authorized": false',
    )
    for token in required_contract_tokens:
        if token not in contract_text:
            failures.append(f"CONTRACT_REQUIRED_TOKEN_MISSING:{token}")

    status = "PASS_COLLECTOR_AUGUST1_PROVIDER_RECONCILIATION_GOVERNANCE" if not failures else "FAIL_COLLECTOR_AUGUST1_PROVIDER_RECONCILIATION_GOVERNANCE"
    print(json.dumps({
        "status": status,
        "governing_snapshot_id": SNAPSHOT_ID,
        "governing_operating_date": OPERATING_DATE,
        "governing_product_count": PRODUCT_COUNT,
        "failure_count": len(failures),
        "failures": failures,
        "historical_source_reconstruction_authorized": False,
        "historical_observation_ledger_build_authorized": False,
        "model_tournament_authorized": False,
        "purchase_recommendations_authorized": False,
    }, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
