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

def test_low_group_coverage_fails_and_keeps_the_previous_files(tmp_path, capsys):
    # Was: one of two groups failing still exited 0 and overwrote the latest file with the other
    # group alone, silently dropping box 111. 1 of 2 groups is 50% coverage, below the 95% bar.
    out = tmp_path / "o"
    args = ["--boxes", str(box_file(tmp_path)), "--output-dir", str(out), "--sleep-seconds", "0"]
    good = {"results": [{"productId": 111, "marketPrice": 300}, {"productId": 222, "marketPrice": 450}]}
    assert bx.main(args, fetch=lambda url: good, today=date(2026, 10, 5)) == 0
    before = (out / "collector_latest_prices.csv").read_text()
    def fetch(url):
        if "/10/" in url: raise OSError("down")
        return {"results": [{"productId": 222, "marketPrice": 460}]}
    assert bx.main(args, fetch=fetch, today=date(2026, 10, 12)) == 1
    printed = capsys.readouterr().out
    assert "10: OSError" in printed and "BOX FETCH FAILED" in printed
    assert (out / "collector_latest_prices.csv").read_text() == before
    weekly = list(csv.DictReader((out / "collector_weekly_prices.csv").open()))
    assert {r["snapshot_date"] for r in weekly} == {"2026-10-05"}


def many_boxes(tmp, n=25):
    p = tmp / "many.csv"
    with p.open("w", newline="") as h:
        w = csv.writer(h); w.writerow(["box_name", "tcgplayer_product_id", "tcgcsv_group_id"])
        for g in range(n):
            w.writerow([f"Box {g}", str(500 + g), str(100 + g)])
    return p


def test_one_failed_group_of_many_carries_its_previous_row_forward(tmp_path):
    out = tmp_path / "o"
    args = ["--boxes", str(many_boxes(tmp_path)), "--output-dir", str(out), "--sleep-seconds", "0"]
    def priced(price):
        return lambda url: {"results": [{"productId": 500 + int(url.split("/")[-2]) - 100, "marketPrice": price}]}
    assert bx.main(args, fetch=priced(100), today=date(2026, 10, 5)) == 0
    def one_down(url):
        if "/1/100/" in url: raise OSError("down")
        return priced(110)(url)
    assert bx.main(args, fetch=one_down, today=date(2026, 10, 12)) == 0       # 24 of 25 groups = 96%
    latest = {r["tcgplayer_product_id"]: r for r in csv.DictReader((out / "collector_latest_prices.csv").open())}
    assert len(latest) == 25
    assert (latest["500"]["snapshot_date"], latest["500"]["market_price"], latest["500"]["stale_carried"]) == ("2026-10-05", "100.00", "true")
    assert (latest["501"]["snapshot_date"], latest["501"]["market_price"], latest["501"]["stale_carried"]) == ("2026-10-12", "110.00", "")
    weekly = list(csv.DictReader((out / "collector_weekly_prices.csv").open()))
    assert "stale_carried" not in weekly[0]                                    # history keeps its old columns
    assert sorted(r["tcgplayer_product_id"] for r in weekly if r["snapshot_date"] == "2026-10-12") == [str(500 + g) for g in range(1, 25)]
    def two_down(url):                                                         # 23 of 25 = 92%: refuse
        if "/1/100/" in url or "/1/101/" in url: raise OSError("down")
        return priced(120)(url)
    assert bx.main(args, fetch=two_down, today=date(2026, 10, 19)) == 1

def test_nothing_priced_fails_without_writing(tmp_path):
    out = tmp_path / "o"
    assert bx.main(["--boxes", str(box_file(tmp_path)), "--output-dir", str(out), "--sleep-seconds", "0"], fetch=lambda url: {"results": []}, today=date(2026, 10, 5)) == 1
    assert not out.exists()
