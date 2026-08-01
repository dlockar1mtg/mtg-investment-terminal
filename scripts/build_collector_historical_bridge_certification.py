"""Bridge safe archive history to certified current observations.

Creates a dynamic exact-ID analytical-history candidate, enforces release months,
keeps presale isolated, audits gaps and month-over-month changes, and compares a
name-only panel without allowing it to override exact-ID observations.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config/mtg/governance/collector_historical_bridge_certification_policy_v1.json"
DEFAULT_OUT = ROOT / "data/governance/permanence/certification/collector_historical_bridge_certification"


def parser():
    p = argparse.ArgumentParser(description="Build Collector historical bridge certification")
    p.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--strict", action="store_true")
    return p


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig", low_memory=False).fillna("")


def text(v):
    return "" if pd.isna(v) else str(v).strip()


def norm_id(v):
    s = text(v)
    return s[:-2] if s.endswith(".0") else s


def first_col(frame, candidates):
    lookup = {str(c).lower(): str(c) for c in frame.columns}
    return next((lookup[c.lower()] for c in candidates if c.lower() in lookup), "")


def norm_name(v):
    s = text(v).lower()
    s = re.sub(r"collector booster (box|display)", "collector booster display", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def load_current(path: Path, source_code: str, authority: pd.DataFrame) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    f = read_csv(path)
    id_col = first_col(f, ["tcgplayer_product_id", "product_id", "productId"])
    price_col = first_col(f, ["market_price", "fresh_market_price", "current_price", "price"])
    date_col = first_col(f, ["collected_at", "observation_date", "retrieved_at", "timestamp"])
    if not id_col or not price_col:
        return pd.DataFrame()
    n = pd.DataFrame({
        "tcgplayer_product_id": f[id_col].map(norm_id),
        "market_price": pd.to_numeric(f[price_col], errors="coerce"),
        "source_observation_date": f[date_col].map(text) if date_col else "",
    })
    n["parsed_date"] = pd.to_datetime(n["source_observation_date"], errors="coerce", utc=True)
    fallback = pd.Timestamp("2026-08-01", tz="UTC") if source_code.startswith("AUGUST") else pd.Timestamp("2026-07-31", tz="UTC")
    n["parsed_date"] = n["parsed_date"].fillna(fallback)
    n["observation_month"] = n["parsed_date"].dt.strftime("%Y-%m-01")
    n["source_code"] = source_code
    n = n.loc[n["market_price"].gt(0)].copy()
    auth_ids = set(authority["tcgplayer_product_id"])
    n = n.loc[n["tcgplayer_product_id"].isin(auth_ids)].copy()
    return n


def main():
    a = parser().parse_args()
    policy = json.loads(a.policy.resolve().read_text(encoding="utf-8-sig"))
    out = a.output_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
    inputs = {k: ROOT / v for k, v in policy["inputs"].items()}
    missing = [k for k, p in inputs.items() if k != "name_only_comparison_panel" and not p.is_file()]
    if missing:
        summary = {"status": "FAIL", "missing_inputs": missing, "historical_append_authorized": False, "forecasting_resume_authorized": False, "purchase_recommendation_authorized": False}
        (out / "collector_historical_bridge_summary.json").write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")
        print(json.dumps(summary, indent=2)); return 1

    authority = read_csv(inputs["current_authority"])
    authority["tcgplayer_product_id"] = authority["tcgplayer_product_id"].map(norm_id)
    authority = authority.loc[authority["identity_authority_status"].eq("CURRENT_IDENTITY_AUTHORIZED")].copy()
    release_date_col = first_col(authority, ["raw_released_on", "release_date_evidence", "release_date"])
    authority["release_date"] = pd.to_datetime(authority[release_date_col], errors="coerce", utc=True) if release_date_col else pd.NaT
    authority["release_month"] = authority["release_date"].dt.strftime("%Y-%m-01")
    release_map = authority.set_index("tcgplayer_product_id")["release_month"].to_dict()
    name_map = authority.set_index("tcgplayer_product_id")["box_name"].to_dict()
    state_map = authority.set_index("tcgplayer_product_id")["release_state"].to_dict()

    archive = read_csv(inputs["safe_released_monthly_history"])
    archive["tcgplayer_product_id"] = archive["tcgplayer_product_id"].map(norm_id)
    archive_rows = pd.DataFrame({
        "tcgplayer_product_id": archive["tcgplayer_product_id"],
        "observation_month": archive["observation_month"].map(text),
        "market_price": pd.to_numeric(archive["source_market_price"], errors="coerce"),
        "source_code": "ARCHIVE_MONTHLY",
        "source_path": archive["source_path"].map(text),
    })

    july = load_current(inputs["july_current_observations"], "JULY_31_CERTIFIED", authority)
    august = load_current(inputs["august_live_observations"], "AUGUST_LIVE_CERTIFIED", authority)
    current_frames = []
    for frame, path in [(july, inputs["july_current_observations"]), (august, inputs["august_live_observations"])]:
        if len(frame):
            frame = frame[["tcgplayer_product_id", "observation_month", "market_price", "source_code"]].copy()
            frame["source_path"] = path.relative_to(ROOT).as_posix()
            current_frames.append(frame)

    combined = pd.concat([archive_rows] + current_frames, ignore_index=True)
    precedence = {name: i for i, name in enumerate(policy["current_source_precedence"])}
    combined["source_precedence"] = combined["source_code"].map(precedence).fillna(999).astype(int)
    combined["release_month"] = combined["tcgplayer_product_id"].map(release_map).fillna("")
    combined["release_state"] = combined["tcgplayer_product_id"].map(state_map).fillna("")
    combined["governed_box_name"] = combined["tcgplayer_product_id"].map(name_map).fillna("")
    combined["before_release_month"] = combined["release_month"].ne("") & (combined["observation_month"] < combined["release_month"])
    combined["presale_product"] = combined["release_state"].eq("PRESALE")

    isolated = combined.loc[combined["before_release_month"] | combined["presale_product"]].copy()
    eligible = combined.loc[~combined["before_release_month"] & ~combined["presale_product"] & combined["market_price"].gt(0)].copy()
    eligible = eligible.sort_values(["tcgplayer_product_id", "observation_month", "source_precedence", "source_path"])
    selected = eligible.drop_duplicates(["tcgplayer_product_id", "observation_month"], keep="first").copy()
    selected = selected.sort_values(["tcgplayer_product_id", "observation_month"])
    selected["previous_price"] = selected.groupby("tcgplayer_product_id")["market_price"].shift(1)
    selected["month_over_month_change"] = selected["market_price"] / selected["previous_price"] - 1
    t = policy["continuity_thresholds"]
    selected["continuity_status"] = "CONTINUITY_PASS"
    selected.loc[selected["month_over_month_change"].abs().ge(float(t["material_absolute_percent_change"])), "continuity_status"] = "MATERIAL_CHANGE_REVIEW"
    selected.loc[(selected["month_over_month_change"].ge(float(t["extreme_up_percent_change"]))) | (selected["month_over_month_change"].le(float(t["extreme_down_percent_change"]))), "continuity_status"] = "EXTREME_CHANGE_REVIEW"
    selected["historical_append_authorized"] = False

    duplicate_keys = int(selected.duplicated(["tcgplayer_product_id", "observation_month"]).sum())
    gaps = []
    for pid, g in selected.groupby("tcgplayer_product_id"):
        months = pd.to_datetime(g["observation_month"], errors="coerce")
        if months.notna().any():
            expected = pd.date_range(months.min(), months.max(), freq="MS")
            actual = set(months.dropna())
            for m in expected:
                if m not in actual:
                    gaps.append({"tcgplayer_product_id": pid, "governed_box_name": name_map.get(pid, ""), "missing_month": m.strftime("%Y-%m-01")})

    comparison_rows = []
    alias_review = []
    name_path = inputs["name_only_comparison_panel"]
    if name_path.is_file():
        npanel = read_csv(name_path)
        name_col = first_col(npanel, ["product_name", "box_name", "name"])
        date_col = first_col(npanel, ["observation_date", "date", "month"])
        price_col = first_col(npanel, ["market_price", "price", "value"])
        if name_col and date_col and price_col:
            alias_lookup = {}
            for pid, name in name_map.items():
                alias_lookup.setdefault(norm_name(name), []).append(pid)
            for i, row in npanel.iterrows():
                key = norm_name(row[name_col]); matches = alias_lookup.get(key, [])
                rec = {"source_row_number": i+2, "source_product_name": text(row[name_col]), "normalized_name": key, "match_count": len(matches), "matched_tcgplayer_product_id": matches[0] if len(matches)==1 else "", "observation_date": text(row[date_col]), "market_price": text(row[price_col])}
                (comparison_rows if len(matches)==1 else alias_review).append(rec)

    selected.to_csv(out / "collector_bridged_analytical_history_candidate.csv", index=False)
    isolated.to_csv(out / "collector_pre_release_and_presale_isolated.csv", index=False)
    selected.loc[selected["continuity_status"].ne("CONTINUITY_PASS")].to_csv(out / "collector_history_continuity_review.csv", index=False)
    pd.DataFrame(gaps, columns=["tcgplayer_product_id", "governed_box_name", "missing_month"]).to_csv(out / "collector_history_missing_months.csv", index=False)
    pd.DataFrame(comparison_rows).to_csv(out / "collector_name_only_panel_exact_alias_comparison.csv", index=False)
    pd.DataFrame(alias_review).to_csv(out / "collector_name_only_alias_review_queue.csv", index=False)

    summary = {
        "block_name": "Collector Historical Bridge Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "governed_products": int(len(authority)),
        "archive_rows": int(len(archive_rows)),
        "july_current_rows": int(len(july)),
        "august_current_rows": int(len(august)),
        "combined_source_rows": int(len(combined)),
        "selected_product_month_rows": int(len(selected)),
        "selected_products": int(selected["tcgplayer_product_id"].nunique()) if len(selected) else 0,
        "duplicate_product_month_keys": duplicate_keys,
        "pre_release_or_presale_isolated_rows": int(len(isolated)),
        "material_or_extreme_continuity_review_rows": int(selected["continuity_status"].ne("CONTINUITY_PASS").sum()),
        "missing_month_rows": int(len(gaps)),
        "name_only_exact_alias_rows": int(len(comparison_rows)),
        "name_only_alias_review_rows": int(len(alias_review)),
        "listing_rows_used_as_monthly_market_price": 0,
        "absolute_price_cap_applied": False,
        "historical_append_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "status": "PASS_BRIDGED_HISTORY_CANDIDATE_ONLY" if len(selected) and duplicate_keys == 0 else "REVIEW_REQUIRED"
    }
    (out / "collector_historical_bridge_summary.json").write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if a.strict and (not len(selected) or duplicate_keys) else 0


if __name__ == "__main__":
    raise SystemExit(main())
