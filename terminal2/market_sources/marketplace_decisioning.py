from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Iterable

CONSOLIDATED_FIELDS = (
    "tcgplayer_product_id",
    "product_name",
    "consolidated_price",
    "source_count",
    "source_names",
    "minimum_source_price",
    "maximum_source_price",
    "cross_source_spread_pct",
    "price_quality_state",
)

DECISION_FIELDS = (
    "rank",
    "tcgplayer_product_id",
    "product_name",
    "consolidated_market_price",
    "forecast_anchor",
    "forecast_anchor_type",
    "expected_upside_pct",
    "deal_score",
    "signal",
    "source_count",
    "source_names",
    "cross_source_spread_pct",
    "data_quality_score",
    "liquidity_score",
    "reprint_risk",
    "prob_loss",
    "prob_double",
    "decision_reason_codes",
)


def _number(value: object) -> float | None:
    try:
        text = str(value or "").replace("$", "").replace(",", "").strip()
        return float(text) if text else None
    except ValueError:
        return None


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def consolidate_certified_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        product_id = str(row.get("tcgplayer_product_id") or "").strip()
        price = _number(row.get("certified_price"))
        if not product_id or not price or price <= 0:
            continue
        if not _truthy(row.get("eligible_for_decisioning")):
            continue
        grouped[product_id].append(dict(row))

    consolidated: list[dict[str, Any]] = []
    for product_id, product_rows in grouped.items():
        prices = [float(_number(row.get("certified_price")) or 0.0) for row in product_rows]
        prices = [price for price in prices if price > 0]
        if not prices:
            continue
        sources = sorted({str(row.get("source_name") or "").strip().upper() for row in product_rows if str(row.get("source_name") or "").strip()})
        low = min(prices)
        high = max(prices)
        spread = ((high - low) / low * 100.0) if low > 0 else 0.0
        names = [str(row.get("product_name") or "").strip() for row in product_rows if str(row.get("product_name") or "").strip()]
        consolidated.append({
            "tcgplayer_product_id": product_id,
            "product_name": names[0] if names else product_id,
            "consolidated_price": round(float(median(prices)), 2),
            "source_count": len(sources),
            "source_names": "|".join(sources),
            "minimum_source_price": round(low, 2),
            "maximum_source_price": round(high, 2),
            "cross_source_spread_pct": round(spread, 2),
            "price_quality_state": "MULTI_SOURCE_CERTIFIED" if len(sources) >= 2 else "SINGLE_SOURCE_CERTIFIED",
        })
    consolidated.sort(key=lambda row: str(row["tcgplayer_product_id"]))
    return consolidated


def _forecast_anchor(row: dict[str, Any]) -> tuple[float | None, str]:
    for field, label in (
        ("mc_median", "MC_MEDIAN"),
        ("mc_expected_value", "MC_EXPECTED_VALUE"),
        ("fair_value_estimate", "FAIR_VALUE_ESTIMATE"),
    ):
        value = _number(row.get(field))
        if value and value > 0:
            return value, label
    return None, ""


