from __future__ import annotations

import csv
import json
from pathlib import Path

from terminal2.integration.uip_export import build_mtg_uip_export
from terminal2.portfolio.operations import record_purchase, update_carry_forward


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_purchase_recording_is_idempotent(tmp_path: Path) -> None:
    holdings = tmp_path / "holdings.csv"
    ledger = tmp_path / "ledger.csv"
    result = record_purchase(
        holdings,
        ledger,
        investment_product_id="INV-271509",
        quantity=1,
        unit_price=434.07,
        transaction_date="2026-07-26",
        transaction_id="TX-1",
    )
    duplicate = record_purchase(
        holdings,
        ledger,
        investment_product_id="INV-271509",
        quantity=1,
        unit_price=434.07,
        transaction_date="2026-07-26",
        transaction_id="TX-1",
    )
    assert result["status"] == "PASS"
    assert duplicate["status"] == "DUPLICATE_IGNORED"
    rows = list(csv.DictReader(holdings.open(encoding="utf-8")))
    assert rows[0]["quantity"] == "1.0"
    assert rows[0]["acquisition_cost_total"] == "434.07"


def test_carry_forward_uses_only_uip_assigned_capital(tmp_path: Path) -> None:
    path = tmp_path / "carry.json"
    payload = update_carry_forward(
        path,
        uip_allocation=600,
        actual_spend=434.07,
        prior_carry_forward=100,
        period="2026-08",
    )
    assert payload["available_carry_forward"] == 265.93
    assert payload["allocation_authority"] == "UIP"


def test_uip_export_disables_domain_self_allocation(tmp_path: Path) -> None:
    decisions = tmp_path / "decisions.csv"
    plan = tmp_path / "plan.csv"
    summary = tmp_path / "summary.json"
    holdings = tmp_path / "holdings.csv"
    _write_csv(decisions, [{
        "policy_version": "10.14.0",
        "tcgplayer_product_id": "271509",
        "product_name": "Double Masters 2022",
        "signal": "STRONG_BUY",
        "deal_score": 41.22,
        "consolidated_market_price": 434.07,
        "expected_upside_pct": 37.23,
        "prob_loss": 0.107,
        "source_count": 2,
        "data_quality_score": 90,
        "liquidity_score": 80,
        "decision_reason_codes": "CROSS_SOURCE_CONFIRMED",
    }])
    _write_csv(plan, [{
        "tcgplayer_product_id": "271509",
        "investment_product_id": "INV-271509",
    }])
    summary.write_text(json.dumps({"status": "PASS", "planned_spend": 434.07, "unspent_capital": 165.93, "policy_version": "10.15.0"}), encoding="utf-8")
    payload = build_mtg_uip_export(decisions, plan, summary, holdings)
    assert payload["domain_status"] == "PASS"
    assert payload["allocation_authority"] == "UIP"
    assert payload["scheduling_authority"] == "UIP"
    assert payload["domain_self_allocation_disabled"] is True
    opportunity = payload["opportunities"][0]
    assert opportunity["minimum_allocation"] == 434.07
    assert opportunity["maximum_units"] == 2
    assert opportunity["allocation_score"] > 70
