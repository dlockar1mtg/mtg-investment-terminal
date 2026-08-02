from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_august1_historical_reconstruction_scope_contract_v1.json"
SCRIPT = ROOT / "scripts/certify_collector_v1_august1_historical_reconstruction_scope.py"
SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
OPERATING_DATE = "2026-08-01"
PRODUCT_COUNT = 50


def main() -> int:
    failures: list[str] = []
    for path in (CONTRACT, SCRIPT):
        if not path.is_file():
            failures.append(f"REQUIRED_ARTIFACT_MISSING:{path.relative_to(ROOT)}")
    if failures:
        print(json.dumps({"status": "FAIL_COLLECTOR_AUGUST1_HISTORICAL_RECONSTRUCTION_SCOPE_GOVERNANCE", "failures": failures}, indent=2))
        return 2

    contract = CONTRACT.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")
    required = [SNAPSHOT_ID, OPERATING_DATE, str(PRODUCT_COUNT), "older_output_artifact_as_input_prohibited", "current_snapshot_as_history_prohibited", "ebay_listing_price_cannot_become_authoritative_market_price"]
    for token in required:
        if token not in contract + script:
            failures.append(f"REQUIRED_CONTROL_MISSING:{token}")
    prohibited = ["rglob(", "glob(", "FROZEN_MANIFEST", '"historical_observation_ledger_build_authorized": True', '"model_tournament_authorized": True', '"purchase_recommendations_authorized": True']
    for token in prohibited:
        if token in script:
            failures.append(f"PROHIBITED_PATTERN:{token}")

    summary = {
        "status": "PASS_COLLECTOR_AUGUST1_HISTORICAL_RECONSTRUCTION_SCOPE_GOVERNANCE" if not failures else "FAIL_COLLECTOR_AUGUST1_HISTORICAL_RECONSTRUCTION_SCOPE_GOVERNANCE",
        "governing_snapshot_id": SNAPSHOT_ID,
        "governing_operating_date": OPERATING_DATE,
        "governing_product_count": PRODUCT_COUNT,
        "failure_count": len(failures),
        "failures": failures,
        "historical_observation_ledger_build_authorized": False,
        "model_tournament_authorized": False,
        "purchase_recommendations_authorized": False,
    }
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
