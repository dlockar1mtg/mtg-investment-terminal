"""Certify Collector V1 coherence using canonical route and daily-history inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CANON = ROOT / "data/governance/permanence/certification/collector_v1_canonical_inputs"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_canonical_data_coherence"
PATHS = {
    "canonical_summary": CANON / "collector_v1_canonical_inputs_summary.json",
    "routes": CANON / "collector_v1_canonical_forecast_routes.csv",
    "history": CANON / "collector_v1_canonical_daily_price_history.csv",
    "scarcity": ROOT / "data/governance/permanence/certification/collector_supply_scarcity_index_v1/collector_supply_scarcity_index_v1.csv",
    "release": ROOT / "data/governance/permanence/certification/collector_official_release_date_authority/collector_official_release_date_authority.csv",
    "comparables": ROOT / "data/operations/collector_comparable_selection/candidate_v1_0_0/collector_selected_comparables.csv",
    "horizons": ROOT / "config/mtg/governance/collector_v1_forecast_horizons.json",
}


def load(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")


def norm(value: object) -> str:
    text = str(value or "").strip().removeprefix("TCGPLAYER-")
    return text[:-2] if text.endswith(".0") else text


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def add(rows: list[dict], category: str, check: str, passed: bool, severity: str, details: str) -> None:
    rows.append({"category": category, "check": check, "passed": bool(passed), "severity": severity, "details": details})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    missing = [name for name, path in PATHS.items() if not path.is_file()]
    if missing:
        print(json.dumps({"status": "FAIL_REQUIRED_INPUTS_MISSING", "missing": missing}, indent=2))
        return 1 if args.strict else 0

    canon_summary = json.loads(PATHS["canonical_summary"].read_text(encoding="utf-8"))
    routes = load(PATHS["routes"])
    history = load(PATHS["history"])
    scarcity = load(PATHS["scarcity"])
    release = load(PATHS["release"])
    comparables = load(PATHS["comparables"])
    horizons = json.loads(PATHS["horizons"].read_text(encoding="utf-8"))
    checks: list[dict] = []
    exceptions: list[dict] = []

    route_ids = routes["tcgplayer_product_id"].map(norm)
    scarcity_ids = scarcity["tcgplayer_product_id"].map(norm)
    release_ids = release["tcgplayer_product_id"].map(norm)
    history_ids = history["tcgplayer_product_id"].map(norm)

    add(checks, "canonical", "canonical inputs passed", canon_summary.get("status") == "PASS_COLLECTOR_V1_CANONICAL_INPUTS_READY", "CRITICAL", str(canon_summary.get("status")))
    add(checks, "universe", "all 51 routes map to governed TCGplayer IDs", len(routes) == 51 and route_ids.ne("").all(), "CRITICAL", f"rows={len(routes)}, mapped={int(route_ids.ne('').sum())}")
    add(checks, "universe", "canonical route IDs are unique", not route_ids.duplicated().any(), "CRITICAL", f"duplicates={int(route_ids.duplicated().sum())}")

    routed_not_scarcity = sorted(set(route_ids) - set(scarcity_ids))
    scarcity_not_routed = sorted(set(scarcity_ids) - set(route_ids))
    for pid in routed_not_scarcity:
        row = routes[route_ids.eq(pid)].iloc[0]
        exceptions.append({
            "exception_type": "ROUTED_WITHOUT_EBAY_SCARCITY_V1",
            "tcgplayer_product_id": pid,
            "investment_product_id": row.get("investment_product_id", ""),
            "product_name": row.get("product_name", ""),
            "forecast_method": row.get("forecast_method", ""),
            "v1_missing_feature_policy": "SCARCITY_MISSING_WITH_CONFIDENCE_PENALTY_NO_IMPUTED_SCORE",
        })
    add(checks, "universe", "all 50 scarcity products are routed", len(scarcity_not_routed) == 0, "CRITICAL", f"scarcity_not_routed={scarcity_not_routed}")
    add(checks, "universe", "51-to-50 exception count is explicit", len(routed_not_scarcity) == 1, "CRITICAL", f"routed_without_scarcity={routed_not_scarcity}")

    add(checks, "history", "canonical history key is unique", not history.duplicated(subset=["tcgplayer_product_id", "observation_date_utc"]).any(), "CRITICAL", f"duplicates={int(history.duplicated(subset=['tcgplayer_product_id','observation_date_utc']).sum())}")
    prices = pd.to_numeric(history["market_price"], errors="coerce")
    add(checks, "history", "canonical prices are positive", prices.notna().all() and prices.gt(0).all(), "CRITICAL", f"invalid={int(prices.isna().sum() + prices.fillna(0).le(0).sum())}")
    dates = pd.to_datetime(history["observation_date_utc"], errors="coerce", utc=True)
    add(checks, "history", "canonical dates are valid", dates.notna().all(), "CRITICAL", f"invalid={int(dates.isna().sum())}")
    covered_routes = set(route_ids) & set(history_ids)
    add(checks, "history", "routed products intersect canonical history", len(covered_routes) > 0, "CRITICAL", f"covered={len(covered_routes)}/51")
    uncovered_routes = sorted(set(route_ids) - set(history_ids))
    add(checks, "history", "history coverage exceptions are explicit", True, "GOVERNED_GAP" if uncovered_routes else "INFO", f"uncovered={uncovered_routes}")

    release_covered = set(route_ids) & set(release_ids)
    add(checks, "release", "released authority intersects routes", len(release_covered) > 0, "CRITICAL", f"covered={len(release_covered)}/51")
    release_missing = sorted(set(route_ids) - set(release_ids))
    add(checks, "release", "release-authority exceptions are explicit", True, "GOVERNED_GAP" if release_missing else "INFO", f"missing={release_missing}")

    seller = pd.to_numeric(scarcity.get("observable_seller_count", pd.Series(dtype=float)), errors="coerce").fillna(0)
    seller_usable = bool(seller.gt(0).any())
    add(checks, "scarcity", "seller feature differentiates products", seller_usable, "GOVERNED_GAP", f"nonzero_products={int(seller.gt(0).sum())}")
    scarcity_score = pd.to_numeric(scarcity["supply_scarcity_index_v1"], errors="coerce")
    confidence = pd.to_numeric(scarcity["scarcity_confidence"], errors="coerce")
    adjusted = pd.to_numeric(scarcity["scarcity_adjusted_score"], errors="coerce")
    add(checks, "scarcity", "scarcity scores are coherent", scarcity_score.between(0,100).all() and confidence.between(0,1).all() and np.allclose(adjusted, scarcity_score * confidence, atol=0.01), "CRITICAL", "bounds and adjusted-score identity")

    method_col = "forecast_method"
    allowed = {"DIRECT_HISTORY_CALIBRATED", "DIRECT_HISTORY_LIMITED", "COMPARABLE_PRODUCT_ADJUSTED", "FUNDAMENTAL_COMPARABLE_HYBRID"}
    methods = set(routes[method_col].astype(str).str.strip())
    add(checks, "routing", "all methods are governed", methods <= allowed, "CRITICAL", f"methods={sorted(methods)}")

    comparable_key = next((c for c in ["target_investment_product_id", "investment_product_id", "target_product_id"] if c in comparables.columns), None)
    comparable_targets = set(routes.loc[routes[method_col].isin(["COMPARABLE_PRODUCT_ADJUSTED", "FUNDAMENTAL_COMPARABLE_HYBRID"]), "investment_product_id"])
    comparable_available = set(comparables[comparable_key].astype(str).str.strip()) if comparable_key else set()
    add(checks, "comparables", "comparable-routed products have peer evidence", comparable_key is not None and comparable_targets <= comparable_available, "CRITICAL", f"missing={sorted(comparable_targets-comparable_available)}")

    horizon_rows = horizons.get("horizons", horizons.get("forecast_horizons", []))
    found = set()
    for row in horizon_rows:
        value = row.get("days", row.get("horizon_days")) if isinstance(row, dict) else row
        try:
            found.add(int(value))
        except (TypeError, ValueError):
            pass
    required = {30,90,180,365,1095,1825}
    add(checks, "horizons", "all V1 horizons are defined", required <= found, "CRITICAL", f"found={sorted(found)}")

    critical = [row for row in checks if row["severity"] == "CRITICAL" and not row["passed"]]
    gaps = [row for row in checks if row["severity"] == "GOVERNED_GAP" and not row["passed"]]
    coherent = len(critical) == 0
    pd.DataFrame(checks).to_csv(OUT / "collector_v1_canonical_data_coherence_checks.csv", index=False)
    pd.DataFrame(exceptions).to_csv(OUT / "collector_v1_canonical_governed_exceptions.csv", index=False)
    summary = {
        "block_name": "Collector V1 Canonical Data Coherence",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "route_rows": int(len(routes)),
        "route_unique_tcgplayer_ids": int(route_ids.nunique()),
        "scarcity_product_rows": int(len(scarcity)),
        "routed_without_scarcity_v1": routed_not_scarcity,
        "scarcity_without_route": scarcity_not_routed,
        "canonical_history_rows": int(len(history)),
        "canonical_history_products": int(history_ids.nunique()),
        "history_uncovered_route_ids": uncovered_routes,
        "release_missing_route_ids": release_missing,
        "seller_feature_usable": seller_usable,
        "critical_failures": critical,
        "governed_gaps": gaps,
        "data_coherence_certified": coherent,
        "feature_matrix_authorized": coherent,
        "forecast_experiments_authorized": coherent,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "artifact_hashes": {name: sha256(path) for name, path in PATHS.items()},
        "status": "PASS_COLLECTOR_V1_CANONICAL_DATA_COHERENCE_WITH_GOVERNED_GAPS" if coherent else "FAIL_COLLECTOR_V1_CANONICAL_DATA_COHERENCE",
    }
    (OUT / "collector_v1_canonical_data_coherence_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if coherent else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
