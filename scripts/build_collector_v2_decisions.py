"""Collector booster box model v2: life-cycle sweet spot, trend and price, refit daily.

Research (October 2026, walk-forward on the 2024-02 to 2026-07 TCGCSV history of 44 boxes with
official release dates, 6-month horizon, 16 test months): a model of the 6-to-24-months-after-
release sweet spot, 6-month trend and price rank ranked boxes correctly in 81% of months (rank
correlation +0.19); its top quarter returned +31.7% over 6 months against +25.4% for all boxes.
The September model's inputs (own-trend Monte Carlo forecasts) were never tested against outcomes.

Each run refits expected 6-month return = a + b*sweet_spot + c*trend_rank + d*price_rank on every
month whose 6-month outcome is known (market price to market price), then scores today's prices.
BUY the top quarter by expected return when the return after selling costs is positive; HOLD the
rest; NO_PRICE without a current price or release date.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data" / "history" / "mtg_ledger" / "universal_mtg_daily_consolidated_ledger.csv"
WEEKLY = ROOT / "data" / "history" / "boxes" / "collector_weekly_prices.csv"
LATEST = ROOT / "data" / "history" / "boxes" / "collector_latest_prices.csv"
RELEASES = ROOT / "config" / "mtg" / "governance" / "collector_official_release_date_registry_v1.csv"
OUTPUT = ROOT / "data" / "history" / "boxes" / "collector_v2_decisions.csv"

MODEL_VERSION = "collector-v2"
HORIZON = 6
SWEET_SPOT = (6.0, 24.0)
BUY_SHARE = 0.25
SELL_COST = 0.13
MIN_ROWS = 150
FIELDS = ["tcgplayer_product_id", "box_name", "as_of", "market_price", "low_price", "direct_low_price",
          "months_since_release", "in_sweet_spot", "trend_6m", "expected_return_6m", "expected_net_return_6m",
          "call", "rank", "ranked_products", "model_version"]


def _rows(path: Path):
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _months_between(earlier: date, later: date) -> float:
    return (later - earlier).days / 30.44


def _month(day: str) -> str:
    return day[:7]


def _shift(month: str, k: int) -> str:
    y, m = int(month[:4]), int(month[5:7]) - 1 + k
    return f"{y + m // 12:04d}-{m % 12 + 1:02d}"


def releases(rows):
    out = {}
    for r in rows:
        product, day = str(r.get("tcgplayer_product_id", "")).strip(), str(r.get("official_release_date", "")).strip()[:10]
        try:
            out[product] = date.fromisoformat(day)
        except ValueError:
            continue
    return out


def panel(ledger_rows, weekly_rows):
    """(product, 'YYYY-MM') -> market price: last observation in each month."""
    obs = []
    for r in ledger_rows:
        if r.get("product_class") == "COLLECTOR_BOOSTER_BOX" and "TCGCSV" in str(r.get("source_names", "")):
            obs.append((str(r.get("tcgplayer_product_id", "")).strip(), str(r.get("observation_date", ""))[:10], _float(r.get("consolidated_market_price"))))
    for r in weekly_rows:
        obs.append((str(r.get("tcgplayer_product_id", "")).strip(), str(r.get("snapshot_date", ""))[:10], _float(r.get("market_price"))))
    out = {}
    for product, day, price in sorted(obs, key=lambda o: (o[0], o[1])):
        if product and len(day) == 10 and price:
            out[(product, _month(day))] = price
    return out


def _centred_ranks(values: dict[str, float | None]) -> dict[str, float]:
    known = sorted((v, k) for k, v in values.items() if v is not None)
    n = len(known)
    ranks = {k: (i + 1) / n - 0.5 for i, (v, k) in enumerate(known)} if n else {}
    return {k: ranks.get(k, 0.0) for k in values}


def features(prices: dict[str, float], month: str, panel_, rel):
    """Feature rows for the products priced in `month` that have a release date."""
    products = [p for p in prices if p in rel]
    first_day = date.fromisoformat(month + "-01")
    ages = {p: _months_between(rel[p], first_day) for p in products}
    products = [p for p in products if ages[p] >= 0]
    trend = {}
    for p in products:
        past = panel_.get((p, _shift(month, -HORIZON)))
        trend[p] = prices[p] / past - 1.0 if past else None
    trend_r = _centred_ranks(trend)
    price_r = _centred_ranks({p: prices[p] for p in products})
    return {p: {"sweet": 1.0 if SWEET_SPOT[0] <= ages[p] <= SWEET_SPOT[1] else 0.0, "trend_r": trend_r[p],
                "price_r": price_r[p], "age": ages[p], "trend": trend[p]} for p in products}


def _solve(xs, ys):
    """Least squares with intercept via normal equations (4 x 4)."""
    rows = [[1.0, *x] for x in xs]
    k = len(rows[0])
    m = [[sum(r[i] * r[j] for r in rows) for j in range(k)] + [sum(r[i] * y for r, y in zip(rows, ys))] for i in range(k)]
    for c in range(k):
        pivot = max(range(c, k), key=lambda r: abs(m[r][c]))
        m[c], m[pivot] = m[pivot], m[c]
        if abs(m[c][c]) < 1e-12:
            raise ValueError("singular design")
        for r in range(k):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [a - f * b for a, b in zip(m[r], m[c])]
    return [m[i][k] / m[i][i] for i in range(k)]


def calibrate(panel_, rel):
    months = sorted({m for _, m in panel_})
    xs, ys = [], []
    for month in months:
        later = _shift(month, HORIZON)
        prices = {p: v for (p, m), v in panel_.items() if m == month}
        for p, f in features(prices, month, panel_, rel).items():
            future = panel_.get((p, later))
            if future:
                forward = future / prices[p] - 1.0
                if -0.9 <= forward <= 5.0:
                    xs.append([f["sweet"], f["trend_r"], f["price_r"]])
                    ys.append(forward)
    if len(ys) < MIN_ROWS:
        raise ValueError(f"only {len(ys)} known 6-month outcomes; need {MIN_ROWS}")
    b = _solve(xs, ys)
    return {"intercept": b[0], "sweet_spot": b[1], "trend_rank": b[2], "price_rank": b[3], "rows": len(ys)}


def latest_prices(rows):
    out = {}
    for r in rows:
        p = str(r.get("tcgplayer_product_id", "")).strip()
        market = _float(r.get("market_price"))
        if p and (p not in out or (market and not out[p]["market"])):
            out[p] = {"market": market, "low": _float(r.get("low_price")), "direct": _float(r.get("direct_low_price")),
                      "name": r.get("box_name", ""), "as_of": str(r.get("snapshot_date", ""))[:10]}
    return out


def score(latest, panel_, rel, model):
    as_of = max((v["as_of"] for v in latest.values() if v["as_of"]), default=date.today().isoformat())
    prices = {p: v["market"] for p, v in latest.items() if v["market"]}
    feats = features(prices, _month(as_of), panel_, rel)
    rows = []
    for p, v in sorted(latest.items()):
        base = {"tcgplayer_product_id": p, "box_name": v["name"], "as_of": v["as_of"], "market_price": v["market"] or "",
                "low_price": v["low"] or "", "direct_low_price": v["direct"] or "", "model_version": MODEL_VERSION}
        f = feats.get(p)
        if not v["market"] or not f:
            rows.append({**base, "call": "NO_PRICE"})
            continue
        expected = model["intercept"] + model["sweet_spot"] * f["sweet"] + model["trend_rank"] * f["trend_r"] + model["price_rank"] * f["price_r"]
        rows.append({**base, "months_since_release": round(f["age"], 1), "in_sweet_spot": int(f["sweet"]),
                     "trend_6m": "" if f["trend"] is None else round(f["trend"], 4), "expected_return_6m": round(expected, 4),
                     "expected_net_return_6m": round((1 + expected) * (1 - SELL_COST) - 1, 4)})
    ranked = sorted((r for r in rows if r.get("call") != "NO_PRICE"), key=lambda r: r["expected_return_6m"], reverse=True)
    cutoff = max(1, round(len(ranked) * BUY_SHARE))
    for n, r in enumerate(ranked, start=1):
        r["rank"], r["ranked_products"] = n, len(ranked)
        r["call"] = "BUY" if n <= cutoff and r["expected_net_return_6m"] > 0 else "HOLD"
    return sorted(rows, key=lambda r: (r.get("rank") or 10**9, r["tcgplayer_product_id"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--weekly", type=Path, default=WEEKLY)
    parser.add_argument("--latest", type=Path, default=LATEST)
    parser.add_argument("--releases", type=Path, default=RELEASES)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    rel = releases(_rows(args.releases))
    panel_ = panel(_rows(args.ledger), _rows(args.weekly))
    model = calibrate(panel_, rel)
    latest = latest_prices(_rows(args.latest))
    if not latest:
        raise SystemExit("no latest Collector box prices")
    rows = score(latest, panel_, rel, model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    calls = {c: sum(1 for r in rows if r["call"] == c) for c in ("BUY", "HOLD", "NO_PRICE")}
    summary = {"model_version": MODEL_VERSION, "as_of": max((r["as_of"] for r in rows if r.get("as_of")), default=""),
               "calibration": model, "buy_share": BUY_SHARE, "sell_cost": SELL_COST, "horizon_months": HORIZON,
               "sweet_spot_months": list(SWEET_SPOT), "calls": calls}
    args.output.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
