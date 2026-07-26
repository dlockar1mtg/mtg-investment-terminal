from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "uip-domain-opportunity-v1"
DEPLOYABLE_SIGNALS = {"STRONG_BUY", "BUY"}
SIGNAL_BONUS = {"STRONG_BUY": 30.0, "BUY": 20.0, "WATCH": 5.0, "HOLD": 0.0, "AVOID": -20.0}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _number(value: object, default: float = 0.0) -> float:
    try:
        text = str(value or "").replace("$", "").replace(",", "").strip()
        return float(text) if text else default
    except ValueError:
        return default


def _holdings(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        product_id = str(row.get("investment_product_id") or "").strip()
        quantity = _number(row.get("quantity"))
        if not product_id or quantity <= 0:
            continue
        output.append({
            "investment_product_id": product_id,
            "quantity": quantity,
            "acquisition_cost_total": round(_number(row.get("acquisition_cost_total")), 2),
            "acquisition_date": str(row.get("acquisition_date") or ""),
            "notes": str(row.get("notes") or ""),
        })
    return output


def build_mtg_uip_export(
    decisions_path: Path,
    purchase_plan_path: Path,
    purchase_summary_path: Path,
    holdings_path: Path,
    carry_forward_path: Path | None = None,
) -> dict[str, Any]:
    decisions = _read_csv(decisions_path)
    plan_rows = _read_csv(purchase_plan_path)
    plan_by_tcg = {
        str(row.get("tcgplayer_product_id") or "").strip(): row
        for row in plan_rows
        if str(row.get("tcgplayer_product_id") or "").strip()
    }
    purchase_summary: dict[str, Any] = {}
    if purchase_summary_path.is_file():
        purchase_summary = json.loads(purchase_summary_path.read_text(encoding="utf-8"))

    carry_forward = 0.0
    if carry_forward_path and carry_forward_path.is_file():
        payload = json.loads(carry_forward_path.read_text(encoding="utf-8"))
        carry_forward = _number(payload.get("available_carry_forward"))

    opportunities: list[dict[str, Any]] = []
    for row in decisions:
        tcg_id = str(row.get("tcgplayer_product_id") or "").strip()
        if not tcg_id:
            continue
        signal = str(row.get("signal") or "").strip().upper()
        unit_price = _number(row.get("consolidated_market_price"))
        deal_score = _number(row.get("deal_score"))
        allocation_score = max(0.0, min(100.0, deal_score + SIGNAL_BONUS.get(signal, 0.0)))
        plan = plan_by_tcg.get(tcg_id, {})
        max_units = 2 if signal in DEPLOYABLE_SIGNALS and unit_price > 0 else 0
        opportunities.append({
            "opportunity_id": f"MTG:{tcg_id}",
            "domain": "mtg",
            "asset_class": "collectibles",
            "asset_id": tcg_id,
            "investment_product_id": str(plan.get("investment_product_id") or ""),
            "name": str(row.get("product_name") or tcg_id),
            "signal": signal,
            "eligible_for_new_capital": signal in DEPLOYABLE_SIGNALS and unit_price > 0,
            "allocation_score": round(allocation_score, 2),
            "confidence_score": round(min(100.0, (_number(row.get("data_quality_score")) + _number(row.get("liquidity_score"))) / 2.0), 2),
            "unit_price": round(unit_price, 2),
            "minimum_allocation": round(unit_price, 2) if max_units else 0.0,
            "allocation_increment": round(unit_price, 2) if max_units else 0.0,
            "maximum_units": max_units,
            "maximum_allocation": round(unit_price * max_units, 2),
            "whole_units_required": True,
            "expected_upside_pct": round(_number(row.get("expected_upside_pct")), 2),
            "probability_of_loss": round(_number(row.get("prob_loss")), 4),
            "source_count": int(_number(row.get("source_count"))),
            "policy_version": str(row.get("policy_version") or ""),
            "reason_codes": [code for code in str(row.get("decision_reason_codes") or "").split("|") if code],
        })

    status = "PASS" if opportunities and purchase_summary.get("status") in {"PASS", "NO_ACTION"} else "INCOMPLETE"
    return {
        "schema_version": SCHEMA_VERSION,
        "domain": "mtg",
        "domain_status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "allocation_authority": "UIP",
        "scheduling_authority": "UIP",
        "domain_self_allocation_disabled": True,
        "opportunity_count": len(opportunities),
        "deployable_opportunity_count": sum(bool(row["eligible_for_new_capital"]) for row in opportunities),
        "opportunities": opportunities,
        "holdings": _holdings(_read_csv(holdings_path)),
        "holdings_file_found": holdings_path.is_file(),
        "assigned_carry_forward": round(carry_forward, 2),
        "latest_domain_plan": {
            "status": purchase_summary.get("status", "NOT_AVAILABLE"),
            "planned_spend": _number(purchase_summary.get("planned_spend")),
            "unspent_capital": _number(purchase_summary.get("unspent_capital")),
            "policy_version": purchase_summary.get("policy_version", ""),
        },
        "reason_codes": ["MTG_UIP_DOMAIN_EXPORT_COMPLETED"] if status == "PASS" else ["MTG_UIP_DOMAIN_EXPORT_INCOMPLETE"],
    }


def write_mtg_uip_export(output_path: Path, **kwargs: Any) -> dict[str, Any]:
    payload = build_mtg_uip_export(**kwargs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
