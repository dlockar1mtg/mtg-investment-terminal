from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_walk_forward_replay_foundation_v1.json"

ID_COLUMNS = ["canonical_tcgplayer_product_id", "product_id", "tcgplayer_product_id"]
NAME_COLUMNS = ["product_name", "name"]
DATE_COLUMNS = ["observation_date", "price_date", "date", "as_of_date", "snapshot_date"]
KNOWLEDGE_COLUMNS = ["knowledge_date", "available_date", "captured_at", "capture_timestamp"]
PRICE_COLUMNS = ["price", "market_price", "current_price", "observed_price", "value"]


def first_present(columns: list[str], candidates: list[str]) -> str | None:
    lowered = {str(c).lower(): str(c) for c in columns}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_sources() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    roots = [ROOT / "data", ROOT / "outputs"]
    for base in roots:
        if not base.exists():
            continue
        for path in base.rglob("*.csv"):
            rel = path.relative_to(ROOT).as_posix()
            lowered = rel.lower()
            if any(token in lowered for token in ["archive/", "repair/", "superseded/"]):
                continue
            try:
                sample = pd.read_csv(path, nrows=10, low_memory=False)
            except Exception:
                continue
            cols = list(sample.columns)
            id_col = first_present(cols, ID_COLUMNS)
            name_col = first_present(cols, NAME_COLUMNS)
            date_col = first_present(cols, DATE_COLUMNS)
            knowledge_col = first_present(cols, KNOWLEDGE_COLUMNS)
            price_col = first_present(cols, PRICE_COLUMNS)
            score = sum(x is not None for x in [id_col or name_col, date_col, price_col])
            if score < 3:
                continue
            rows.append({
                "path": rel,
                "sha256": sha256(path),
                "id_column": id_col,
                "name_column": name_col,
                "observation_date_column": date_col,
                "knowledge_date_column": knowledge_col,
                "price_column": price_col,
                "explicit_knowledge_date_available": knowledge_col is not None,
                "source_candidate_status": "POINT_IN_TIME_CANDIDATE" if knowledge_col else "OBSERVATION_DATE_ONLY_REVIEW_REQUIRED",
            })
    return pd.DataFrame(rows)


