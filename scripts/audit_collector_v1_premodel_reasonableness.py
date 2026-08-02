from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_premodel_reasonableness_audit_contract_v1.json"
LEDGER = ROOT / "data/governance/permanence/certification/collector_v1_august1_historical_observation_ledger/collector_august1_historical_observation_ledger.csv"
LEDGER_SUMMARY = ROOT / "data/governance/permanence/certification/collector_v1_august1_historical_observation_ledger/collector_august1_historical_observation_ledger_summary.json"
FOUNDATION = ROOT / "data/governance/permanence/certification/collector_v1_august1_snapshot_bound_current_foundation/collector_v1_august1_snapshot_bound_current_foundation.csv"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_premodel_reasonableness_audit"

PRODUCT_FIELDS = [
    "canonical_product_id", "tcgplayer_product_id", "product_name", "release_date", "release_state",
    "forecast_route", "observation_count", "first_observation_date", "last_observation_date", "history_span_days",
    "expected_months_in_window", "missing_months_in_window", "selection_method_count", "selection_method_switches",
    "extreme_return_count", "severe_return_count", "max_absolute_return", "longest_flatline_run",
    "current_price", "last_history_price", "current_to_history_gap", "current_price_authority_status",
    "comparable_rows", "coverage_classification", "modeling_classification", "blocking_reasons", "review_warnings"
]

ANOMALY_FIELDS = [
    "canonical_product_id", "tcgplayer_product_id", "product_name", "observation_date", "anomaly_type",
    "severity", "value", "prior_value", "selection_method", "prior_selection_method", "details"
]

RISK_FIELDS = ["risk_id", "risk_name", "status", "severity", "evidence", "required_action"]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def clean(value: Any) -> str:
    return str(value or "").strip()


def number(value: Any) -> float | None:
    text = clean(value).replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def date_value(value: Any) -> datetime | None:
    text = clean(value)[:10]
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def month_index(value: datetime) -> int:
    return value.year * 12 + value.month


