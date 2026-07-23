from __future__ import annotations

import csv
import re
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER_ROOT = ROOT / "data/terminal2/master_secret_lair"
PRODUCTS_PATH = MASTER_ROOT / "master_secret_lair_products.csv"
PRODUCT_MAP_PATH = MASTER_ROOT / "master_secret_lair_product_map.csv"
VALIDATION_ROOT = ROOT / "data/validation/phase_10/premium_universe_eligibility"
OLD_CANDIDATES_PATH = VALIDATION_ROOT / "secret_lair_structural_candidates_2026-07-22.csv"
FULL_OUTPUT = VALIDATION_ROOT / "secret_lair_master_governed_universe.csv"
READY_OUTPUT = VALIDATION_ROOT / "secret_lair_master_registry_ready_universe.csv"
REVIEW_OUTPUT = VALIDATION_ROOT / "secret_lair_master_review_required_universe.csv"
OWNED_OUTPUT = VALIDATION_ROOT / "secret_lair_owned_inventory_master_crosswalk.csv"
SUMMARY_OUTPUT = VALIDATION_ROOT / "secret_lair_master_expansion_summary.csv"

OWNED_PRODUCTS = [
    ("Secret Lair: Mark Poole - Traditional Foil", "traditional_foil", ""),
    ("Secret Lair: Path of Ancestry - Rainbow Foil", "rainbow_foil", ""),
    ("Secret Lair: A Lot to Learn", "unspecified", ""),
    ("Secret Lair: One with the Elements", "unspecified", ""),
    ("Secret Lair: My Cabbages!", "unspecified", ""),
    ("Secret Lair: Ember Island Players", "unspecified", ""),
    ("Secret Lair: Everything Changed", "unspecified", ""),
    ("Secret Lair: February Superdrop - Special Guest: Yuko Shimizu - Traditional Foil", "traditional_foil", ""),
    ("Secret Lair: Mother's Day 2021 - Traditional Foil", "traditional_foil", ""),
    ("Secret Lair: The Space Beyond the Stars - Traditional Foil", "traditional_foil", ""),
    ("Secret Lair: Hatsune Miku: Winter Diva - Rainbow Foil", "rainbow_foil", "EN"),
    ("Secret Lair: Blood Bowl - Traditional Foil", "traditional_foil", ""),
]


def clean(value: object) -> str:
    return " ".join(str(value or "").replace("\u2019", "'").replace("\u2014", "-").split())


