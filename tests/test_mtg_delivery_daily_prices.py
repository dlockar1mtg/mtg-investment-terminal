"""Daily model prices refresh the hosted package's current prices (synthetic decision files)."""
import csv
import importlib.util
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


delivery = _load("mtg_delivery_daily", "build_mtg_hosted_uip_delivery.py")
overlay = _load("mtg_overlay_daily", "apply_mtg_live_uip_overlay.py")

TODAY = date(2026, 10, 10)


def write(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def read(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def lanes(tmp_path, sl_rows=(), collector_rows=(), precollector_rows=()):
    sl = write(tmp_path / "sl.csv", ["secret_lair_id", "tcgplayer_product_id", "as_of", "market_price", "call", "rank"], sl_rows)
    co = write(tmp_path / "co.csv", ["tcgplayer_product_id", "box_name", "as_of", "market_price", "call", "rank"], collector_rows)
    pc = write(tmp_path / "pc.csv", ["tcgplayer_product_id", "box_name", "as_of", "price_date", "price", "price_source", "call"], precollector_rows)
    spec = dict(delivery.DAILY_PRICE_LANES)
    spec["SECRET_LAIR_V1_1"] = (sl, *spec["SECRET_LAIR_V1_1"][1:])
    spec["COLLECTOR_V1"] = (co, *spec["COLLECTOR_V1"][1:])
    spec["PRE_COLLECTOR_V1"] = (pc, *spec["PRE_COLLECTOR_V1"][1:])
    return spec


def row(lane, native, price, status="WATCHLIST", rank="3"):
    return {"mtg_lane": lane, "native_asset_id": native, "current_price_usd": price, "native_purchase_status": status,
            "native_rank": rank, "native_rank_type": "CERTIFIED_RANK", "purchase_semantic": "SEMANTIC",
            "lane_authority_state": "CERTIFIED_CLOSED", "current_price_authority_available": "true"}


def test_each_lane_takes_its_daily_price_by_its_own_id(tmp_path):
    rows = [row("SECRET_LAIR_V1_1", "SL-BB7E07A2986BB4", "137.62"),
            row("COLLECTOR_V1", "MTG-CANON-TCGPLAYER-692983", "475.42"),
            row("PRE_COLLECTOR_V1", "tcgplayer:102715", "221.39")]
    spec = lanes(tmp_path,
                 sl_rows=[{"secret_lair_id": "SL-BB7E07A2986BB4", "tcgplayer_product_id": "999", "as_of": "2026-10-10", "market_price": "154.92", "call": "WAIT", "rank": "400"}],
                 collector_rows=[{"tcgplayer_product_id": "692983", "box_name": "Reality Fracture", "as_of": "2026-10-09", "market_price": "437.72", "call": "HOLD", "rank": "40"}],
                 precollector_rows=[{"tcgplayer_product_id": "102715", "box_name": "BFZ", "as_of": "2026-10-10", "price_date": "2026-10-06", "price": "241.58", "price_source": "TCGCSV_DAILY", "call": "HOLD"}])
    summary = delivery.refresh_daily_prices(rows, today=TODAY, lanes=spec)
    sl, collector, precollector = rows
    assert (sl["current_price_usd"], sl["current_price_as_of"], sl["current_price_source"]) == ("154.92", "2026-10-10", "SECRET_LAIR_V2_DECISIONS_TCGPLAYER_MARKET")
    assert (collector["current_price_usd"], collector["current_price_as_of"]) == ("437.72", "2026-10-09")
    assert collector["current_price_source"] == "COLLECTOR_V2_DECISIONS_TCGPLAYER_MARKET"
    # Pre-Collector dates its price separately from the decision run: the price date is used.
    assert (precollector["current_price_usd"], precollector["current_price_as_of"]) == ("241.58", "2026-10-06")
    assert summary["refreshed"] == 3 and summary["certified_fallback"] == 0
    assert summary["by_lane"]["PRE_COLLECTOR_V1"] == {"refreshed": 1, "certified": 0}
    # Calls, ranks and certification are not touched.
    for r in rows:
        assert (r["native_purchase_status"], r["native_rank"], r["native_rank_type"], r["purchase_semantic"], r["lane_authority_state"]) == \
            ("WATCHLIST", "3", "CERTIFIED_RANK", "SEMANTIC", "CERTIFIED_CLOSED")


def test_stale_missing_or_unpriced_decisions_keep_the_certified_price(tmp_path):
    rows = [row("SECRET_LAIR_V1_1", "SL-STALE", "10"),        # 5 days old
            row("SECRET_LAIR_V1_1", "SL-NOPRICE", "11"),      # NO_PRICE, empty price
            row("SECRET_LAIR_V1_1", "SL-ABSENT", "12"),       # not in the decisions
            row("SECRET_LAIR_V1_1", "SL-EDGE", "13"),         # exactly 4 days old: still current
            row("COLLECTOR_V1", "MTG-CANON-TCGPLAYER-555", "14"),   # price 0
            row("PRE_COLLECTOR_V1", "tcgplayer:777", "15"),        # month-only ledger price
            row("PRE_COLLECTOR_V1", "tcgplayer:888", "")]          # no certified price, no daily price
    spec = lanes(tmp_path,
                 sl_rows=[{"secret_lair_id": "SL-STALE", "as_of": "2026-10-05", "market_price": "20", "call": "WAIT"},
                          {"secret_lair_id": "SL-NOPRICE", "as_of": "2026-10-10", "market_price": "", "call": "NO_PRICE"},
                          {"secret_lair_id": "SL-EDGE", "as_of": "2026-10-06", "market_price": "23", "call": "WAIT"}],
                 collector_rows=[{"tcgplayer_product_id": "555", "as_of": "2026-10-10", "market_price": "0", "call": "NO_PRICE"}],
                 precollector_rows=[{"tcgplayer_product_id": "777", "as_of": "2026-10-10", "price_date": "2026-07", "price": "30", "price_source": "LEDGER_LAST_MONTH", "call": "NO_PRICE"}])
    summary = delivery.refresh_daily_prices(rows, today=TODAY, lanes=spec)
    prices = [(r["current_price_usd"], r["current_price_as_of"], r["current_price_source"]) for r in rows]
    assert prices == [("10", "", "CERTIFIED_EXPORT"), ("11", "", "CERTIFIED_EXPORT"), ("12", "", "CERTIFIED_EXPORT"),
                      ("23", "2026-10-06", "SECRET_LAIR_V2_DECISIONS_TCGPLAYER_MARKET"),
                      ("14", "", "CERTIFIED_EXPORT"), ("15", "", "CERTIFIED_EXPORT"), ("", "", "")]
    assert summary["refreshed"] == 1 and summary["certified_fallback"] == 6


def test_ids_never_cross_lanes(tmp_path):
    # The same TCGplayer id in another lane's file must not price this row, and a Collector id
    # must be the MTG-CANON-TCGPLAYER-<id> form.
    rows = [row("COLLECTOR_V1", "MTG-CANON-TCGPLAYER-4242", "100"), row("PRE_COLLECTOR_V1", "tcgplayer:5151", "50"),
            row("COLLECTOR_V1", "4242-UNRELATED", "70")]
    spec = lanes(tmp_path,
                 collector_rows=[{"tcgplayer_product_id": "5151", "as_of": "2026-10-10", "market_price": "999", "call": "HOLD"}],
                 precollector_rows=[{"tcgplayer_product_id": "4242", "as_of": "2026-10-10", "price_date": "2026-10-10", "price": "888", "price_source": "TCGCSV_DAILY", "call": "HOLD"}])
    delivery.refresh_daily_prices(rows, today=TODAY, lanes=spec)
    assert [r["current_price_usd"] for r in rows] == ["100", "50", "70"]


def test_missing_decision_files_change_no_price(tmp_path):
    rows = [row("SECRET_LAIR_V1_1", "SL-A", "10"), row("COLLECTOR_V1", "MTG-CANON-TCGPLAYER-1", "20")]
    spec = {lane: (tmp_path / f"missing-{lane}.csv", *rest) for lane, (_path, *rest) in delivery.DAILY_PRICE_LANES.items()}
    summary = delivery.refresh_daily_prices(rows, today=TODAY, lanes=spec)
    assert [r["current_price_usd"] for r in rows] == ["10", "20"] and summary["refreshed"] == 0


def test_package_carries_daily_prices_and_keeps_the_native_authority_byte_identical(tmp_path, monkeypatch):
    today = datetime.now(timezone.utc).date().isoformat()
    spec = lanes(tmp_path,
                 sl_rows=[{"secret_lair_id": "SL-BB7E07A2986BB4", "as_of": today, "market_price": "154.92", "call": "WAIT", "rank": "400"}],
                 collector_rows=[{"tcgplayer_product_id": "692983", "as_of": today, "market_price": "437.72", "call": "HOLD", "rank": "40"}])
    monkeypatch.setattr(delivery, "DAILY_PRICE_LANES", spec)
    monkeypatch.delenv(delivery.SECRET_LAIR_V2_ENV, raising=False)
    result = delivery.build(tmp_path / "out")
    latest = tmp_path / "out" / "latest"
    assert (latest / "mtg_native_authority.csv").read_bytes() == delivery.CERTIFIED_PAYLOAD.read_bytes()
    forecasts = {r["source_product_id"]: r for r in read(latest / "forecasts.csv")}
    sl, collector = forecasts["SL-BB7E07A2986BB4"], forecasts["MTG-CANON-TCGPLAYER-692983"]
    assert (sl["current_market_value_usd"], sl["current_price_as_of"], sl["current_price_source"]) == ("154.92", today, "SECRET_LAIR_V2_DECISIONS_TCGPLAYER_MARKET")
    assert (collector["current_market_value_usd"], collector["current_price_as_of"]) == ("437.72", today)
    certified = {r["native_asset_id"]: r for r in read(delivery.CERTIFIED_PAYLOAD)}
    other = forecasts["tcgplayer:102715"]
    assert other["current_market_value_usd"] == certified["tcgplayer:102715"]["current_price_usd"]
    assert (other["current_price_as_of"], other["current_price_source"]) == ("", "CERTIFIED_EXPORT")
    assert result["daily_price_refresh"]["refreshed"] == 2 and result["daily_price_refresh"]["by_lane"]["SECRET_LAIR_V1_1"]["refreshed"] == 1
    # Calls stay certified while the v2 overlay is off.
    recs = {r["source_product_id"]: r for r in read(latest / "recommendations.csv")}
    assert recs["SL-BB7E07A2986BB4"]["native_purchase_status"] == certified["SL-BB7E07A2986BB4"]["native_purchase_status"]
    assert result["semantic_authority_sha256"] == delivery.sha256(delivery.CERTIFIED_PAYLOAD)


def test_live_overlay_fallback_names_the_daily_price(tmp_path, monkeypatch):
    package, market = tmp_path / "pkg", tmp_path / "market"
    package.mkdir()
    market.mkdir()
    write(package / "asset_master.csv", ["asset_id", "source_product_id"], [{"asset_id": a, "source_product_id": s} for a, s in (("A1", "SL-LIVE"), ("A2", "SL-DAILY"), ("A3", "SL-CERT"))])
    write(package / "forecasts.csv", ["asset_id", "source_product_id", "current_market_value_usd", "current_price_as_of", "current_price_source"],
          [{"asset_id": "A1", "source_product_id": "SL-LIVE", "current_market_value_usd": "5", "current_price_as_of": "2026-10-10", "current_price_source": "SECRET_LAIR_V2_DECISIONS_TCGPLAYER_MARKET"},
           {"asset_id": "A2", "source_product_id": "SL-DAILY", "current_market_value_usd": "6", "current_price_as_of": "2026-10-09", "current_price_source": "SECRET_LAIR_V2_DECISIONS_TCGPLAYER_MARKET"},
           {"asset_id": "A3", "source_product_id": "SL-CERT", "current_market_value_usd": "7", "current_price_as_of": "", "current_price_source": "CERTIFIED_EXPORT"}])
    write(package / "recommendations.csv", ["asset_id", "source_product_id"], [{"asset_id": "A1", "source_product_id": "SL-LIVE"}])
    write(package / "risk_metrics.csv", ["asset_id"], [{"asset_id": "A1"}])
    write(package / "platform_status.csv", ["platform"], [{"platform": "MTG"}])
    for name in ("package_summary.json", "export_manifest.json"):
        (package / name).write_text(json.dumps({"status": "PASS", "products": 3}), encoding="utf-8")
    write(market / "consolidated_marketplace_prices.csv", ["source_product_id", "consolidated_market_price_usd", "observed_at_utc"],
          [{"source_product_id": "SL-LIVE", "consolidated_market_price_usd": "8", "observed_at_utc": "2026-10-10T12:00:00+00:00"}])
    write(market / "certified_marketplace_decisions.csv", ["source_product_id", "signal"], [{"source_product_id": "SL-LIVE", "signal": "HOLD"}])
    monkeypatch.setattr(sys, "argv", ["overlay", "--package", str(package), "--market-root", str(market)])
    assert overlay.main() == 0
    rows = {r["asset_id"]: r for r in read(package / "forecasts.csv")}
    assert (rows["A1"]["current_market_value_usd"], rows["A1"]["market_data_status"]) == ("8", "LIVE_CERTIFIED")
    assert (rows["A2"]["market_data_status"], rows["A2"]["market_source"], rows["A2"]["market_observed_at_utc"]) == \
        ("BASELINE_FALLBACK", "SECRET_LAIR_V2_DECISIONS_TCGPLAYER_MARKET", "2026-10-09")
    assert (rows["A3"]["market_source"], rows["A3"]["market_observed_at_utc"]) == ("PHASE_10_CERTIFIED_BASELINE", "")
