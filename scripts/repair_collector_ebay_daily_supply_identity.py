"""Repair governed product identity propagation in the certified Collector eBay supply outputs.

Offline-only. This script fills governed_box_name from the official Collector authority,
corrects the 4x multi-display adjudication edge case, and fails closed on blank identities.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SUPPLY = ROOT / "data/governance/permanence/certification/collector_ebay_daily_supply"
AUTHORITY = ROOT / "data/governance/permanence/certification/collector_official_release_date_authority/collector_official_release_date_authority.csv"
LEDGER = SUPPLY / "collector_ebay_certified_daily_listing_ledger.csv"
SNAPSHOT = SUPPLY / "collector_ebay_certified_product_supply_snapshot.csv"
ADJUDICATION = SUPPLY / "collector_ebay_downgrade_adjudication.csv"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Repair Collector eBay certified supply identity propagation")
    p.add_argument("--authority", type=Path, default=AUTHORITY)
    p.add_argument("--ledger", type=Path, default=LEDGER)
    p.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    p.add_argument("--adjudication", type=Path, default=ADJUDICATION)
    p.add_argument("--strict", action="store_true")
    return p


def norm_id(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def main() -> int:
    args = parser().parse_args()
    generated = datetime.now(timezone.utc)
    required = [args.authority, args.ledger, args.snapshot, args.adjudication]
    missing = [str(p) for p in required if not p.resolve().is_file()]
    if missing:
        summary = {
            "block_name": "Collector eBay Daily Supply Identity Repair",
            "block_version": "1.0.0",
            "generated_at": generated.isoformat(),
            "missing_required_inputs": missing,
            "status": "REQUIRED_INPUTS_MISSING",
        }
        SUPPLY.mkdir(parents=True, exist_ok=True)
        (SUPPLY / "collector_ebay_daily_supply_identity_repair_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1 if args.strict else 0

    authority = pd.read_csv(args.authority.resolve(), dtype=str, encoding="utf-8-sig").fillna("")
    ledger = pd.read_csv(args.ledger.resolve(), dtype=str, encoding="utf-8-sig").fillna("")
    snapshot = pd.read_csv(args.snapshot.resolve(), dtype=str, encoding="utf-8-sig").fillna("")
    adjudication = pd.read_csv(args.adjudication.resolve(), dtype=str, encoding="utf-8-sig").fillna("")

    for frame in (authority, ledger, snapshot, adjudication):
        frame["tcgplayer_product_id"] = frame["tcgplayer_product_id"].map(norm_id)

    name_col = next((c for c in ["box_name", "governed_box_name", "product_name"] if c in authority.columns), None)
    if not name_col:
        raise ValueError("Official authority does not contain a governed product name column")
    name_by_id = {
        row["tcgplayer_product_id"]: str(row[name_col]).strip()
        for _, row in authority.iterrows()
        if str(row["tcgplayer_product_id"]).strip()
    }

    def fill_names(frame: pd.DataFrame) -> int:
        before = int(frame.get("governed_box_name", pd.Series([""] * len(frame))).astype(str).str.strip().eq("").sum())
        if "governed_box_name" not in frame.columns:
            frame["governed_box_name"] = ""
        frame["governed_box_name"] = frame.apply(
            lambda r: str(r.get("governed_box_name", "")).strip() or name_by_id.get(norm_id(r.get("tcgplayer_product_id", "")), ""),
            axis=1,
        )
        return before

    ledger_blank_before = fill_names(ledger)
    snapshot_blank_before = fill_names(snapshot)
    adjudication_blank_before = fill_names(adjudication)

    corrected_multi_display = 0
    for index, row in adjudication.iterrows():
        title = str(row.get("title_production", ""))
        if re.search(r"(?:^|\W)4x", title, flags=re.IGNORECASE) and "omega" not in title.lower():
            if row.get("adjudication_reason", "") != "CONFIRMED_MULTI_DISPLAY_LOT":
                adjudication.at[index, "adjudication_status"] = "CONFIRMED_REJECTED"
                adjudication.at[index, "adjudication_reason"] = "CONFIRMED_MULTI_DISPLAY_LOT"
                corrected_multi_display += 1

    ledger.to_csv(args.ledger.resolve(), index=False)
    snapshot.to_csv(args.snapshot.resolve(), index=False)
    adjudication.to_csv(args.adjudication.resolve(), index=False)

    ledger_blank_after = int(ledger["governed_box_name"].astype(str).str.strip().eq("").sum())
    snapshot_blank_after = int(snapshot["governed_box_name"].astype(str).str.strip().eq("").sum())
    adjudication_blank_after = int(adjudication["governed_box_name"].astype(str).str.strip().eq("").sum())
    unresolved = int((adjudication["adjudication_status"] != "CONFIRMED_REJECTED").sum())

    passed = (
        ledger_blank_after == 0
        and snapshot_blank_after == 0
        and adjudication_blank_after == 0
        and unresolved == 0
        and len(ledger) > 0
        and len(snapshot) > 0
    )
    summary = {
        "block_name": "Collector eBay Daily Supply Identity Repair",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "offline_only": True,
        "quota_calls": 0,
        "ledger_rows": len(ledger),
        "snapshot_rows": len(snapshot),
        "adjudication_rows": len(adjudication),
        "ledger_blank_names_before": ledger_blank_before,
        "snapshot_blank_names_before": snapshot_blank_before,
        "adjudication_blank_names_before": adjudication_blank_before,
        "ledger_blank_names_after": ledger_blank_after,
        "snapshot_blank_names_after": snapshot_blank_after,
        "adjudication_blank_names_after": adjudication_blank_after,
        "multi_display_adjudications_corrected": corrected_multi_display,
        "unresolved_adjudications": unresolved,
        "status": "PASS_COLLECTOR_EBAY_DAILY_SUPPLY_IDENTITY_REPAIR" if passed else "REVIEW_REQUIRED",
    }
    (SUPPLY / "collector_ebay_daily_supply_identity_repair_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
