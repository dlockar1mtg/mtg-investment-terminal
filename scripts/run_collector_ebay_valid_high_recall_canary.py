"""Run the evidence-based Collector eBay high-recall canary.

This is a limited live acquisition test. It does not update the certified supply
continuity baseline. The existing targeted collector supplies the query ladder,
Browse API client, quota handling, and precision-v3-universal matcher.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "data/governance/permanence/certification/collector_ebay_reconstructed_recall/collector_ebay_valid_high_recall_canary_plan.csv"
CURRENT = ROOT / "data/governance/permanence/certification/collector_ebay_supply_collection/collector_ebay_listing_observations_shadow.csv"
HISTORY = ROOT / "data/governance/permanence/certification/collector_ebay_historical_reconstruction/collector_ebay_reconstructed_historical_listing_evidence.csv"
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_valid_high_recall_canary"
LEGACY_OUT = ROOT / "data/validation/phase_10/ebay_matching"


def norm_id(value: object) -> str:
    text = str(value or "").strip()
    return text[:-2] if text.endswith(".0") else text


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run limited evidence-based Collector eBay recall canary")
    p.add_argument("--plan", type=Path, default=PLAN)
    p.add_argument("--current", type=Path, default=CURRENT)
    p.add_argument("--history", type=Path, default=HISTORY)
    p.add_argument("--output-dir", type=Path, default=OUT)
    p.add_argument("--limit-per-product", type=int, default=200)
    p.add_argument("--strict", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc)

    missing = [str(path) for path in (args.plan, args.current, args.history) if not path.is_file()]
    credentials_ready = bool(os.getenv("EBAY_CLIENT_ID", "").strip() and os.getenv("EBAY_CLIENT_SECRET", "").strip())
    if missing or not credentials_ready:
        summary = {
            "block_name": "Collector eBay Valid High-Recall Canary",
            "generated_at": generated.isoformat(),
            "missing_inputs": missing,
            "credentials_ready": credentials_ready,
            "live_collection_executed": False,
            "status": "REQUIRED_INPUT_OR_CREDENTIAL_MISSING",
        }
        (out / "collector_ebay_valid_high_recall_canary_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1 if args.strict else 0

    plan = pd.read_csv(args.plan, dtype=str, encoding="utf-8-sig").fillna("")
    plan = plan[plan["live_canary_authorized"].astype(str).str.lower().isin({"true", "1", "yes"})].copy()
    if plan.empty or len(plan) > 6:
        raise RuntimeError(f"Expected 1-6 authorized canary products; found {len(plan)}")

    target_map = out / "collector_ebay_valid_high_recall_canary_product_map.csv"
    pd.DataFrame({
        "tcgplayer_product_id": plan["tcgplayer_product_id"].map(norm_id),
        "box_name": plan["governed_box_name"],
        "source_product_name": plan["governed_box_name"],
        "canary_role": plan["canary_role"],
    }).to_csv(target_map, index=False)

    # Import only after the repository path and credentials are confirmed.
    from terminal2.market_sources.ebay_precision_production import run_precision_targeted_coverage

    run_summary = run_precision_targeted_coverage(target_map, limit_per_product=args.limit_per_product)
    date = generated.date().isoformat()
    source_results = LEGACY_OUT / f"ebay_listing_match_results_{date}.csv"
    source_coverage = LEGACY_OUT / f"ebay_product_coverage_{date}.csv"
    source_universe = LEGACY_OUT / f"ebay_canonical_match_universe_{date}.csv"
    source_review = LEGACY_OUT / f"ebay_manual_review_{date}.csv"

    copied: dict[str, str] = {}
    for source, name in (
        (source_results, "collector_ebay_canary_listing_results.csv"),
        (source_coverage, "collector_ebay_canary_product_coverage.csv"),
        (source_universe, "collector_ebay_canary_universe.csv"),
        (source_review, "collector_ebay_canary_manual_review.csv"),
    ):
        if source.is_file():
            destination = out / name
            shutil.copy2(source, destination)
            copied[name] = str(source.relative_to(ROOT))

    if not source_results.is_file() or not source_coverage.is_file():
        raise RuntimeError("Targeted collector did not create expected result and coverage files")

    results = pd.read_csv(source_results, dtype=str, encoding="utf-8-sig").fillna("")
    coverage = pd.read_csv(source_coverage, dtype=str, encoding="utf-8-sig").fillna("")
    current = pd.read_csv(args.current, dtype=str, encoding="utf-8-sig").fillna("")
    history = pd.read_csv(args.history, dtype=str, encoding="utf-8-sig").fillna("")

    current_item_col = "item_id" if "item_id" in current.columns else "ebay_item_id"
    current["tcgplayer_product_id"] = current["tcgplayer_product_id"].map(norm_id)
    history["tcgplayer_product_id"] = history["tcgplayer_product_id"].map(norm_id)

    comparison_rows: list[dict[str, object]] = []
    for _, row in plan.iterrows():
        pid = norm_id(row["tcgplayer_product_id"])
        current_ids = set(current.loc[current["tcgplayer_product_id"] == pid, current_item_col].astype(str))
        historical_ids = set(history.loc[history["tcgplayer_product_id"] == pid, "ebay_item_id"].astype(str))
        canary_product = results[results["canonical_product_id"] == f"TCGPLAYER-{pid}"]
        canary_ids = set(canary_product["ebay_item_id"].astype(str))
        accepted_ids = set(canary_product.loc[canary_product["match_state"] == "ACCEPTED", "ebay_item_id"].astype(str))
        comparison_rows.append({
            "canary_role": row["canary_role"],
            "tcgplayer_product_id": pid,
            "governed_box_name": row["governed_box_name"],
            "current_sample_unique_item_ids": len(current_ids),
            "historical_unique_item_ids": len(historical_ids),
            "canary_unique_candidate_item_ids": len(canary_ids),
            "canary_production_accepted_item_ids": len(accepted_ids),
            "incremental_candidates_vs_current": len(canary_ids - current_ids),
            "historical_item_ids_recovered_by_canary": len(canary_ids & historical_ids),
            "historical_only_ids_still_not_recovered": len(historical_ids - canary_ids),
            "candidate_recall_improved": len(canary_ids) > len(current_ids),
        })
    comparison = pd.DataFrame(comparison_rows)
    comparison.to_csv(out / "collector_ebay_canary_recall_comparison.csv", index=False)

    source_errors = int((coverage.get("coverage_state", pd.Series(dtype=str)) == "SOURCE_ERROR").sum())
    incremental_products = int(comparison["candidate_recall_improved"].astype(str).str.lower().isin({"true", "1"}).sum())
    total_incremental = int(pd.to_numeric(comparison["incremental_candidates_vs_current"], errors="coerce").fillna(0).sum())
    summary = {
        "block_name": "Collector eBay Valid High-Recall Canary",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "live_collection_executed": True,
        "canary_only": True,
        "continuity_written": False,
        "canary_products": len(plan),
        "limit_per_product": args.limit_per_product,
        "matcher_version": run_summary.get("matcher_version", ""),
        "queries_used": run_summary.get("queries_used", 0),
        "candidate_listing_rows": run_summary.get("listing_rows", 0),
        "accepted_rows": run_summary.get("accepted_rows", 0),
        "review_rows": run_summary.get("review_rows", 0),
        "rejected_rows": run_summary.get("rejected_rows", 0),
        "source_errors": source_errors,
        "products_with_candidate_recall_improvement": incremental_products,
        "total_incremental_candidates_vs_current": total_incremental,
        "acquisition_recall_certified": False,
        "full_universe_collection_authorized": source_errors == 0 and incremental_products > 0,
        "continuity_accumulation_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "copied_artifacts": copied,
        "status": "PASS_LIMITED_HIGH_RECALL_CANARY_REVIEW_REQUIRED" if source_errors == 0 else "CANARY_SOURCE_ERROR",
    }
    (out / "collector_ebay_valid_high_recall_canary_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if source_errors == 0 else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
