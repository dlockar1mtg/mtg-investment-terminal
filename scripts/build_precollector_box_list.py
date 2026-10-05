"""Build the Pre-Collector box list for daily TCGCSV prices.

Joins the Pre-Collector registry (names, TCGplayer product ids, release dates) with the TCGCSV
routing table (group ids) and writes data/product_master/precollector_model_input.csv, the
--boxes input of collect_box_tcgcsv_prices.py --segment precollector.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "reference" / "phase_11" / "mtg_hosted_baseline" / "pre_collector_registry.csv"
ROUTING = ROOT / "data" / "validation" / "phase_10" / "historical_tcgcsv_routing" / "historical_tcgcsv_product_routing_2026-07-22.csv"
OUTPUT = ROOT / "data" / "product_master" / "precollector_model_input.csv"
FIELDS = ["tcgplayer_product_id", "tcgcsv_group_id", "box_name", "release_date", "canonical_product_id"]


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def build(registry, routing):
    groups = {str(r.get("tcgplayer_product_id") or "").strip(): str(r.get("group_id") or "").strip() for r in routing}
    out, missing = [], []
    for r in registry:
        product = str(r.get("tcgplayer_product_id") or "").strip()
        group = groups.get(product, "")
        if not (product.isdigit() and group.isdigit()):
            missing.append(product or str(r.get("canonical_product_id") or ""))
            continue
        out.append({"tcgplayer_product_id": product, "tcgcsv_group_id": group,
                    "box_name": str(r.get("canonical_product_name") or "").strip(),
                    "release_date": str(r.get("release_date") or "").strip()[:10],
                    "canonical_product_id": str(r.get("canonical_product_id") or "").strip()})
    out.sort(key=lambda r: (r["release_date"], r["box_name"]))
    return out, missing


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--routing", type=Path, default=ROUTING)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    rows, missing = build(_rows(args.registry), _rows(args.routing))
    if not rows:
        raise SystemExit("no Pre-Collector boxes with product and group ids")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} Pre-Collector boxes written; {len(missing)} without a TCGCSV group id")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
