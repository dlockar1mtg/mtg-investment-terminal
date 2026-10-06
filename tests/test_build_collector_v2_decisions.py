import csv, importlib.util, json, math, subprocess, sys
from datetime import date
from pathlib import Path
import pytest
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("cv2", SCRIPTS / "build_collector_v2_decisions.py")
cv2 = importlib.util.module_from_spec(spec); sys.modules["cv2"] = cv2; spec.loader.exec_module(cv2)

def write(path, fields, rows):
    with path.open("w", newline="") as h:
        w = csv.DictWriter(h, fieldnames=fields); w.writeheader(); w.writerows(rows)

def fixture(tmp):
    # 24 boxes released 2021-2025; boxes in the 6-24 month window grow faster
    rel, ledger = [], []
    for b in range(24):
        product = str(1000 + b); released = date(2021 + b % 5, 1 + b % 12, 1)
        rel.append({"tcgplayer_product_id": product, "official_release_date": released.isoformat()})
        price = 200.0 + 10 * b
        for k in range(30):
            y, m = divmod(1 + k, 12); day = date(2024 + y, m + 1, 1)
            age = (day - released).days / 30.44
            if age < 0: continue
            ledger.append({"product_class": "COLLECTOR_BOOSTER_BOX", "source_names": "TCGCSV_ARCHIVE", "tcgplayer_product_id": product,
                           "observation_date": day.isoformat(), "consolidated_market_price": f"{price:.2f}"})
            price *= 1.0 + (0.04 if 6 <= age <= 24 else 0.01)
    write(tmp / "rel.csv", ["tcgplayer_product_id", "official_release_date"], rel)
    write(tmp / "ledger.csv", ["product_class", "source_names", "tcgplayer_product_id", "observation_date", "consolidated_market_price"], ledger)
    latest = [{"snapshot_date": "2026-10-05", "tcgplayer_product_id": str(1000 + b), "box_name": f"Box {b}", "market_price": "300", "low_price": "280", "direct_low_price": ""} for b in range(24)]
    latest.append({"snapshot_date": "2026-10-05", "tcgplayer_product_id": "9999", "box_name": "No release date", "market_price": "100", "low_price": "", "direct_low_price": ""})
    write(tmp / "latest.csv", ["snapshot_date", "tcgplayer_product_id", "box_name", "market_price", "low_price", "direct_low_price"], latest)
    return tmp

def run(t, out):
    return subprocess.run([sys.executable, str(SCRIPTS / "build_collector_v2_decisions.py"), "--ledger", str(t / "ledger.csv"), "--weekly", str(t / "none.csv"),
                           "--latest", str(t / "latest.csv"), "--releases", str(t / "rel.csv"), "--output", str(out)], capture_output=True, text=True)

def test_calibration_learns_the_sweet_spot(tmp_path):
    t = fixture(tmp_path)
    p = cv2.panel(cv2._rows(t / "ledger.csv"), [])
    model = cv2.calibrate(p, cv2.releases(cv2._rows(t / "rel.csv")))
    assert model["sweet_spot"] > 0 and model["rows"] >= cv2.MIN_ROWS

def test_top_quarter_buy_after_costs_rest_hold(tmp_path):
    t = fixture(tmp_path); out = t / "d.csv"
    proc = run(t, out)
    assert proc.returncode == 0, proc.stderr
    rows = list(csv.DictReader(out.open()))
    ranked = [r for r in rows if r["call"] != "NO_PRICE"]
    buys = [r for r in ranked if r["call"] == "BUY"]
    assert 0 < len(buys) <= round(len(ranked) * 0.25)
    assert all(float(r["expected_net_return_6m"]) > 0 for r in buys)
    assert all(r["in_sweet_spot"] == "1" for r in buys) or buys[0]["in_sweet_spot"] == "1"
    assert [int(r["rank"]) for r in ranked] == list(range(1, len(ranked) + 1))
    assert next(r for r in rows if r["tcgplayer_product_id"] == "9999")["call"] == "NO_PRICE"
    summary = json.loads(out.with_suffix(".json").read_text())
    assert summary["calls"]["NO_PRICE"] == 1 and summary["calibration"]["sweet_spot"] > 0

