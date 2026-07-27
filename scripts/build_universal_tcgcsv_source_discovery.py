from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data/reference/phase_11/mtg_hosted_baseline/secret_lair_registry.csv"
SNAPSHOT_ROOT = ROOT / "data/operations/mtg_source_discovery/tcgcsv_snapshots"
OUTPUT = ROOT / "data/operations/mtg_source_discovery/universal_tcgcsv_discovery"

def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))

def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())

def norm(value: object) -> str:
    value_text = text(value).casefold()
    replacements = (
        "secret lair drop series",
        "secret lair commander deck",
        "secret lair drop",
        "secret lair",
        "traditional foil edition",
        "rainbow foil edition",
        "galaxy foil edition",
        "double rainbow foil edition",
        "foil etched edition",
        "etched foil edition",
        "non-foil edition",
        "nonfoil edition",
        "foil edition",
    )
    for item in replacements:
        value_text = value_text.replace(item, " ")
    value_text = re.sub(r"\b(drop|edition)\b", " ", value_text)
    value_text = re.sub(r"[^a-z0-9]+", " ", value_text)
    return re.sub(r"\s+", " ", value_text).strip()

def finish(value: object) -> str:
    value_text = f" {text(value).casefold()} "
    checks = (
        ("DOUBLE_RAINBOW_FOIL", ("double rainbow foil",)),
        ("RAINBOW_FOIL", ("rainbow foil",)),
        ("GALAXY_FOIL", ("galaxy foil",)),
        ("HALO_FOIL", ("halo foil",)),
        ("RAISED_FOIL", ("raised foil",)),
        ("NEON_INK_FOIL", ("neon ink foil",)),
        ("ETCHED_FOIL", ("etched foil", "foil etched")),
        ("NONFOIL", ("non foil", "non-foil", "nonfoil")),
        ("FOIL", ("traditional foil", " foil ")),
    )
    for label, terms in checks:
        if any(term in value_text for term in terms):
            return label
    return "UNSPECIFIED"

def secret_lair_evidence(row: dict[str, str]) -> bool:
    combined = f"{text(row.get('group_name'))} {text(row.get('product_name'))}".casefold()
    return "secret lair" in combined or text(row.get("group_name")).casefold() == "slx cards"

def sealed_evidence(row: dict[str, str]) -> bool:
    group = text(row.get("group_name")).casefold()
    product = text(row.get("product_name")).casefold()

    bad_patterns = (
        r"display commander",
        r"thick stock",
        r"double[- ]sided token",
        r"\btoken\b",
        r"\bemblem\b",
        r"\bplaymat\b",
        r"\bsleeves?\b",
        r"\bdeck box\b",
        r"\bempty box\b",
    )
    if any(re.search(pattern, product) for pattern in bad_patterns):
        return False

    good_patterns = (
        r"\bsecret lair drop\s*:",
        r"\bsecret lair commander deck\s*:",
        r"\bsecret lair.*\bbundle\b",
        r"\bcountdown kit\b",
        r"\bfestival in a box\b",
        r"\bfull bundle\b",
    )
    if any(re.search(pattern, product) for pattern in good_patterns):
        return True

    if "secret lair countdown kit" in group:
        return "countdown kit" in product or "book club bundle" in product

    return False

def latest_snapshot(root: Path) -> Path:
    valid: list[tuple[str, Path]] = []
    for manifest in root.glob("*/tcgcsv_snapshot_manifest.json"):
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        products = manifest.parent / "tcgcsv_magic_products.csv"
        if (
            payload.get("snapshot_status") == "COMPLETE"
            and not bool(payload.get("limited_run"))
            and int(payload.get("failed_groups", 0) or 0) == 0
            and products.is_file()
        ):
            valid.append((str(payload.get("generated_at_utc") or manifest.parent.name), products))
    if not valid:
        raise FileNotFoundError("No complete archived TCGCSV snapshot found.")
    return sorted(valid, key=lambda item: item[0])[-1][1]

