import csv, importlib.util, json, subprocess, sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("pcv2", SCRIPTS / "build_precollector_v2_decisions.py")
pc = importlib.util.module_from_spec(spec)
sys.modules["pcv2"] = pc
spec.loader.exec_module(pc)


def _months(n, start=(2024, 2)):
    out = []
    for i in range(n):
        y, m = divmod(start[1] - 1 + i, 12)
        out.append(f"{start[0] + y:04d}-{m + 1:02d}-15")
    return out


def _ledger(n_boxes=20, n_months=26):
    rows = []
    for b in range(n_boxes):
        price = 100.0 + 60 * b                      # cheaper boxes grow faster
        for day in _months(n_months):
            rows.append({"product_class": pc.CLASS, "tcgplayer_product_id": str(1000 + b), "observation_date": day,
                         "consolidated_market_price": f"{price:.2f}", "source_names": "TCGCSV_ARCHIVE"})
            price *= 1.02 - 0.0015 * b
    return rows


def _boxes(n_boxes=20):
    boxes = [{"tcgplayer_product_id": str(1000 + b), "box_name": f"Box {b}", "release_date": "2012-05-01"} for b in range(n_boxes)]
    boxes[-1]["release_date"] = "1996-06-01"                        # a vintage box
    boxes.append({"tcgplayer_product_id": "5555", "box_name": "Unpriced", "release_date": "2010-01-01"})
    return boxes


def test_cheapest_two_fifths_are_buy_vintage_is_hold_and_unpriced_is_no_price():
    panel = pc.monthly_panel(_ledger(), [])
    boxes = _boxes()
    years = {b["tcgplayer_product_id"]: int(b["release_date"][:4]) for b in boxes}
    history = pc.tier_history(panel, years)
    assert history[1]["avg_return"] > history[5]["avg_return"]
    rows = {r["tcgplayer_product_id"]: r for r in pc.score(boxes, pc.latest_prices([], panel), history, "2026-03")}
    assert rows["1000"]["call"] == "BUY" and rows["1000"]["tier"] == 1 and rows["1000"]["rank"] == 1
    assert rows["1018"]["call"] == "HOLD" and rows["1018"]["tier"] == 5
    assert sum(1 for r in rows.values() if r["call"] == "BUY") == 8          # 2 of 5 tiers of 19 modeled boxes
    assert rows["1019"]["call"] == "HOLD" and rows["1019"]["note"] == "VINTAGE_NO_MODEL_EDGE" and "tier" not in rows["1019"]
    assert rows["5555"]["call"] == "NO_PRICE"


def test_ebay_only_ledger_rows_are_ignored():
    ledger = _ledger()
    ledger.append({"product_class": pc.CLASS, "tcgplayer_product_id": "1018", "observation_date": "2026-04-20",
                   "consolidated_market_price": "40.00", "source_names": "EBAY"})          # a pack listed as a box
    prices = pc.latest_prices([], pc.monthly_panel(ledger, []))
    assert prices["1018"][0] > 500 and prices["1018"][2] == "LEDGER_LAST_MONTH"


def test_daily_prices_take_precedence_over_the_ledger():
    panel = pc.monthly_panel(_ledger(), [])
    prices = pc.latest_prices([{"tcgplayer_product_id": "1000", "market_price": "123.45", "snapshot_date": "2026-10-06"}], panel)
    assert prices["1000"] == (123.45, "2026-10-06", "TCGCSV_DAILY") and prices["1001"][2] == "LEDGER_LAST_MONTH"


def _write(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_runs_as_a_script(tmp_path):
    out = tmp_path / "precollector_v2_decisions.csv"
    proc = subprocess.run([sys.executable, str(SCRIPTS / "build_precollector_v2_decisions.py"),
                           "--ledger", str(_write(tmp_path / "ledger.csv", _ledger())), "--boxes", str(_write(tmp_path / "boxes.csv", _boxes())),
                           "--weekly", str(tmp_path / "none.csv"), "--latest", str(tmp_path / "none.csv"), "--output", str(out)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    rows = list(csv.DictReader(out.open()))
    assert rows[0]["call"] == "BUY" and rows[0]["rank"] == "1" and len(rows) == 21
    summary = json.loads(out.with_suffix(".json").read_text())
    assert summary["calls"] == {"BUY": 8, "HOLD": 12, "NO_PRICE": 1} and set(summary["tier_history"]) == {"1", "2", "3", "4", "5"}
    history = json.loads(out.with_name("precollector_v2_history.json").read_text())
    assert len(history["1000"]) == 26


def test_old_prices_are_stale_and_left_out_of_the_tiers():
    panel = pc.monthly_panel(_ledger(), [])
    boxes = _boxes()
    years = {b["tcgplayer_product_id"]: int(b["release_date"][:4]) for b in boxes}
    history = pc.tier_history(panel, years)
    # Only boxes 1000-1009 have a fresh daily price; the rest only have ledger months that end in 2026-03.
    daily = [{"tcgplayer_product_id": str(1000 + b), "market_price": f"{100 + b}", "snapshot_date": "2026-10-06"} for b in range(10)]
    prices = pc.latest_prices(daily, panel)
    rows = {r["tcgplayer_product_id"]: r for r in pc.score(boxes, prices, history, "2026-10-06")}
    assert (rows["1012"]["call"], rows["1012"]["note"]) == ("NO_PRICE", "STALE_PRICE")
    assert "tier" not in rows["1012"] and "rank" not in rows["1012"] and rows["1012"]["price_date"] == "2026-03"
    assert rows["1019"]["note"] == "STALE_PRICE"                                  # stale before vintage
    ranked = [r for r in rows.values() if r.get("rank")]
    assert sorted(r["tcgplayer_product_id"] for r in ranked) == [str(1000 + b) for b in range(10)]
    assert all(r["ranked_boxes"] == 10 for r in ranked) and sum(1 for r in ranked if r["call"] == "BUY") == 4
    assert pc.is_stale("2026-09-15", pc.date(2026, 10, 6)) is False and pc.is_stale("2026-09-14", pc.date(2026, 10, 6)) is True
    assert pc.is_stale("2026-09", pc.date(2026, 10, 21)) is False                # a ledger month counts as its last day


def test_carried_rows_are_labelled_and_age_from_their_own_date():
    prices = pc.latest_prices([{"tcgplayer_product_id": "1000", "market_price": "50", "snapshot_date": "2026-09-01", "stale_carried": "true"}], {})
    assert prices["1000"] == (50.0, "2026-09-01", "TCGCSV_DAILY_CARRIED")
    row = pc.score([{"tcgplayer_product_id": "1000", "box_name": "A", "release_date": "2012-01-01"}], prices, {}, "2026-10-06")[0]
    assert (row["call"], row["note"]) == ("NO_PRICE", "STALE_PRICE")
