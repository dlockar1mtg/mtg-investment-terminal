from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / "config/mtg/governance/collector_display_source_authority_v1.json"
OUT_DIR = ROOT / "data/governance/permanence/certification"
SUMMARY_PATH = OUT_DIR / "collector_fresh_source_readiness_summary.json"
RAW_TCGCSV = ROOT / "data/raw/tcgcsv"


def git_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", path], cwd=ROOT, capture_output=True, text=True
    )
    return result.returncode == 0


def newest(paths: list[Path]) -> str | None:
    existing = [path for path in paths if path.is_file()]
    if not existing:
        return None
    stamp = max(path.stat().st_mtime for path in existing)
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    failures: list[str] = []
    warnings: list[str] = []

    vault_ignored = git_ignored("data_vault/")
    permanence_ignored = git_ignored("data/governance/permanence/")
    if not vault_ignored:
        failures.append("data_vault_not_git_ignored")
    if not permanence_ignored:
        failures.append("permanence_runtime_not_git_ignored")

    tcg_public_key = bool(os.getenv("TCGPLAYER_PUBLIC_KEY"))
    tcg_private_key = bool(os.getenv("TCGPLAYER_PRIVATE_KEY"))
    tcg_bearer_token = bool(os.getenv("TCGPLAYER_BEARER_TOKEN"))
    tcgplayer_authenticated_ready = tcg_bearer_token or (tcg_public_key and tcg_private_key)

    tcgcsv_scripts = [
        ROOT / "scripts/run_daily_tcgcsv_collection.py",
        ROOT / "collectors/tcgcsv_collector.py",
    ]
    tcgcsv_products = list(RAW_TCGCSV.glob("products_1_*.json"))
    tcgcsv_prices = list(RAW_TCGCSV.glob("prices_1_*.json"))
    tcgcsv_metadata = [RAW_TCGCSV / "categories.json", RAW_TCGCSV / "groups_category_1.json"]
    tcgcsv_public_ready = (
        all(path.is_file() for path in tcgcsv_scripts)
        and bool(tcgcsv_products)
        and bool(tcgcsv_prices)
        and all(path.is_file() for path in tcgcsv_metadata)
    )
    if not tcgcsv_public_ready:
        warnings.append("tcgcsv_public_route_not_ready")
    if not tcgplayer_authenticated_ready:
        warnings.append("tcgplayer_authenticated_route_not_configured")

    required_contract = cfg.get("collector_universe_contract", {})
    required_values = {
        "required_product_class": "COLLECTOR_BOOSTER",
        "required_packaging_type": "SEALED_DISPLAY",
        "required_language": "ENGLISH",
        "required_sealed_status": "FACTORY_SEALED",
        "required_condition": "NORMAL_RETAIL_CONDITION",
    }
    for key, expected in required_values.items():
        if required_contract.get(key) != expected:
            failures.append(f"eligibility_contract_mismatch:{key}")

    excluded = set(cfg.get("excluded_configurations", []))
    required_exclusions = {
        "SINGLE_PACK", "DISPLAY_CASE", "EMPTY_DISPLAY", "OPENED_DISPLAY",
        "DAMAGED_DISPLAY", "FOREIGN_LANGUAGE", "AMBIGUOUS_CONFIGURATION",
    }
    for item in sorted(required_exclusions - excluded):
        failures.append(f"missing_required_exclusion:{item}")

    authority_ids = {row.get("source_id") for row in cfg.get("source_authority", [])}
    for source_id in [
        "TCGPLAYER_CATALOG_API", "WIZARDS_OFFICIAL_PRODUCT_PAGES",
        "MTGJSON_SEALED_DATA", "EXISTING_PROJECT_HISTORY"
    ]:
        if source_id not in authority_ids:
            failures.append(f"missing_source_authority:{source_id}")

    if not cfg.get("fresh_pull_required_before_certification"):
        failures.append("fresh_pull_not_required_before_certification")
    if not cfg.get("cross_source_reconciliation_required"):
        failures.append("cross_source_reconciliation_not_required")
    if not cfg.get("raw_response_vaulting_required"):
        failures.append("raw_response_vaulting_not_required")

    if any(cfg.get(field) for field in [
        "forecasting_resume_authorized", "production_projection_authorized",
        "purchase_recommendation_authorized", "automatic_model_update_allowed",
        "technical_freeze_authorized", "uip_acceptance_authorized",
    ]):
        failures.append("authorization_gate_open")

    status = "PASS" if not failures else "FAIL"
    fresh_pull_status = "READY_VIA_TCGCSV_PUBLIC_ROUTE" if tcgcsv_public_ready and not failures else "NOT_READY"
    summary = {
        "audit_name": "Collector Fresh Source Readiness Audit",
        "audit_version": "1.1.0",
        "git_boundary": {
            "data_vault_ignored": vault_ignored,
            "permanence_runtime_ignored": permanence_ignored,
        },
        "source_readiness": {
            "fresh_pull_status": fresh_pull_status,
            "tcgcsv_public_route_ready": tcgcsv_public_ready,
            "tcgcsv_product_file_count": len(tcgcsv_products),
            "tcgcsv_price_file_count": len(tcgcsv_prices),
            "tcgcsv_newest_product_utc": newest(tcgcsv_products),
            "tcgcsv_newest_price_utc": newest(tcgcsv_prices),
            "tcgplayer_authenticated_route_ready": tcgplayer_authenticated_ready,
            "tcgplayer_bearer_token_present": tcg_bearer_token,
            "tcgplayer_public_key_present": tcg_public_key,
            "tcgplayer_private_key_present": tcg_private_key,
        },
        "fresh_pull_required_before_certification": cfg.get("fresh_pull_required_before_certification"),
        "cross_source_reconciliation_required": cfg.get("cross_source_reconciliation_required"),
        "raw_response_vaulting_required": cfg.get("raw_response_vaulting_required"),
        "forecasting_resume_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
        "warning_count": len(warnings),
        "warnings": warnings,
        "status": status,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.strict and (failures or not tcgcsv_public_ready):
        return 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
