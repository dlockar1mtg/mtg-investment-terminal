"""Pre-Collector model v2: rank 2000+ booster boxes by price; the cheapest two-fifths are BUY.

Research (October 2026, monthly ledger 2024-02 to 2026-07, walk-forward): cheaper boxes beat pricier
ones over 12 months in all 17 test months (rank correlation +0.50). The effect is price, not era:
with release year added, price still carries it. It holds within 2000s and 2010s boxes but not for
1990s vintage, where the priciest boxes did best, so pre-2000 boxes are HOLD with no model call.
After a 13% selling cost, only the cheapest two price fifths made money on average (+7.4% and
+4.3% a year vs -2.7% for all boxes). Return levels varied a lot by year, so calibrated forecasts and
ranges did not validate (80% ranges held 55%); the model reports tiers and their past results only.

Stale prices: a box whose price is more than MAX_PRICE_AGE_DAYS older than the run's as_of date
(the newest daily-feed price) is not ranked against today's prices; typical cases are a box with
only a July ledger month, or a daily-feed row carried forward after a failed fetch. It gets call
NO_PRICE with note STALE_PRICE (the UIP loader accepts only BUY / HOLD / NO_PRICE), keeps its
price and price_date for reference, and is left out of the tiers and ranks. Ledger prices are
dated by month; a month counts as its last day, so a price is never called stale early.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import json
from datetime import date
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data" / "history" / "mtg_ledger" / "universal_mtg_daily_consolidated_ledger.csv"
BOXES = ROOT / "data" / "product_master" / "precollector_model_input.csv"
WEEKLY = ROOT / "data" / "history" / "boxes" / "precollector_weekly_prices.csv"
LATEST = ROOT / "data" / "history" / "boxes" / "precollector_latest_prices.csv"
OUTPUT = ROOT / "data" / "history" / "boxes" / "precollector_v2_decisions.csv"

MODEL_VERSION = "precollector-v2"
CLASS = "PRE_COLLECTOR_BOOSTER_BOX"
HORIZON_MONTHS = 12
SELL_COST = 0.13
TIERS = 5
BUY_TIERS = (1, 2)
FIRST_MODELED_YEAR = 2000
MAX_PRICE_AGE_DAYS = 21   # older prices are STALE_PRICE: not ranked against today's
FIELDS = ["tcgplayer_product_id", "box_name", "release_date", "as_of", "price_date", "price", "price_source",
          "call", "note", "tier", "rank", "ranked_boxes", "tier_avg_return_12m", "tier_avg_net_return_12m",
          "tier_share_profitable", "tier_cases", "model_version"]


def _float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _rows(path: Path):
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def monthly_panel(ledger_rows, weekly_rows):
    """(product, 'YYYY-MM') -> last market price in the month, from the ledger and daily prices.

    Only TCGCSV-sourced ledger rows count: the July 2026 ledger also carries single eBay observations
    (e.g. a $40 "Planar Chaos box" against a $758 TCGCSV price) that are packs or partial lots."""
    obs = [(str(r.get("tcgplayer_product_id") or "").split(".")[0], str(r.get("observation_date") or "")[:10], _float(r.get("consolidated_market_price")))
           for r in ledger_rows if r.get("product_class") == CLASS and "TCGCSV" in str(r.get("source_names") or "")]
    obs += [(str(r.get("tcgplayer_product_id") or ""), str(r.get("snapshot_date") or "")[:10], _float(r.get("market_price"))) for r in weekly_rows]
    panel = {}
    for product, day, price in sorted(obs, key=lambda o: (o[0], o[1])):
        if product.isdigit() and len(day) == 10 and price:
            panel[(product, day[:7])] = price
    return panel


def _month_add(month: str, k: int) -> str:
    y, m = int(month[:4]), int(month[5:7]) - 1 + k
    return f"{y + m // 12:04d}-{m % 12 + 1:02d}"


def _tiers(prices: dict) -> dict:
    """Price tier 1 (cheapest fifth) .. 5 (priciest) for each product."""
    ordered = sorted(prices, key=lambda p: (prices[p], p))
    n = len(ordered)
    return {p: min(TIERS, 1 + i * TIERS // n) for i, p in enumerate(ordered)} if n else {}


def tier_history(panel, years):
    """Past 12-month results of each tier, ranking 2000+ boxes each month on that month's prices."""
    months = sorted({m for (_, m) in panel})
    out = {t: [] for t in range(1, TIERS + 1)}
    by_period = {t: {} for t in range(1, TIERS + 1)}
    for month in months:
        later = _month_add(month, HORIZON_MONTHS)
        prices = {p: v for (p, m), v in panel.items() if m == month and years.get(p, 0) >= FIRST_MODELED_YEAR and (p, later) in panel}
        if len(prices) < 2 * TIERS:
            continue
        for product, tier in _tiers(prices).items():
            fwd = panel[(product, later)] / prices[product] - 1.0
            out[tier].append(fwd)
            by_period[tier].setdefault(month[:4], []).append(fwd)
    summary = {}
    for tier, fwds in out.items():
        if not fwds:
            continue
        nets = [(1 + f) * (1 - SELL_COST) - 1 for f in fwds]
        summary[tier] = {"cases": len(fwds), "avg_return": mean(fwds), "avg_net_return": mean(nets),
                         "share_profitable": sum(1 for x in nets if x > 0) / len(nets),
                         "by_start_year": {y: round((1 + mean(v)) * (1 - SELL_COST) - 1, 4) for y, v in sorted(by_period[tier].items())}}
    return summary


