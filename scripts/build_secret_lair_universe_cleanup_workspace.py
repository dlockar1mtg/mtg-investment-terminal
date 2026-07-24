from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/validation/phase_10/premium_universe_eligibility/secret_lair_structural_candidates_2026-07-22.csv"
OUTPUT_DIR = SOURCE.parent
INVENTORY_PATH = OUTPUT_DIR / "secret_lair_owned_inventory_seed.csv"
CROSSWALK_PATH = OUTPUT_DIR / "secret_lair_owned_inventory_crosswalk.csv"
ADDITIONS_PATH = OUTPUT_DIR / "secret_lair_universe_additions.csv"
WORKING_UNIVERSE_PATH = OUTPUT_DIR / "secret_lair_complete_universe_working.csv"

OWNED_PRODUCTS = [
    "Secret Lair: Mark Poole - Traditional Foil",
    "Secret Lair: Path of Ancestry - Rainbow Foil",
    "Secret Lair: A Lot to Learn",
    "Secret Lair: One with the Elements",
    "Secret Lair: My Cabbages!",
    "Secret Lair: Ember Island Players",
    "Secret Lair: Everything Changed",
    "Secret Lair: February Superdrop - Special Guest: Yuko Shimizu - Traditional Foil",
    "Secret Lair: Mother's Day 2021 - Traditional Foil",
    "Secret Lair: The Space Beyond the Stars - Traditional Foil",
    "Secret Lair: Hatsune Miku: Winter Diva - Rainbow Foil",
    "Secret Lair: Blood Bowl - Traditional Foil",
]

