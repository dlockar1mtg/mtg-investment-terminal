"""Normalize MTGJSON Collector display contents into governed packaging fields."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CROSSWALK = ROOT / "data/governance/permanence/certification/collector_mtgjson_sealed_crosswalk/collector_mtgjson_sealed_crosswalk.csv"
DEFAULT_OUT = ROOT / "data/governance/permanence/certification/collector_packaging_normalization"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Normalize Collector display packaging")
    p.add_argument("--crosswalk", type=Path, default=DEFAULT_CROSSWALK)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--strict", action="store_true")
    return p


def norm_id(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def parse_contents(value: object) -> dict:
    text = "" if pd.isna(value) else str(value).strip()
    if not text:
        return {}
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


def main() -> int:
    args = parser().parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    if not args.crosswalk.resolve().is_file():
        summary = {"status": "FAIL", "reason": "CROSSWALK_MISSING", "packaging_complete_for_verified_products": False}
        (out / "collector_packaging_normalization_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1

    crosswalk = pd.read_csv(args.crosswalk.resolve(), dtype=str, encoding="utf-8-sig", low_memory=False).fillna("")
    rows: list[dict[str, object]] = []
    review: list[dict[str, object]] = []

    for _, row in crosswalk.iterrows():
        pid = norm_id(row.get("tcgplayer_product_id", ""))
        verified = row.get("structural_verification_status", "") == "MTGJSON_STRUCTURE_VERIFIED"
        contents = parse_contents(row.get("contents_json", ""))
        sealed = contents.get("sealed", []) if isinstance(contents, dict) else []
        sealed = sealed if isinstance(sealed, list) else []

        collector_packs = []
        toppers = []
        other_sealed = []
        for item in sealed:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            lower = name.lower()
            count_raw = item.get("count", 0)
            try:
                count = int(count_raw)
            except (TypeError, ValueError):
                count = 0
            normalized = {
                "count": count,
                "name": name,
                "set": str(item.get("set", "")).strip(),
                "uuid": str(item.get("uuid", "")).strip(),
            }
            if "collector booster pack" in lower:
                collector_packs.append(normalized)
            elif "topper" in lower:
                toppers.append(normalized)
            else:
                other_sealed.append(normalized)

        collector_pack_count = sum(x["count"] for x in collector_packs)
        topper_count = sum(x["count"] for x in toppers)
        other_count = sum(x["count"] for x in other_sealed)
        unique_collector_pack = len(collector_packs) == 1

        if not verified:
            status = "PRESALE_STRUCTURE_PENDING" if row.get("match_evidence_class", "") == "NOT_PRESENT_IN_CURRENT_MTGJSON_RELEASE" else "STRUCTURE_REVIEW_REQUIRED"
        elif not unique_collector_pack or collector_pack_count <= 0:
            status = "COLLECTOR_PACK_STRUCTURE_REVIEW_REQUIRED"
        else:
            status = "PACKAGING_STRUCTURE_VERIFIED"

        record = {
            "tcgplayer_product_id": pid,
            "box_name": row.get("box_name", ""),
            "lifecycle_state": row.get("lifecycle_state", ""),
            "mtgjson_uuid": row.get("mtgjson_uuid", ""),
            "set_code": row.get("set_code", ""),
            "match_evidence_class": row.get("match_evidence_class", ""),
            "collector_packs_per_display": collector_pack_count if unique_collector_pack else "",
            "collector_pack_name": collector_packs[0]["name"] if unique_collector_pack else "",
            "collector_pack_uuid": collector_packs[0]["uuid"] if unique_collector_pack else "",
            "collector_pack_set_code": collector_packs[0]["set"] if unique_collector_pack else "",
            "box_topper_pack_count": topper_count,
            "box_topper_items_json": json.dumps(toppers, ensure_ascii=False, sort_keys=True),
            "additional_sealed_item_count": other_count,
            "additional_sealed_items_json": json.dumps(other_sealed, ensure_ascii=False, sort_keys=True),
            "total_inner_sealed_units": collector_pack_count + topper_count + other_count,
            "configuration_quantity_status": status,
            "source_contents_json": row.get("contents_json", ""),
        }
        rows.append(record)
        if status not in {"PACKAGING_STRUCTURE_VERIFIED", "PRESALE_STRUCTURE_PENDING"}:
            review.append(record)

    frame = pd.DataFrame(rows)
    review_frame = pd.DataFrame(review, columns=frame.columns)
    frame.to_csv(out / "collector_packaging_normalization.csv", index=False)
    review_frame.to_csv(out / "collector_packaging_review.csv", index=False)

    verified_rows = frame[frame["configuration_quantity_status"] == "PACKAGING_STRUCTURE_VERIFIED"]
    pending_presale = frame[frame["configuration_quantity_status"] == "PRESALE_STRUCTURE_PENDING"]
    blockers = len(review_frame)
    summary = {
        "block_name": "Collector Packaging Normalization",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "governed_products": int(len(frame)),
        "packaging_structure_verified": int(len(verified_rows)),
        "presale_structure_pending": int(len(pending_presale)),
        "released_product_packaging_blockers": int(blockers),
        "four_pack_displays": int((pd.to_numeric(verified_rows["collector_packs_per_display"], errors="coerce") == 4).sum()),
        "twelve_pack_displays": int((pd.to_numeric(verified_rows["collector_packs_per_display"], errors="coerce") == 12).sum()),
        "displays_with_topper_contents": int((pd.to_numeric(verified_rows["box_topper_pack_count"], errors="coerce") > 0).sum()),
        "packaging_complete_for_verified_products": blockers == 0,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_PACKAGING_NORMALIZATION" if blockers == 0 else "REVIEW_REQUIRED",
    }
    (out / "collector_packaging_normalization_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if args.strict and blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