def longest_flatline(prices: list[float]) -> int:
    longest = 0
    current = 0
    previous: float | None = None
    for price in prices:
        if previous is not None and price == previous:
            current += 1
        else:
            current = 1
        longest = max(longest, current)
        previous = price
    return longest


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    thresholds = contract["thresholds"]
    ledger_summary = json.loads(LEDGER_SUMMARY.read_text(encoding="utf-8"))
    ledger = read_csv(LEDGER)
    foundation = read_csv(FOUNDATION)
    failures: list[str] = []

    if ledger_summary.get("status") != "PASS_COLLECTOR_AUGUST1_HISTORICAL_OBSERVATION_LEDGER":
        failures.append("LEDGER_NOT_CERTIFIED")
    if len(ledger) != contract["required_ledger_rows"]:
        failures.append("LEDGER_ROW_COUNT_MISMATCH")
    if len(foundation) != contract["required_product_count"]:
        failures.append("FOUNDATION_PRODUCT_COUNT_MISMATCH")

    foundation_by_id = {clean(r.get("identity__canonical_product_id")): r for r in foundation}
    ledger_by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in ledger:
        ledger_by_id[clean(row.get("canonical_product_id"))].append(row)

    archive_end = date_value(contract["archive_endpoint"])
    products: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []

    for canonical_id, foundation_row in foundation_by_id.items():
        rows = sorted(ledger_by_id.get(canonical_id, []), key=lambda r: clean(r.get("observation_date")))
        tcg_id = clean(foundation_row.get("tcgplayer_product_id"))
        name = clean(foundation_row.get("identity__canonical_product_name"))
        release = date_value(foundation_row.get("identity__raw_released_on"))
        release_state = clean(foundation_row.get("identity__release_state"))
        route = clean(foundation_row.get("forecast_route"))
        prices = [number(r.get("selected_price")) for r in rows]
        valid_prices = [p for p in prices if p is not None]
        dates = [date_value(r.get("observation_date")) for r in rows]
        valid_dates = [d for d in dates if d is not None]
        first_date = min(valid_dates) if valid_dates else None
        last_date = max(valid_dates) if valid_dates else None
        span_days = (last_date - first_date).days if first_date and last_date else 0
        expected_start = first_date
        if release and archive_end and release <= archive_end:
            expected_start = max(first_date, release) if first_date else release
        expected_months = month_index(archive_end) - month_index(expected_start) + 1 if expected_start and archive_end and expected_start <= archive_end else 0
        observed_months = len({(d.year, d.month) for d in valid_dates})
        missing_months = max(expected_months - observed_months, 0)

        methods = [clean(r.get("selection_method")) for r in rows]
        method_count = len({m for m in methods if m})
        method_switches = sum(1 for i in range(1, len(methods)) if methods[i] != methods[i - 1])

        returns: list[float] = []
        extreme_count = 0
        severe_count = 0
        for i in range(1, len(rows)):
            prior = number(rows[i - 1].get("selected_price"))
            current = number(rows[i].get("selected_price"))
            if prior is None or current is None or prior <= 0:
                continue
            change = current / prior - 1.0
            returns.append(change)
            severity = None
            if abs(change) >= thresholds["severe_absolute_monthly_return"]:
                severe_count += 1
                severity = "SEVERE"
            elif abs(change) >= thresholds["extreme_absolute_monthly_return"]:
                extreme_count += 1
                severity = "HIGH"
            if severity:
                anomalies.append({
                    "canonical_product_id": canonical_id,
                    "tcgplayer_product_id": tcg_id,
                    "product_name": name,
                    "observation_date": clean(rows[i].get("observation_date")),
                    "anomaly_type": "EXTREME_MONTHLY_RETURN",
                    "severity": severity,
                    "value": change,
                    "prior_value": prior,
                    "selection_method": clean(rows[i].get("selection_method")),
                    "prior_selection_method": clean(rows[i - 1].get("selection_method")),
                    "details": "Return may reflect market movement, thin data, or price-method transition.",
                })
            if methods[i] != methods[i - 1]:
                anomalies.append({
                    "canonical_product_id": canonical_id,
                    "tcgplayer_product_id": tcg_id,
                    "product_name": name,
                    "observation_date": clean(rows[i].get("observation_date")),
                    "anomaly_type": "SELECTION_METHOD_SWITCH",
                    "severity": "REVIEW",
                    "value": change,
                    "prior_value": prior,
                    "selection_method": methods[i],
                    "prior_selection_method": methods[i - 1],
                    "details": "Observed return coincides with a selected-price methodology change.",
                })

        flatline = longest_flatline(valid_prices)
        if flatline >= thresholds["flatline_run_observations"]:
            anomalies.append({
                "canonical_product_id": canonical_id,
                "tcgplayer_product_id": tcg_id,
                "product_name": name,
                "observation_date": clean(rows[-1].get("observation_date")) if rows else "",
                "anomaly_type": "PRICE_FLATLINE_RUN",
                "severity": "REVIEW",
                "value": flatline,
                "prior_value": "",
                "selection_method": "",
                "prior_selection_method": "",
                "details": "Repeated identical monthly prices may indicate stale or thin observations.",
            })

        pre_release = [d for d in valid_dates if release and d < release]
        if pre_release:
            anomalies.append({
                "canonical_product_id": canonical_id,
                "tcgplayer_product_id": tcg_id,
                "product_name": name,
                "observation_date": pre_release[0].date().isoformat(),
                "anomaly_type": "PRE_RELEASE_HISTORY",
                "severity": "REVIEW",
                "value": len(pre_release),
                "prior_value": "",
                "selection_method": "",
                "prior_selection_method": "",
                "details": "Presale observations must be separated from post-release behavior.",
            })

        current_price = number(foundation_row.get("current_price")) or number(foundation_row.get("price__fresh_market_price"))
        last_history = valid_prices[-1] if valid_prices else None
        gap = (current_price / last_history - 1.0) if current_price and last_history and last_history > 0 else None
        warnings: list[str] = []
        blockers: list[str] = []
        if gap is not None and abs(gap) >= thresholds["large_current_to_history_gap"]:
            warnings.append("LARGE_CURRENT_TO_HISTORY_GAP")
            anomalies.append({
                "canonical_product_id": canonical_id,
                "tcgplayer_product_id": tcg_id,
                "product_name": name,
                "observation_date": contract["archive_endpoint"],
                "anomaly_type": "CURRENT_TO_HISTORY_GAP",
                "severity": "HIGH",
                "value": gap,
                "prior_value": last_history,
                "selection_method": "CURRENT_AUTHORITY",
                "prior_selection_method": clean(rows[-1].get("selection_method")) if rows else "",
                "details": "Current price differs materially from the final certified historical observation.",
            })

        obs = len(rows)
        comparable_rows = clean(foundation_row.get("feature__selected_comparable_rows"))
        if obs == 0 or route == "COMPARABLE_PRODUCT_ADJUSTED":
            coverage_class = "COMPARABLE_ONLY"
            model_class = "COMPARABLE_ROUTE_REVIEW_REQUIRED"
            if not comparable_rows or comparable_rows == "0":
                blockers.append("COMPARABLE_SET_NOT_EVIDENCED")
        elif obs >= thresholds["minimum_direct_history_observations"] and span_days >= thresholds["minimum_direct_history_span_days"]:
            coverage_class = "DIRECT_HISTORY"
            model_class = "SIMPLE_MODEL_TOURNAMENT_CANDIDATE"
        elif obs >= thresholds["minimum_limited_history_observations"]:
            coverage_class = "LIMITED_HISTORY"
            model_class = "LIMITED_MODEL_FAMILIES_ONLY"
        else:
            coverage_class = "INSUFFICIENT_HISTORY"
            model_class = "BLOCKED_FROM_DIRECT_MODEL_TOURNAMENT"
            blockers.append("INSUFFICIENT_HISTORY")

        authority_status = clean(foundation_row.get("identity__current_price_authority_status"))
        if authority_status not in {"CURRENT_PRICE_AUTHORIZED", "CURRENT_PRICE_CERTIFIED"}:
            warnings.append(f"CURRENT_PRICE_STATUS:{authority_status or 'MISSING'}")

        if method_switches:
            warnings.append("SELECTION_METHOD_TRANSITIONS_PRESENT")
        if missing_months:
            warnings.append("MISSING_MONTHS_WITHIN_EXPECTED_WINDOW")
        if pre_release:
            warnings.append("PRESALE_HISTORY_PRESENT")

        products.append({
            "canonical_product_id": canonical_id,
            "tcgplayer_product_id": tcg_id,
            "product_name": name,
            "release_date": release.date().isoformat() if release else "",
            "release_state": release_state,
            "forecast_route": route,
            "observation_count": obs,
            "first_observation_date": first_date.date().isoformat() if first_date else "",
            "last_observation_date": last_date.date().isoformat() if last_date else "",
            "history_span_days": span_days,
            "expected_months_in_window": expected_months,
            "missing_months_in_window": missing_months,
            "selection_method_count": method_count,
            "selection_method_switches": method_switches,
            "extreme_return_count": extreme_count,
            "severe_return_count": severe_count,
            "max_absolute_return": max((abs(x) for x in returns), default=0.0),
            "longest_flatline_run": flatline,
            "current_price": current_price if current_price is not None else "",
            "last_history_price": last_history if last_history is not None else "",
            "current_to_history_gap": gap if gap is not None else "",
            "current_price_authority_status": authority_status,
            "comparable_rows": comparable_rows,
            "coverage_classification": coverage_class,
            "modeling_classification": model_class,
            "blocking_reasons": ";".join(blockers),
            "review_warnings": ";".join(warnings),
        })

    risk_rows = [
        {"risk_id": "R01", "risk_name": "Governance audit freshness", "status": "REVIEW_REQUIRED", "severity": "HIGH", "evidence": "Repeated governance output timestamp must be compared with newest artifact timestamps.", "required_action": "Recompute governance inventory dynamically before tournament authorization."},
        {"risk_id": "R02", "risk_name": "Uneven historical coverage", "status": "MEASURED", "severity": "HIGH", "evidence": f"{sum(int(p['missing_months_in_window']) for p in products)} missing product-months inside expected windows.", "required_action": "Review product-level coverage classifications and unexplained gaps."},
        {"risk_id": "R03", "risk_name": "Small samples", "status": "MEASURED", "severity": "HIGH", "evidence": f"Maximum observations={max((int(p['observation_count']) for p in products), default=0)}.", "required_action": "Restrict tournaments to simple model families and minimum sample thresholds."},
        {"risk_id": "R04", "risk_name": "Current versus historical anchor", "status": "MEASURED", "severity": "HIGH", "evidence": f"Large anchor gaps={sum('LARGE_CURRENT_TO_HISTORY_GAP' in p['review_warnings'] for p in products)}.", "required_action": "Govern August current price as a separate anchor unless formally admitted as history."},
        {"risk_id": "R05", "risk_name": "Selected-price method transitions", "status": "MEASURED", "severity": "HIGH", "evidence": f"Products with transitions={sum(int(p['selection_method_switches']) > 0 for p in products)}.", "required_action": "Run sensitivity checks around market/mid method transitions."},
        {"risk_id": "R06", "risk_name": "Release and presale alignment", "status": "MEASURED", "severity": "HIGH", "evidence": f"Products with presale history={sum('PRESALE_HISTORY_PRESENT' in p['review_warnings'] for p in products)}.", "required_action": "Separate presale and post-release regimes."},
        {"risk_id": "R07", "risk_name": "Extreme movements and flatlines", "status": "MEASURED", "severity": "HIGH", "evidence": f"Anomaly rows={len(anomalies)}.", "required_action": "Review all severe/high anomalies before modeling."},
        {"risk_id": "R08", "risk_name": "Current-universe survivorship bias", "status": "STRUCTURAL_RISK_PRESENT", "severity": "HIGH", "evidence": "History is filtered to the August 1 current 50-product universe.", "required_action": "Do not claim unbiased strategy backtests without point-in-time historical universes."},
        {"risk_id": "R09", "risk_name": "Comparable-route validity", "status": "REVIEW_REQUIRED", "severity": "HIGH", "evidence": f"Comparable-only products={sum(p['coverage_classification'] == 'COMPARABLE_ONLY' for p in products)}.", "required_action": "Certify comparable membership, similarity dimensions, and no future leakage."},
        {"risk_id": "R10", "risk_name": "Current-only feature leakage", "status": "STRUCTURAL_RISK_PRESENT", "severity": "CRITICAL", "evidence": "August 1 supply, seller, scarcity, and current eligibility fields are not historical features.", "required_action": "Exclude current-only features from historical folds unless point-in-time snapshots exist."},
        {"risk_id": "R11", "risk_name": "Cross-market source mismatch", "status": "STRUCTURAL_RISK_PRESENT", "severity": "HIGH", "evidence": "TCGplayer historical prices and eBay current supply measure different markets.", "required_action": "Keep source-specific semantics and avoid treating listing supply as realized historical liquidity."},
        {"risk_id": "R12", "risk_name": "Current-price authority status", "status": "MEASURED", "severity": "HIGH", "evidence": f"Non-final statuses={sum(not p['current_price_authority_status'].endswith(('AUTHORIZED','CERTIFIED')) for p in products)}.", "required_action": "Resolve current-price authority before expected-return ranking."},
    ]

    critical_anomalies = [a for a in anomalies if a["severity"] in {"SEVERE", "CRITICAL"}]
    blocked_products = [p for p in products if p["blocking_reasons"]]
    unresolved_structural = [r for r in risk_rows if r["status"] in {"STRUCTURAL_RISK_PRESENT", "REVIEW_REQUIRED"}]

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_premodel_product_reasonableness.csv", products, PRODUCT_FIELDS)
    write_csv(OUTPUT / "collector_premodel_anomalies.csv", anomalies, ANOMALY_FIELDS)
    write_csv(OUTPUT / "collector_premodel_structural_risks.csv", risk_rows, RISK_FIELDS)

    summary = {
        "block_name": contract["contract_name"],
        "block_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "governing_snapshot_id": contract["governing_snapshot_id"],
        "product_rows": len(products),
        "ledger_rows": len(ledger),
        "anomaly_rows": len(anomalies),
        "critical_or_severe_anomaly_rows": len(critical_anomalies),
        "blocked_product_count": len(blocked_products),
        "direct_history_candidates": sum(p["coverage_classification"] == "DIRECT_HISTORY" for p in products),
        "limited_history_products": sum(p["coverage_classification"] == "LIMITED_HISTORY" for p in products),
        "insufficient_history_products": sum(p["coverage_classification"] == "INSUFFICIENT_HISTORY" for p in products),
        "comparable_only_products": sum(p["coverage_classification"] == "COMPARABLE_ONLY" for p in products),
        "products_with_method_switches": sum(int(p["selection_method_switches"]) > 0 for p in products),
        "products_with_missing_months": sum(int(p["missing_months_in_window"]) > 0 for p in products),
        "products_with_large_anchor_gaps": sum("LARGE_CURRENT_TO_HISTORY_GAP" in p["review_warnings"] for p in products),
        "unresolved_structural_risk_count": len(unresolved_structural),
        "historical_coverage_assessment_completed": not failures,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": "PASS_COLLECTOR_PREMODEL_REASONABLENESS_AUDIT_COMPLETED" if not failures else "FAIL_COLLECTOR_PREMODEL_REASONABLENESS_AUDIT",
    }
    (OUTPUT / "collector_premodel_reasonableness_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