def test_too_little_history_is_refused():
    with pytest.raises(ValueError):
        cv2.calibrate({("1", "2026-01"): 100.0}, {"1": date(2025, 1, 1)})

def test_walk_forward_reports_realized_results_by_quarter(tmp_path):
    t = fixture(tmp_path); out = t / "d.csv"
    assert run(t, out).returncode == 0
    wf = json.loads(out.with_suffix(".json").read_text())["walk_forward"]
    assert wf["test_months"] > 0 and set(wf["quarters"]) == {"1", "2", "3", "4"}
    for q in wf["quarters"].values():
        assert q["p10_net_return"] <= q["p50_net_return"] <= q["p90_net_return"] and 0 <= q["share_profitable"] <= 1
    assert wf["status"] in ("VALIDATED", "PROVISIONAL") and wf["recent"]["test_months"] <= cv2.RECENT_MONTHS
    rows = [r for r in csv.DictReader(out.open()) if r["call"] != "NO_PRICE"]
    top = rows[0]
    assert top["quarter"] == "1" and float(top["calibrated_net_return_6m"]) == wf["quarters"]["1"]["avg_net_return"]
    assert rows[-1]["quarter"] == "4"
    history = json.loads(out.with_name("collector_v2_history.json").read_text())
    assert history["1000"][0][0] <= history["1000"][-1][0]

def test_walk_forward_refits_only_on_known_outcomes():
    # outcomes that start in a test month must not be in that month's training set
    panel = {}
    rel = {str(p): date(2022 + p % 3, 1 + p % 12, 1) for p in range(20)}
    for p in range(20):
        for k in range(36):
            panel[(str(p), cv2._shift("2024-01", k))] = (100.0 + 37 * ((p * 7) % 20)) * (1.01 + 0.002 * (p % 5) + 0.003 * (k % 4 == p % 4)) ** k
    seen = []
    real = cv2._solve
    def spy(xs, ys):
        seen.append(len(ys)); return real(xs, ys)
    cv2._solve = spy
    try:
        wf = cv2.walk_forward(panel, rel)
    finally:
        cv2._solve = real
    assert wf["test_months"] > 0 and seen == sorted(seen)  # training only grows as outcomes become known

def test_quarters_split_evenly():
    assert [cv2._quarter(i, 8) for i in range(8)] == [1, 1, 2, 2, 3, 3, 4, 4]
    assert cv2._quarter(0, 1) == 1

def test_unreleased_and_just_released_boxes(tmp_path):
    t = fixture(tmp_path); out = t / "d.csv"
    rel = list(csv.DictReader((t / "rel.csv").open()))
    rel += [{"tcgplayer_product_id": "8001", "official_release_date": "2026-10-02"},   # released this month, before as_of
            {"tcgplayer_product_id": "8002", "official_release_date": "2026-11-13"}]   # preorder
    write(t / "rel.csv", ["tcgplayer_product_id", "official_release_date"], rel)
    latest = list(csv.DictReader((t / "latest.csv").open()))
    latest += [{"snapshot_date": "2026-10-05", "tcgplayer_product_id": p, "box_name": n, "market_price": "450", "low_price": "", "direct_low_price": ""}
               for p, n in (("8001", "Just released"), ("8002", "Preorder"))]
    write(t / "latest.csv", ["snapshot_date", "tcgplayer_product_id", "box_name", "market_price", "low_price", "direct_low_price"], latest)
    assert run(t, out).returncode == 0
    rows = {r["tcgplayer_product_id"]: r for r in csv.DictReader(out.open())}
    assert rows["8001"]["call"] in ("BUY", "HOLD") and rows["8001"]["release_date"] == "2026-10-02"
    assert (rows["8002"]["call"], rows["8002"]["note"]) == ("NO_PRICE", "NOT_YET_RELEASED")
    assert (rows["9999"]["call"], rows["9999"]["note"]) == ("NO_PRICE", "NO_RELEASE_DATE")
