from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
ACTIVE = ROOT / "data/governance/permanence/authority/collector_v1_current_data_authority_active.json"
MANIFEST = ROOT / "data/governance/permanence/snapshots" / SNAPSHOT_ID / "collector_snapshot_manifest.json"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_august1_missing_history_coverage"
KEY = "tcgplayer_product_id"
BOUNDED_ROOTS = (
    ROOT / "data/governance/permanence/certification",
    ROOT / "data/operations",
    ROOT / "data/product_master",
    ROOT / "artifacts",
)


def load(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")


def first(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    return next((name for name in names if name in frame.columns), None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)

    active = json.loads(ACTIVE.read_text(encoding="utf-8-sig"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    by_role = {str(item.get("role")): item for item in manifest.get("files", []) if isinstance(item, dict)}

    identity = load(ROOT / str(by_role["current_authority"]["path"]))
    history = load(ROOT / str(active["historical_authority"]))
    route = load(ROOT / str(active["route_authority"]))
    price = load(ROOT / str(active["price_authority"]))

    for frame, role in ((identity, "identity"), (history, "history"), (route, "route"), (price, "price")):
        if KEY not in frame.columns:
            raise RuntimeError(f"{role} missing {KEY}")
        frame[KEY] = frame[KEY].astype(str).str.strip()

    universe = set(identity[KEY])
    history_products = set(history[KEY])
    missing = sorted(universe - history_products)
    extra = sorted(history_products - universe)

    name_col = first(identity, ("product_name", "canonical_product_name", "name"))
    route_col = first(route, ("forecast_method", "forecast_route", "resolved_route", "route", "tournament_lane"))
    price_col = first(price, ("market_price", "current_price", "certified_current_price", "price"))

    detail = identity[identity[KEY].isin(missing)].copy()
    keep = [KEY]
    if name_col:
        keep.append(name_col)
    detail = detail[keep]
    if route_col:
        detail = detail.merge(route[[KEY, route_col]].drop_duplicates(KEY), on=KEY, how="left")
    if price_col:
        detail = detail.merge(price[[KEY, price_col]].drop_duplicates(KEY), on=KEY, how="left")
    detail["history_coverage_status"] = "MISSING_CANONICAL_HISTORY"
    detail.to_csv(OUT / "collector_v1_august1_missing_history_products.csv", index=False)

    candidate_rows: list[dict[str, object]] = []
    if missing:
        for root in BOUNDED_ROOTS:
            if not root.exists():
                continue
            for path in root.rglob("*.csv"):
                if OUT in path.parents or path == ROOT / str(active["historical_authority"]):
                    continue
                try:
                    header = pd.read_csv(path, nrows=0, encoding="utf-8-sig").columns.astype(str).tolist()
                except Exception:
                    continue
                id_col = next((name for name in (KEY, "resolved_tcgplayer_product_id", "product_id") if name in header), None)
                date_col = next((name for name in ("observation_date_utc", "observation_date", "date", "price_date", "snapshot_date", "as_of_date", "observed_at", "timestamp") if name in header), None)
                price_candidate = next((name for name in ("market_price", "price", "value", "market", "median_price", "low_price") if name in header), None)
                if not id_col or not date_col or not price_candidate:
                    continue
                try:
                    frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig", usecols=[id_col, date_col, price_candidate]).fillna("")
                except Exception:
                    continue
                frame[id_col] = frame[id_col].astype(str).str.strip().str.removeprefix("TCGPLAYER-").str.removesuffix(".0")
                matched = frame[frame[id_col].isin(missing)]
                if matched.empty:
                    continue
                candidate_rows.append({
                    "path": str(path.relative_to(ROOT)),
                    "matched_missing_product_count": int(matched[id_col].nunique()),
                    "matched_row_count": int(len(matched)),
                    "id_column": id_col,
                    "date_column": date_col,
                    "price_column": price_candidate,
                    "matched_product_ids": "|".join(sorted(set(matched[id_col]))),
                })

    candidates = pd.DataFrame(candidate_rows)
    if not candidates.empty:
        candidates = candidates.sort_values(["matched_missing_product_count", "matched_row_count", "path"], ascending=[False, False, True])
    candidates.to_csv(OUT / "collector_v1_august1_missing_history_recovery_candidates.csv", index=False)

    summary = {
        "block_name": "Collector V1 August 1 Missing History Coverage Audit",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_snapshot_id": SNAPSHOT_ID,
        "governed_product_count": len(universe),
        "history_product_count": len(history_products & universe),
        "missing_history_product_count": len(missing),
        "missing_history_product_ids": missing,
        "extra_history_product_ids": extra,
        "recovery_candidate_file_count": int(len(candidates)),
        "current_foundation_authorized": len(missing) == 0,
        "forecast_ranking_rebuild_authorized": len(missing) == 0,
        "purchase_recommendations_authorized": False,
        "critical_failures": [] if not missing else ["canonical_history_missing_governed_products"],
        "status": "PASS_COLLECTOR_V1_AUGUST1_HISTORY_COVERAGE_COMPLETE" if not missing else "BLOCKED_COLLECTOR_V1_AUGUST1_HISTORY_COVERAGE_INCOMPLETE",
    }
    (OUT / "collector_v1_august1_missing_history_coverage_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if (not missing or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
