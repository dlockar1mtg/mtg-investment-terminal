"""Reconcile current Collector eBay shadow listings with the certified production matcher.

This block is offline-only: it performs no network calls and consumes zero eBay quota.
It recovers prior certification/migration evidence, replays current shadow listings through
precision-v3-universal, compares decisions, and emits a permanent authority matrix.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from terminal2.market_sources.ebay_matching import CanonicalProduct
from terminal2.market_sources.ebay_precision_production import MATCHER_VERSION
from terminal2.market_sources.ebay_precision_v3 import identity_match_listing

ROOT = Path(__file__).resolve().parents[1]
SHADOW = ROOT / "data/governance/permanence/certification/collector_ebay_supply_collection/collector_ebay_listing_observations_shadow.csv"
AUTHORITY = ROOT / "data/governance/permanence/certification/collector_official_release_date_authority/collector_official_release_date_authority.csv"
CONTRACTS = ROOT / "data/governance/permanence/certification/collector_ebay_supply_contracts/collector_ebay_search_contracts.csv"
PRIOR_CERT = ROOT / "data/validation/phase_10/ebay_matching/collector_booster_ebay_certification.json"
MIGRATION_ROOT = ROOT / "data/operations/ebay_full_universe_migration"
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_authority_reconciliation"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Offline Collector eBay authority reconciliation")
    p.add_argument("--shadow", type=Path, default=SHADOW)
    p.add_argument("--authority", type=Path, default=AUTHORITY)
    p.add_argument("--contracts", type=Path, default=CONTRACTS)
    p.add_argument("--prior-certification", type=Path, default=PRIOR_CERT)
    p.add_argument("--migration-root", type=Path, default=MIGRATION_ROOT)
    p.add_argument("--output-dir", type=Path, default=OUT)
    p.add_argument("--strict", action="store_true")
    return p


def norm_id(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def text(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def number(value: object) -> float | None:
    try:
        if pd.isna(value) or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {"value": value}
    except Exception as exc:
        return {"_read_error": f"{type(exc).__name__}: {exc}"}


def latest_migration_summary(root: Path) -> tuple[Path | None, dict[str, Any]]:
    matches = sorted(root.glob("migration_*/ebay_full_universe_migration_summary.json")) if root.is_dir() else []
    if not matches:
        return None, {}
    path = matches[-1]
    return path, load_json(path)


def build_product(row: pd.Series, contract: pd.Series | None) -> CanonicalProduct:
    pid = norm_id(row.get("tcgplayer_product_id", ""))
    name = text(row.get("box_name", ""))
    query = text(contract.get("search_query", "")) if contract is not None else f'Magic The Gathering "{name}" sealed'
    return CanonicalProduct(
        canonical_product_id=f"TCGPLAYER:{pid}",
        canonical_product_name=name,
        canonical_set_name=name.replace(" Collector Booster Display", ""),
        product_class="COLLECTOR_BOOSTER_BOX",
        tcgplayer_product_id=pid,
        release_date=text(row.get("release_date", "")),
        ebay_query=query,
    )


def item_from_shadow(row: pd.Series) -> dict[str, object]:
    price = number(row.get("price_value"))
    delivered = number(row.get("delivered_price_estimate"))
    shipping = None if price is None or delivered is None else max(0.0, delivered - price)
    buying_raw = text(row.get("buying_options_json", ""))
    try:
        buying = json.loads(buying_raw) if buying_raw else []
    except json.JSONDecodeError:
        buying = [buying_raw] if buying_raw else []
    return {
        "itemId": text(row.get("item_id", "")),
        "title": text(row.get("title", "")),
        "itemWebUrl": text(row.get("item_web_url", row.get("item_url", ""))),
        "price": {"value": price, "currency": text(row.get("price_currency", "USD"))},
        "shippingOptions": [] if shipping is None else [{"shippingCost": {"value": shipping, "currency": text(row.get("price_currency", "USD"))}}],
        "seller": {"username": text(row.get("seller_pseudonym_sha256", ""))},
        "buyingOptions": buying,
        "condition": text(row.get("condition", "")),
    }


def decision_map(value: object) -> str:
    raw = text(value).upper()
    return {"ACCEPT": "ACCEPTED", "QUARANTINE": "REVIEW", "REJECT": "REJECTED"}.get(raw, raw)


def main() -> int:
    args = parser().parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc)

    required = [args.shadow, args.authority, args.contracts]
    missing = [str(p) for p in required if not p.resolve().is_file()]
    if missing:
        summary = {
            "block_name": "Collector eBay Authority Reconciliation",
            "block_version": "1.0.0",
            "generated_at": generated.isoformat(),
            "offline_only": True,
            "quota_calls": 0,
            "missing_required_inputs": missing,
            "status": "REQUIRED_INPUTS_MISSING",
        }
        (out / "collector_ebay_authority_reconciliation_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1 if args.strict else 0

    shadow = pd.read_csv(args.shadow.resolve(), dtype=str, encoding="utf-8-sig").fillna("")
    authority = pd.read_csv(args.authority.resolve(), dtype=str, encoding="utf-8-sig").fillna("")
    contracts = pd.read_csv(args.contracts.resolve(), dtype=str, encoding="utf-8-sig").fillna("")
    for frame in (shadow, authority, contracts):
        frame["tcgplayer_product_id"] = frame["tcgplayer_product_id"].map(norm_id)

    auth_by_id = {r["tcgplayer_product_id"]: r for _, r in authority.iterrows()}
    contract_by_id = {r["tcgplayer_product_id"]: r for _, r in contracts.iterrows()}

    replay_rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for index, row in shadow.iterrows():
        pid = norm_id(row.get("tcgplayer_product_id", ""))
        auth = auth_by_id.get(pid)
        if auth is None:
            failures.append({"row_index": index, "tcgplayer_product_id": pid, "item_id": text(row.get("item_id")), "error": "GOVERNED_PRODUCT_NOT_FOUND"})
            continue
        product = build_product(auth, contract_by_id.get(pid))
        try:
            result = identity_match_listing(product, item_from_shadow(row), text(row.get("retrieval_id", "offline-replay")), text(row.get("observed_at", generated.isoformat())))
            old = decision_map(row.get("listing_decision", ""))
            new = result.match_state.upper()
            replay_rows.append({
                **asdict(result),
                "tcgplayer_product_id": pid,
                "governed_box_name": text(row.get("governed_box_name", auth.get("box_name", ""))),
                "shadow_decision": old,
                "shadow_reason": text(row.get("listing_decision_reason", "")),
                "production_decision": new,
                "production_reason_codes": result.exclusion_reasons,
                "decision_agreement": old == new,
                "classification_transition": f"{old or 'BLANK'}->{new or 'BLANK'}",
                "manual_review_required": new == "REVIEW" or old != new,
                "matcher_version": MATCHER_VERSION,
            })
        except Exception as exc:
            failures.append({"row_index": index, "tcgplayer_product_id": pid, "item_id": text(row.get("item_id")), "error": f"{type(exc).__name__}: {exc}"})

    replay = pd.DataFrame(replay_rows)
    failure_frame = pd.DataFrame(failures)
    replay.to_csv(out / "collector_ebay_shadow_reclassified.csv", index=False)
    failure_frame.to_csv(out / "collector_ebay_shadow_replay_failures.csv", index=False)

    if not replay.empty:
        changes = replay[~replay["decision_agreement"].astype(bool)].copy()
        reasons = replay.groupby(["production_decision", "production_reason_codes"], dropna=False).size().reset_index(name="listing_count")
        products = replay.groupby(["tcgplayer_product_id", "governed_box_name", "production_decision"], dropna=False).size().reset_index(name="listing_count")
        transitions = replay.groupby("classification_transition", dropna=False).size().reset_index(name="listing_count")
    else:
        changes = replay.copy()
        reasons = pd.DataFrame(columns=["production_decision", "production_reason_codes", "listing_count"])
        products = pd.DataFrame(columns=["tcgplayer_product_id", "governed_box_name", "production_decision", "listing_count"])
        transitions = pd.DataFrame(columns=["classification_transition", "listing_count"])
    changes.to_csv(out / "collector_ebay_shadow_classification_changes.csv", index=False)
    reasons.to_csv(out / "collector_ebay_shadow_reason_summary.csv", index=False)
    products.to_csv(out / "collector_ebay_shadow_product_summary.csv", index=False)
    transitions.to_csv(out / "collector_ebay_shadow_transition_summary.csv", index=False)

    prior = load_json(args.prior_certification.resolve())
    migration_path, migration = latest_migration_summary(args.migration_root.resolve())
    authority_summary = {
        "production_matcher_version": MATCHER_VERSION,
        "production_matcher_entrypoint": "terminal2.market_sources.ebay_precision_v3.identity_match_listing",
        "production_policy": "DOWNGRADE_ONLY_UNIVERSAL",
        "prior_collector_certification_path": str(args.prior_certification.resolve().relative_to(ROOT)) if args.prior_certification.resolve().is_file() else "",
        "prior_collector_certification_present": args.prior_certification.resolve().is_file(),
        "prior_collector_certification": prior,
        "latest_migration_summary_path": str(migration_path.relative_to(ROOT)) if migration_path else "",
        "latest_migration_summary_present": migration_path is not None,
        "latest_migration_summary": migration,
    }
    (out / "collector_ebay_existing_authority_summary.json").write_text(json.dumps(authority_summary, indent=2, default=str) + "\n", encoding="utf-8")

    matrix = pd.DataFrame([
        {"component": "terminal2/market_sources/ebay_precision_production.py", "role": "production matcher selector", "decision": "AUTHORITATIVE_REUSE", "rationale": f"Explicitly promotes {MATCHER_VERSION}."},
        {"component": "terminal2/market_sources/ebay_precision_v3.py", "role": "listing identity classification", "decision": "AUTHORITATIVE_REUSE", "rationale": "Certified precision-v2 plus downgrade-only universal policy."},
        {"component": "terminal2/market_sources/ebay_product_identity.py", "role": "canonical identity diagnostics", "decision": "AUTHORITATIVE_REUSE", "rationale": "Supports product-form and identity reason codes."},
        {"component": "terminal2/market_sources/ebay_universal_classification.py", "role": "universal downgrade policy", "decision": "AUTHORITATIVE_REUSE", "rationale": "Fail-closed language, form, condition and completeness controls."},
        {"component": "scripts/replay_ebay_matching_offline.py", "role": "historical regression replay", "decision": "PRESERVE_FOR_OFFLINE_REPLAY", "rationale": "Zero-quota regression evidence."},
        {"component": "scripts/certify_collector_booster_ebay_batches.py", "role": "Collector certification", "decision": "AUTHORITATIVE_REUSE", "rationale": "Existing Collector-specific certification gate."},
        {"component": "scripts/run_collector_ebay_supply_collection.py", "role": "current Browse API acquisition and enrichment", "decision": "ADAPT_TO_COLLECTOR_SUPPLY", "rationale": "Keep OAuth, pagination, payload vaulting, quantity and seller enrichment; remove simple title decisions as authority."},
        {"component": "build_collector_ebay_search_contracts.py", "role": "governed query contracts", "decision": "ADAPT_TO_COLLECTOR_SUPPLY", "rationale": "Use as current universe query input, subject to existing query-planning authority."},
        {"component": "simple classify_title in current shadow collector", "role": "temporary title classification", "decision": "SUPERSEDED", "rationale": f"Replaced by {MATCHER_VERSION}."},
        {"component": "July 22-28 Phase 10 match outputs", "role": "historical certification evidence", "decision": "HISTORICAL_EVIDENCE", "rationale": "Retain for overlap, regression and transition analysis."},
    ])
    matrix.to_csv(out / "collector_ebay_component_decision_matrix.csv", index=False)

    replayed = len(replay)
    changed = len(changes)
    reviews = int((replay["production_decision"] == "REVIEW").sum()) if not replay.empty else 0
    accepted = int((replay["production_decision"] == "ACCEPTED").sum()) if not replay.empty else 0
    rejected = int((replay["production_decision"] == "REJECTED").sum()) if not replay.empty else 0
    complete = replayed == len(shadow) and len(failures) == 0 and replayed > 0
    prior_evidence_present = args.prior_certification.resolve().is_file() and migration_path is not None
    status = "PASS_COLLECTOR_EBAY_AUTHORITY_RECONCILIATION" if complete and prior_evidence_present else "REVIEW_REQUIRED"

    summary = {
        "block_name": "Collector eBay Authority Reconciliation",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "offline_only": True,
        "quota_calls": 0,
        "shadow_rows_received": len(shadow),
        "shadow_rows_replayed": replayed,
        "replay_failures": len(failures),
        "production_matcher_version": MATCHER_VERSION,
        "production_accepted": accepted,
        "production_review": reviews,
        "production_rejected": rejected,
        "classification_changes": changed,
        "prior_collector_certification_present": args.prior_certification.resolve().is_file(),
        "latest_full_universe_migration_present": migration_path is not None,
        "reconciliation_complete": complete,
        "authority_designated": complete and prior_evidence_present,
        "acquisition_authority": "CURRENT_BROWSE_API_ADAPTER_PLUS_EXISTING_QUERY_PLANNING",
        "matching_authority": MATCHER_VERSION,
        "certification_authority": "PHASE_10_COLLECTOR_CERTIFICATION_PLUS_OFFLINE_REPLAY",
        "raw_payload_authority": "IMMUTABLE_CONTENT_ADDRESSED_EBAY_VAULT",
        "quantity_enrichment_authority": "CURRENT_BROWSE_ITEM_DETAIL_ADAPTER",
        "daily_ledger_authority": "PENDING_NEXT_BLOCK",
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": status,
    }
    (out / "collector_ebay_authority_reconciliation_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if status.startswith("PASS_") else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
