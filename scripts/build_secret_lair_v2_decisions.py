"""Secret Lair model v2: buy when a reliable listing is well below the market price.

Research (October 2026, monthly TCGCSV history 2024-02 to 2026-07, walk-forward): of the
signals available, only the listing gap predicted 6-month returns on a consistent price
basis (rank correlation +0.26 listing-to-listing, +0.43 market-to-market, positive in every
test month). Trend, drawdown, age and price level did not. Products bought at a gap of at
least 10% returned +27% over 6 months versus +17% for all products; after a 13% selling
cost, +10.5% versus +2.1%.

Each run: refit expected 6-month return = a + b * gap on every month pair in the stored
history whose outcome is known (gap = 1 - cheapest listing / market price, capped at +/-40%;
returns measured listing to listing), then score today's prices.

Buy price: the TCGplayer Direct low would be used if the feed carried one, but TCGCSV leaves
direct_low_price empty for Secret Lairs (0 of 876 rows on 2026-10-09), so in practice buy_price
is the lowest listing from any seller. A buyer also pays shipping, which the listing price
excludes, so scoring uses the landed cost = buy_price + BUY_SHIPPING_USD (an assumed flat
$4.00 per order; change the constant if your typical shipping differs):
  gap                 = 1 - landed cost / market price (the discount actually captured)
  expected_return_6m  = predicted listing price in 6 months (model fitted on listing gaps)
                        / landed cost - 1
  prob_profit_6m      = share of similar past deals that beat the landed cost after selling costs
range_low/median/high_6m stay listing-to-listing price changes (multiply buy_price by 1 + range
for the listing's expected worth). BUY when the gap is at least 10% and the expected return after
selling costs is positive; otherwise WAIT; NO_PRICE when there is no market or buy price.
Listings 30% or more below market (before shipping) are flagged CHECK_LISTING_LARGE_GAP: such
listings are often mislisted, damaged or single copies, and rank after the clean deals.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
HISTORY_MONTHLY = ROOT / "data" / "history" / "secret_lair" / "master_secret_lair_price_history.csv"
HISTORY_WEEKLY = ROOT / "data" / "history" / "tcgcsv_weekly" / "secret_lair_weekly_prices.csv"
LATEST = ROOT / "data" / "history" / "tcgcsv_weekly" / "secret_lair_latest_prices.csv"
NAMES = ROOT / "docs" / "phase_8" / "secret_lair" / "secret_lair_v1_tcg_current_price_status.csv"
OUTPUT = ROOT / "data" / "history" / "tcgcsv_weekly" / "secret_lair_v2_decisions.csv"

MODEL_VERSION = "secret-lair-v2"
HORIZON_MONTHS = 6
GAP_CAP = 0.40
BUY_GAP = 0.10
CHECK_GAP = 0.30          # gaps this large are often mislisted, damaged or single odd copies
SELL_COST = 0.13          # TCGplayer seller fees plus shipping, as a share of the sale price
BUY_SHIPPING_USD = 4.00   # ASSUMPTION: buyer-side shipping added to every purchase (flat, per order)
MIN_PAIRS = 200
FIELDS = ["secret_lair_id", "tcgplayer_product_id", "product_name", "as_of", "market_price", "buy_price", "buy_price_basis",
          "gap", "expected_return_6m", "expected_net_return_6m", "range_low_6m", "range_median_6m", "range_high_6m", "prob_profit_6m", "similar_cases", "call", "note", "rank", "ranked_products", "model_version",
          "buy_shipping_usd", "landed_buy_price"]


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


def monthly_panel(monthly_rows, weekly_rows):
    """(product, 'YYYY-MM') -> (market, low): the last observation in each month, both sources."""
    observations = []
    for r in monthly_rows:
        observations.append((r.get("secret_lair_id", ""), r.get("observation_date", "")[:10], _float(r.get("market_price")), _float(r.get("low_price"))))
    for r in weekly_rows:
        observations.append((r.get("secret_lair_id", ""), r.get("snapshot_date", "")[:10], _float(r.get("market_price")), _float(r.get("low_price"))))
    panel = {}
    for product, day, market, low in sorted(observations, key=lambda o: (o[0], o[1])):
        if product and len(day) == 10 and market:
            panel[(product, day[:7])] = (market, low)
    return panel


def _month_add(month: str, k: int) -> str:
    y, m = int(month[:4]), int(month[5:7]) - 1 + k
    return f"{y + m // 12:04d}-{m % 12 + 1:02d}"


def gap_of(buy, market):
    return max(-GAP_CAP, min(GAP_CAP, 1.0 - buy / market))


OUTCOME_BINS = (-0.41, -0.05, 0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.41)
MIN_BIN_CASES = 30


def _quantile(values, q):
    s = sorted(values)
    pos = (len(s) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def outcome_bins(pairs):
    """What similar deals did: 6-month outcomes grouped by gap below market.

    These are full-sample ranges (every known 6-month pair, including the months the ranges are
    later shown for), not a walk-forward test; treat their coverage as in-sample. Each bin keeps
    its sorted outcomes under "forwards" so scoring can count profits net of shipping; main()
    drops them from the JSON summary."""
    out = []
    for lo, hi in zip(OUTCOME_BINS, OUTCOME_BINS[1:]):
        forwards = [fwd for gap, fwd in pairs if lo < gap <= hi]
        if len(forwards) >= MIN_BIN_CASES:
            out.append({"low": lo, "high": hi, "n": len(forwards), "q10": _quantile(forwards, 0.1),
                        "median": _quantile(forwards, 0.5), "q90": _quantile(forwards, 0.9),
                        "p_profit": sum(1 for f in forwards if (1 + f) * (1 - SELL_COST) - 1 > 0) / len(forwards),
                        "forwards": sorted(forwards)})
    return out


def _band_fields(model, gap, cost_ratio=1.0):
    """Outcome ranges for the band holding this listing gap. cost_ratio = landed cost / listing
    price: a past outcome counts as a profit only if it beats the landed cost after selling costs."""
    band = next((b for b in model.get("bins", []) if b["low"] < gap <= b["high"]), None)
    if not band:
        return {"range_low_6m": "", "range_median_6m": "", "range_high_6m": "", "prob_profit_6m": "", "similar_cases": ""}
    forwards = band.get("forwards")
    p_profit = (sum(1 for f in forwards if (1 + f) * (1 - SELL_COST) > cost_ratio) / len(forwards)) if forwards else band["p_profit"]
    return {"range_low_6m": round(band["q10"], 4), "range_median_6m": round(band["median"], 4), "range_high_6m": round(band["q90"], 4),
            "prob_profit_6m": round(p_profit, 4), "similar_cases": band["n"]}


def calibrate(panel):
    """Least squares of the 6-month listing-to-listing return on the gap, over known pairs."""
    pairs = []
    for (product, month), (market, low) in panel.items():
        later = panel.get((product, _month_add(month, HORIZON_MONTHS)))
        if not later or not low or not later[1]:
            continue
        forward = later[1] / low - 1.0
        if -0.9 <= forward <= 5.0:
            pairs.append((gap_of(low, market), forward))
    if len(pairs) < MIN_PAIRS:
        raise ValueError(f"only {len(pairs)} known 6-month pairs; need {MIN_PAIRS}")
    xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
    mx, my = mean(xs), mean(ys)
    slope = sum((x - mx) * (y - my) for x, y in pairs) / sum((x - mx) ** 2 for x in xs)
    return {"intercept": my - slope * mx, "slope": slope, "pairs": len(pairs), "bins": outcome_bins(pairs)}


def latest_prices(rows):
    """One row per product: the sub-type with a market price (first found)."""
    out = {}
    for r in rows:
        product = r.get("secret_lair_id", "")
        market = _float(r.get("market_price"))
        if not product or product in out and out[product]["market"]:
            continue
        direct, low = _float(r.get("direct_low_price")), _float(r.get("low_price"))
        out[product] = {"market": market, "buy": direct or low, "basis": "TCGPLAYER_DIRECT_LOW" if direct else ("LOWEST_LISTING" if low else ""),
                        "as_of": r.get("snapshot_date", "")}
    return out


def history_by_product(panel):
    """Monthly market and lowest-listing prices per product, for the research page chart."""
    out = {}
    for (product, month), (market, low) in sorted(panel.items()):
        out.setdefault(product, []).append([month, round(market, 2), round(low, 2) if low else None])
    return out


def market_index(panel):
    """Chain-linked Secret Lair market index (start = 100): each month, the median price change
    across products priced in both that month and the one before, so new drops do not distort it."""
    by_month = {}
    for (product, month), (market, _low) in panel.items():
        by_month.setdefault(month, {})[product] = market
    months = sorted(by_month)
    if not months:
        return []
    level, out = 100.0, [[months[0], 100.0, len(by_month[months[0]])]]
    for prev, cur in zip(months, months[1:]):
        ratios = sorted(by_month[cur][p] / by_month[prev][p] for p in by_month[cur] if p in by_month[prev])
        if ratios:
            mid = len(ratios) // 2
            level *= ratios[mid] if len(ratios) % 2 else (ratios[mid - 1] + ratios[mid]) / 2
        out.append([cur, round(level, 2), len(ratios)])
    return out


def score(latest, model, names, tcg_ids=None, shipping=BUY_SHIPPING_USD):
    rows = []
    for product, p in sorted(latest.items()):
        if not p["market"] or not p["buy"]:
            rows.append({"secret_lair_id": product, "call": "NO_PRICE", "as_of": p["as_of"], "market_price": p["market"] or "", "buy_price": p["buy"] or ""})
            continue
        landed = p["buy"] + shipping
        listing_gap = gap_of(p["buy"], p["market"])           # what the model was fitted on
        gap = gap_of(landed, p["market"])                     # discount after paying shipping
        listing_change = model["intercept"] + model["slope"] * listing_gap
        expected = (1.0 + listing_change) * p["buy"] / landed - 1.0
        net = (1.0 + expected) * (1.0 - SELL_COST) - 1.0
        rows.append({"secret_lair_id": product, "as_of": p["as_of"], "market_price": round(p["market"], 2), "buy_price": round(p["buy"], 2),
                     "buy_price_basis": p["basis"], "buy_shipping_usd": round(shipping, 2), "landed_buy_price": round(landed, 2),
                     "gap": round(gap, 4), "expected_return_6m": round(expected, 4),
                     "expected_net_return_6m": round(net, 4), "call": "BUY" if gap >= BUY_GAP and net > 0 else "WAIT",
                     "note": "CHECK_LISTING_LARGE_GAP" if listing_gap >= CHECK_GAP else "", **_band_fields(model, listing_gap, landed / p["buy"])})
    # Clean BUYs first, then BUYs with very large gaps (often mislisted or damaged copies), then the rest,
    # each by after-cost return.
    ranked = sorted((r for r in rows if r["call"] != "NO_PRICE"), key=lambda r: (0 if r["call"] == "BUY" and not r["note"] else 1 if r["call"] == "BUY" else 2, -r["expected_net_return_6m"]))
    for n, r in enumerate(ranked, start=1):
        r["rank"], r["ranked_products"] = n, len(ranked)
    for r in rows:
        r["product_name"] = names.get(r["secret_lair_id"], "")
        r["tcgplayer_product_id"] = (tcg_ids or {}).get(r["secret_lair_id"], "")
        r["model_version"] = MODEL_VERSION
    return sorted(rows, key=lambda r: (r.get("rank") or 10**9, r["secret_lair_id"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--history-monthly", type=Path, default=HISTORY_MONTHLY)
    parser.add_argument("--history-weekly", type=Path, default=HISTORY_WEEKLY)
    parser.add_argument("--latest", type=Path, default=LATEST)
    parser.add_argument("--names", type=Path, default=NAMES)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    panel = monthly_panel(_rows(args.history_monthly), _rows(args.history_weekly))
    model = calibrate(panel)
    latest = latest_prices(_rows(args.latest))
    if not latest:
        raise SystemExit("no latest prices")
    name_rows = [r for r in _rows(args.names) if r.get("secret_lair_id")]
    names = {r["secret_lair_id"]: r.get("product_name", "") for r in name_rows}
    tcg_ids = {r["secret_lair_id"]: str(r.get("tcgplayer_product_id") or "").strip() for r in name_rows}
    rows = score(latest, model, names, tcg_ids)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    calls = {c: sum(1 for r in rows if r["call"] == c) for c in ("BUY", "WAIT", "NO_PRICE")}
    calibration = {**model, "bins": [{k: v for k, v in b.items() if k != "forwards"} for b in model.get("bins", [])]}
    summary = {"model_version": MODEL_VERSION, "as_of": max((r["as_of"] for r in rows if r.get("as_of")), default=""),
               "calibration": calibration, "buy_gap": BUY_GAP, "sell_cost": SELL_COST, "buy_shipping_usd": BUY_SHIPPING_USD, "horizon_months": HORIZON_MONTHS, "calls": calls, "market_index": market_index(panel)}
    args.output.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    history = history_by_product(panel)
    args.output.with_name("secret_lair_v2_history.json").write_text(json.dumps(history, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
