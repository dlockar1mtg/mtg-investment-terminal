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
    text = clean(value).lower().replace("mother's", "mothers")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def identity_core(value: object) -> str:
    text = norm(value)
    phrases = (
        "traditional foil edition", "rainbow foil edition", "non foil edition",
        "nonfoil edition", "foil edition", "standard edition", "traditional foil",
        "rainbow foil", "etched foil", "galaxy foil", "gilded foil",
        "textured foil", "non foil", "nonfoil",
    )
    for phrase in phrases:
        text = text.replace(phrase, " ")
    text = re.sub(r"\b(secret lair promo|secret lair|drop|edition)\b", " ", text)
    text = text.replace("the last air bender", "the last airbender")
    return " ".join(text.split())


def infer_detailed_finish(row: dict[str, str]) -> str:
    raw = clean(f"{row.get('product_name', '')} {row.get('drop_name', '')} {row.get('variant_name', '')}").lower()
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
    if "non-foil" in raw or "nonfoil" in raw or "non foil" in raw:
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


def infer_configuration(row: dict[str, str]) -> str:
    value = norm(f"{row.get('product_name', '')} {row.get('drop_name', '')} {row.get('product_family', '')}")
    if "festival in a box" in value:
        return "festival_in_a_box"
    if "commander deck" in value or re.search(r"\bdeck\b", value):
        return "deck"
    if "countdown kit" in value or re.search(r"\bkit\b", value):
        return "kit"
    if "bundle" in value:
        return "bundle"
    return "individual_drop"


def finish_compatible(owned: str, candidate: str) -> bool:
    if owned == "unspecified":
        return True
    if owned == candidate:
        return True
    return owned in {"traditional_foil", "rainbow_foil", "etched_foil", "galaxy_foil", "gilded_foil", "textured_foil"} and candidate == "foil_unspecified"


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
        detailed_finish = infer_detailed_finish(row)
        configuration = infer_configuration(row)
        finish_required = configuration == "individual_drop"
        reasons: list[str] = []
        if confidence < 75:
            reasons.append("LOW_SOURCE_CONFIDENCE")
        if finish_required and detailed_finish == "unknown":
            reasons.append("UNKNOWN_FINISH_INDIVIDUAL_DROP")
        if not tcg_ids:
            reasons.append("MISSING_TCGPLAYER_ID")
        governance_status = "REGISTRY_READY" if not reasons else "REVIEW_REQUIRED"
        governed.append({
            **row,
            "detailed_finish": detailed_finish,
            "language": infer_language(row),
            "sealed_configuration": configuration,
            "finish_required": finish_required,
            "tcgplayer_product_id": "|".join(tcg_ids),
            "tcgplayer_mapping_count": len(tcg_ids),
            "governance_status": governance_status,
            "review_reason": "|".join(reasons),
            "ebay_matching_allowed": governance_status == "REGISTRY_READY",
            "normalized_identity": identity_core(row.get("product_name")),
        })

    old_ids = {clean(row.get("tcgplayer_product_id")) for row in old_candidates if clean(row.get("tcgplayer_product_id"))}
    old_names = {identity_core(row.get("canonical_product_name")) for row in old_candidates if identity_core(row.get("canonical_product_name"))}
    for row in governed:
        tcg_ids = [x for x in clean(row.get("tcgplayer_product_id")).split("|") if x]
        row["in_old_phase_10_subset"] = any(x in old_ids for x in tcg_ids) or clean(row.get("normalized_identity")) in old_names

    owned_crosswalk: list[dict[str, object]] = []
    for owned_name, owned_finish, owned_language in OWNED_PRODUCTS:
        owned_core = identity_core(owned_name)
        candidates: list[tuple[float, dict[str, object]]] = []
        for row in governed:
            candidate_core = clean(row.get("normalized_identity"))
            if not candidate_core:
                continue
            score = SequenceMatcher(None, owned_core, candidate_core).ratio()
            if owned_core == candidate_core:
                score = 1.0
            elif owned_core in candidate_core or candidate_core in owned_core:
                score = max(score, 0.94)
            elif not set(owned_core.split()).intersection(candidate_core.split()):
                continue
            candidate_finish = clean(row.get("detailed_finish"))
            compatible_finish = finish_compatible(owned_finish, candidate_finish)
            if owned_finish != "unspecified" and not compatible_finish:
                continue
            candidate_language = clean(row.get("language"))
            if owned_language and candidate_language and candidate_language != owned_language:
                continue
            if owned_finish != "unspecified" and candidate_finish == owned_finish:
                score += 0.04
            if owned_language and candidate_language == owned_language:
                score += 0.02
            candidates.append((score, row))

        candidates.sort(key=lambda item: item[0], reverse=True)
        if not candidates:
            owned_crosswalk.append({
                "owned_product_name": owned_name,
                "owned_finish": owned_finish,
                "owned_language": owned_language,
                "crosswalk_status": "MISSING_NEEDS_ID_RESOLUTION",
                "match_score": 0,
                "ambiguity_reason": "NO_TITLE_AND_VARIANT_COMPATIBLE_MATCH",
            })
            continue

        best_score, best = candidates[0]
        same_core = [row for _, row in candidates if clean(row.get("normalized_identity")) == owned_core]
        same_core_finishes = sorted({clean(row.get("detailed_finish")) for row in same_core})
        ambiguity = ""
        if owned_finish == "unspecified" and len(same_core_finishes) > 1:
            ambiguity = "OWNED_FINISH_UNSPECIFIED_MULTIPLE_MASTER_VARIANTS"
        elif len(candidates) > 1 and abs(best_score - candidates[1][0]) < 0.02:
            ambiguity = "MULTIPLE_NEAR_EQUAL_IDENTITY_MATCHES"

        if best_score >= 0.94 and not ambiguity:
            status = "MATCHED_CONFIDENT"
        elif best_score >= 0.78:
            status = "MATCHED_REVIEW"
        else:
            status = "MISSING_NEEDS_ID_RESOLUTION"

        owned_crosswalk.append({
            "owned_product_name": owned_name,
            "owned_finish": owned_finish,
            "owned_language": owned_language,
            "crosswalk_status": status,
            "match_score": round(best_score, 4),
            "ambiguity_reason": ambiguity,
            "secret_lair_id": best.get("secret_lair_id", ""),
            "master_product_name": best.get("product_name", ""),
            "master_detailed_finish": best.get("detailed_finish", ""),
            "master_language": best.get("language", ""),
            "tcgplayer_product_id": best.get("tcgplayer_product_id", ""),
            "governance_status": best.get("governance_status", ""),
            "ebay_matching_allowed": best.get("ebay_matching_allowed", ""),
        })

    fields = list(governed[0].keys()) if governed else []
    ready = [row for row in governed if row["governance_status"] == "REGISTRY_READY"]
    review = [row for row in governed if row["governance_status"] == "REVIEW_REQUIRED"]
    write_csv(FULL_OUTPUT, governed, fields)
    write_csv(READY_OUTPUT, ready, fields)
    write_csv(REVIEW_OUTPUT, review, fields)
    owned_fields = [
        "owned_product_name", "owned_finish", "owned_language", "crosswalk_status",
        "match_score", "ambiguity_reason", "secret_lair_id", "master_product_name",
        "master_detailed_finish", "master_language", "tcgplayer_product_id",
        "governance_status", "ebay_matching_allowed",
    ]
    write_csv(OWNED_OUTPUT, owned_crosswalk, owned_fields)

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
