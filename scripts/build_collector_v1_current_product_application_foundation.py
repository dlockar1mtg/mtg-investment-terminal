from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DECISION_DIR = ROOT / "data/governance/permanence/certification/collector_v1_decision_readiness_tournament"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_current_product_application_foundation"

BOUNDED_ROOTS = [
    ROOT / "data/governance/permanence/certification",
    ROOT / "data",
    ROOT / "artifacts/weekend_readiness",
]

ID_COLUMNS = ["tcgplayer_product_id", "product_id", "asset_id", "id"]
NAME_COLUMNS = ["product_name", "name", "asset_name", "set_name"]
PRICE_COLUMNS = [
    "current_price", "market_price", "latest_price", "price", "cutoff_price",
    "tcgplayer_market_price", "observed_price", "price_usd",
]
DATE_COLUMNS = [
    "price_date", "as_of_date", "observation_date", "cutoff_date", "snapshot_date",
    "date", "month", "timestamp",
]
ROUTE_COLUMNS = ["resolved_route", "forecast_route", "route", "tournament_lane", "forecast_method"]
HISTORY_COLUMNS = ["history_months", "history_months_at_cutoff", "months_history", "age_months"]
RELEASE_COLUMNS = ["release_date", "released_at", "first_release_date"]
SCARCITY_COLUMNS = ["supply_scarcity_index_v1a", "ssi_v1a", "scarcity_score", "scarcity_tier"]
LIQUIDITY_COLUMNS = ["accepted_listing_count", "listing_count", "liquidity_score", "availability_tier"]

EXPECTED_ROUTES = {
    "COMPARABLE_PRODUCT_ADJUSTED",
    "DIRECT_HISTORY_CALIBRATED",
    "DIRECT_HISTORY_LIMITED",
    "EARLY_OPPORTUNITY_COHORT_FALLBACK",
}


def first_present(columns: list[str], candidates: list[str]) -> str | None:
    lookup = {str(c).lower(): str(c) for c in columns}
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_header(path: Path) -> list[str]:
    try:
        return pd.read_csv(path, nrows=0).columns.astype(str).tolist()
    except Exception:
        return []


def row_count(path: Path) -> int:
    try:
        return int(len(pd.read_csv(path, usecols=[0])))
    except Exception:
        return -1


