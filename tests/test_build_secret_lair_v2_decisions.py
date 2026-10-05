import csv, importlib.util, json, math, subprocess, sys
from pathlib import Path
import pytest
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("slv2", SCRIPTS / "build_secret_lair_v2_decisions.py")
v2 = importlib.util.module_from_spec(spec); sys.modules["slv2"] = v2; spec.loader.exec_module(v2)

def months(n, start=(2024, 2)):
    out = []
    for i in range(n):
        y, m = divmod(start[1] - 1 + i, 12)
        out.append(f"{start[0] + y:04d}-{m + 1:02d}-01")
    return out

def write(path, fields, rows):
    with path.open("w", newline="") as h:
        w = csv.DictWriter(h, fieldnames=fields); w.writeheader(); w.writerows(rows)

def history(tmp):
    # 60 products; listings below market (positive gap) are followed by higher listings 6 months later
    rows = []
    for p in range(60):
        gap = (p % 10) / 25 - 0.12                      # -12% .. +24%
        level = 50.0
        for k, day in enumerate(months(20)):
            low = level * (1 - gap)
            rows.append({"secret_lair_id": f"SL-{p:03d}", "observation_date": day, "market_price": f"{level:.2f}", "low_price": f"{low:.2f}"})
            level *= 1.0 + 0.03 + 0.10 * gap               # bigger gap -> faster rise
    path = tmp / "monthly.csv"; write(path, ["secret_lair_id", "observation_date", "market_price", "low_price"], rows)
    return path

def latest(tmp, rows):
    path = tmp / "latest.csv"
    write(path, ["snapshot_date", "secret_lair_id", "sub_type", "market_price", "low_price", "direct_low_price"], rows)
    return path

def test_calibration_learns_the_gap_effect(tmp_path):
    panel = v2.monthly_panel(v2._rows(history(tmp_path)), [])
    model = v2.calibrate(panel)
    assert model["slope"] > 0 and model["pairs"] >= v2.MIN_PAIRS

def test_calls_follow_the_gap_and_costs(tmp_path):
    model = {"intercept": 0.13, "slope": 0.53, "pairs": 500}
    lat = v2.latest_prices([
        {"secret_lair_id": "A", "market_price": "100", "low_price": "80", "direct_low_price": "", "snapshot_date": "2026-10-05"},   # 20% gap
        {"secret_lair_id": "B", "market_price": "100", "low_price": "97", "direct_low_price": "", "snapshot_date": "2026-10-05"},   # 3% gap
        {"secret_lair_id": "C", "market_price": "100", "low_price": "70", "direct_low_price": "95", "snapshot_date": "2026-10-05"}, # Direct low wins
        {"secret_lair_id": "D", "market_price": "", "low_price": "40", "direct_low_price": "", "snapshot_date": "2026-10-05"},
    ])
    rows = {r["secret_lair_id"]: r for r in v2.score(lat, model, {"A": "Drop A"})}
    assert rows["A"]["call"] == "BUY" and rows["A"]["rank"] == 1 and rows["A"]["product_name"] == "Drop A"
    assert rows["A"]["note"] == "" and rows["B"]["note"] == ""
    assert rows["B"]["call"] == "WAIT"
    assert rows["C"]["buy_price_basis"] == "TCGPLAYER_DIRECT_LOW" and rows["C"]["call"] == "WAIT"
    assert rows["D"]["call"] == "NO_PRICE" and "rank" not in rows["D"]
    a = rows["A"]
    assert a["expected_return_6m"] == pytest.approx(0.13 + 0.53 * 0.20, abs=1e-4)
    assert a["expected_net_return_6m"] == pytest.approx((1 + a["expected_return_6m"]) * 0.87 - 1, abs=1e-4)

