"""Unified MTG marketplace production orchestrator.

Runs governed eBay and TCGCSV lanes against the same product map, creates
normalized operational evidence, and generates a lightweight deal ranking.
Live execution requires both --live and MTG_LIVE_EXECUTION=true.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.reconcile_tcgcsv_group_ids import reconcile

EBAY_SCRIPT = ROOT / "scripts" / "run_daily_ebay_collection.py"
TCGCSV_SCRIPT = ROOT / "scripts" / "run_daily_tcgcsv_collection.py"
DEFAULT_MAP = ROOT / "data" / "reference" / "product_map.csv"
DEFAULT_MODEL = ROOT / "data" / "product_master" / "product_master_model_input.csv"
DEFAULT_OUTPUT = ROOT / "data" / "operations" / "mtg_marketplace" / "latest.json"
DEFAULT_RECONCILIATION_ROOT = ROOT / "data"
EBAY_OUTPUT_ROOT = ROOT / "data" / "validation" / "phase_10" / "ebay_matching"
NORMALIZED_FIELDS = (
    "observed_at_utc", "source_name", "product_name", "tcgplayer_product_id",
    "market_price", "low_price", "median_price", "listing_count", "seller_count",
    "confidence", "source_status", "source_run_id",
)


def _run(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    try:
        payload: dict[str, Any] = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {"status": "FAILED", "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    payload["exit_code"] = result.returncode
    return payload


def _number(value: object) -> float | None:
    try:
        text = str(value or "").replace("$", "").replace(",", "").strip()
        return float(text) if text else None
    except ValueError:
        return None


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _deal_rankings(model_path: Path, limit: int = 25) -> list[dict[str, Any]]:
    if not model_path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with model_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            current = _number(row.get("current_price"))
            fair = _number(row.get("fair_value_estimate"))
            forecast = _number(row.get("mc_median")) or _number(row.get("mc_expected_value"))
            quality = _number(row.get("data_quality_score")) or 0.0
            liquidity = _number(row.get("liquidity_score")) or 0.0
            risk = _number(row.get("reprint_risk")) or 0.0
            if not current or current <= 0:
                continue
            anchor = fair or forecast
            if not anchor or anchor <= 0:
                continue
            discount = (anchor - current) / current
            score = discount * 70.0 + quality * 0.15 + liquidity * 0.15 - risk * 0.10
            rows.append({
                "box_name": row.get("box_name") or row.get("box_name_master") or "",
                "current_price": round(current, 2),
                "valuation_anchor": round(anchor, 2),
                "discount_to_value_pct": round(discount * 100.0, 2),
                "deal_score": round(score, 2),
                "signal": "BUY" if discount >= 0.15 else "WATCH" if discount >= 0.05 else "HOLD",
            })
    rows.sort(key=lambda item: (-float(item["deal_score"]), str(item["box_name"])))
    return rows[:limit]


def _materialize_reconciled_map(product_map: Path, search_root: Path, output_path: Path) -> tuple[Path, dict[str, Any]]:
    if not product_map.is_file() or not search_root.is_dir():
        return product_map, {"status": "NOT_RUN", "reason_codes": ["TCGCSV_RECONCILIATION_INPUT_NOT_AVAILABLE"]}
    report = reconcile(product_map, search_root)
    if report.get("status") != "PASS":
        return product_map, report
    resolutions = {
        str(item.get("tcgplayer_product_id", "")): item
        for item in report.get("results", [])
        if item.get("selected_group_id")
    }
    with product_map.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    for row in rows:
        product_id = str(row.get("tcgplayer_product_id") or "").strip()
        resolution = resolutions.get(product_id)
        if not resolution:
            continue
        row["tcgcsv_group_id"] = str(resolution["selected_group_id"])
        category_ids = sorted({
            str(evidence.get("tcgcsv_category_id") or "").strip()
            for evidence in resolution.get("evidence", [])
            if str(evidence.get("tcgcsv_category_id") or "").strip()
        })
        if len(category_ids) == 1:
            row["tcgcsv_category_id"] = category_ids[0]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    report = dict(report)
    report["runtime_product_map"] = str(output_path.resolve())
    report["reference_product_map_modified"] = False
    return output_path, report


def _normalize_live_observations(tcgcsv_path: Path, ebay_summary: dict[str, Any], output_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _read_csv(tcgcsv_path):
        rows.append({
            "observed_at_utc": row.get("collected_at") or row.get("source_timestamp") or "",
            "source_name": "TCGCSV",
            "product_name": row.get("box_name") or "",
            "tcgplayer_product_id": row.get("tcgplayer_product_id") or "",
            "market_price": row.get("market_price") or "",
            "low_price": row.get("low_price") or "",
            "median_price": row.get("mid_price") or "",
            "listing_count": "",
            "seller_count": "",
            "confidence": row.get("price_data_quality") or "",
            "source_status": "OBSERVED",
            "source_run_id": "",
        })
    observed = str(ebay_summary.get("observed_at_utc") or "")
    date = observed[:10] if len(observed) >= 10 else datetime.now(timezone.utc).date().isoformat()
    coverage_path = EBAY_OUTPUT_ROOT / f"ebay_product_coverage_{date}.csv"
    requested_ids = {str(value) for value in ebay_summary.get("requested_tcgplayer_product_ids", [])}
    for row in _read_csv(coverage_path):
        product_id = str(row.get("tcgplayer_product_id") or "")
        if requested_ids and product_id not in requested_ids:
            continue
        accepted = int(_number(row.get("accepted_listing_count")) or 0)
        state = row.get("coverage_state") or ""
        confidence = 90 if state == "STRONG_MATCH_COVERAGE" else 70 if state == "LIMITED_MATCH_COVERAGE" else 40 if state == "AMBIGUOUS_RESULTS" else 0
        rows.append({
            "observed_at_utc": observed,
            "source_name": "EBAY",
            "product_name": row.get("canonical_product_name") or "",
            "tcgplayer_product_id": product_id,
            "market_price": row.get("median_accepted_landed_price") or "",
            "low_price": row.get("lowest_accepted_landed_price") or "",
            "median_price": row.get("median_accepted_landed_price") or "",
            "listing_count": accepted,
            "seller_count": row.get("accepted_seller_count") or "",
            "confidence": confidence,
            "source_status": state,
            "source_run_id": ebay_summary.get("run_id") or "",
        })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=NORMALIZED_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the unified MTG marketplace production cycle")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--product-map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--reconciliation-search-root", type=Path, default=DEFAULT_RECONCILIATION_ROOT)
    parser.add_argument("--model-input", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-ebay-products", type=int, default=3, help="Retained for compatibility; product-map targeting controls live scope")
    parser.add_argument("--ebay-limit", type=int, default=20)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    live_env = os.getenv("MTG_LIVE_EXECUTION", "false").strip().lower() == "true"
    live = bool(args.live and live_env)
    blocked_live = bool(args.live and not live_env)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    lane_root = output.parent / "lanes"
    lane_root.mkdir(parents=True, exist_ok=True)

    runtime_map, reconciliation = _materialize_reconciled_map(
        args.product_map.resolve(),
        args.reconciliation_search_root.resolve(),
        output.parent / "runtime" / "tcgcsv_product_map.csv",
    )
    tcgcsv_observations = lane_root / "tcgcsv_price_observations.csv"
    normalized_output = output.parent / "normalized_marketplace_observations.csv"

    ebay_command = [
        sys.executable,
        str(EBAY_SCRIPT),
        "--limit-per-product",
        str(args.ebay_limit),
        "--product-map",
        str(runtime_map.resolve()),
        "--summary-output",
        str(lane_root / "ebay.json"),
    ]
    tcgcsv_command = [
        sys.executable,
        str(TCGCSV_SCRIPT),
        "--product-map",
        str(runtime_map.resolve()),
        "--summary-output",
        str(lane_root / "tcgcsv.json"),
        "--observations-output",
        str(tcgcsv_observations),
    ]
    if not live:
        ebay_command.append("--dry-run")
        tcgcsv_command.append("--dry-run")

    ebay = _run(ebay_command)
    tcgcsv = _run(tcgcsv_command)
    normalized = _normalize_live_observations(tcgcsv_observations, ebay, normalized_output) if live else []
    deals = _deal_rankings(args.model_input.resolve())

    lane_failures = [name for name, lane in (("EBAY", ebay), ("TCGCSV", tcgcsv)) if int(lane.get("exit_code", 1)) != 0]
    reasons: list[str] = []
    if blocked_live:
        reasons.append("MTG_LIVE_EXECUTION_ENV_DISABLED")
    if reconciliation.get("status") not in {"PASS", "NOT_RUN"}:
        reasons.append("TCGCSV_RECONCILIATION_NOT_READY")
    if ebay.get("missing_tcgplayer_product_ids"):
        reasons.append("EBAY_TARGET_PRODUCTS_MISSING_FROM_UNIVERSE")
    if lane_failures:
        reasons.extend(f"{name}_LANE_NOT_READY" for name in lane_failures)
    if live and not normalized:
        reasons.append("NORMALIZED_MARKETPLACE_OBSERVATIONS_NOT_AVAILABLE")
    if not deals:
        reasons.append("DEAL_RANKINGS_NOT_AVAILABLE")

    if blocked_live:
        status = "SAFE_HOLD"
    elif lane_failures or (live and not normalized):
        status = "INCOMPLETE"
    else:
        status = "PASS" if live else "DRY_RUN_PASS"

    payload = {
        "status": status,
        "mode": "LIVE" if live else "NON_LIVE",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "live_execution_requested": bool(args.live),
        "live_execution_enabled": live_env,
        "live_api_called": bool(live),
        "reference_product_map": str(args.product_map.resolve()),
        "runtime_product_map": str(runtime_map.resolve()),
        "ebay_selection_mode": ebay.get("selection_mode", ""),
        "reconciliation": reconciliation,
        "lanes": {"ebay": ebay, "tcgcsv": tcgcsv},
        "normalized_observations_output": str(normalized_output.resolve()),
        "normalized_observation_count": len(normalized),
        "deal_rankings": deals,
        "deal_ranking_count": len(deals),
        "reason_codes": reasons or ["MTG_MARKETPLACE_CYCLE_COMPLETED"],
    }
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if status in {"PASS", "DRY_RUN_PASS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
