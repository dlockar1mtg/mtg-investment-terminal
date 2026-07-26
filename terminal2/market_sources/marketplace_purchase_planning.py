from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

POLICY_VERSION = "10.15.0"
DEPLOYABLE_SIGNALS = {"STRONG_BUY", "BUY"}
SIGNAL_UTILITY = {"STRONG_BUY": 100.0, "BUY": 70.0}

PLAN_FIELDS = (
    "purchase_rank",
    "policy_version",
    "tcgplayer_product_id",
    "investment_product_id",
    "product_name",
    "signal",
    "allocation_action",
    "unit_price",
    "recommended_units",
    "planned_spend",
    "monthly_capital_pct",
    "existing_quantity",
    "existing_value",
    "projected_quantity",
    "projected_value",
    "projected_portfolio_weight_pct",
    "whole_unit_band_exception",
    "plan_action",
    "plan_reason_codes",
)

PROJECTION_FIELDS = (
    "investment_product_id",
    "tcgplayer_product_id",
    "product_name",
    "existing_quantity",
    "existing_value",
    "planned_units",
    "planned_spend",
    "projected_quantity",
    "projected_value",
    "projected_portfolio_weight_pct",
)


@dataclass(frozen=True)
class PurchasePolicy:
    monthly_capital: float = 600.0
    reserve_pct: float = 10.0
    max_units_per_product: int = 2
    max_projected_product_weight_pct: float = 35.0
    bootstrap_max_projected_product_weight_pct: float = 100.0
    bootstrap_portfolio_value_threshold: float = 1200.0

    @property
    def reserve_amount(self) -> float:
        return round(self.monthly_capital * self.reserve_pct / 100.0, 2)

    @property
    def deployable_capital(self) -> float:
        return round(max(0.0, self.monthly_capital - self.reserve_amount), 2)


def _number(value: object) -> float | None:
    try:
        text = str(value or "").replace("$", "").replace(",", "").strip()
        return float(text) if text else None
    except ValueError:
        return None