def score(product: dict[str, str], candidate: dict[str, str]) -> dict[str, Any]:
    governed = norm(product.get("canonical_product_name"))
    catalog = norm(candidate.get("product_name"))
    governed_tokens = set(governed.split())
    catalog_tokens = set(catalog.split())
    exact = bool(governed) and governed == catalog
    sequence = SequenceMatcher(None, governed, catalog).ratio()
    union = governed_tokens | catalog_tokens
    jaccard = len(governed_tokens & catalog_tokens) / len(union) if union else 0.0
    containment = (
        len(governed_tokens & catalog_tokens) / len(governed_tokens)
        if governed_tokens else 0.0
    )

    governed_finish = text(product.get("finish_group")).upper() or "UNSPECIFIED"
    catalog_finish = finish(candidate.get("product_name"))
    finish_conflict = (
        governed_finish != "UNSPECIFIED"
        and catalog_finish != "UNSPECIFIED"
        and governed_finish != catalog_finish
    )
    finish_match = not finish_conflict

    value = (
        (0.55 if exact else 0.0)
        + 0.20 * sequence
        + 0.15 * jaccard
        + 0.10 * containment
        + (0.05 if finish_match else -0.20)
    )
    return {
        "candidate_score": round(max(0.0, min(1.0, value)), 6),
        "exact_normalized_name": exact,
        "governed_normalized_name": governed,
        "candidate_normalized_name": catalog,
        "sequence_similarity": round(sequence, 6),
        "token_jaccard": round(jaccard, 6),
        "governed_token_containment": round(containment, 6),
        "governed_finish": governed_finish,
        "candidate_finish": catalog_finish,
        "finish_match": finish_match,
        "finish_conflict": finish_conflict,
    }

