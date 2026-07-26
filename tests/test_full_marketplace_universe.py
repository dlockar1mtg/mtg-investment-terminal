from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.build_full_marketplace_product_map import build_full_product_map
from scripts.run_full_marketplace_universe import _batch_ranges


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_full_product_map_classifies_ready_and_incomplete_rows(tmp_path: Path) -> None:
    model = tmp_path / "model.csv"
    _write(model, [
        {
            "box_name_master": "Ready Box",
            "approved_product_name": "Ready Box Display",
            "approved_tcgplayer_product_id": "123",
            "tcgcsv_category_id_master": "1",
            "tcgcsv_group_id_master": "99",
            "approval_status": "approved",
            "investment_product_id": "IP-1",
            "investment_product_type": "Collector Booster Display",
            "notes": "",
        },
        {
            "box_name_master": "Missing Group",
            "approved_product_name": "Missing Group Display",
            "approved_tcgplayer_product_id": "456",
            "tcgcsv_category_id_master": "1",
            "tcgcsv_group_id_master": "",
            "approval_status": "approved",
            "investment_product_id": "IP-2",
            "investment_product_type": "Collector Booster Display",
            "notes": "",
        },
    ])
    output = tmp_path / "map.csv"
    summary = tmp_path / "summary.json"
    payload = build_full_product_map(model, output, summary)
    assert payload["status"] == "PASS"
    assert payload["ready_product_count"] == 1
    assert payload["status_counts"]["MISSING_TCGCSV_GROUP"] == 1
    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert rows[0]["mapping_status"] == "READY"
    assert rows[1]["mapping_status"] == "MISSING_TCGCSV_GROUP"
    assert json.loads(summary.read_text(encoding="utf-8"))["unique_product_count"] == 2


def test_duplicate_product_identity_is_written_once(tmp_path: Path) -> None:
    model = tmp_path / "model.csv"
    row = {
        "box_name_master": "Box",
        "approved_product_name": "Box Display",
        "approved_tcgplayer_product_id": "123",
        "tcgcsv_category_id_master": "1",
        "tcgcsv_group_id_master": "99",
        "approval_status": "approved",
        "investment_product_id": "IP-1",
        "investment_product_type": "Collector Booster Display",
        "notes": "",
    }
    _write(model, [row, dict(row)])
    payload = build_full_product_map(model, tmp_path / "map.csv", tmp_path / "summary.json")
    assert payload["unique_product_count"] == 1
    assert payload["status_counts"]["DUPLICATE_IDENTITY"] == 1


def test_batch_ranges_cover_entire_universe_without_overlap() -> None:
    ranges = _batch_ranges(1001, 50)
    assert len(ranges) == 21
    assert ranges[0] == (0, 50)
    assert ranges[-1] == (1000, 1001)
    covered = [index for start, end in ranges for index in range(start, end)]
    assert covered == list(range(1001))
