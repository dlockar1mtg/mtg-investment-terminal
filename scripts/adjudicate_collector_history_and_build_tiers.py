"""Adjudicate bridged Collector history and build dynamic product history tiers.

Consumes the official release-date authority when available. This script never
authorizes purchases or UIP delivery.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config/mtg/governance/collector_history_adjudication_tiering_policy_v1.json"
DEFAULT_HISTORY = ROOT / "data/governance/permanence/certification/collector_historical_bridge_certification/collector_bridged_analytical_history_candidate.csv"
DEFAULT_AUTHORITY = ROOT / "data/governance/permanence/certification/collector_current_authority/collector_current_authority_all.csv"
DEFAULT_ALIAS_REVIEW = ROOT / "data/governance/permanence/certification/collector_historical_bridge_certification/collector_name_only_alias_review_queue.csv"
DEFAULT_OUT = ROOT / "data/governance/permanence/certification/collector_history_adjudication_tiering"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Adjudicate Collector history and build tiers")
    p.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    p.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    p.add_argument("--authority", type=Path, default=DEFAULT_AUTHORITY)
    p.add_argument("--alias-review", type=Path, default=DEFAULT_ALIAS_REVIEW)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--strict", action="store_true")
    return p


def read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig", low_memory=False).fillna("")


def norm_id(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def month_diff(start: pd.Timestamp, end: pd.Timestamp) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def choose_column(frame: pd.DataFrame, candidates: list[str]) -> str:
    return next((name for name in candidates if name in frame.columns), "")


def main() -> int:
    args = parser().parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    missing = [str(p) for p in [args.policy, args.history, args.authority] if not p.resolve().is_file()]
    if missing:
        summary = {"status": "FAIL", "missing_inputs": missing, "purchase_recommendation_authorized": False, "uip_delivery_authorized": False}
        (out / "collector_history_adjudication_tiering_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1

    policy = json.loads(args.policy.resolve().read_text(encoding="utf-8-sig"))
    hist = read(args.history.resolve())
    auth = read(args.authority.resolve())
    hist["tcgplayer_product_id"] = hist["tcgplayer_product_id"].map(norm_id)
    auth["tcgplayer_product_id"] = auth["tcgplayer_product_id"].map(norm_id)

    release_col = choose_column(auth, ["release_date", "official_release_date", "raw_released_on"])
    name_col = choose_column(auth, ["box_name", "box_name_current", "governed_box_name"])
    identity_col = choose_column(auth, ["identity_authority_status", "identity_authority_status_current"])
    release_status_col = choose_column(auth, ["release_date_authority_status", "release_date_verification_status"])

    if not release_col or not name_col:
        raise ValueError(f"authority missing required columns release={release_col!r} name={name_col!r}")

    governed = auth.copy()
    if identity_col:
        governed = governed.loc[governed[identity_col].eq("CURRENT_IDENTITY_AUTHORIZED")].copy()
    governed_ids = set(governed["tcgplayer_product_id"])
    release_map = governed.set_index("tcgplayer_product_id")[release_col].to_dict()
    name_map = governed.set_index("tcgplayer_product_id")[name_col].to_dict()
    release_verified_map = (
        governed.set_index("tcgplayer_product_id")[release_status_col].to_dict()
        if release_status_col else {}
    )

    hist["observation_dt"] = pd.to_datetime(hist["observation_month"], errors="coerce")
    hist["market_price_num"] = pd.to_numeric(hist["market_price"], errors="coerce")
    hist["mom_num"] = pd.to_numeric(hist.get("month_over_month_change", ""), errors="coerce")
    latest = hist["observation_dt"].max()
    latest_month = latest.strftime("%Y-%m-01") if pd.notna(latest) else ""

    attested = set(policy["owner_attested_high_value_product_ids"])
    material_threshold = float(policy["continuity_thresholds"]["material_absolute_percent_change"])
    extreme_up = float(policy["continuity_thresholds"]["extreme_up_percent_change"])
    extreme_down = float(policy["continuity_thresholds"]["extreme_down_percent_change"])

    hist["extreme_break"] = (hist["mom_num"] > extreme_up) | (hist["mom_num"] < extreme_down)
    hist["material_change"] = hist["mom_num"].abs() >= material_threshold
    hist["owner_attested_high_value"] = hist["tcgplayer_product_id"].isin(attested)
    hist["adjudication_status"] = "CONTINUITY_PASS"
    hist.loc[hist["material_change"], "adjudication_status"] = "MATERIAL_CHANGE_ANNOTATED"
    hist.loc[
        hist["material_change"]
        & hist["owner_attested_high_value"]
        & hist["source_code"].isin(["JULY_31_CERTIFIED", "AUGUST_LIVE_CERTIFIED"]),
        "adjudication_status",
    ] = "OWNER_ATTESTED_MATERIAL_CHANGE"
    hist.loc[hist["extreme_break"], "adjudication_status"] = "EXTREME_BREAK_UNRESOLVED"
    hist["forecast_input_row_authorized"] = ~hist["extreme_break"]
    hist["purchase_recommendation_authorized"] = False

    hist.to_csv(out / "collector_adjudicated_analytical_history.csv", index=False)
    hist.loc[hist["extreme_break"]].to_csv(out / "collector_extreme_continuity_unresolved.csv", index=False)
    hist.loc[hist["material_change"] & ~hist["extreme_break"]].to_csv(out / "collector_material_change_annotations.csv", index=False)

    rows: list[dict[str, object]] = []
    for product_id in sorted(governed_ids):
        product_history = hist.loc[hist["tcgplayer_product_id"].eq(product_id)].copy()
        release_raw = str(release_map.get(product_id, "")).strip()
        release_dt = pd.to_datetime(release_raw, errors="coerce")
        months = int(product_history["observation_month"].nunique()) if len(product_history) else 0
        first = product_history["observation_dt"].min() if len(product_history) else pd.NaT
        last = product_history["observation_dt"].max() if len(product_history) else pd.NaT
        extreme = int(product_history["extreme_break"].sum()) if len(product_history) else 0
        material = int(product_history["material_change"].sum()) if len(product_history) else 0

        official_status = str(release_verified_map.get(product_id, "")).strip()
        authority_verified = (
            official_status in {"OFFICIAL_RELEASE_DATE_AUTHORIZED", "OFFICIAL_WIZARDS_VERIFIED"}
            if release_status_col else bool(release_raw)
        )

        if not release_raw or pd.isna(release_dt) or not authority_verified:
            lifecycle = "RELEASE_DATE_UNVERIFIED"
            age = None
        elif pd.notna(latest) and release_dt > latest:
            lifecycle = "PRESALE"
            age = None
        else:
            age = max(0, month_diff(release_dt, latest)) if pd.notna(latest) else None
            lifecycle = "RELEASED_EARLY_LIFECYCLE" if age is not None and age < int(policy["early_lifecycle_months"]) else "RELEASED_MATURE"

        if lifecycle == "PRESALE" or months == 0:
            tier = "PRESALE_OR_NO_RELEASED_HISTORY"
        elif months >= 24:
            tier = "DIRECT_HISTORY_MATURE"
        elif months >= 12:
            tier = "DIRECT_HISTORY_DEVELOPING"
        elif months >= 3:
            tier = "LIMITED_HISTORY"
        else:
            tier = "EARLY_LIFECYCLE"

        status = "FORECAST_INPUT_CANDIDATE" if extreme == 0 and lifecycle not in {"PRESALE", "RELEASE_DATE_UNVERIFIED"} else "FORECAST_INPUT_BLOCKED"
        rows.append({
            "tcgplayer_product_id": product_id,
            "governed_box_name": name_map.get(product_id, ""),
            "release_date": release_raw,
            "release_date_authority_status": official_status,
            "latest_observation_month": latest_month,
            "recomputed_lifecycle_state": lifecycle,
            "released_history_months": months,
            "first_history_month": first.strftime("%Y-%m-01") if pd.notna(first) else "",
            "last_history_month": last.strftime("%Y-%m-01") if pd.notna(last) else "",
            "material_change_annotations": material,
            "extreme_unresolved_rows": extreme,
            "history_tier": tier,
            "forecast_input_status": status,
            "purchase_recommendation_authorized": False,
            "uip_delivery_authorized": False,
        })

    tiers = pd.DataFrame(rows).sort_values(["history_tier", "governed_box_name"])
    tiers.to_csv(out / "collector_product_history_tiers.csv", index=False)
    tiers.loc[tiers["forecast_input_status"].eq("FORECAST_INPUT_CANDIDATE")].to_csv(out / "collector_forecast_input_candidates.csv", index=False)
    tiers.loc[tiers["forecast_input_status"].eq("FORECAST_INPUT_BLOCKED")].to_csv(out / "collector_forecast_input_blocked.csv", index=False)

    alias = read(args.alias_review.resolve()) if args.alias_review.resolve().is_file() else pd.DataFrame()
    alias.to_csv(out / "collector_unresolved_name_only_quarantine.csv", index=False)

    duplicate_keys = int(hist.duplicated(["tcgplayer_product_id", "observation_month"]).sum())
    extreme_rows = int(hist["extreme_break"].sum())
    unverified_lifecycle = int(tiers["recomputed_lifecycle_state"].eq("RELEASE_DATE_UNVERIFIED").sum())
    summary = {
        "block_name": "Collector History Adjudication and Tiering",
        "block_version": "1.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authority_release_column": release_col,
        "authority_release_status_column": release_status_col,
        "latest_observation_month": latest_month,
        "governed_products": int(len(governed_ids)),
        "adjudicated_history_rows": int(len(hist)),
        "adjudicated_products": int(hist["tcgplayer_product_id"].nunique()),
        "duplicate_product_month_keys": duplicate_keys,
        "material_change_annotation_rows": int((hist["material_change"] & ~hist["extreme_break"]).sum()),
        "owner_attested_material_change_rows": int(hist["adjudication_status"].eq("OWNER_ATTESTED_MATERIAL_CHANGE").sum()),
        "extreme_unresolved_rows": extreme_rows,
        "product_tier_rows": int(len(tiers)),
        "release_date_unverified_products": unverified_lifecycle,
        "forecast_input_candidate_products": int(tiers["forecast_input_status"].eq("FORECAST_INPUT_CANDIDATE").sum()),
        "forecast_input_blocked_products": int(tiers["forecast_input_status"].eq("FORECAST_INPUT_BLOCKED").sum()),
        "unresolved_name_only_rows": int(len(alias)),
        "absolute_price_cap_applied": False,
        "historical_append_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_ADJUDICATION_TIERING_CANDIDATE_ONLY" if duplicate_keys == 0 and unverified_lifecycle == 0 else "REVIEW_REQUIRED",
    }
    (out / "collector_history_adjudication_tiering_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if args.strict and (duplicate_keys > 0 or extreme_rows > 0 or unverified_lifecycle > 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