def classify(rows: list[dict[str, Any]]) -> tuple[str, str]:
    if not rows:
        return "TCGCSV_ID_NOT_FOUND", "No TCGCSV candidate was found."

    best = rows[0]
    best_score = float(best["candidate_score"])
    second_score = float(rows[1]["candidate_score"]) if len(rows) > 1 else -1.0
    margin = best_score - second_score

    exact_compatible = bool(best["exact_normalized_name"]) and bool(best["finish_match"])
    competing_exact = any(
        bool(row["exact_normalized_name"])
        and bool(row["finish_match"])
        and row["tcgplayer_product_id"] != best["tcgplayer_product_id"]
        for row in rows[1:]
    )

    if exact_compatible and not competing_exact and margin >= 0.03:
        return "TCGCSV_ID_CONFIRMED", "Unique exact normalized-name match with compatible finish."
    if exact_compatible and competing_exact:
        return "TCGCSV_ID_AMBIGUOUS", "Multiple exact finish-compatible TCGCSV products require review."
    if best_score >= 0.85 and bool(best["finish_match"]) and margin >= 0.05:
        return "TCGCSV_ID_HIGH_CONFIDENCE_CANDIDATE", "Strong compatible candidate with a clear score margin."
    return "TCGCSV_ID_AMBIGUOUS", "At least one candidate exists but requires manual or rule-based review."

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--snapshot-root", type=Path, default=SNAPSHOT_ROOT)
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    args = parser.parse_args()

    registry = read_csv(args.registry.resolve())
    if len(registry) != 973:
        raise SystemExit(f"Expected 973 Secret Lairs; found {len(registry)}")

    snapshot_path = args.snapshot.resolve() if args.snapshot else latest_snapshot(args.snapshot_root.resolve())
    snapshot = read_csv(snapshot_path)
    secret_rows = [row for row in snapshot if secret_lair_evidence(row)]
    sealed_rows = [row for row in secret_rows if sealed_evidence(row)]

    exact_index: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in secret_rows:
        key = norm(row.get("product_name"))
        if key:
            exact_index[key].append(row)

    candidates: list[dict[str, Any]] = []
    resolutions: list[dict[str, Any]] = []

    for product in registry:
        governed_key = norm(product.get("canonical_product_name"))
        pool: dict[str, dict[str, str]] = {}

        for candidate in exact_index.get(governed_key, []):
            product_id = text(candidate.get("tcgplayer_product_id"))
            if product_id:
                pool[product_id] = candidate

        governed_tokens = set(governed_key.split())
        for candidate in sealed_rows:
            candidate_key = norm(candidate.get("product_name"))
            candidate_tokens = set(candidate_key.split())
            if governed_tokens and candidate_tokens and not (governed_tokens & candidate_tokens):
                continue
            product_id = text(candidate.get("tcgplayer_product_id"))
            if product_id:
                pool.setdefault(product_id, candidate)

        rows: list[dict[str, Any]] = []
        for candidate in pool.values():
            metrics = score(product, candidate)
            if not metrics["exact_normalized_name"] and float(metrics["candidate_score"]) < 0.45:
                continue
            rows.append({
                "investment_product_id": product.get("investment_product_id", ""),
                "canonical_product_name": product.get("canonical_product_name", ""),
                "finish_group": product.get("finish_group", ""),
                "product_group": product.get("product_group", ""),
                "tcgcsv_group_id": candidate.get("tcgcsv_group_id", ""),
                "tcgcsv_group_name": candidate.get("group_name", ""),
                "tcgplayer_product_id": candidate.get("tcgplayer_product_id", ""),
                "tcgcsv_product_name": candidate.get("product_name", ""),
                "sealed_evidence": sealed_evidence(candidate),
                **metrics,
            })

        rows.sort(
            key=lambda row: (
                float(row["candidate_score"]),
                bool(row["exact_normalized_name"]),
                bool(row["finish_match"]),
                bool(row["sealed_evidence"]),
            ),
            reverse=True,
        )

        for rank, row in enumerate(rows[:10], start=1):
            output_row = dict(row)
            output_row["candidate_rank"] = rank
            candidates.append(output_row)

        status, reason = classify(rows)
        best = rows[0] if rows else {}
        resolutions.append({
            "investment_product_id": product.get("investment_product_id", ""),
            "canonical_product_name": product.get("canonical_product_name", ""),
            "finish_group": product.get("finish_group", ""),
            "product_group": product.get("product_group", ""),
            "tcgcsv_group_id": best.get("tcgcsv_group_id", ""),
            "tcgcsv_group_name": best.get("tcgcsv_group_name", ""),
            "tcgplayer_product_id": best.get("tcgplayer_product_id", ""),
            "tcgcsv_product_name": best.get("tcgcsv_product_name", ""),
            "candidate_score": best.get("candidate_score", ""),
            "exact_normalized_name": best.get("exact_normalized_name", False),
            "candidate_finish": best.get("candidate_finish", ""),
            "finish_match": best.get("finish_match", False),
            "finish_conflict": best.get("finish_conflict", False),
            "sealed_evidence": best.get("sealed_evidence", False),
            "candidate_count": len(rows),
            "discovery_status": status,
            "discovery_reason": reason,
        })

    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    candidate_fields = list(candidates[0].keys()) if candidates else ["investment_product_id"]
    resolution_fields = list(resolutions[0].keys())

    write_csv(output / "universal_tcgcsv_candidate_matches.csv", candidates, candidate_fields)
    write_csv(output / "universal_tcgcsv_identity_resolution.csv", resolutions, resolution_fields)

    review = [
        row for row in resolutions
        if row["discovery_status"] in {
            "TCGCSV_ID_HIGH_CONFIDENCE_CANDIDATE",
            "TCGCSV_ID_AMBIGUOUS",
        }
    ]
    write_csv(output / "universal_tcgcsv_manual_review_queue.csv", review, resolution_fields)

    counts = Counter(row["discovery_status"] for row in resolutions)
    products_with_candidates = sum(int(row["candidate_count"]) > 0 for row in resolutions)
    classified_with_candidates = sum(
        counts.get(status, 0)
        for status in (
            "TCGCSV_ID_CONFIRMED",
            "TCGCSV_ID_HIGH_CONFIDENCE_CANDIDATE",
            "TCGCSV_ID_AMBIGUOUS",
        )
    )

    summary = {
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_path": str(snapshot_path),
        "snapshot_product_rows": len(snapshot),
        "secret_lair_evidence_rows": len(secret_rows),
        "sealed_candidate_rows": len(sealed_rows),
        "governed_secret_lair_products": len(registry),
        "identity_resolution_rows": len(resolutions),
        "candidate_match_rows": len(candidates),
        "discovery_status_counts": dict(sorted(counts.items())),
        "products_with_any_candidate": products_with_candidates,
        "products_without_candidate": sum(int(row["candidate_count"]) == 0 for row in resolutions),
        "review_queue_rows": len(review),
        "certification_checks": {
            "governed_secret_lairs_equal_973": len(registry) == 973,
            "identity_rows_equal_973": len(resolutions) == 973,
            "canonical_ids_unique": len({row["investment_product_id"] for row in resolutions}) == 973,
            "all_products_accounted_for": sum(counts.values()) == 973,
            "snapshot_contains_full_catalog": len(snapshot) >= 100000,
            "candidate_products_not_mislabeled_not_found": products_with_candidates == classified_with_candidates,
            "review_queue_matches_review_statuses": len(review) == (
                counts.get("TCGCSV_ID_HIGH_CONFIDENCE_CANDIDATE", 0)
                + counts.get("TCGCSV_ID_AMBIGUOUS", 0)
            ),
        },
    }
    if not all(summary["certification_checks"].values()):
        summary["status"] = "FAIL"

    (output / "universal_tcgcsv_source_discovery_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2

if __name__ == "__main__":
    raise SystemExit(main())
