"""Build an exact-TCGplayer-ID MTGJSON sealed-product crosswalk from preserved JSON sources."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "data/governance/permanence/certification/collector_official_release_date_authority/collector_official_release_date_authority.csv"
OUT = ROOT / "data/governance/permanence/certification/collector_mtgjson_sealed_crosswalk"
SEARCH_ROOTS = [ROOT / "data/raw/mtgjson", ROOT / "data_vault/raw/mtg/collector_booster"]


def norm(value: object) -> str:
    text = "" if value is None else str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def walk(obj: object, path: str = ""):
    if isinstance(obj, dict):
        yield obj, path
        for key, value in obj.items():
            child = f"{path}.{key}" if path else str(key)
            yield from walk(value, child)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from walk(value, f"{path}[{index}]")


def collect_tcgplayer_ids(obj: object) -> set[str]:
    """Collect TCGplayer product IDs recursively while retaining the parent product record."""
    found: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            normalized_key = str(key).lower().replace("_", "").replace("-", "")
            is_tcg_key = "tcgplayer" in normalized_key
            is_product_id_key = "productid" in normalized_key or normalized_key.endswith("id")
            if is_tcg_key and is_product_id_key:
                if isinstance(value, (str, int, float)):
                    found.add(norm(value))
                elif isinstance(value, list):
                    found.update(norm(item) for item in value if isinstance(item, (str, int, float)))
            found.update(collect_tcgplayer_ids(value))
    elif isinstance(obj, list):
        for value in obj:
            found.update(collect_tcgplayer_ids(value))
    return {value for value in found if value and value.lower() != "nan"}


def first(record: dict, *keys: str):
    for key in keys:
        if key in record and record[key] not in (None, "", [], {}):
            return record[key]
    return ""


def is_product_record(record: dict) -> bool:
    """Reject nested identifier-only dictionaries and retain structural sealed-product parents."""
    has_identity = bool(first(record, "uuid", "id")) and bool(first(record, "name", "productName"))
    has_structure = any(
        key in record
        for key in (
            "category",
            "productType",
            "type",
            "subtype",
            "subType",
            "contents",
            "sealedProductContents",
            "packContents",
            "productSize",
            "identifiers",
        )
    )
    return has_identity and has_structure


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority", type=Path, default=AUTH)
    parser.add_argument("--output-dir", type=Path, default=OUT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    authority = pd.read_csv(args.authority, dtype=str, encoding="utf-8-sig").fillna("")
    authority["tcgplayer_product_id"] = authority["tcgplayer_product_id"].map(norm)
    wanted = set(authority["tcgplayer_product_id"])

    matches: dict[str, list[dict[str, object]]] = {product_id: [] for product_id in wanted}
    seen_candidates: set[tuple[str, str, str, str]] = set()
    files_scanned = 0
    errors: list[dict[str, str]] = []

    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for source_path in root.rglob("*.json"):
            files_scanned += 1
            relative_path = str(source_path.relative_to(ROOT)).replace("\\", "/")
            try:
                raw = source_path.read_bytes()
                payload = json.loads(raw.decode("utf-8-sig"))
                source_hash = hashlib.sha256(raw).hexdigest()
                for record, json_path in walk(payload):
                    if not is_product_record(record):
                        continue
                    matching_ids = collect_tcgplayer_ids(record) & wanted
                    if not matching_ids:
                        continue
                    candidate = {
                        "source_path": relative_path,
                        "source_sha256": source_hash,
                        "json_path": json_path,
                        "mtgjson_uuid": str(first(record, "uuid", "id")),
                        "mtgjson_name": str(first(record, "name", "productName")),
                        "category": str(first(record, "category", "productType", "type")),
                        "subtype": str(first(record, "subtype", "subType")),
                        "release_date_mtgjson": str(first(record, "releaseDate", "release_date")),
                        "product_size": str(first(record, "productSize", "product_size")),
                        "contents_json": json.dumps(
                            first(record, "contents", "sealedProductContents", "packContents"),
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                        if first(record, "contents", "sealedProductContents", "packContents") != ""
                        else "",
                    }
                    for product_id in matching_ids:
                        signature = (
                            product_id,
                            relative_path,
                            str(candidate["json_path"]),
                            str(candidate["mtgjson_uuid"]),
                        )
                        if signature not in seen_candidates:
                            seen_candidates.add(signature)
                            matches[product_id].append(candidate)
            except Exception as exc:
                errors.append(
                    {
                        "source_path": relative_path,
                        "error": f"{type(exc).__name__}: {exc}",
                        "review_status": "SOURCE_FILE_UNREADABLE_REVIEW_REQUIRED",
                    }
                )

    rows: list[dict[str, object]] = []
    for _, authority_row in authority.iterrows():
        product_id = authority_row["tcgplayer_product_id"]
        candidates = matches.get(product_id, [])
        exact = len(candidates) == 1
        candidate = candidates[0] if exact else {}
        rows.append(
            {
                "tcgplayer_product_id": product_id,
                "box_name": authority_row.get("box_name", ""),
                "candidate_count": len(candidates),
                **candidate,
                "configuration_match_status": (
                    "EXACT_TCGPLAYER_ID_MATCH"
                    if exact
                    else "NO_EXACT_MATCH"
                    if not candidates
                    else "MULTIPLE_EXACT_ID_CANDIDATES"
                ),
                "structural_verification_status": "MTGJSON_STRUCTURE_VERIFIED" if exact else "REVIEW_REQUIRED",
            }
        )

    frame = pd.DataFrame(rows)
    unresolved = frame.loc[frame["structural_verification_status"] != "MTGJSON_STRUCTURE_VERIFIED"].copy()
    error_frame = pd.DataFrame(errors, columns=["source_path", "error", "review_status"])

    frame.to_csv(out / "collector_mtgjson_sealed_crosswalk.csv", index=False)
    unresolved.to_csv(out / "collector_mtgjson_sealed_crosswalk_review.csv", index=False)
    error_frame.to_csv(out / "collector_mtgjson_source_errors.csv", index=False)

    exact_matches = int(frame["structural_verification_status"].eq("MTGJSON_STRUCTURE_VERIFIED").sum())
    summary = {
        "block_name": "Collector MTGJSON Sealed Crosswalk",
        "block_version": "1.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "governed_products": int(len(frame)),
        "source_json_files_scanned": files_scanned,
        "exact_id_matches": exact_matches,
        "review_required": int(len(unresolved)),
        "source_errors": int(len(errors)),
        "crosswalk_complete": exact_matches == len(frame) and len(unresolved) == 0,
        "status": "PASS_MTGJSON_SEALED_CROSSWALK" if exact_matches == len(frame) and len(unresolved) == 0 else "REVIEW_REQUIRED",
    }
    (out / "collector_mtgjson_sealed_crosswalk_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))

    strict_failure = len(unresolved) > 0 or len(errors) > 0
    return 1 if args.strict and strict_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
