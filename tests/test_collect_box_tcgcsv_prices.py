import csv, importlib.util, sys
from datetime import date
from pathlib import Path
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("boxes", SCRIPTS / "collect_box_tcgcsv_prices.py")
bx = importlib.util.module_from_spec(spec); sys.modules["boxes"] = bx; spec.loader.exec_module(bx)

def box_file(tmp):
    p = tmp / "boxes.csv"
    with p.open("w", newline="") as h:
        w = csv.writer(h); w.writerow(["box_name", "tcgplayer_product_id", "tcgcsv_group_id"])
        w.writerow(["Set A Collector", "111", "10"]); w.writerow(["Set B Collector", "222", "20"]); w.writerow(["Bad", "", "30"])
    return p

def test_one_request_per_group_latest_daily_history_weekly(tmp_path):
    prices = {"https://tcgcsv.com/tcgplayer/1/10/prices": {"results": [{"productId": 111, "subTypeName": "Normal", "marketPrice": 300, "lowPrice": 270, "directLowPrice": 285}, {"productId": 999, "marketPrice": 5}]},
              "https://tcgcsv.com/tcgplayer/1/20/prices": {"results": [{"productId": 222, "marketPrice": 450.5}]}}
    calls = []
    def fetch(url):
        calls.append(url); return prices[url]
    args = ["--boxes", str(box_file(tmp_path)), "--output-dir", str(tmp_path / "out"), "--sleep-seconds", "0"]
    assert bx.main(args, fetch=fetch, today=date(2026, 10, 5)) == 0
    assert sorted(calls) == sorted(prices)                                       # one request per group
    latest = list(csv.DictReader((tmp_path / "out" / "collector_latest_prices.csv").open()))
    assert [(r["tcgplayer_product_id"], r["market_price"], r["low_price"], r["direct_low_price"]) for r in latest] == [("111", "300.00", "270.00", "285.00"), ("222", "450.50", "", "")]
    assert bx.main(args, fetch=fetch, today=date(2026, 10, 7)) == 0             # same week: history not duplicated
    weekly = list(csv.DictReader((tmp_path / "out" / "collector_weekly_prices.csv").open()))
    assert {r["snapshot_date"] for r in weekly} == {"2026-10-05"}

def test_a_failed_group_is_reported_and_others_continue(tmp_path, capsys):
    def fetch(url):
        if "/10/" in url: raise OSError("down")
        return {"results": [{"productId": 222, "marketPrice": 450}]}
    assert bx.main(["--boxes", str(box_file(tmp_path)), "--output-dir", str(tmp_path / "o"), "--sleep-seconds", "0"], fetch=fetch, today=date(2026, 10, 5)) == 0
    assert "10: OSError" in capsys.readouterr().out

def test_nothing_priced_fails_without_writing(tmp_path):
    out = tmp_path / "o"
    assert bx.main(["--boxes", str(box_file(tmp_path)), "--output-dir", str(out), "--sleep-seconds", "0"], fetch=lambda url: {"results": []}, today=date(2026, 10, 5)) == 1
    assert not out.exists()