def test_runs_as_a_script(tmp_path):
    lat = latest(tmp_path, [{"snapshot_date": "2026-10-05", "secret_lair_id": "SL-001", "sub_type": "Normal", "market_price": "60", "low_price": "48", "direct_low_price": ""},
                            {"snapshot_date": "2026-10-05", "secret_lair_id": "SL-002", "sub_type": "Normal", "market_price": "60", "low_price": "59", "direct_low_price": ""}])
    out = tmp_path / "decisions.csv"
    proc = subprocess.run([sys.executable, str(SCRIPTS / "build_secret_lair_v2_decisions.py"), "--history-monthly", str(history(tmp_path)),
                           "--history-weekly", str(tmp_path / "none.csv"), "--latest", str(lat), "--names", str(tmp_path / "none.csv"), "--output", str(out)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    rows = list(csv.DictReader(out.open()))
    assert [r["call"] for r in rows] == ["BUY", "WAIT"]
    price_history = json.loads(out.with_name("secret_lair_v2_history.json").read_text())
    assert price_history["SL-001"][0][0] == "2024-02" and len(price_history["SL-001"]) == 20 and len(price_history["SL-001"][0]) == 3
    summary = json.loads(out.with_suffix(".json").read_text())
    assert summary["calls"] == {"BUY": 1, "WAIT": 1, "NO_PRICE": 0} and summary["calibration"]["slope"] > 0

def test_too_little_history_is_refused():
    with pytest.raises(ValueError):
        v2.calibrate({("A", "2026-01"): (10.0, 9.0)})

def test_very_large_gaps_are_flagged():
    lat = v2.latest_prices([{"secret_lair_id": "X", "market_price": "100", "low_price": "60", "direct_low_price": "", "snapshot_date": "2026-10-05"}])
    row = v2.score(lat, {"intercept": 0.13, "slope": 0.53, "pairs": 500}, {})[0]
    assert row["call"] == "BUY" and row["note"] == "CHECK_LISTING_LARGE_GAP"

def test_clean_deals_rank_ahead_of_check_listing_gaps():
    lat = v2.latest_prices([
        {"secret_lair_id": "FLAG", "market_price": "100", "low_price": "55", "direct_low_price": "", "snapshot_date": "2026-10-05"},   # 45% gap
        {"secret_lair_id": "CLEAN", "market_price": "100", "low_price": "85", "direct_low_price": "", "snapshot_date": "2026-10-05"},  # 15% gap
        {"secret_lair_id": "WAIT", "market_price": "100", "low_price": "99", "direct_low_price": "", "snapshot_date": "2026-10-05"},
    ])
    rows = v2.score(lat, {"intercept": 0.13, "slope": 0.53, "pairs": 500}, {})
    assert [(r["secret_lair_id"], r["call"], r["rank"]) for r in rows] == [("CLEAN", "BUY", 1), ("FLAG", "BUY", 2), ("WAIT", "WAIT", 3)]


def test_tcgplayer_ids_travel_with_the_decisions():
    lat = v2.latest_prices([{"secret_lair_id": "A", "market_price": "100", "low_price": "80", "direct_low_price": "", "snapshot_date": "2026-10-05"}])
    row = v2.score(lat, {"intercept": 0.13, "slope": 0.53, "pairs": 500}, {"A": "Drop A"}, {"A": "512345"})[0]
    assert row["tcgplayer_product_id"] == "512345"


def test_outcome_ranges_attach_to_scored_products():
    pairs = [((k % 80) / 100 - 0.4, 0.1 + ((k % 13) - 6) / 20) for k in range(2000)]
    bins = v2.outcome_bins(pairs)
    assert bins and all(b["q10"] <= b["median"] <= b["q90"] and b["n"] >= v2.MIN_BIN_CASES for b in bins)
    lat = v2.latest_prices([{"secret_lair_id": "A", "market_price": "100", "low_price": "80", "direct_low_price": "", "snapshot_date": "2026-10-05"}])
    row = v2.score(lat, {"intercept": 0.13, "slope": 0.53, "pairs": 500, "bins": bins}, {})[0]
    assert row["similar_cases"] > 0 and 0 <= row["prob_profit_6m"] <= 1 and row["range_low_6m"] <= row["range_high_6m"]
    empty = v2.score(lat, {"intercept": 0.13, "slope": 0.53, "pairs": 500}, {})[0]
    assert empty["similar_cases"] == "" and empty["prob_profit_6m"] == ""
