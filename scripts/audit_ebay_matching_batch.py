from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SUSPICIOUS_PATTERN = re.compile(
    r"presell|pre[- ]?sale|pre[- ]?order|pre aug|\bopened\b|empty|proxy|digital|"
    r"single card|case of|upick|u[- ]?pick|you pick|choice of|"
    r"foil\s*/\s*non[- ]?foil|non[- ]?foil\s*\+\s*foil|"
    r"foil\s*\+\s*non[- ]?foil|foil and non[- ]?foil|"
    r"non[- ]?foil and foil",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an exception-based audit for one eBay matching batch."
    )
    parser.add_argument(
        "--batch-root",
        required=True,
        help="Path to a generated eBay batch directory.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=25,
        help="Number of clean accepted rows to sample deterministically.",
    )
    parser.add_argument(
        "--low-score-threshold",
        type=float,
        default=0.82,
        help="Accepted rows below this score are flagged.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=10,
        help="Deterministic random seed for the accepted-row sample.",
    )
    return parser.parse_args()


def latest_file(batch_root: Path, pattern: str) -> Path:
    files = sorted(batch_root.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No files matching {pattern!r} under {batch_root}")
    return files[0]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def norm(value: str | None) -> str:
    text = (value or "").translate(str.maketrans({"‑": "-", "–": "-", "—": "-", "−": "-"}))
    return re.sub(r"\s+", " ", text.strip())


def finish_subtype(value: str) -> str | None:
    text = value.lower()
    if "double rainbow foil" in text:
        return "double_rainbow"
    if "rainbow foil" in text:
        return "rainbow"
    if "traditional foil" in text or "trad. foil" in text or "trad foil" in text:
        return "traditional"
    if "raised foil" in text:
        return "raised"
    if "foil etched" in text or "etched foil" in text:
        return "etched"
    return None


def flag_row(row: dict[str, str], low_score_threshold: float) -> list[str]:
    reasons: list[str] = []
    state = norm(row.get("match_state")).upper()
    if state != "ACCEPTED":
        return reasons

    canonical = norm(row.get("canonical_product_name"))
    title = norm(row.get("title"))
    exclusion = norm(row.get("exclusion_reasons"))
    score = as_float(row.get("match_score"))

    if exclusion:
        reasons.append("accepted_with_exclusion_reason")
    if score is not None and score < low_score_threshold:
        reasons.append("accepted_below_score_threshold")
    if SUSPICIOUS_PATTERN.search(title):
        reasons.append("suspicious_title_term")

    canonical_bundle = bool(re.search(r"\bbundle\b", canonical, re.IGNORECASE))
    title_bundle = bool(re.search(r"\bbundle\b", title, re.IGNORECASE))
    if canonical_bundle != title_bundle:
        reasons.append("bundle_identity_mismatch")

    canonical_subtype = finish_subtype(canonical)
    title_subtype = finish_subtype(title)
    if canonical_subtype and title_subtype and canonical_subtype != title_subtype:
        reasons.append("explicit_finish_subtype_mismatch")

    nonfoil_pattern = r"\bnon(?:foil|\s*-\s*foil|\s+foil)\b"
    canonical_nonfoil = bool(re.search(nonfoil_pattern, canonical, re.IGNORECASE))
    title_nonfoil = bool(re.search(nonfoil_pattern, title, re.IGNORECASE))
    title_without_nonfoil = re.sub(nonfoil_pattern, " ", title, flags=re.IGNORECASE)
    title_positive_foil = bool(re.search(r"\bfoil\b", title_without_nonfoil, re.IGNORECASE))
    if canonical_nonfoil and title_positive_foil:
        reasons.append("nonfoil_canonical_with_positive_foil_title")
    if not canonical_nonfoil and title_nonfoil and re.search(r"\bfoil\b", canonical, re.IGNORECASE):
        reasons.append("foil_canonical_with_nonfoil_title")

    return reasons


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    batch_root = Path(args.batch_root).resolve()
    if not batch_root.exists():
        raise FileNotFoundError(batch_root)

    listing_path = latest_file(batch_root, "ebay_listing_match_results_*.csv")
    coverage_path = latest_file(batch_root, "ebay_product_coverage_*.csv")
    listings = read_csv(listing_path)
    coverage = read_csv(coverage_path)

    state_counts = Counter(norm(row.get("match_state")).upper() for row in listings)
    coverage_counts = Counter(norm(row.get("coverage_state")) for row in coverage)

    accepted = [row for row in listings if norm(row.get("match_state")).upper() == "ACCEPTED"]
    review = [row for row in listings if norm(row.get("match_state")).upper() == "REVIEW"]

    duplicate_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in accepted:
        item_id = norm(row.get("ebay_item_id"))
        if item_id:
            duplicate_groups[item_id].append(row)

    duplicate_rows: list[dict[str, Any]] = []
    for item_id, rows in duplicate_groups.items():
        canonical_ids = {norm(r.get("canonical_product_id")) for r in rows}
        canonical_names = {norm(r.get("canonical_product_name")) for r in rows}
        if len(canonical_ids) > 1 or len(canonical_names) > 1:
            for row in rows:
                duplicate_rows.append({**row, "audit_reason": "accepted_item_mapped_to_multiple_products"})

    exception_rows: list[dict[str, Any]] = []
    for row in accepted:
        reasons = flag_row(row, args.low_score_threshold)
        if reasons:
            exception_rows.append({**row, "audit_reason": ";".join(sorted(set(reasons)))})

    exception_rows.extend(duplicate_rows)

    seen_keys: set[tuple[str, str, str]] = set()
    deduped_exceptions: list[dict[str, Any]] = []
    for row in exception_rows:
        key = (
            norm(row.get("canonical_product_id")),
            norm(row.get("ebay_item_id")),
            norm(row.get("audit_reason")),
        )
        if key not in seen_keys:
            seen_keys.add(key)
            deduped_exceptions.append(row)

    flagged_item_ids = {norm(row.get("ebay_item_id")) for row in deduped_exceptions}
    clean_accepted = [row for row in accepted if norm(row.get("ebay_item_id")) not in flagged_item_ids]

    rng = random.Random(args.seed)
    sample_size = min(max(args.sample_size, 0), len(clean_accepted))
    sample = rng.sample(clean_accepted, sample_size) if sample_size else []

    review_by_product = Counter(norm(row.get("canonical_product_name")) for row in review)
    review_summary = [
        {"canonical_product_name": name, "review_rows": count}
        for name, count in sorted(review_by_product.items(), key=lambda item: (-item[1], item[0]))
    ]

    output_dir = batch_root / "exception_audit"
    output_dir.mkdir(parents=True, exist_ok=True)

    base_fields = list(listings[0].keys()) if listings else []
    exception_fields = base_fields + (["audit_reason"] if "audit_reason" not in base_fields else [])
    write_csv(output_dir / "accepted_exceptions.csv", deduped_exceptions, exception_fields)
    write_csv(output_dir / "accepted_random_sample.csv", sample, base_fields)
    write_csv(
        output_dir / "review_summary_by_product.csv",
        review_summary,
        ["canonical_product_name", "review_rows"],
    )

    status = "PASS" if not deduped_exceptions else "REVIEW_REQUIRED"
    report = {
        "status": status,
        "batch_root": str(batch_root),
        "listing_path": str(listing_path),
        "coverage_path": str(coverage_path),
        "listing_rows": len(listings),
        "state_counts": dict(sorted(state_counts.items())),
        "coverage_counts": dict(sorted(coverage_counts.items())),
        "accepted_rows": len(accepted),
        "review_rows": len(review),
        "accepted_exception_rows": len(deduped_exceptions),
        "cross_product_duplicate_rows": len(duplicate_rows),
        "clean_accepted_rows": len(clean_accepted),
        "sample_rows": len(sample),
        "sample_seed": args.seed,
        "low_score_threshold": args.low_score_threshold,
        "outputs": {
            "accepted_exceptions": str(output_dir / "accepted_exceptions.csv"),
            "accepted_random_sample": str(output_dir / "accepted_random_sample.csv"),
            "review_summary_by_product": str(output_dir / "review_summary_by_product.csv"),
        },
    }

    report_path = output_dir / "audit_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("EBAY MATCHING EXCEPTION AUDIT: COMPLETE")
    print(json.dumps(report, indent=2))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