def build_decisions(
    consolidated_rows: Iterable[dict[str, Any]],
    model_rows: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    price_by_id = {
        str(row.get("tcgplayer_product_id") or "").strip(): dict(row)
        for row in consolidated_rows
        if str(row.get("tcgplayer_product_id") or "").strip()
    }
    model_by_id: dict[str, dict[str, Any]] = {}
    for row in model_rows:
        product_id = str(
            row.get("approved_tcgplayer_product_id")
            or row.get("tcgplayer_product_id")
            or row.get("tcgplayer_product_id_str")
            or ""
        ).strip()
        if product_id and product_id not in model_by_id:
            model_by_id[product_id] = dict(row)

    decisions: list[dict[str, Any]] = []
    unmatched_prices: list[str] = []
    missing_forecasts: list[str] = []

    for product_id, price_row in price_by_id.items():
        model = model_by_id.get(product_id)
        if model is None:
            unmatched_prices.append(product_id)
            continue
        current = _number(price_row.get("consolidated_price"))
        anchor, anchor_type = _forecast_anchor(model)
        if not current or current <= 0 or not anchor or anchor <= 0:
            missing_forecasts.append(product_id)
            continue

        upside = (anchor - current) / current
        quality = _number(model.get("data_quality_score")) or 0.0
        liquidity = _number(model.get("liquidity_score")) or 0.0
        reprint_risk = _number(model.get("reprint_risk")) or 0.0
        prob_loss = _number(model.get("prob_loss"))
        prob_double = _number(model.get("prob_double"))
        source_count = int(_number(price_row.get("source_count")) or 0)
        spread = _number(price_row.get("cross_source_spread_pct")) or 0.0

        source_bonus = 5.0 if source_count >= 2 else 0.0
        spread_penalty = max(0.0, spread - 10.0) * 0.20
        loss_penalty = (prob_loss or 0.0) * 20.0
        score = (
            upside * 70.0
            + quality * 0.10
            + liquidity * 0.10
            - reprint_risk * 0.08
            + source_bonus
            - spread_penalty
            - loss_penalty
        )

        if upside >= 0.25:
            signal = "STRONG_BUY"
        elif upside >= 0.15:
            signal = "BUY"
        elif upside >= 0.05:
            signal = "WATCH"
        elif upside >= -0.10:
            signal = "HOLD"
        else:
            signal = "AVOID"

        reasons = [f"PRICE_{price_row.get('price_quality_state', 'CERTIFIED')}", f"ANCHOR_{anchor_type}"]
        if source_count >= 2:
            reasons.append("CROSS_SOURCE_CONFIRMED")
        if spread > 15:
            reasons.append("CROSS_SOURCE_SPREAD_ELEVATED")
        if prob_loss is not None and prob_loss >= 0.35:
            reasons.append("MONTE_CARLO_LOSS_RISK_ELEVATED")

        decisions.append({
            "rank": 0,
            "tcgplayer_product_id": product_id,
            "product_name": model.get("box_name") or model.get("box_name_master") or price_row.get("product_name") or product_id,
            "consolidated_market_price": round(current, 2),
            "forecast_anchor": round(anchor, 2),
            "forecast_anchor_type": anchor_type,
            "expected_upside_pct": round(upside * 100.0, 2),
            "deal_score": round(score, 2),
            "signal": signal,
            "source_count": source_count,
            "source_names": price_row.get("source_names") or "",
            "cross_source_spread_pct": round(spread, 2),
            "data_quality_score": round(quality, 2),
            "liquidity_score": round(liquidity, 2),
            "reprint_risk": round(reprint_risk, 2),
            "prob_loss": "" if prob_loss is None else round(prob_loss, 4),
            "prob_double": "" if prob_double is None else round(prob_double, 4),
            "decision_reason_codes": "|".join(reasons),
        })

    decisions.sort(key=lambda row: (-float(row["deal_score"]), str(row["product_name"])))
    for index, row in enumerate(decisions, start=1):
        row["rank"] = index

    summary = {
        "status": "PASS" if decisions else "INCOMPLETE",
        "certified_products": len(price_by_id),
        "decision_count": len(decisions),
        "unmatched_certified_product_ids": sorted(unmatched_prices),
        "missing_forecast_product_ids": sorted(missing_forecasts),
        "signal_counts": {
            signal: sum(row["signal"] == signal for row in decisions)
            for signal in ("STRONG_BUY", "BUY", "WATCH", "HOLD", "AVOID")
            if any(row["signal"] == signal for row in decisions)
        },
    }
    return decisions, summary


def write_outputs(
    certified_path: Path,
    model_path: Path,
    consolidated_output: Path,
    decisions_output: Path,
    summary_output: Path,
) -> dict[str, Any]:
    consolidated = consolidate_certified_rows(_read_csv(certified_path))
    decisions, summary = build_decisions(consolidated, _read_csv(model_path))

    consolidated_output.parent.mkdir(parents=True, exist_ok=True)
    with consolidated_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CONSOLIDATED_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(consolidated)

    decisions_output.parent.mkdir(parents=True, exist_ok=True)
    with decisions_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DECISION_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(decisions)

    summary.update({
        "consolidated_price_count": len(consolidated),
        "consolidated_prices_output": str(consolidated_output.resolve()),
        "decision_rankings_output": str(decisions_output.resolve()),
        "certified_observations_input": str(certified_path.resolve()),
        "model_input": str(model_path.resolve()),
        "reason_codes": ["CERTIFIED_MARKETPLACE_DECISIONING_COMPLETED"] if decisions else ["CERTIFIED_MARKETPLACE_DECISIONS_NOT_AVAILABLE"],
    })
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
