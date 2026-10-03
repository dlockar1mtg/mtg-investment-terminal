import csv, importlib.util, json, sys
from datetime import date
from pathlib import Path
import py7zr, pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("bf", ROOT / "scripts" / "backfill_secret_lair_tcgcsv_history.py")
bf = importlib.util.module_from_spec(spec); sys.modules["bf"] = bf; spec.loader.exec_module(bf)

def write_map(tmp):
    p = tmp / "map.csv"
    with p.open("w", newline="") as h:
        w = csv.writer(h); w.writerow(["secret_lair_id", "product_name", "tcgplayer_product_id", "tcgcsv_group_id"])
        w.writerow(["SL-A", "Drop A", "111", "2576"]); w.writerow(["SL-B", "Drop B", "222", "2576"]); w.writerow(["SL-C", "Bad", "", "2576"])
    return p

def fake_archive(tmp, stamp, prices):
    src = tmp / f"src-{stamp}"; d = src / stamp / "1" / "2576"; d.mkdir(parents=True)
    (d / "prices").write_text(json.dumps({"success": True, "results": prices}))
    other = src / stamp / "3" / "999"; other.mkdir(parents=True); (other / "prices").write_text("{}")
    out = tmp / f"prices-{stamp}.7z"
    with py7zr.SevenZipFile(out, "w") as z: z.writeall(src / stamp, arcname=stamp)
    return out

def test_weekly_dates_are_mondays_from_the_first_archive():
    d = bf.weekly_dates(date(2024, 1, 1), date(2024, 3, 1))
    assert d[0] == date(2024, 2, 12) and all(x.weekday() == 0 for x in d) and d[-1] == date(2024, 2, 26)

def test_backfill_selects_mapped_products_and_resumes(tmp_path):
    archives = {
        "2024-02-12": fake_archive(tmp_path, "2024-02-12", [{"productId": 111, "subTypeName": "Normal", "marketPrice": 40.5, "lowPrice": 35}, {"productId": 999, "marketPrice": 9}]),
        "2024-02-19": fake_archive(tmp_path, "2024-02-19", [{"productId": 111, "subTypeName": "Normal", "marketPrice": 41}, {"productId": 222, "subTypeName": "Foil", "marketPrice": None, "lowPrice": 70}]),
    }
    download = lambda url, dest: dest.write_bytes(archives[url.split("prices-")[1][:10]].read_bytes())
    out = tmp_path / "hist.csv"
    args = ["--map", str(write_map(tmp_path)), "--output", str(out), "--start", "2024-02-12", "--end", "2024-02-19", "--sleep-seconds", "0"]
    assert bf.main(args + ["--max-snapshots", "1"], download=download) == 0
    assert bf.existing_dates(out) == {"2024-02-12"}
    assert bf.main(args, download=download) == 0          # resumes: only the missing week is fetched
    rows = list(csv.DictReader(out.open()))
    assert [(r["snapshot_date"], r["secret_lair_id"], r["market_price"]) for r in rows] == [
        ("2024-02-12", "SL-A", "40.50"), ("2024-02-19", "SL-A", "41.00"), ("2024-02-19", "SL-B", "")]
    assert rows[2]["low_price"] == "70.00" and rows[2]["sub_type"] == "Foil"
    assert bf.main(args, download=download) == 0          # nothing new: no duplicate rows
    assert len(list(csv.DictReader(out.open()))) == 3

def test_a_failed_download_is_reported_and_other_weeks_continue(tmp_path, capsys):
    good = fake_archive(tmp_path, "2024-02-19", [{"productId": 111, "marketPrice": 41}])
    def download(url, dest):
        if "2024-02-12" in url: raise OSError("404")
        dest.write_bytes(good.read_bytes())
    out = tmp_path / "h.csv"
    code = bf.main(["--map", str(write_map(tmp_path)), "--output", str(out), "--start", "2024-02-12", "--end", "2024-02-19", "--sleep-seconds", "0"], download=download)
    assert code == 0 and bf.existing_dates(out) == {"2024-02-19"}
    assert "2024-02-12: OSError" in capsys.readouterr().out
