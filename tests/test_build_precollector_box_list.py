import csv, importlib.util, subprocess, sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lst = _load("build_precollector_box_list")
REGISTRY = [{"canonical_product_id": "MTG-CANON-TCGPLAYER-188210", "canonical_product_name": "Core Set 2020 - Booster Box", "tcgplayer_product_id": "188210", "release_date": "2019-07-12"},
            {"canonical_product_id": "MTG-CANON-TCGPLAYER-27262", "canonical_product_name": "Alpha Edition - Booster Box", "tcgplayer_product_id": "27262", "release_date": "1993-08-05"},
            {"canonical_product_id": "MTG-CANON-TCGPLAYER-999", "canonical_product_name": "No Route - Booster Box", "tcgplayer_product_id": "999", "release_date": "2010-01-01"}]
ROUTING = [{"tcgplayer_product_id": "188210", "group_id": "2550"}, {"tcgplayer_product_id": "27262", "group_id": "7"}]


def _write(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_joins_group_ids_and_drops_unrouted_boxes():
    rows, missing = lst.build(REGISTRY, ROUTING)
    assert [r["tcgplayer_product_id"] for r in rows] == ["27262", "188210"]   # oldest first
    assert rows[1]["tcgcsv_group_id"] == "2550" and rows[1]["release_date"] == "2019-07-12"
    assert missing == ["999"]


def test_output_is_readable_by_the_box_collector(tmp_path):
    out = tmp_path / "precollector_model_input.csv"
    proc = subprocess.run([sys.executable, str(SCRIPTS / "build_precollector_box_list.py"),
                           "--registry", str(_write(tmp_path / "reg.csv", REGISTRY)),
                           "--routing", str(_write(tmp_path / "route.csv", ROUTING)), "--output", str(out)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "2 Pre-Collector boxes written; 1 without" in proc.stdout
    boxes = _load("collect_box_tcgcsv_prices").load_boxes(out)
    assert set(boxes) == {"27262", "188210"} and boxes["188210"] == {"box_name": "Core Set 2020 - Booster Box", "group": "2550"}
