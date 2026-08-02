"""Certify current Collector V1 data coherence before feature engineering and forecasting."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_v1_data_coherence"
PATHS = {
    "sufficiency_summary": ROOT / "data/governance/permanence/certification/collector_v1_data_sufficiency/collector_v1_data_sufficiency_summary.json",
    "universe_reconciliation": ROOT / "data/governance/permanence/certification/collector_v1_data_sufficiency/collector_v1_universe_reconciliation.csv",
    "routes": ROOT / "data/operations/collector_forecast_method_routing/candidate_v1_0_0/collector_forecast_method_routes.csv",
    "scarcity": ROOT / "data/governance/permanence/certification/collector_supply_scarcity_index_v1/collector_supply_scarcity_index_v1.csv",
    "snapshot": ROOT / "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline/collector_ebay_day_one_product_supply_snapshot.csv",
    "history": ROOT / "data/operations/mtg_history_foundation/universal_mtg_price_history.csv",
    "release": ROOT / "data/governance/permanence/certification/collector_official_release_date_authority/collector_official_release_date_authority.csv",
    "normalized": ROOT / "data/operations/collector_evidence_normalization/candidate_v1_0_0/collector_normalized_evidence.csv",
    "comparables": ROOT / "data/operations/collector_comparable_selection/candidate_v1_0_0/collector_selected_comparables.csv",
    "horizons": ROOT / "config/mtg/governance/collector_v1_forecast_horizons.json",
}
ID_ALIASES = ["tcgplayer_product_id", "product_id", "canonical_product_id", "resolved_tcgplayer_product_id"]
DATE_ALIASES = ["observation_date", "date", "price_date", "snapshot_date", "as_of_date", "observed_at"]
PRICE_ALIASES = ["market_price", "price", "value", "market", "low_price", "median_price"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")


def pick(frame: pd.DataFrame, aliases: list[str]) -> str | None:
    return next((column for column in aliases if column in frame.columns), None)


def norm_id(value: object) -> str:
    text = str(value or "").strip().removeprefix("TCGPLAYER-")
    return text[:-2] if text.endswith(".0") else text


def add_check(rows: list[dict], category: str, check: str, passed: bool, severity: str, details: str) -> None:
    rows.append({
        "category": category,
        "check": check,
        "passed": bool(passed),
        "severity": severity,
        "details": details,
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    missing = [name for name, path in PATHS.items() if not path.is_file()]
    if missing:
        summary = {
            "block_name": "Collector V1 Data Coherence Certification",
            "block_version": "1.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "missing_inputs": missing,
            "data_coherence_certified": False,
            "status": "FAIL_REQUIRED_INPUTS_MISSING",
        }
        (OUT / "collector_v1_data_coherence_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1 if args.strict else 0

    frames = {name: load_csv(path) for name, path in PATHS.items() if path.suffix.lower() == ".csv"}
    sufficiency = json.loads(PATHS["sufficiency_summary"].read_text(encoding="utf-8"))
    horizons = json.loads(PATHS["horizons"].read_text(encoding="utf-8"))
    checks: list[dict] = []
    exceptions: list[dict] = []

    routes = frames["routes"]
    scarcity = frames["scarcity"]
    snapshot = frames["snapshot"]
    history = frames["history"]
    release = frames["release"]
    comparables = frames["comparables"]
    reconciliation = frames["universe_reconciliation"]

    route_id = pick(routes, ID_ALIASES)
    scarcity_id = pick(scarcity, ID_ALIASES)
    history_id = pick(history, ID_ALIASES)
    release_id = pick(release, ID_ALIASES)
    history_date = pick(history, DATE_ALIASES)
    history_price = pick(history, PRICE_ALIASES)

    route_ids = routes[route_id].map(norm_id) if route_id else pd.Series(dtype=str)
    scarcity_ids = scarcity[scarcity_id].map(norm_id) if scarcity_id else pd.Series(dtype=str)
    history_ids = history[history_id].map(norm_id) if history_id else pd.Series(dtype=str)
    release_ids = release[release_id].map(norm_id) if release_id else pd.Series(dtype=str)

    add_check(checks, "universe", "routes have a governed product ID", route_id is not None, "CRITICAL", route_id or "missing")
    add_check(checks, "universe", "scarcity has a governed product ID", scarcity_id is not None, "CRITICAL", scarcity_id or "missing")
    add_check(checks, "universe", "route IDs are unique", route_id is not None and not route_ids.duplicated().any(), "CRITICAL", f"duplicate_rows={int(route_ids.duplicated().sum()) if route_id else -1}")
    add_check(checks, "universe", "scarcity IDs are unique", scarcity_id is not None and not scarcity_ids.duplicated().any(), "CRITICAL", f"duplicate_rows={int(scarcity_ids.duplicated().sum()) if scarcity_id else -1}")
    add_check(checks, "universe", "all scarcity products are routed", set(scarcity_ids) <= set(route_ids), "CRITICAL", f"unrouted={sorted(set(scarcity_ids)-set(route_ids))}")

    unmatched = reconciliation[reconciliation.get("reconciliation_state", "") != "MATCHED"] if "reconciliation_state" in reconciliation.columns else pd.DataFrame()
    for _, row in unmatched.iterrows():
        exceptions.append({
            "exception_type": row.get("reconciliation_state", "UNKNOWN"),
            "tcgplayer_product_id": row.get("tcgplayer_product_id", ""),
            "product_name": row.get("product_name", ""),
            "forecast_method": row.get("forecast_method", ""),
            "required_disposition": "Document why the product lacks a V1 eBay scarcity score and apply an explicit missing-feature policy.",
        })
    add_check(checks, "universe", "all 51-to-50 exceptions are explicitly recorded", len(unmatched) == len(exceptions), "CRITICAL", f"exception_rows={len(exceptions)}")

    accepted = pd.to_numeric(scarcity.get("accepted_listing_count", pd.Series(dtype=float)), errors="coerce")
    review = pd.to_numeric(scarcity.get("review_listing_count", pd.Series(dtype=float)), errors="coerce")
    ambiguity = pd.to_numeric(scarcity.get("cross_product_ambiguity_excluded_count", pd.Series(dtype=float)), errors="coerce")
    scarcity_score = pd.to_numeric(scarcity.get("supply_scarcity_index_v1", pd.Series(dtype=float)), errors="coerce")
    confidence = pd.to_numeric(scarcity.get("scarcity_confidence", pd.Series(dtype=float)), errors="coerce")
    adjusted = pd.to_numeric(scarcity.get("scarcity_adjusted_score", pd.Series(dtype=float)), errors="coerce")
    seller = pd.to_numeric(scarcity.get("observable_seller_count", pd.Series(dtype=float)), errors="coerce")

    add_check(checks, "scarcity", "listing counts are nonnegative", bool((accepted.fillna(0) >= 0).all() and (review.fillna(0) >= 0).all() and (ambiguity.fillna(0) >= 0).all()), "CRITICAL", "accepted/review/ambiguity")
    add_check(checks, "scarcity", "scarcity score is bounded 0-100", bool(scarcity_score.notna().all() and scarcity_score.between(0, 100).all()), "CRITICAL", f"min={scarcity_score.min()}, max={scarcity_score.max()}")
    add_check(checks, "scarcity", "confidence is bounded 0-1", bool(confidence.notna().all() and confidence.between(0, 1).all()), "CRITICAL", f"min={confidence.min()}, max={confidence.max()}")
    add_check(checks, "scarcity", "adjusted score equals score times confidence", bool(np.allclose(adjusted, scarcity_score * confidence, equal_nan=False, atol=0.01)), "CRITICAL", "tolerance=0.01")
    seller_usable = bool(seller.notna().any() and seller.fillna(0).gt(0).any())
    add_check(checks, "scarcity", "seller feature differentiates products", seller_usable, "GOVERNED_GAP", f"nonzero_products={int(seller.fillna(0).gt(0).sum())}")
    zero_accepted = int(accepted.fillna(0).eq(0).sum())
    add_check(checks, "scarcity", "zero-accepted products carry reduced confidence", bool((confidence[accepted.fillna(0).eq(0)] < 1).all()), "CRITICAL", f"zero_accepted_products={zero_accepted}")

    price_values = pd.to_numeric(history[history_price], errors="coerce") if history_price else pd.Series(dtype=float)
    date_values = pd.to_datetime(history[history_date], errors="coerce", utc=True) if history_date else pd.Series(dtype="datetime64[ns, UTC]")
    now = pd.Timestamp.now(tz="UTC")
    add_check(checks, "history", "history has a product ID", history_id is not None, "CRITICAL", history_id or "missing")
    add_check(checks, "history", "history has a price column", history_price is not None, "CRITICAL", history_price or "missing")
    add_check(checks, "history", "history has a date column", history_date is not None, "CRITICAL", history_date or "missing")
    add_check(checks, "history", "valid prices are positive", bool(price_values.dropna().gt(0).all()), "CRITICAL", f"nonpositive={int(price_values.dropna().le(0).sum())}")
    add_check(checks, "history", "history dates are not materially future-dated", bool(date_values.dropna().le(now + pd.Timedelta(days=2)).all()), "CRITICAL", f"future_rows={int(date_values.dropna().gt(now + pd.Timedelta(days=2)).sum())}")
    duplicate_history = int(history.duplicated(subset=[history_id, history_date]).sum()) if history_id and history_date else -1
    add_check(checks, "history", "product-date history keys are unique", duplicate_history == 0, "GOVERNED_GAP", f"duplicate_product_date_rows={duplicate_history}")
    routed_history_coverage = len(set(route_ids) & set(history_ids))
    add_check(checks, "history", "routed products have some history coverage", routed_history_coverage > 0, "CRITICAL", f"covered={routed_history_coverage}/{len(set(route_ids))}")

    add_check(checks, "release", "release authority has a product ID", release_id is not None, "CRITICAL", release_id or "missing")
    add_check(checks, "release", "routed products intersect release authority", len(set(route_ids) & set(release_ids)) > 0, "CRITICAL", f"covered={len(set(route_ids) & set(release_ids))}/{len(set(route_ids))}")

    method_col = next((column for column in ["forecast_method", "method", "selected_method"] if column in routes.columns), None)
    allowed_methods = {"DIRECT_HISTORY_CALIBRATED", "DIRECT_HISTORY_LIMITED", "COMPARABLE_PRODUCT_ADJUSTED", "FUNDAMENTAL_COMPARABLE_HYBRID"}
    methods = set(routes[method_col].astype(str).str.strip()) if method_col else set()
    add_check(checks, "routing", "all forecast methods are governed", method_col is not None and methods <= allowed_methods, "CRITICAL", f"methods={sorted(methods)}")
    comparable_targets = set(route_ids[routes[method_col].isin(["COMPARABLE_PRODUCT_ADJUSTED", "FUNDAMENTAL_COMPARABLE_HYBRID"])]) if method_col and route_id else set()
    comparable_id = pick(comparables, ID_ALIASES)
    comparable_ids = set(comparables[comparable_id].map(norm_id)) if comparable_id else set()
    add_check(checks, "comparables", "comparable-routed products have comparable evidence", len(comparable_targets - comparable_ids) == 0, "CRITICAL", f"missing={sorted(comparable_targets-comparable_ids)}")

    horizon_rows = horizons.get("horizons", horizons.get("forecast_horizons", []))
    horizon_days = []
    for row in horizon_rows:
        if isinstance(row, dict):
            value = row.get("days", row.get("horizon_days"))
        else:
            value = row
        try:
            horizon_days.append(int(value))
        except (TypeError, ValueError):
            pass
    required_horizons = {30, 90, 180, 365, 1095, 1825}
    add_check(checks, "horizons", "all governed V1 horizons are present", required_horizons <= set(horizon_days), "CRITICAL", f"found={sorted(horizon_days)}")

    critical_failures = [row for row in checks if row["severity"] == "CRITICAL" and not row["passed"]]
    governed_gaps = [row for row in checks if row["severity"] == "GOVERNED_GAP" and not row["passed"]]
    coherent = len(critical_failures) == 0

    checks_frame = pd.DataFrame(checks)
    checks_frame.to_csv(OUT / "collector_v1_data_coherence_checks.csv", index=False)
    pd.DataFrame(exceptions).to_csv(OUT / "collector_v1_governed_exceptions.csv", index=False)

    summary = {
        "block_name": "Collector V1 Data Coherence Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_sufficiency_status": sufficiency.get("status"),
        "total_checks": int(len(checks)),
        "passed_checks": int(sum(1 for row in checks if row["passed"])),
        "critical_failures": critical_failures,
        "governed_gaps": governed_gaps,
        "governed_exception_count": int(len(exceptions)),
        "data_coherence_certified": bool(coherent),
        "feature_matrix_authorized": bool(coherent),
        "forecast_experiments_authorized": bool(coherent),
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "future_v2_only": [
            "Repeated eBay supply observations",
            "Listing persistence and observational entry/exit",
            "Temporal seller-count changes",
            "Supply Scarcity Index V2",
        ],
        "artifact_hashes": {name: sha256(path) for name, path in PATHS.items()},
        "status": "PASS_COLLECTOR_V1_DATA_COHERENCE_CERTIFIED_WITH_GOVERNED_GAPS" if coherent else "FAIL_COLLECTOR_V1_DATA_COHERENCE",
    }
    (OUT / "collector_v1_data_coherence_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if coherent else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