def _read_csv(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _model_maps(model_rows: Iterable[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_tcg: dict[str, dict[str, Any]] = {}
    by_investment: dict[str, dict[str, Any]] = {}
    for raw in model_rows:
        row = dict(raw)
        tcg_id = str(
            row.get("approved_tcgplayer_product_id")
            or row.get("tcgplayer_product_id")
            or row.get("tcgplayer_product_id_str")
            or ""
        ).strip()
        investment_id = str(row.get("investment_product_id") or "").strip()
        if tcg_id and tcg_id not in by_tcg:
            by_tcg[tcg_id] = row
        if investment_id and investment_id not in by_investment:
            by_investment[investment_id] = row
    return by_tcg, by_investment


def _holdings_state(
    holdings_rows: Iterable[dict[str, Any]],
    model_by_investment: dict[str, dict[str, Any]],
    decision_price_by_tcg: dict[str, float],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    state: dict[str, dict[str, Any]] = {}
    unknown: list[str] = []
    for raw in holdings_rows:
        investment_id = str(raw.get("investment_product_id") or "").strip()
        quantity = _number(raw.get("quantity")) or 0.0
        if not investment_id or quantity <= 0:
            continue
        model = model_by_investment.get(investment_id)
        if model is None:
            unknown.append(investment_id)
            continue
        tcg_id = str(
            model.get("approved_tcgplayer_product_id")
            or model.get("tcgplayer_product_id")
            or model.get("tcgplayer_product_id_str")
            or ""
        ).strip()
        current_price = decision_price_by_tcg.get(tcg_id)
        if current_price is None:
            current_price = _number(model.get("current_price")) or _number(model.get("current_price_db")) or 0.0
        current_value = quantity * current_price
        existing = state.setdefault(investment_id, {
            "investment_product_id": investment_id,
            "tcgplayer_product_id": tcg_id,
            "product_name": model.get("box_name") or model.get("box_name_master") or investment_id,
            "quantity": 0.0,
            "value": 0.0,
        })
        existing["quantity"] += quantity
        existing["value"] += current_value
    return state, sorted(set(unknown))


def _candidate_rows(
    decision_rows: Iterable[dict[str, Any]],
    model_by_tcg: dict[str, dict[str, Any]],
    holdings: dict[str, dict[str, Any]],
    policy: PurchasePolicy,
) -> tuple[list[dict[str, Any]], list[str]]:
    candidates: list[dict[str, Any]] = []
    unmatched: list[str] = []
    for raw in decision_rows:
        row = dict(raw)
        signal = str(row.get("signal") or "").strip().upper()
        if signal not in DEPLOYABLE_SIGNALS:
            continue
        tcg_id = str(row.get("tcgplayer_product_id") or "").strip()
        model = model_by_tcg.get(tcg_id)
        if model is None:
            unmatched.append(tcg_id)
            continue
        investment_id = str(model.get("investment_product_id") or "").strip()
        unit_price = _number(row.get("consolidated_market_price")) or 0.0
        if not investment_id or unit_price <= 0:
            unmatched.append(tcg_id)
            continue
        existing = holdings.get(investment_id, {})
        affordable_units = min(
            policy.max_units_per_product,
            int(math.floor(policy.deployable_capital / unit_price)),
        )
        candidates.append({
            "tcgplayer_product_id": tcg_id,
            "investment_product_id": investment_id,
            "product_name": row.get("product_name") or model.get("box_name") or investment_id,
            "signal": signal,
            "allocation_action": row.get("allocation_action") or "",
            "unit_price": round(unit_price, 2),
            "deal_score": _number(row.get("deal_score")) or 0.0,
            "policy_min_pct": _number(row.get("suggested_new_capital_min_pct")) or 0.0,
            "policy_max_pct": _number(row.get("suggested_new_capital_max_pct")) or 0.0,
            "existing_quantity": float(existing.get("quantity", 0.0)),
            "existing_value": float(existing.get("value", 0.0)),
            "max_units": affordable_units,
        })
    candidates.sort(key=lambda item: (-SIGNAL_UTILITY[item["signal"]], -item["deal_score"], item["product_name"]))
    return candidates, sorted(set(unmatched))


def _enumerate_combinations(candidates: list[dict[str, Any]]) -> Iterable[list[int]]:
    if not candidates:
        yield []
        return

    units = [0] * len(candidates)

    def visit(index: int) -> Iterable[list[int]]:
        if index == len(candidates):
            yield list(units)
            return
        for value in range(int(candidates[index]["max_units"]) + 1):
            units[index] = value
            yield from visit(index + 1)

    yield from visit(0)


def _select_combination(
    candidates: list[dict[str, Any]],
    holdings: dict[str, dict[str, Any]],
    policy: PurchasePolicy,
) -> list[int]:
    existing_total = sum(float(row.get("value", 0.0)) for row in holdings.values())
    bootstrap = existing_total < policy.bootstrap_portfolio_value_threshold
    max_weight = (
        policy.bootstrap_max_projected_product_weight_pct
        if bootstrap
        else policy.max_projected_product_weight_pct
    ) / 100.0

    best_units = [0] * len(candidates)
    best_objective = float("-inf")
    for units in _enumerate_combinations(candidates):
        spend = sum(units[i] * candidates[i]["unit_price"] for i in range(len(candidates)))
        if spend > policy.deployable_capital + 1e-9:
            continue
        projected_total = existing_total + spend
        if projected_total > 0:
            valid = True
            for i, candidate in enumerate(candidates):
                projected_value = candidate["existing_value"] + units[i] * candidate["unit_price"]
                if projected_value / projected_total > max_weight + 1e-9:
                    valid = False
                    break
            if not valid:
                continue

        utility = sum(
            units[i] * (SIGNAL_UTILITY[candidates[i]["signal"]] + max(0.0, candidates[i]["deal_score"]))
            for i in range(len(candidates))
        )
        utilization = spend / policy.deployable_capital if policy.deployable_capital > 0 else 0.0
        diversification = sum(1 for value in units if value > 0) * 2.0
        objective = utility + utilization * 10.0 + diversification
        tie_break = (spend, tuple(-value for value in units))
        best_tie = (
            sum(best_units[i] * candidates[i]["unit_price"] for i in range(len(candidates))),
            tuple(-value for value in best_units),
        )
        if objective > best_objective or (abs(objective - best_objective) < 1e-9 and tie_break > best_tie):
            best_objective = objective
            best_units = list(units)
    return best_units


def build_purchase_plan(
    decision_rows: Iterable[dict[str, Any]],
    model_rows: Iterable[dict[str, Any]],
    holdings_rows: Iterable[dict[str, Any]],
    policy: PurchasePolicy,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    decisions = [dict(row) for row in decision_rows]
    model_by_tcg, model_by_investment = _model_maps(model_rows)
    decision_price_by_tcg = {
        str(row.get("tcgplayer_product_id") or "").strip(): float(_number(row.get("consolidated_market_price")) or 0.0)
        for row in decisions
        if str(row.get("tcgplayer_product_id") or "").strip()
    }
    holdings, unknown_holdings = _holdings_state(holdings_rows, model_by_investment, decision_price_by_tcg)
    candidates, unmatched_candidates = _candidate_rows(decisions, model_by_tcg, holdings, policy)
    units = _select_combination(candidates, holdings, policy)

    existing_total = sum(float(row.get("value", 0.0)) for row in holdings.values())
    total_spend = round(sum(units[i] * candidates[i]["unit_price"] for i in range(len(candidates))), 2)
    projected_total = existing_total + total_spend
    plan: list[dict[str, Any]] = []
    purchase_rank = 0

    for index, candidate in enumerate(candidates):
        recommended_units = int(units[index])
        planned_spend = round(recommended_units * candidate["unit_price"], 2)
        projected_quantity = candidate["existing_quantity"] + recommended_units
        projected_value = candidate["existing_value"] + planned_spend
        weight_pct = projected_value / projected_total * 100.0 if projected_total > 0 else 0.0
        spend_pct = planned_spend / policy.monthly_capital * 100.0 if policy.monthly_capital > 0 else 0.0
        band_exception = bool(
            recommended_units > 0
            and candidate["policy_max_pct"] > 0
            and spend_pct > candidate["policy_max_pct"] + 1e-9
        )
        reasons = [f"SIGNAL_{candidate['signal']}", "WHOLE_BOX_CONSTRAINT_APPLIED"]
        if band_exception:
            reasons.append("WHOLE_UNIT_POLICY_BAND_EXCEPTION")
        if recommended_units > 0:
            purchase_rank += 1
            action = "BUY_NOW"
            reasons.append("CAPITAL_AND_CONCENTRATION_TESTS_PASSED")
        elif candidate["unit_price"] > policy.deployable_capital:
            action = "CARRY_FORWARD_INSUFFICIENT_CAPITAL"
            reasons.append("UNIT_PRICE_EXCEEDS_DEPLOYABLE_CAPITAL")
        else:
            action = "DEFER_PORTFOLIO_OPTIMIZATION"
            reasons.append("NOT_SELECTED_BY_PORTFOLIO_OPTIMIZER")

        plan.append({
            "purchase_rank": purchase_rank if recommended_units > 0 else "",
            "policy_version": POLICY_VERSION,
            "tcgplayer_product_id": candidate["tcgplayer_product_id"],
            "investment_product_id": candidate["investment_product_id"],
            "product_name": candidate["product_name"],
            "signal": candidate["signal"],
            "allocation_action": candidate["allocation_action"],
            "unit_price": candidate["unit_price"],
            "recommended_units": recommended_units,
            "planned_spend": planned_spend,
            "monthly_capital_pct": round(spend_pct, 2),
            "existing_quantity": round(candidate["existing_quantity"], 4),
            "existing_value": round(candidate["existing_value"], 2),
            "projected_quantity": round(projected_quantity, 4),
            "projected_value": round(projected_value, 2),
            "projected_portfolio_weight_pct": round(weight_pct, 2),
            "whole_unit_band_exception": band_exception,
            "plan_action": action,
            "plan_reason_codes": "|".join(reasons),
        })

    projection_map: dict[str, dict[str, Any]] = {}
    for investment_id, row in holdings.items():
        projection_map[investment_id] = {
            "investment_product_id": investment_id,
            "tcgplayer_product_id": row.get("tcgplayer_product_id", ""),
            "product_name": row.get("product_name", investment_id),
            "existing_quantity": round(float(row.get("quantity", 0.0)), 4),
            "existing_value": round(float(row.get("value", 0.0)), 2),
            "planned_units": 0,
            "planned_spend": 0.0,
        }
    for row in plan:
        investment_id = str(row["investment_product_id"])
        projection = projection_map.setdefault(investment_id, {
            "investment_product_id": investment_id,
            "tcgplayer_product_id": row["tcgplayer_product_id"],
            "product_name": row["product_name"],
            "existing_quantity": row["existing_quantity"],
            "existing_value": row["existing_value"],
            "planned_units": 0,
            "planned_spend": 0.0,
        })
        projection["planned_units"] += int(row["recommended_units"])
        projection["planned_spend"] += float(row["planned_spend"])

    projections: list[dict[str, Any]] = []
    for row in projection_map.values():
        projected_quantity = float(row["existing_quantity"]) + int(row["planned_units"])
        projected_value = float(row["existing_value"]) + float(row["planned_spend"])
        projections.append({
            **row,
            "planned_spend": round(float(row["planned_spend"]), 2),
            "projected_quantity": round(projected_quantity, 4),
            "projected_value": round(projected_value, 2),
            "projected_portfolio_weight_pct": round(projected_value / projected_total * 100.0, 2) if projected_total > 0 else 0.0,
        })
    projections.sort(key=lambda row: (-float(row["projected_value"]), str(row["product_name"])))

    unspent = round(policy.monthly_capital - total_spend, 2)
    reserve_preserved = unspent >= policy.reserve_amount - 1e-9
    summary = {
        "status": "PASS" if candidates and not unmatched_candidates and not unknown_holdings else "INCOMPLETE",
        "policy_version": POLICY_VERSION,
        "monthly_capital": round(policy.monthly_capital, 2),
        "reserve_pct": round(policy.reserve_pct, 2),
        "required_reserve_amount": policy.reserve_amount,
        "deployable_capital": policy.deployable_capital,
        "planned_spend": total_spend,
        "unspent_capital": unspent,
        "carry_forward_capital": unspent,
        "capital_utilization_pct": round(total_spend / policy.monthly_capital * 100.0, 2) if policy.monthly_capital > 0 else 0.0,
        "reserve_preserved": reserve_preserved,
        "holdings_file_found": bool(list(holdings_rows)) or bool(holdings),
        "existing_portfolio_value": round(existing_total, 2),
        "projected_portfolio_value": round(projected_total, 2),
        "deployable_candidate_count": len(candidates),
        "purchase_line_count": sum(int(row["recommended_units"]) > 0 for row in plan),
        "total_units": sum(int(row["recommended_units"]) for row in plan),
        "whole_unit_band_exception_count": sum(bool(row["whole_unit_band_exception"]) for row in plan),
        "unknown_holding_product_ids": unknown_holdings,
        "unmatched_deployable_product_ids": unmatched_candidates,
        "reason_codes": ["MTG_PORTFOLIO_PURCHASE_PLAN_COMPLETED"],
    }
    if not candidates:
        summary["status"] = "NO_ACTION"
        summary["reason_codes"] = ["NO_DEPLOYABLE_MARKETPLACE_DECISIONS"]
    elif total_spend <= 0:
        summary["reason_codes"].append("CAPITAL_CARRIED_FORWARD_NO_FEASIBLE_WHOLE_UNIT_PURCHASE")
    if not reserve_preserved:
        summary["status"] = "FAILED"
        summary["reason_codes"].append("REQUIRED_CASH_RESERVE_NOT_PRESERVED")
    return plan, projections, summary


def write_outputs(
    decisions_path: Path,
    model_path: Path,
    holdings_path: Path | None,
    plan_output: Path,
    projection_output: Path,
    summary_output: Path,
    policy: PurchasePolicy,
) -> dict[str, Any]:
    decisions = _read_csv(decisions_path)
    models = _read_csv(model_path)
    holdings = _read_csv(holdings_path)
    plan, projections, summary = build_purchase_plan(decisions, models, holdings, policy)

    plan_output.parent.mkdir(parents=True, exist_ok=True)
    with plan_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PLAN_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(plan)

    projection_output.parent.mkdir(parents=True, exist_ok=True)
    with projection_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROJECTION_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(projections)

    summary.update({
        "decisions_input": str(decisions_path.resolve()),
        "model_input": str(model_path.resolve()),
        "holdings_input": str(holdings_path.resolve()) if holdings_path is not None else "",
        "purchase_plan_output": str(plan_output.resolve()),
        "portfolio_projection_output": str(projection_output.resolve()),
    })
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