def load_best_ledger(inventory: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    if inventory.empty:
        return pd.DataFrame(), ""
    ranked = inventory.copy()
    ranked["rank"] = ranked["explicit_knowledge_date_available"].astype(int) * 100
    ranked["rank"] += ranked["path"].str.lower().str.contains("collector").astype(int) * 20
    ranked["rank"] += ranked["path"].str.lower().str.contains("ledger|history|observation", regex=True).astype(int) * 10
    ranked = ranked.sort_values(["rank", "path"], ascending=[False, True])
    for _, meta in ranked.iterrows():
        path = ROOT / str(meta["path"])
        try:
            df = pd.read_csv(path, low_memory=False)
        except Exception:
            continue
        id_col = meta["id_column"] if pd.notna(meta["id_column"]) else None
        name_col = meta["name_column"] if pd.notna(meta["name_column"]) else None
        date_col = str(meta["observation_date_column"])
        price_col = str(meta["price_column"])
        knowledge_col = meta["knowledge_date_column"] if pd.notna(meta["knowledge_date_column"]) else None
        work = pd.DataFrame({
            "product_key": df[id_col].astype(str) if id_col else df[name_col].astype(str),
            "product_name": df[name_col].astype(str) if name_col else df[id_col].astype(str),
            "observation_date": pd.to_datetime(df[date_col], errors="coerce", utc=True).dt.tz_localize(None),
            "knowledge_date": pd.to_datetime(df[knowledge_col], errors="coerce", utc=True).dt.tz_localize(None) if knowledge_col else pd.to_datetime(df[date_col], errors="coerce", utc=True).dt.tz_localize(None),
            "price": pd.to_numeric(df[price_col], errors="coerce"),
        }).dropna(subset=["product_key", "observation_date", "knowledge_date", "price"])
        work = work[work["price"] > 0].copy()
        if len(work) >= 100:
            return work, str(meta["path"])
    return pd.DataFrame(), ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    out = ROOT / cfg["output_directory"]
    out.mkdir(parents=True, exist_ok=True)

    inventory = discover_sources()
    inventory.to_csv(out / "collector_walk_forward_source_inventory.csv", index=False)
    ledger, selected_source = load_best_ledger(inventory)

    failures: list[str] = []
    if ledger.empty:
        failures.append("no_usable_point_in_time_price_ledger")
        schedule = pd.DataFrame()
        matrix = pd.DataFrame()
        outcomes = pd.DataFrame()
    else:
        leakage_rows = ledger[ledger["knowledge_date"] < ledger["observation_date"]]
        if not leakage_rows.empty:
            failures.append("knowledge_date_before_observation_date")
        start = ledger["knowledge_date"].min().to_period("M").to_timestamp("M")
        end = ledger["knowledge_date"].max().to_period("M").to_timestamp("M")
        cutoffs = pd.date_range(start, end, freq="ME")
        schedule = pd.DataFrame({"decision_cutoff": cutoffs})
        schedule["cutoff_status"] = "HISTORICAL_REPLAY_CANDIDATE"
        matrix_rows: list[dict[str, object]] = []
        outcome_rows: list[dict[str, object]] = []
        horizons = [int(x) for x in cfg["outcome_horizons_days"]]
        slippage = int(cfg["maximum_outcome_date_slippage_days"])
        for cutoff in cutoffs:
            available = ledger[ledger["knowledge_date"] <= cutoff]
            for product_key, group in available.groupby("product_key"):
                group = group.sort_values("observation_date")
                entry = group[group["observation_date"] <= cutoff].tail(1)
                if entry.empty:
                    continue
                entry_row = entry.iloc[0]
                history_days = int((cutoff - group["observation_date"].min()).days)
                eligible = history_days >= int(cfg["minimum_history_days"])
                matrix_rows.append({
                    "decision_cutoff": cutoff,
                    "product_key": product_key,
                    "product_name": entry_row["product_name"],
                    "entry_observation_date": entry_row["observation_date"],
                    "entry_knowledge_date": entry_row["knowledge_date"],
                    "entry_price": entry_row["price"],
                    "available_observation_count": int(len(group)),
                    "available_history_days": history_days,
                    "replay_eligible": eligible,
                    "future_information_used": False,
                })
                if not eligible:
                    continue
                future = ledger[(ledger["product_key"] == product_key) & (ledger["observation_date"] > cutoff)].sort_values("observation_date")
                for horizon in horizons:
                    target = cutoff + pd.Timedelta(days=horizon)
                    candidates = future[(future["observation_date"] >= target) & (future["observation_date"] <= target + pd.Timedelta(days=slippage))]
                    if candidates.empty:
                        continue
                    realized = candidates.iloc[0]
                    realized_return = float(realized["price"] / entry_row["price"] - 1)
                    outcome_rows.append({
                        "decision_cutoff": cutoff,
                        "product_key": product_key,
                        "product_name": entry_row["product_name"],
                        "entry_price": entry_row["price"],
                        "horizon_days": horizon,
                        "target_outcome_date": target,
                        "realized_observation_date": realized["observation_date"],
                        "realized_price": realized["price"],
                        "realized_return": realized_return,
                        "outcome_held_out_from_decision_inputs": bool(realized["knowledge_date"] > cutoff),
                    })
        matrix = pd.DataFrame(matrix_rows)
        outcomes = pd.DataFrame(outcome_rows)
        if not outcomes.empty and not outcomes["outcome_held_out_from_decision_inputs"].all():
            failures.append("outcome_not_held_out")

    schedule.to_csv(out / "collector_walk_forward_decision_schedule.csv", index=False)
    matrix.to_csv(out / "collector_walk_forward_eligibility_matrix.csv", index=False)
    outcomes.to_csv(out / "collector_walk_forward_outcome_availability.csv", index=False)

    summary = {
        "audit_name": "Collector Leakage-Safe Walk-Forward Replay Foundation",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "selected_price_ledger": selected_source,
        "source_candidate_count": int(len(inventory)),
        "decision_cutoff_count": int(len(schedule)),
        "eligible_product_cutoff_count": int(matrix["replay_eligible"].sum()) if not matrix.empty else 0,
        "available_outcome_count": int(len(outcomes)),
        "available_90_day_outcome_count": int((outcomes["horizon_days"] == 90).sum()) if not outcomes.empty else 0,
        "available_180_day_outcome_count": int((outcomes["horizon_days"] == 180).sum()) if not outcomes.empty else 0,
        "available_365_day_outcome_count": int((outcomes["horizon_days"] == 365).sum()) if not outcomes.empty else 0,
        "future_information_prohibited": True,
        "today_candidate_outputs_used_as_historical_inputs": False,
        "freeze_suspended_pending_walk_forward": True,
        "historical_forecasts_generated": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "failure_count": len(failures),
        "failures": failures,
        "governing_note": "This batch proves whether a point-in-time replay is feasible and creates leakage-safe cutoffs and held-out outcomes. It does not yet generate historical model forecasts or claim accuracy.",
    }
    (out / "collector_walk_forward_replay_foundation_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