def newest_snapshot(frame: pd.DataFrame, id_col: str, date_col: str | None) -> pd.DataFrame:
    work = frame.copy()
    work[id_col] = work[id_col].astype(str)
    if date_col and date_col in work.columns:
        work["__date"] = pd.to_datetime(work[date_col], errors="coerce", utc=True)
        work = work.sort_values([id_col, "__date"]).drop_duplicates(id_col, keep="last")
    else:
        work = work.drop_duplicates(id_col, keep="last")
    return work


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    cert_path = DECISION_DIR / "collector_v1_decision_readiness_tournament_certification.json"
    if not cert_path.exists():
        raise FileNotFoundError(cert_path)
    decision_cert = json.loads(cert_path.read_text(encoding="utf-8"))
    if decision_cert.get("current_product_application_authorized") is not True:
        raise RuntimeError("Decision-readiness certification does not authorize current-product application")

    csv_paths: list[Path] = []
    seen: set[str] = set()
    for bounded_root in BOUNDED_ROOTS:
        if not bounded_root.exists():
            continue
        for path in bounded_root.rglob("*.csv"):
            resolved = str(path.resolve())
            if resolved in seen or OUT_DIR in path.parents:
                continue
            seen.add(resolved)
            csv_paths.append(path)

    inventory_rows: list[dict] = []
    for path in sorted(csv_paths):
        columns = read_header(path)
        if not columns:
            continue
        id_col = first_present(columns, ID_COLUMNS)
        name_col = first_present(columns, NAME_COLUMNS)
        price_col = first_present(columns, PRICE_COLUMNS)
        date_col = first_present(columns, DATE_COLUMNS)
        route_col = first_present(columns, ROUTE_COLUMNS)
        history_col = first_present(columns, HISTORY_COLUMNS)
        release_col = first_present(columns, RELEASE_COLUMNS)
        scarcity_col = first_present(columns, SCARCITY_COLUMNS)
        liquidity_col = first_present(columns, LIQUIDITY_COLUMNS)
        rows = row_count(path)
        universe_score = int(bool(id_col)) * 4 + int(bool(name_col)) * 3 + int(40 <= rows <= 60) * 3
        price_score = int(bool(id_col)) * 3 + int(bool(price_col)) * 5 + int(bool(date_col)) * 2 + int(rows >= 40) * 1
        route_score = int(bool(id_col)) * 3 + int(bool(route_col)) * 5 + int(rows >= 40) * 1
        feature_score = (
            int(bool(id_col)) * 2 + int(bool(history_col)) * 2 + int(bool(release_col)) * 1
            + int(bool(scarcity_col)) * 2 + int(bool(liquidity_col)) * 2 + int(bool(price_col)) * 1
        )
        inventory_rows.append({
            "path": str(path.relative_to(ROOT)),
            "rows": rows,
            "sha256": sha256(path),
            "id_column": id_col or "",
            "name_column": name_col or "",
            "price_column": price_col or "",
            "date_column": date_col or "",
            "route_column": route_col or "",
            "history_column": history_col or "",
            "release_column": release_col or "",
            "scarcity_column": scarcity_col or "",
            "liquidity_column": liquidity_col or "",
            "universe_score": universe_score,
            "price_score": price_score,
            "route_score": route_score,
            "feature_score": feature_score,
        })

    inventory = pd.DataFrame(inventory_rows)
    inventory.to_csv(OUT_DIR / "collector_v1_current_product_source_inventory.csv", index=False)

    def choose(role: str, score_col: str, minimum: int) -> dict | None:
        if inventory.empty:
            return None
        candidates = inventory[inventory[score_col] >= minimum].copy()
        if candidates.empty:
            return None
        candidates = candidates.sort_values([score_col, "rows", "path"], ascending=[False, False, True])
        candidates.to_csv(OUT_DIR / f"collector_v1_{role}_authority_candidates.csv", index=False)
        best_score = candidates.iloc[0][score_col]
        top = candidates[candidates[score_col] == best_score]
        # A role is considered unambiguous only when the best score has one candidate.
        if len(top) != 1:
            return None
        return top.iloc[0].to_dict()

    selected = {
        "product_universe": choose("product_universe", "universe_score", 7),
        "latest_price": choose("latest_price", "price_score", 8),
        "route_assignment": choose("route_assignment", "route_score", 8),
        "current_features": choose("current_features", "feature_score", 6),
    }

    authority_rows = []
    for role, item in selected.items():
        authority_rows.append({
            "authority_role": role,
            "resolved": item is not None,
            "path": "" if item is None else item["path"],
            "rows": 0 if item is None else int(item["rows"]),
            "sha256": "" if item is None else item["sha256"],
            "id_column": "" if item is None else item["id_column"],
            "name_column": "" if item is None else item["name_column"],
            "price_column": "" if item is None else item["price_column"],
            "date_column": "" if item is None else item["date_column"],
            "route_column": "" if item is None else item["route_column"],
        })
    authority_df = pd.DataFrame(authority_rows)
    authority_df.to_csv(OUT_DIR / "collector_v1_current_product_authority_manifest.csv", index=False)

    universe_products: set[str] = set()
    price_products: set[str] = set()
    route_products: set[str] = set()
    assigned_routes: set[str] = set()
    duplicate_price_products = 0
    stale_price_rows = 0

    if selected["product_universe"]:
        item = selected["product_universe"]
        frame = pd.read_csv(ROOT / item["path"])
        universe_products = set(frame[item["id_column"]].dropna().astype(str))

    if selected["latest_price"]:
        item = selected["latest_price"]
        frame = pd.read_csv(ROOT / item["path"])
        id_col, price_col, date_col = item["id_column"], item["price_column"], item["date_column"] or None
        frame[price_col] = pd.to_numeric(frame[price_col], errors="coerce")
        duplicate_price_products = int(frame[id_col].astype(str).duplicated().sum())
        latest = newest_snapshot(frame, id_col, date_col)
        price_products = set(latest.loc[latest[price_col].gt(0), id_col].dropna().astype(str))
        if date_col:
            dates = pd.to_datetime(latest[date_col], errors="coerce", utc=True)
            if dates.notna().any():
                newest = dates.max()
                stale_price_rows = int(((newest - dates).dt.days > 45).fillna(True).sum())

    if selected["route_assignment"]:
        item = selected["route_assignment"]
        frame = pd.read_csv(ROOT / item["path"])
        id_col, route_col = item["id_column"], item["route_column"]
        frame[route_col] = frame[route_col].astype(str)
        route_products = set(frame[id_col].dropna().astype(str))
        assigned_routes = set(frame[route_col].dropna().astype(str))

    expected_count = 50
    universe_count = len(universe_products)
    missing_price_products = sorted(universe_products - price_products)
    missing_route_products = sorted(universe_products - route_products)
    unknown_routes = sorted(assigned_routes - EXPECTED_ROUTES)

    checks = {
        "decision_readiness_certified": True,
        "all_four_authorities_resolved": all(item is not None for item in selected.values()),
        "governed_product_count_50": universe_count == expected_count,
        "all_products_have_positive_latest_price": bool(universe_products) and not missing_price_products,
        "all_products_have_route_assignment": bool(universe_products) and not missing_route_products,
        "all_routes_governed": not unknown_routes,
        "latest_price_duplicates_adjudicated": duplicate_price_products == 0 or bool(selected["latest_price"] and selected["latest_price"]["date_column"]),
        "latest_prices_within_45_days_of_authority_max": stale_price_rows == 0,
    }
    failures = [name for name, passed in checks.items() if not passed]
    ready = not failures

    diagnostics = {
        "missing_price_products": missing_price_products,
        "missing_route_products": missing_route_products,
        "unknown_routes": unknown_routes,
        "duplicate_price_rows_before_latest_selection": duplicate_price_products,
        "stale_latest_price_rows": stale_price_rows,
    }
    (OUT_DIR / "collector_v1_current_product_application_diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2), encoding="utf-8"
    )

    summary = {
        "block_name": "Collector V1 Current Product Application Foundation",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bounded_roots": [str(path.relative_to(ROOT)) for path in BOUNDED_ROOTS if path.exists()],
        "csv_files_examined": int(len(inventory)),
        "authorities_required": 4,
        "authorities_resolved": int(authority_df["resolved"].sum()),
        "governed_products": universe_count,
        "products_with_positive_latest_price": len(price_products & universe_products),
        "products_with_route_assignment": len(route_products & universe_products),
        "checks": checks,
        "critical_failures": failures,
        "current_product_application_foundation_ready": ready,
        "product_level_forecast_tournament_authorized_after_certification": ready,
        "product_ranking_certified": False,
        "maximum_purchase_prices_certified": False,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_CURRENT_PRODUCT_APPLICATION_FOUNDATION_READY" if ready else "PARTIAL_COLLECTOR_V1_CURRENT_PRODUCT_APPLICATION_FOUNDATION",
    }
    (OUT_DIR / "collector_v1_current_product_application_foundation_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if (ready or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