FINISH_PATTERNS = (
    ("rainbow_foil", re.compile(r"\brainbow\s+foil\b", re.I)),
    ("traditional_foil", re.compile(r"\btraditional\s+foil\b|\bfoil\s+edition\b", re.I)),
    ("non_foil", re.compile(r"\bnon[-\s]?foil\b", re.I)),
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def finish(value: str) -> str:
    for label, pattern in FINISH_PATTERNS:
        if pattern.search(value):
            return label
    return "unspecified"


def normalize(value: str, *, remove_finish: bool = False) -> str:
    text = value.lower()
    text = text.replace("’", "'")
    text = re.sub(r"^secret\s+lair(?:\s+drop)?\s*:\s*", "", text)
    text = re.sub(r"^secret\s+lair\s+drop\s+series\s*", "", text)
    text = re.sub(r"\bsecret\s+lair\b", " ", text)
    text = re.sub(r"\b(drop|series|edition|sealed|factory|bundle|pack)\b", " ", text)
    if remove_finish:
        text = re.sub(r"\brainbow\s+foil\b", " ", text)
        text = re.sub(r"\btraditional\s+foil\b", " ", text)
        text = re.sub(r"\bnon[-\s]?foil\b", " ", text)
        text = re.sub(r"\bfoil\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def token_similarity(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def best_match(owned_name: str, candidates: list[dict[str, str]]) -> tuple[dict[str, str] | None, str, float]:
    owned_exact = normalize(owned_name)
    owned_base = normalize(owned_name, remove_finish=True)
    owned_finish = finish(owned_name)

    exact_matches = [
        row for row in candidates
        if normalize(row.get("canonical_product_name", "")) == owned_exact
    ]
    if exact_matches:
        return exact_matches[0], "FOUND_EXACT", 1.0

    scored: list[tuple[float, dict[str, str]]] = []
    for row in candidates:
        candidate_name = row.get("canonical_product_name", "")
        candidate_base = normalize(candidate_name, remove_finish=True)
        score = token_similarity(owned_base, candidate_base)
        candidate_finish = finish(candidate_name)
        if owned_finish != "unspecified" and candidate_finish not in {owned_finish, "unspecified"}:
            score -= 0.25
        scored.append((score, row))

    scored.sort(key=lambda item: item[0], reverse=True)
    if scored and scored[0][0] >= 0.72:
        return scored[0][1], "FOUND_RELAXED_REVIEW", round(scored[0][0], 4)
    return (scored[0][1] if scored else None), "MISSING_NEEDS_ID_RESOLUTION", round(scored[0][0], 4) if scored else 0.0


def pending_id(name: str) -> str:
    slug = normalize(name, remove_finish=False).upper().replace(" ", "-")
    return f"MTG-PENDING-SECRET-LAIR-{slug[:80]}"


def main() -> int:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Missing source file: {SOURCE}")

    source_rows = read_csv(SOURCE)
    if not source_rows:
        raise RuntimeError("Secret Lair source file contains no rows")

    source_fields = list(source_rows[0].keys())
    inventory_rows = [
        {
            "owned_product_name": name,
            "owned_finish": finish(name),
            "condition": "sealed",
            "language": "English",
            "inventory_review_status": "mandatory_universe_check",
        }
        for name in OWNED_PRODUCTS
    ]
    write_csv(
        INVENTORY_PATH,
        inventory_rows,
        ["owned_product_name", "owned_finish", "condition", "language", "inventory_review_status"],
    )

    crosswalk_rows: list[dict[str, str]] = []
    addition_rows: list[dict[str, str]] = []
    working_rows = list(source_rows)

    for owned_name in OWNED_PRODUCTS:
        match, status, similarity = best_match(owned_name, source_rows)
        matched_name = match.get("canonical_product_name", "") if match else ""
        matched_id = match.get("canonical_product_id", "") if match else ""
        matched_tcg = match.get("tcgplayer_product_id", "") if match else ""
        finish_match = ""
        if match:
            finish_match = str(finish(owned_name) == finish(matched_name) or finish(matched_name) == "unspecified")

        crosswalk_rows.append(
            {
                "owned_product_name": owned_name,
                "owned_finish": finish(owned_name),
                "crosswalk_status": status,
                "similarity": str(similarity),
                "matched_canonical_product_id": matched_id,
                "matched_tcgplayer_product_id": matched_tcg,
                "matched_canonical_product_name": matched_name,
                "finish_compatible": finish_match,
                "review_note": "Verify identity and finish" if status == "FOUND_RELAXED_REVIEW" else "Resolve official/market product ID" if status.startswith("MISSING") else "",
            }
        )

        if status.startswith("MISSING"):
            row = {field: "" for field in source_fields}
            row.update(
                {
                    "canonical_product_id": pending_id(owned_name),
                    "tcgplayer_product_id": "",
                    "canonical_set_name": "Secret Lair Drop Series",
                    "canonical_product_name": owned_name,
                    "canonical_product_class": "secret_lair_product",
                    "canonical_product_family": "secret_lair",
                    "canonical_product_type": "secret_lair_individual_drop",
                    "canonical_packaging_level": "individual_drop",
                    "identity_lifecycle_status": "active",
                    "source_availability_status": "user_verified_owned_sealed",
                    "governance_review_status": "required",
                    "investment_approval_status": "review_required",
                    "prior_investment_eligibility_status": "not_evaluated",
                    "structural_eligibility_state": "provisionally_eligible",
                    "structural_eligibility_reason": "user_verified_sealed_secret_lair_missing_from_candidate_universe",
                    "final_eligibility_decision": "not_decided",
                    "final_decision_reason": "pending_product_id_and_catalog_verification",
                    "historical_review_required": "False",
                    "sealed_product_review_required": "True",
                    "classification_review_required": "True",
                    "scoring_allowed": "False",
                    "universal_investable_allowed": "False",
                }
            )
            addition_rows.append(row)
            working_rows.append(row)

    write_csv(
        CROSSWALK_PATH,
        crosswalk_rows,
        [
            "owned_product_name",
            "owned_finish",
            "crosswalk_status",
            "similarity",
            "matched_canonical_product_id",
            "matched_tcgplayer_product_id",
            "matched_canonical_product_name",
            "finish_compatible",
            "review_note",
        ],
    )
    write_csv(ADDITIONS_PATH, addition_rows, source_fields)
    write_csv(
        WORKING_UNIVERSE_PATH,
        sorted(working_rows, key=lambda row: row.get("canonical_product_name", "")),
        source_fields,
    )

    counts: dict[str, int] = {}
    for row in crosswalk_rows:
        status = row["crosswalk_status"]
        counts[status] = counts.get(status, 0) + 1

    print("SECRET LAIR UNIVERSE CLEANUP WORKSPACE: COMPLETE")
    print(f"Current source rows: {len(source_rows)}")
    print(f"Owned products checked: {len(OWNED_PRODUCTS)}")
    print(f"Provisional additions: {len(addition_rows)}")
    for status in sorted(counts):
        print(f"{status}: {counts[status]}")
    print(f"Inventory seed: {INVENTORY_PATH.relative_to(ROOT)}")
    print(f"Crosswalk: {CROSSWALK_PATH.relative_to(ROOT)}")
    print(f"Additions: {ADDITIONS_PATH.relative_to(ROOT)}")
    print(f"Working universe: {WORKING_UNIVERSE_PATH.relative_to(ROOT)}")
    print("Active eBay universe source was not changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