def norm(value: object) -> str:
    text = clean(value).lower()
    replacements = {
        "non-foil": "nonfoil",
        "non foil": "nonfoil",
        "traditional foil edition": "foil",
        "rainbow foil edition": "foil",
        "foil edition": "foil",
        "standard edition": "",
        "secret lair promo": "",
        "secret lair": "",
        "drop": "",
        "edition": "",
        "the last air bender": "the last airbender",
        "mother's": "mothers",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def infer_detailed_finish(row: dict[str, str]) -> str:
    value = norm(f"{row.get('product_name', '')} {row.get('drop_name', '')} {row.get('variant_name', '')}")
    raw = clean(f"{row.get('product_name', '')} {row.get('drop_name', '')}").lower()
    if "rainbow foil" in raw:
        return "rainbow_foil"
    if "traditional foil" in raw:
        return "traditional_foil"
    if "etched foil" in raw or "foil etched" in raw:
        return "etched_foil"
    if "galaxy foil" in raw:
        return "galaxy_foil"
    if "gilded foil" in raw:
        return "gilded_foil"
    if "textured foil" in raw:
        return "textured_foil"
    if "nonfoil" in value:
        return "nonfoil"
    if clean(row.get("finish")).lower() == "foil":
        return "foil_unspecified"
    return clean(row.get("finish")).lower() or "unknown"


def infer_language(row: dict[str, str]) -> str:
    value = f" {clean(row.get('product_name')).upper()} {clean(row.get('drop_name')).upper()} "
    if " JP " in value or value.rstrip().endswith(" JP"):
        return "JP"
    if " EN " in value or value.rstrip().endswith(" EN"):
        return "EN"
    return ""


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    products = read_csv(PRODUCTS_PATH)
    product_map = read_csv(PRODUCT_MAP_PATH)
    old_candidates = read_csv(OLD_CANDIDATES_PATH) if OLD_CANDIDATES_PATH.exists() else []

    map_by_id: dict[str, list[dict[str, str]]] = {}
    for row in product_map:
        map_by_id.setdefault(clean(row.get("secret_lair_id")), []).append(row)

    governed: list[dict[str, object]] = []
    for row in products:
        sl_id = clean(row.get("secret_lair_id"))
        mappings = map_by_id.get(sl_id, [])
        tcg_ids = sorted({clean(x.get("tcgplayer_product_id")) for x in mappings if clean(x.get("tcgplayer_product_id"))})
        confidence = int(float(clean(row.get("source_confidence")) or 0))
        finish = clean(row.get("finish")).lower() or "unknown"
        governance_status = "REGISTRY_READY" if confidence >= 75 and finish != "unknown" else "REVIEW_REQUIRED"
        review_reason = ""
        if confidence < 75:
            review_reason = "LOW_SOURCE_CONFIDENCE"
        if finish == "unknown":
            review_reason = f"{review_reason}|UNKNOWN_FINISH".strip("|")
        governed.append(
            {
                **row,
                "detailed_finish": infer_detailed_finish(row),
                "language": infer_language(row),
                "tcgplayer_product_id": "|".join(tcg_ids),
                "tcgplayer_mapping_count": len(tcg_ids),
                "governance_status": governance_status,
                "review_reason": review_reason,
                "ebay_matching_allowed": governance_status == "REGISTRY_READY",
                "normalized_identity": norm(row.get("product_name")),
            }
        )

    old_ids = {clean(row.get("tcgplayer_product_id")) for row in old_candidates if clean(row.get("tcgplayer_product_id"))}
    old_names = {norm(row.get("canonical_product_name")) for row in old_candidates if norm(row.get("canonical_product_name"))}
    for row in governed:
        tcg_ids = [x for x in clean(row.get("tcgplayer_product_id")).split("|") if x]
        row["in_old_phase_10_subset"] = any(x in old_ids for x in tcg_ids) or norm(row.get("product_name")) in old_names

    owned_crosswalk: list[dict[str, object]] = []
    for owned_name, owned_finish, owned_language in OWNED_PRODUCTS:
        owned_key = norm(owned_name)
        scored: list[tuple[float, dict[str, object]]] = []
        for row in governed:
            candidate_key = clean(row.get("normalized_identity"))
            score = SequenceMatcher(None, owned_key, candidate_key).ratio()
            if owned_key and (owned_key in candidate_key or candidate_key in owned_key):
                score = max(score, 0.93)
            candidate_finish = clean(row.get("detailed_finish"))
            if owned_finish != "unspecified":
                if owned_finish == candidate_finish:
                    score += 0.05
                elif owned_finish in {"traditional_foil", "rainbow_foil"} and candidate_finish == "foil_unspecified":
                    score += 0.01
                elif candidate_finish == "nonfoil":
                    score -= 0.15
            if owned_language and clean(row.get("language")) == owned_language:
                score += 0.03
            scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best = scored[0]
        status = "MATCHED_CONFIDENT" if best_score >= 0.90 else "MATCHED_REVIEW" if best_score >= 0.72 else "MISSING_NEEDS_ID_RESOLUTION"
        owned_crosswalk.append(
            {
                "owned_product_name": owned_name,
                "owned_finish": owned_finish,
                "owned_language": owned_language,
                "crosswalk_status": status,
                "match_score": round(best_score, 4),
                "secret_lair_id": best.get("secret_lair_id", ""),
                "master_product_name": best.get("product_name", ""),
                "master_detailed_finish": best.get("detailed_finish", ""),
                "master_language": best.get("language", ""),
                "tcgplayer_product_id": best.get("tcgplayer_product_id", ""),
                "governance_status": best.get("governance_status", ""),
                "ebay_matching_allowed": best.get("ebay_matching_allowed", ""),
            }
        )

    fields = list(governed[0].keys()) if governed else []
    ready = [row for row in governed if row["governance_status"] == "REGISTRY_READY"]
    review = [row for row in governed if row["governance_status"] == "REVIEW_REQUIRED"]
    write_csv(FULL_OUTPUT, governed, fields)
    write_csv(READY_OUTPUT, ready, fields)
    write_csv(REVIEW_OUTPUT, review, fields)
    write_csv(
        OWNED_OUTPUT,
        owned_crosswalk,
        [
            "owned_product_name",
            "owned_finish",
            "owned_language",
            "crosswalk_status",
            "match_score",
            "secret_lair_id",
            "master_product_name",
            "master_detailed_finish",
            "master_language",
            "tcgplayer_product_id",
            "governance_status",
            "ebay_matching_allowed",
        ],
    )

    summary = [
        {"metric": "master_catalog_rows", "value": len(governed)},
        {"metric": "registry_ready_rows", "value": len(ready)},
        {"metric": "review_required_rows", "value": len(review)},
        {"metric": "old_phase_10_candidate_rows", "value": len(old_candidates)},
        {"metric": "master_rows_in_old_subset", "value": sum(bool(row["in_old_phase_10_subset"]) for row in governed)},
        {"metric": "master_rows_missing_from_old_subset", "value": sum(not bool(row["in_old_phase_10_subset"]) for row in governed)},
        {"metric": "owned_matched_confident", "value": sum(row["crosswalk_status"] == "MATCHED_CONFIDENT" for row in owned_crosswalk)},
        {"metric": "owned_matched_review", "value": sum(row["crosswalk_status"] == "MATCHED_REVIEW" for row in owned_crosswalk)},
        {"metric": "owned_missing", "value": sum(row["crosswalk_status"] == "MISSING_NEEDS_ID_RESOLUTION" for row in owned_crosswalk)},
    ]
    write_csv(SUMMARY_OUTPUT, summary, ["metric", "value"])

    print("SECRET LAIR MASTER GOVERNED EXPANSION: COMPLETE")
    print(f"Master catalog rows: {len(governed)}")
    print(f"Registry-ready rows: {len(ready)}")
    print(f"Review-required rows: {len(review)}")
    print(f"Old Phase 10 rows: {len(old_candidates)}")
    print(f"Owned confident matches: {sum(row['crosswalk_status'] == 'MATCHED_CONFIDENT' for row in owned_crosswalk)}")
    print(f"Owned review matches: {sum(row['crosswalk_status'] == 'MATCHED_REVIEW' for row in owned_crosswalk)}")
    print(f"Owned unresolved: {sum(row['crosswalk_status'] == 'MISSING_NEEDS_ID_RESOLUTION' for row in owned_crosswalk)}")
    print(f"Full universe: {FULL_OUTPUT.relative_to(ROOT)}")
    print(f"eBay-ready staging: {READY_OUTPUT.relative_to(ROOT)}")
    print(f"Review queue: {REVIEW_OUTPUT.relative_to(ROOT)}")
    print(f"Owned crosswalk: {OWNED_OUTPUT.relative_to(ROOT)}")
    print("Active eBay universe source was not changed.")


if __name__ == "__main__":
    main()
