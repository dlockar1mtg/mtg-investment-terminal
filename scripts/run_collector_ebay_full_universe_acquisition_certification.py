"""Run one governed 50-product Collector eBay acquisition-certification cycle.

This live block reuses the existing targeted query ladder and precision-v3-universal
matcher. It certifies only what the collector can prove: governed product coverage,
source completion at the product level, candidate ceilings, deduplication, and
matcher outcomes. It does not write continuity history or authorize investments.
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
AUTHORITY = ROOT / "data/governance/permanence/certification/collector_product_universe/collector_product_universe.csv"
REPLAY_SUMMARY = ROOT / "data/governance/permanence/certification/collector_ebay_canary_hardened_replay/collector_ebay_canary_hardened_replay_summary.json"
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_full_universe_acquisition"
LEGACY_OUT = ROOT / "data/validation/phase_10/ebay_matching"


def norm_id(value: object) -> str:
    text = str(value or "").strip()
    return text[:-2] if text.endswith(".0") else text


def pick_column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    raise RuntimeError(f"None of the required columns exist: {candidates}")


def _authority_score(path: Path) -> tuple[int, str]:
    value = str(path).replace("\\", "/").lower()
    score = 0
    for token, weight in (
        ("governance/permanence/certification", 100),
        ("collector", 40),
        ("authority", 30),
        ("universe", 25),
        ("packaging", 20),
        ("release", 10),
    ):
        if token in value:
            score += weight
    for token, weight in (
        ("ebay_full_universe_acquisition", -200),
        ("canary", -100),
        ("historical", -50),
        ("listing", -40),
        ("review", -40),
    ):
        if token in value:
            score += weight
    return score, value


def resolve_authority(requested: Path) -> tuple[Path | None, list[dict[str, object]]]:
    if requested.is_file():
        return requested.resolve(), [{"path": str(requested.resolve()), "selection": "EXPLICIT_PATH"}]

    candidates: list[dict[str, object]] = []
    search_roots = (
        ROOT / "data/governance/permanence/certification",
        ROOT / "data/validation",
        ROOT / "data",
    )
    seen: set[Path] = set()
    for search_root in search_roots:
        if not search_root.is_dir():
            continue
        for path in search_root.rglob("*.csv"):
            resolved = path.resolve()
            if resolved in seen or OUT.resolve() in resolved.parents:
                continue
            seen.add(resolved)
            try:
                frame = pd.read_csv(resolved, dtype=str, encoding="utf-8-sig", nrows=500).fillna("")
            except Exception:
                continue
            id_candidates = [column for column in ("tcgplayer_product_id", "product_id") if column in frame.columns]
            name_candidates = [column for column in ("governed_box_name", "box_name", "product_name", "name") if column in frame.columns]
            if not id_candidates or not name_candidates:
                continue
            id_col = id_candidates[0]
            name_col = name_candidates[0]
            ids = frame[id_col].map(norm_id)
            usable = frame.loc[ids.ne("") & frame[name_col].astype(str).str.strip().ne("")].copy()
            unique_ids = usable[id_col].map(norm_id).nunique()
            if unique_ids != 50:
                continue
            score, sortable_path = _authority_score(resolved)
            candidates.append({
                "path": str(resolved),
                "id_column": id_col,
                "name_column": name_col,
                "unique_product_ids": int(unique_ids),
                "score": score,
                "sortable_path": sortable_path,
            })

    if not candidates:
        return None, []
    candidates.sort(key=lambda row: (-int(row["score"]), str(row["sortable_path"])))
    return Path(str(candidates[0]["path"])), candidates


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run governed 50-product Collector eBay acquisition certification")
    p.add_argument("--authority", type=Path, default=AUTHORITY)
    p.add_argument("--output-dir", type=Path, default=OUT)
    p.add_argument("--limit-per-product", type=int, default=200)
    p.add_argument("--strict", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc)

    authority_path, authority_candidates = resolve_authority(args.authority)
    missing = [str(REPLAY_SUMMARY)] if not REPLAY_SUMMARY.is_file() else []
    if authority_path is None:
        missing.append(str(args.authority))
    credentials_ready = bool(os.getenv("EBAY_CLIENT_ID", "").strip() and os.getenv("EBAY_CLIENT_SECRET", "").strip())
    replay = json.loads(REPLAY_SUMMARY.read_text(encoding="utf-8")) if REPLAY_SUMMARY.is_file() else {}
    one_run_authorized = bool(replay.get("full_universe_collection_authorized"))
    if missing or not credentials_ready or not one_run_authorized:
        summary = {
            "block_name": "Collector eBay Full-Universe Acquisition Certification",
            "block_version": "1.0.1",
            "generated_at": generated.isoformat(),
            "missing_inputs": missing,
            "credentials_ready": credentials_ready,
            "hardened_replay_authorized_one_run": one_run_authorized,
            "authority_requested": str(args.authority),
            "authority_selected": str(authority_path) if authority_path else "",
            "authority_candidates": authority_candidates,
            "live_collection_executed": False,
            "status": "REQUIRED_INPUT_CREDENTIAL_OR_AUTHORIZATION_MISSING",
        }
        (out / "collector_ebay_full_universe_acquisition_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1 if args.strict else 0

    authority = pd.read_csv(authority_path, dtype=str, encoding="utf-8-sig").fillna("")
    id_col = pick_column(authority, ("tcgplayer_product_id", "product_id"))
    name_col = pick_column(authority, ("governed_box_name", "box_name", "product_name", "name"))
    authority[id_col] = authority[id_col].map(norm_id)
    authority = authority[authority[id_col].ne("") & authority[name_col].astype(str).str.strip().ne("")].drop_duplicates(id_col).copy()
    if len(authority) != 50:
        raise RuntimeError(f"Expected exactly 50 governed Collector products; found {len(authority)} in {authority_path}")

    target_map = out / "collector_ebay_full_universe_product_map.csv"
    pd.DataFrame({
        "tcgplayer_product_id": authority[id_col],
        "box_name": authority[name_col],
        "source_product_name": authority[name_col],
    }).to_csv(target_map, index=False)

    from terminal2.market_sources.ebay_precision_production import run_precision_targeted_coverage

    run_summary = run_precision_targeted_coverage(target_map, limit_per_product=args.limit_per_product)
    date = generated.date().isoformat()
    source_results = LEGACY_OUT / f"ebay_listing_match_results_{date}.csv"
    source_coverage = LEGACY_OUT / f"ebay_product_coverage_{date}.csv"
    source_universe = LEGACY_OUT / f"ebay_canonical_match_universe_{date}.csv"
    source_review = LEGACY_OUT / f"ebay_manual_review_{date}.csv"

    copied: dict[str, str] = {}
    for source, name in (
        (source_results, "collector_ebay_full_universe_listing_results.csv"),
        (source_coverage, "collector_ebay_full_universe_product_coverage.csv"),
        (source_universe, "collector_ebay_full_universe_match_universe.csv"),
        (source_review, "collector_ebay_full_universe_manual_review.csv"),
    ):
        if source.is_file():
            destination = out / name
            shutil.copy2(source, destination)
            copied[name] = str(source.relative_to(ROOT))

    if not source_results.is_file() or not source_coverage.is_file():
        raise RuntimeError("Targeted collector did not create expected result and coverage files")

    results = pd.read_csv(source_results, dtype=str, encoding="utf-8-sig").fillna("")
    coverage = pd.read_csv(source_coverage, dtype=str, encoding="utf-8-sig").fillna("")
    item_col = pick_column(results, ("ebay_item_id", "item_id"))
    canonical_id_col = pick_column(results, ("canonical_product_id",))
    coverage_id_col = pick_column(coverage, ("tcgplayer_product_id", "canonical_product_id"))

    results["resolved_tcgplayer_product_id"] = results[canonical_id_col].astype(str).str.replace("TCGPLAYER-", "", regex=False).map(norm_id)
    coverage["resolved_tcgplayer_product_id"] = coverage[coverage_id_col].astype(str).str.replace("TCGPLAYER-", "", regex=False).map(norm_id)

    duplicate_rows = int(results.duplicated(["resolved_tcgplayer_product_id", item_col]).sum())
    deduped = results.drop_duplicates(["resolved_tcgplayer_product_id", item_col]).copy()
    deduped.to_csv(out / "collector_ebay_full_universe_deduplicated_listing_results.csv", index=False)

    source_errors = int((coverage.get("coverage_state", pd.Series(dtype=str)) == "SOURCE_ERROR").sum())
    covered_ids = set(coverage["resolved_tcgplayer_product_id"].astype(str))
    authority_ids = set(authority[id_col].astype(str))
    missing_product_coverage = sorted(authority_ids - covered_ids)
    extra_product_coverage = sorted(covered_ids - authority_ids)

    results_found = pd.to_numeric(coverage.get("results_found", pd.Series([0] * len(coverage))), errors="coerce").fillna(0)
    ceiling_mask = results_found >= int(args.limit_per_product)
    ceiling_products = coverage.loc[ceiling_mask, "resolved_tcgplayer_product_id"].astype(str).tolist()
    manual_review_rows = int((deduped.get("match_state", pd.Series(dtype=str)) == "REVIEW").sum())
    accepted_rows = int((deduped.get("match_state", pd.Series(dtype=str)) == "ACCEPTED").sum())
    rejected_rows = int((deduped.get("match_state", pd.Series(dtype=str)) == "REJECTED").sum())

    product_rows: list[dict[str, object]] = []
    for _, row in authority.iterrows():
        pid = norm_id(row[id_col])
        subset = deduped[deduped["resolved_tcgplayer_product_id"] == pid]
        cov = coverage[coverage["resolved_tcgplayer_product_id"] == pid]
        product_rows.append({
            "tcgplayer_product_id": pid,
            "governed_box_name": row[name_col],
            "coverage_row_present": not cov.empty,
            "coverage_state": cov.iloc[0].get("coverage_state", "") if not cov.empty else "MISSING",
            "results_found": cov.iloc[0].get("results_found", "") if not cov.empty else "",
            "queries_used": cov.iloc[0].get("queries_used", "") if not cov.empty else "",
            "candidate_ceiling_reached": bool(not cov.empty and pd.to_numeric(pd.Series([cov.iloc[0].get("results_found", 0)]), errors="coerce").fillna(0).iloc[0] >= args.limit_per_product),
            "deduplicated_candidates": len(subset),
            "accepted_rows": int((subset.get("match_state", pd.Series(dtype=str)) == "ACCEPTED").sum()),
            "review_rows": int((subset.get("match_state", pd.Series(dtype=str)) == "REVIEW").sum()),
            "rejected_rows": int((subset.get("match_state", pd.Series(dtype=str)) == "REJECTED").sum()),
        })
    product_cert = pd.DataFrame(product_rows)
    product_cert.to_csv(out / "collector_ebay_full_universe_product_certification.csv", index=False)

    structural_pass = (
        len(authority) == 50
        and len(coverage) == 50
        and source_errors == 0
        and not missing_product_coverage
        and not extra_product_coverage
        and duplicate_rows >= 0
    )
    acquisition_recall_certified = structural_pass and not ceiling_products
    summary = {
        "block_name": "Collector eBay Full-Universe Acquisition Certification",
        "block_version": "1.0.1",
        "generated_at": generated.isoformat(),
        "live_collection_executed": True,
        "authority_requested": str(args.authority),
        "authority_selected": str(authority_path),
        "authority_candidates": authority_candidates,
        "governed_products": len(authority),
        "coverage_rows": len(coverage),
        "queries_used": run_summary.get("queries_used", 0),
        "raw_listing_rows": len(results),
        "deduplicated_listing_rows": len(deduped),
        "duplicate_product_item_rows_removed": duplicate_rows,
        "accepted_rows": accepted_rows,
        "review_rows": manual_review_rows,
        "rejected_rows": rejected_rows,
        "source_errors": source_errors,
        "missing_product_coverage": missing_product_coverage,
        "extra_product_coverage": extra_product_coverage,
        "limit_per_product": args.limit_per_product,
        "candidate_ceiling_products": ceiling_products,
        "pagination_completeness_claimed": False,
        "pagination_note": "The current targeted collector exposes product-level coverage and result counts, not page-level proof. Candidate ceilings fail acquisition recall certification.",
        "structural_coverage_passed": structural_pass,
        "acquisition_recall_certified": acquisition_recall_certified,
        "supply_baseline_authorized": acquisition_recall_certified,
        "continuity_accumulation_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "copied_artifacts": copied,
    }
    summary["status"] = (
        "PASS_FULL_UNIVERSE_ACQUISITION_CERTIFIED_BASELINE_READY"
        if acquisition_recall_certified
        else "REVIEW_FULL_UNIVERSE_ACQUISITION_CEILING_OR_COVERAGE_GAP"
    )
    (out / "collector_ebay_full_universe_acquisition_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if acquisition_recall_certified else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