def latest_prices(latest_rows, panel):
    """Today's price per product: the daily feed when available, else the last ledger month."""
    out = {}
    for r in latest_rows:
        product, price = str(r.get("tcgplayer_product_id") or ""), _float(r.get("market_price"))
        if product.isdigit() and price and product not in out:
            carried = str(r.get("stale_carried") or "").strip().lower() == "true"
            out[product] = (price, str(r.get("snapshot_date") or "")[:10], "TCGCSV_DAILY_CARRIED" if carried else "TCGCSV_DAILY")
    for (product, month), price in sorted(panel.items()):
        if product not in out or out[product][2] == "LEDGER_LAST_MONTH":
            out[product] = (price, month, "LEDGER_LAST_MONTH")
    return out


def _price_day(text: str) -> date | None:
    """The date of a price: YYYY-MM-DD as given, a ledger month YYYY-MM as its last day."""
    try:
        if len(text) == 7:
            y, m = int(text[:4]), int(text[5:7])
            return date(y, m, calendar.monthrange(y, m)[1])
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def is_stale(price_date: str, today: date) -> bool:
    day = _price_day(price_date)
    return day is None or (today - day).days > MAX_PRICE_AGE_DAYS


def score(boxes, prices, history, as_of, today: date | None = None):
    today = today or _price_day(str(as_of or "")) or date.today()
    years = {b["tcgplayer_product_id"]: int(b["release_date"][:4]) for b in boxes if b.get("release_date", "")[:4].isdigit()}
    stale = {p for p in prices if is_stale(prices[p][1], today)}
    modeled = {p: prices[p][0] for p in prices if years.get(p, 0) >= FIRST_MODELED_YEAR and p not in stale}
    tiers = _tiers(modeled)
    ranked = sorted(modeled, key=lambda p: (modeled[p], p))
    rank_of = {p: i + 1 for i, p in enumerate(ranked)}
    rows = []
    for b in boxes:
        product = b["tcgplayer_product_id"]
        row = {"tcgplayer_product_id": product, "box_name": b.get("box_name", ""), "release_date": b.get("release_date", ""),
               "as_of": as_of, "model_version": MODEL_VERSION}
        if product in prices:
            row.update(price=round(prices[product][0], 2), price_date=prices[product][1], price_source=prices[product][2])
        if product not in prices:
            row.update(call="NO_PRICE", note="NO_CURRENT_PRICE")
        elif product in stale:
            row.update(call="NO_PRICE", note="STALE_PRICE")
        elif years.get(product, 0) < FIRST_MODELED_YEAR:
            row.update(call="HOLD", note="VINTAGE_NO_MODEL_EDGE")
        else:
            tier = tiers[product]
            past = history.get(tier, {})
            row.update(call="BUY" if tier in BUY_TIERS else "HOLD", note="", tier=tier, rank=rank_of[product], ranked_boxes=len(ranked),
                       tier_avg_return_12m=round(past.get("avg_return", 0.0), 4) if past else "",
                       tier_avg_net_return_12m=round(past.get("avg_net_return", 0.0), 4) if past else "",
                       tier_share_profitable=round(past.get("share_profitable", 0.0), 4) if past else "",
                       tier_cases=past.get("cases", "") if past else "")
        rows.append(row)
    return sorted(rows, key=lambda r: (r.get("rank") or 10**9, r["box_name"]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--boxes", type=Path, default=BOXES)
    parser.add_argument("--weekly", type=Path, default=WEEKLY)
    parser.add_argument("--latest", type=Path, default=LATEST)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--today", type=date.fromisoformat, default=None, help="reference date for the stale-price check (default: as_of)")
    args = parser.parse_args(argv)
    boxes = [b for b in _rows(args.boxes) if str(b.get("tcgplayer_product_id") or "").isdigit()]
    if not boxes:
        raise SystemExit(f"no boxes in {args.boxes}")
    panel = monthly_panel(_rows(args.ledger), _rows(args.weekly))
    years = {b["tcgplayer_product_id"]: int(b["release_date"][:4]) for b in boxes if b.get("release_date", "")[:4].isdigit()}
    history = tier_history(panel, years)
    if not history:
        raise SystemExit("not enough 12-month history to describe the tiers")
    prices = latest_prices(_rows(args.latest), panel)
    as_of = max((p[1] for p in prices.values() if p[2] == "TCGCSV_DAILY"), default=max(p[1] for p in prices.values()) if prices else "")
    rows = score(boxes, prices, history, as_of, args.today)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    calls = {c: sum(1 for r in rows if r["call"] == c) for c in ("BUY", "HOLD", "NO_PRICE")}
    summary = {"model_version": MODEL_VERSION, "as_of": as_of, "horizon_months": HORIZON_MONTHS, "sell_cost": SELL_COST,
               "buy_tiers": list(BUY_TIERS), "first_modeled_year": FIRST_MODELED_YEAR, "max_price_age_days": MAX_PRICE_AGE_DAYS,
               "stale_prices": sum(1 for r in rows if r.get("note") == "STALE_PRICE"), "calls": calls,
               "tier_history": {str(k): v for k, v in history.items()}}
    args.output.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    price_history = {}
    for (product, month), price in sorted(panel.items()):
        price_history.setdefault(product, []).append([month, round(price, 2)])
    args.output.with_name("precollector_v2_history.json").write_text(json.dumps(price_history, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"as_of": as_of, "calls": calls}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
