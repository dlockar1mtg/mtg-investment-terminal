"""Build the governed Collector sealed-product crosswalk from the current verified MTGJSON source."""
from __future__ import annotations

import argparse
import bz2
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import ijson
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "data/governance/permanence/certification/collector_official_release_date_authority/collector_official_release_date_authority.csv"
POINTER = ROOT / "data/governance/permanence/certification/collector_mtgjson_current_source/current_source_pointer.json"
OUT = ROOT / "data/governance/permanence/certification/collector_mtgjson_sealed_crosswalk"


def norm_id(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def norm_name(value: object) -> str:
    text = str(value or "").lower()
    text = text.replace("booster box", "booster display")
    text = text.replace("collector boosters", "collector booster")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def structural_key(record: dict) -> tuple[str, str, str, str, str]:
    return (
        str(record.get("uuid", "")),
        norm_name(record.get("name", "")),
        str(record.get("category", "")),
        str(record.get("subtype", "")),
        str(record.get("releaseDate", "")),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority", type=Path, default=AUTHORITY)
    parser.add_argument("--pointer", type=Path, default=POINTER)
    parser.add_argument("--output-dir", type=Path, default=OUT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    authority = pd.read_csv(args.authority, dtype=str, encoding="utf-8-sig").fillna("")
    authority["tcgplayer_product_id"] = authority["tcgplayer_product_id"].map(norm_id)
    pointer = json.loads(args.pointer.read_text(encoding="utf-8-sig"))
    source_path = ROOT / pointer["vault_path"]
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    by_id: dict[str, dict[tuple[str, str, str, str, str], dict]] = {}
    by_name: dict[str, dict[tuple[str, str, str, str, str], dict]] = {}
    sealed_records = 0

    with bz2.open(source_path, "rb") as handle:
        for set_code, set_data in ijson.kvitems(handle, "data"):
            for product in set_data.get("sealedProduct", []) or []:
                if not isinstance(product, dict):
                    continue
                sealed_records += 1
                record = {
                    "set_code": str(set_code),
                    "uuid": str(product.get("uuid", "")),
                    "name": str(product.get("name", "")),
                    "category": str(product.get("category", "")),
                    "subtype": str(product.get("subtype", "")),
                    "releaseDate": str(product.get("releaseDate", "")),
                    "productSize": product.get("productSize", ""),
                    "cardCount": product.get("cardCount", ""),
                    "contents": product.get("contents", {}),
                    "identifiers": product.get("identifiers", {}) or {},
                }
                key = structural_key(record)
                pid = norm_id(record["identifiers"].get("tcgplayerProductId", ""))
                if pid:
                    by_id.setdefault(pid, {})[key] = record
                by_name.setdefault(norm_name(record["name"]), {})[key] = record

    rows, review_rows = [], []
    released_blockers = 0
    presale_absent = 0
    exact_id_verified = 0
    exact_name_verified = 0

    for _, item in authority.iterrows():
        pid = item["tcgplayer_product_id"]
        box_name = str(item.get("box_name", ""))
        lifecycle = str(item.get("lifecycle_state", item.get("recomputed_lifecycle_state", "")))
        release_date = str(item.get("release_date", ""))[:10]
        id_candidates = list(by_id.get(pid, {}).values())
        name_candidates = list(by_name.get(norm_name(box_name), {}).values())
        selected: dict = {}
        evidence = ""

        if len(id_candidates) == 1:
            selected = id_candidates[0]
            evidence = "EXACT_TCGPLAYER_ID_VERIFIED"
            exact_id_verified += 1
        elif len(id_candidates) > 1:
            evidence = "MULTIPLE_STRUCTURAL_ID_CANDIDATES_REVIEW_REQUIRED"
        elif len(name_candidates) == 1:
            candidate = name_candidates[0]
            category_ok = str(candidate.get("category", "")).lower() == "booster_box"
            subtype_ok = str(candidate.get("subtype", "")).lower() == "collector"
            date_ok = not candidate.get("releaseDate") or not release_date or str(candidate.get("releaseDate"))[:10] == release_date
            if category_ok and subtype_ok and date_ok:
                selected = candidate
                evidence = "EXACT_SEALED_NAME_STRUCTURALLY_VERIFIED"
                exact_name_verified += 1
            else:
                evidence = "NAME_MATCH_STRUCTURE_OR_DATE_REVIEW_REQUIRED"
        elif len(name_candidates) > 1:
            evidence = "MULTIPLE_STRUCTURAL_NAME_CANDIDATES_REVIEW_REQUIRED"
        else:
            evidence = "NOT_PRESENT_IN_CURRENT_MTGJSON_RELEASE"
            is_presale = lifecycle == "PRESALE" or (release_date and release_date > datetime.now(timezone.utc).date().isoformat())
            if is_presale:
                presale_absent += 1
            else:
                released_blockers += 1

        row = {
            "tcgplayer_product_id": pid,
            "box_name": box_name,
            "official_release_date": release_date,
            "lifecycle_state": lifecycle,
            "exact_id_candidate_count": len(id_candidates),
            "exact_name_candidate_count": len(name_candidates),
            "mtgjson_uuid": selected.get("uuid", ""),
            "mtgjson_name": selected.get("name", ""),
            "set_code": selected.get("set_code", ""),
            "category": selected.get("category", ""),
            "subtype": selected.get("subtype", ""),
            "release_date_mtgjson": selected.get("releaseDate", ""),
            "product_size": selected.get("productSize", ""),
            "card_count": selected.get("cardCount", ""),
            "contents_json": json.dumps(selected.get("contents", {}), ensure_ascii=False, sort_keys=True) if selected else "",
            "match_evidence_class": evidence,
            "structural_verification_status": "MTGJSON_STRUCTURE_VERIFIED" if selected else "REVIEW_REQUIRED",
            "source_sha256": pointer.get("sha256", ""),
            "source_vault_path": pointer.get("vault_path", ""),
            "source_retrieval_id": pointer.get("retrieval_id", ""),
        }
        rows.append(row)
        if not selected:
            review_rows.append(row)

    frame = pd.DataFrame(rows)
    review = pd.DataFrame(review_rows, columns=frame.columns)
    frame.to_csv(out / "collector_mtgjson_sealed_crosswalk.csv", index=False)
    review.to_csv(out / "collector_mtgjson_sealed_crosswalk_review.csv", index=False)

    verified = exact_id_verified + exact_name_verified
    complete_for_released = released_blockers == 0 and not any(
        value.startswith("MULTIPLE_") or "REVIEW_REQUIRED" in value
        for value in frame.loc[frame["structural_verification_status"] != "MTGJSON_STRUCTURE_VERIFIED", "match_evidence_class"].tolist()
        if value != "NOT_PRESENT_IN_CURRENT_MTGJSON_RELEASE"
    )
    summary = {
        "block_name": "Collector Current MTGJSON Sealed Crosswalk",
        "block_version": "2.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "governed_products": len(frame),
        "sealed_records_scanned": sealed_records,
        "exact_tcgplayer_id_verified": exact_id_verified,
        "exact_name_structurally_verified": exact_name_verified,
        "total_structurally_verified": verified,
        "presale_not_present": presale_absent,
        "released_product_blockers": released_blockers,
        "review_required": len(review),
        "current_source_sha256": pointer.get("sha256", ""),
        "current_source_retrieval_id": pointer.get("retrieval_id", ""),
        "crosswalk_complete_for_released_products": complete_for_released,
        "status": "PASS_CURRENT_MTGJSON_CROSSWALK" if complete_for_released else "REVIEW_REQUIRED",
    }
    (out / "collector_mtgjson_sealed_crosswalk_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if args.strict and not complete_for_released else 0


if __name__ == "__main__":
    raise SystemExit(main())
