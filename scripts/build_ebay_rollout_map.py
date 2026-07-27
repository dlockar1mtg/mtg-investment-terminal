from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


PRODUCT_ID_FIELDS = (
    "tcgplayer_product_id",
    "canonical_product_id",
    "product_id",
    "source_product_id",
)

PRODUCT_NAME_FIELDS = (
    "canonical_product_name",
    "source_product_name",
    "box_name",
    "product_name",
    "name",
)


def _clean(value: object) -> str:
    return str(value or "").strip()


def _first_value(row: dict[str, str], fields: tuple[str, ...]) -> str:
    for field in fields:
        value = _clean(row.get(field))
        if value:
            return value
    return ""


def _product_id(row: dict[str, str]) -> str:
    return _first_value(row, PRODUCT_ID_FIELDS)


def _product_name(row: dict[str, str]) -> str:
    return _first_value(row, PRODUCT_NAME_FIELDS)


def build_rollout_map(
    source: Path,
    output: Path,
    summary_output: Path,
    product_count: int,
) -> dict[str, object]:
    if product_count < 1:
        raise ValueError("product_count must be positive")

    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        source_rows = list(reader)

    if not fieldnames:
        raise RuntimeError("source map has no header")

    eligible: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for row in source_rows:
        product_id = _product_id(row)
        if not product_id or product_id in seen_ids:
            continue
        seen_ids.add(product_id)
        eligible.append(row)

    eligible.sort(key=lambda row: (_product_name(row).casefold(), _product_id(row)))

    if len(eligible) < product_count:
        raise RuntimeError(
            f"source map has only {len(eligible)} unique eligible products; "
            f"{product_count} required"
        )

    selected = eligible[:product_count]
    selected_ids = [_product_id(row) for row in selected]

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(selected)

    summary = {
        "status": "PASS",
        "mode": "BOUNDED_ROLLOUT_MAP",
        "source_map": str(source.resolve()),
        "output_map": str(output.resolve()),
        "source_row_count": len(source_rows),
        "eligible_unique_product_count": len(eligible),
        "selected_product_count": len(selected),
        "unique_product_id_count": len(set(selected_ids)),
        "selection_policy": "DETERMINISTIC_NAME_THEN_ID_PREFIX",
        "selected_products": [
            {
                "product_id": _product_id(row),
                "product_name": _product_name(row),
            }
            for row in selected
        ],
    }

    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a deterministic bounded eBay rollout product map"
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--product-count", type=int, default=25)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = build_rollout_map(
        source=args.source,
        output=args.output,
        summary_output=args.summary_output,
        product_count=args.product_count,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
