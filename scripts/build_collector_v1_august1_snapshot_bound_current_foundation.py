from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
ACTIVE = ROOT / "data/governance/permanence/authority/collector_v1_current_data_authority_active.json"
MANIFEST = ROOT / "data/governance/permanence/snapshots" / SNAPSHOT_ID / "collector_snapshot_manifest.json"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_august1_snapshot_bound_current_foundation"
KEY = "tcgplayer_product_id"

ALIASES = {
    "price": ("market_price", "current_price", "certified_current_price", "price"),
    "price_time": ("source_observation_at_utc", "collected_at", "collected_at_utc", "observation_date", "latest_price_date"),
    "listing_count": ("accepted_listing_count", "listing_count", "active_listing_count"),
    "route": ("forecast_method", "forecast_route", "resolved_route", "route", "tournament_lane"),
    "product_name": ("product_name", "canonical_product_name", "name"),
    "history_date": ("observation_date", "date", "price_date", "as_of_date", "timestamp"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def pick(frame: pd.DataFrame, names: tuple[str, ...], label: str) -> str:
    found = [name for name in names if name in frame.columns]
    if len(found) != 1:
        raise RuntimeError(f"Expected exactly one {label}; found {found}")
    return found[0]


def load_csv(path: Path, role: str) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {role} authority: {path}")
    frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
    if KEY not in frame.columns:
        raise RuntimeError(f"{role} authority missing {KEY}")
    frame[KEY] = frame[KEY].astype(str).str.strip()
    if frame[KEY].eq("").any():
        raise RuntimeError(f"{role} authority has blank product IDs")
    return frame


def collapse_unique(frame: pd.DataFrame, role: str, universe: set[str]) -> pd.DataFrame:
    frame = frame[frame[KEY].isin(universe)].copy()
    if frame.empty:
        raise RuntimeError(f"{role} authority has no governed products")
    duplicated = frame[frame.duplicated(KEY, keep=False)]
    if not duplicated.empty:
        conflicts = []
        for product_id, block in duplicated.groupby(KEY):
            if len(block.drop_duplicates()) > 1:
                conflicts.append(str(product_id))
        if conflicts:
            raise RuntimeError(f"{role} authority has conflicting duplicate rows for {conflicts[:10]}")
        frame = frame.drop_duplicates(KEY)
    if set(frame[KEY]) != universe:
        missing = sorted(universe - set(frame[KEY]))
        extra = sorted(set(frame[KEY]) - universe)
        raise RuntimeError(f"{role} authority coverage mismatch missing={missing[:10]} extra={extra[:10]}")
    return frame.sort_values(KEY).reset_index(drop=True)


def prefixed(frame: pd.DataFrame, role: str) -> pd.DataFrame:
    return frame.rename(columns={column: f"{role}__{column}" for column in frame.columns if column != KEY})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    checks: dict[str, bool] = {}
    failures: list[str] = []
    generated = datetime.now(timezone.utc).isoformat()
    try:
        active = json.loads(ACTIVE.read_text(encoding="utf-8-sig"))
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
        checks["active_authority_status"] = active.get("status") == "ACTIVE_AUGUST1_SNAPSHOT_BOUND_MODEL_INPUT_AUTHORITY"
        checks["active_snapshot_matches"] = active.get("source_snapshot_id") == SNAPSHOT_ID
        checks["model_input_authorized"] = active.get("model_input_authorized") is True
        checks["purchase_remains_blocked"] = active.get("purchase_recommendations_authorized") is False

        by_role = {str(item.get("role")): item for item in manifest.get("files", []) if isinstance(item, dict)}
        paths = {
            "price": ROOT / str(active["price_authority"]),
            "identity": ROOT / str(by_role["current_authority"]["path"]),
            "listing": ROOT / str(active["listing_authority"]),
            "supply": ROOT / str(active["supply_authority"]),
            "route": ROOT / str(active["route_authority"]),
            "history": ROOT / str(active["historical_authority"]),
            "feature": ROOT / str(active["feature_authority"]),
        }
        expected_hashes = {
            "price": str(json.loads((ROOT / "data/governance/permanence/certification/collector_v1_august1_price_observation_lineage/collector_v1_august1_price_observation_lineage_summary.json").read_text(encoding="utf-8"))["lineage_enriched_price_authority_sha256"]),
            "identity": str(by_role["current_authority"]["sha256"]),
            "listing": str(by_role["ebay_listing_ledger"]["sha256"]),
            "supply": str(by_role["ebay_supply_snapshot"]["sha256"]),
            "route": str(by_role["canonical_routes"]["sha256"]),
            "history": str(by_role["canonical_history"]["sha256"]),
            "feature": str(by_role["feature_matrix"]["sha256"]),
        }
        actual_hashes = {role: sha256(path) for role, path in paths.items()}
        for role in paths:
            checks[f"{role}_hash_matches"] = actual_hashes[role] == expected_hashes[role]

        identity = load_csv(paths["identity"], "identity")
        if identity[KEY].duplicated().any() or len(identity) != 50:
            raise RuntimeError("Identity authority must contain exactly 50 unique products")
        universe = set(identity[KEY])
        identity = collapse_unique(identity, "identity", universe)
        price = collapse_unique(load_csv(paths["price"], "price"), "price", universe)
        supply = collapse_unique(load_csv(paths["supply"], "supply"), "supply", universe)
        route = collapse_unique(load_csv(paths["route"], "route"), "route", universe)
        feature = collapse_unique(load_csv(paths["feature"], "feature"), "feature", universe)
        listing = load_csv(paths["listing"], "listing")
        listing = listing[listing[KEY].isin(universe)].copy()
        history = load_csv(paths["history"], "history")
        history = history[history[KEY].isin(universe)].copy()

        price_col = pick(price, ALIASES["price"], "price column")
        time_col = pick(price, ALIASES["price_time"], "price observation timestamp")
        listing_count_col = pick(supply, ALIASES["listing_count"], "accepted listing count")
        route_col = pick(route, ALIASES["route"], "forecast route")
        name_candidates = [name for name in ALIASES["product_name"] if name in identity.columns]
        name_col = name_candidates[0] if name_candidates else None
        history_date_col = pick(history, ALIASES["history_date"], "history date")

        price[price_col] = pd.to_numeric(price[price_col], errors="coerce")
        supply[listing_count_col] = pd.to_numeric(supply[listing_count_col], errors="coerce")
        checks["all_prices_positive"] = price[price_col].notna().all() and price[price_col].gt(0).all()
        checks["all_price_timestamps_present"] = price[time_col].astype(str).str.strip().ne("").all()
        checks["all_listing_counts_nonnegative"] = supply[listing_count_col].notna().all() and supply[listing_count_col].ge(0).all()
        checks["all_routes_present"] = route[route_col].astype(str).str.strip().ne("").all()
        checks["accepted_listing_ledger_reconciles"] = int(supply[listing_count_col].sum()) == len(listing)

        history[history_date_col] = pd.to_datetime(history[history_date_col], errors="coerce", utc=True)
        if history[history_date_col].isna().any():
            raise RuntimeError("Historical authority contains unparseable observation dates")
        history_agg = history.groupby(KEY).agg(
            history_observation_count=(history_date_col, "size"),
            history_first_observation_at_utc=(history_date_col, "min"),
            history_latest_observation_at_utc=(history_date_col, "max"),
        ).reset_index()
        if set(history_agg[KEY]) != universe:
            raise RuntimeError("Historical authority does not cover all 50 products")
        for column in ("history_first_observation_at_utc", "history_latest_observation_at_utc"):
            history_agg[column] = history_agg[column].dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        foundation = prefixed(identity, "identity")
        for role, frame in (("price", price), ("supply", supply), ("route", route), ("feature", feature)):
            foundation = foundation.merge(prefixed(frame, role), on=KEY, how="left", validate="one_to_one")
        foundation = foundation.merge(history_agg, on=KEY, how="left", validate="one_to_one")
        foundation["product_name"] = foundation[f"identity__{name_col}"] if name_col else ""
        foundation["current_price"] = foundation[f"price__{price_col}"]
        foundation["source_observation_at_utc"] = foundation[f"price__{time_col}"]
        foundation["accepted_listing_count"] = foundation[f"supply__{listing_count_col}"]
        foundation["forecast_route"] = foundation[f"route__{route_col}"]
        foundation["source_snapshot_id"] = SNAPSHOT_ID
        foundation["source_bundle_sha256"] = str(active["source_bundle_sha256"])
        foundation["source_price_authority_sha256"] = str(active["source_price_authority_sha256"])
        foundation["source_listing_authority_sha256"] = expected_hashes["listing"]
        foundation["source_feature_authority_sha256"] = expected_hashes["feature"]
        foundation["source_identity_authority_sha256"] = expected_hashes["identity"]
        foundation["source_supply_authority_sha256"] = expected_hashes["supply"]
        foundation["source_route_authority_sha256"] = expected_hashes["route"]
        foundation["source_history_authority_sha256"] = expected_hashes["history"]
        foundation["model_generated_at_utc"] = generated
        foundation["purchase_recommendation_authorized"] = False

        checks["foundation_has_50_rows"] = len(foundation) == 50
        checks["foundation_product_ids_unique"] = not foundation[KEY].duplicated().any()
        checks["all_history_present"] = foundation["history_observation_count"].gt(0).all()
        checks["all_required_lineage_present"] = foundation[[
            "source_snapshot_id", "source_bundle_sha256", "source_price_authority_sha256",
            "source_listing_authority_sha256", "source_feature_authority_sha256", "model_generated_at_utc"
        ]].astype(str).apply(lambda col: col.str.strip().ne("").all()).all()

        failures = [name for name, passed in checks.items() if not bool(passed)]
        passed = not failures
        OUT.mkdir(parents=True, exist_ok=True)
        out_csv = OUT / "collector_v1_august1_snapshot_bound_current_foundation.csv"
        foundation.sort_values(KEY).to_csv(out_csv, index=False)
        summary = {
            "block_name": "Collector V1 August 1 Snapshot-Bound Current Foundation",
            "block_version": "1.0.0",
            "generated_at_utc": generated,
            "source_snapshot_id": SNAPSHOT_ID,
            "source_bundle_sha256": active["source_bundle_sha256"],
            "authority_paths": {role: str(path.relative_to(ROOT)) for role, path in paths.items()},
            "authority_sha256": actual_hashes,
            "foundation_path": str(out_csv.relative_to(ROOT)),
            "foundation_sha256": sha256(out_csv),
            "foundation_rows": len(foundation),
            "accepted_listing_rows": len(listing),
            "canonical_history_rows": len(history),
            "checks": checks,
            "critical_failures": failures,
            "current_foundation_certified_input_ready": passed,
            "forecast_ranking_rebuild_authorized": passed,
            "production_forecasting_authorized": False,
            "purchase_recommendations_authorized": False,
            "uip_delivery_authorized": False,
            "status": "PASS_COLLECTOR_V1_AUGUST1_SNAPSHOT_BOUND_CURRENT_FOUNDATION" if passed else "FAIL_COLLECTOR_V1_AUGUST1_SNAPSHOT_BOUND_CURRENT_FOUNDATION",
        }
    except Exception as exc:
        passed = False
        summary = {
            "block_name": "Collector V1 August 1 Snapshot-Bound Current Foundation",
            "block_version": "1.0.0",
            "generated_at_utc": generated,
            "source_snapshot_id": SNAPSHOT_ID,
            "checks": checks,
            "critical_failures": [str(exc)],
            "current_foundation_certified_input_ready": False,
            "forecast_ranking_rebuild_authorized": False,
            "production_forecasting_authorized": False,
            "purchase_recommendations_authorized": False,
            "uip_delivery_authorized": False,
            "status": "FAIL_COLLECTOR_V1_AUGUST1_SNAPSHOT_BOUND_CURRENT_FOUNDATION",
        }
        OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "collector_v1_august1_snapshot_bound_current_foundation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
