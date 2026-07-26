from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

HOLDINGS_FIELDS = ("investment_product_id", "quantity", "acquisition_cost_total", "acquisition_date", "notes")
TRANSACTION_FIELDS = (
    "transaction_id", "transaction_date", "investment_product_id", "transaction_type",
    "quantity", "unit_price", "total_amount", "source", "notes", "recorded_at_utc",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _number(value: object) -> float:
    try:
        return float(str(value or "").replace("$", "").replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def record_purchase(
    holdings_path: Path,
    ledger_path: Path,
    *,
    investment_product_id: str,
    quantity: float,
    unit_price: float,
    transaction_date: str | None = None,
    source: str = "MANUAL",
    notes: str = "",
    transaction_id: str | None = None,
) -> dict[str, Any]:
    product_id = investment_product_id.strip()
    if not product_id or quantity <= 0 or unit_price <= 0:
        raise ValueError("A product ID, positive quantity, and positive unit price are required")
    tx_date = transaction_date or date.today().isoformat()
    datetime.fromisoformat(tx_date)
    tx_id = transaction_id or f"MTG-{tx_date}-{product_id}-{quantity:g}-{unit_price:.2f}"

    ledger = _read_csv(ledger_path)
    if any(str(row.get("transaction_id") or "") == tx_id for row in ledger):
        return {"status": "DUPLICATE_IGNORED", "transaction_id": tx_id}

    holdings = _read_csv(holdings_path)
    by_id = {str(row.get("investment_product_id") or "").strip(): dict(row) for row in holdings if str(row.get("investment_product_id") or "").strip()}
    current = by_id.get(product_id, {
        "investment_product_id": product_id,
        "quantity": 0,
        "acquisition_cost_total": 0,
        "acquisition_date": tx_date,
        "notes": "",
    })
    current["quantity"] = round(_number(current.get("quantity")) + quantity, 4)
    current["acquisition_cost_total"] = round(_number(current.get("acquisition_cost_total")) + quantity * unit_price, 2)
    current["acquisition_date"] = min(str(current.get("acquisition_date") or tx_date), tx_date)
    existing_notes = str(current.get("notes") or "").strip()
    current["notes"] = " | ".join(part for part in (existing_notes, notes.strip()) if part)
    by_id[product_id] = current
    _write_csv(holdings_path, HOLDINGS_FIELDS, sorted(by_id.values(), key=lambda row: str(row["investment_product_id"])))

    ledger.append({
        "transaction_id": tx_id,
        "transaction_date": tx_date,
        "investment_product_id": product_id,
        "transaction_type": "PURCHASE",
        "quantity": round(quantity, 4),
        "unit_price": round(unit_price, 2),
        "total_amount": round(quantity * unit_price, 2),
        "source": source,
        "notes": notes,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    })
    _write_csv(ledger_path, TRANSACTION_FIELDS, ledger)
    return {
        "status": "PASS",
        "transaction_id": tx_id,
        "investment_product_id": product_id,
        "updated_quantity": current["quantity"],
        "updated_cost_basis": current["acquisition_cost_total"],
    }


def update_carry_forward(
    ledger_path: Path,
    *,
    uip_allocation: float,
    actual_spend: float,
    prior_carry_forward: float = 0.0,
    period: str,
) -> dict[str, Any]:
    if min(uip_allocation, actual_spend, prior_carry_forward) < 0:
        raise ValueError("Capital values cannot be negative")
    available = prior_carry_forward + uip_allocation
    if actual_spend > available + 1e-9:
        raise ValueError("Actual spend cannot exceed UIP allocation plus prior carry-forward")
    payload = {
        "schema_version": "mtg-carry-forward-v1",
        "period": period,
        "prior_carry_forward": round(prior_carry_forward, 2),
        "uip_allocation": round(uip_allocation, 2),
        "actual_spend": round(actual_spend, 2),
        "available_carry_forward": round(available - actual_spend, 2),
        "allocation_authority": "UIP",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
