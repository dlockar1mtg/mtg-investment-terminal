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

Calibration check (October 2026 re-test on TCGCSV prices only): the edge is not steady. In a stricter
re-test (boxes with a full 6-month trend only, 7 test months) the top quarter made +8.5% after costs
against +7.1% for all boxes, and its raw expected return (+16.5%) ran high. So each run
also replays the model walk-forward (refit only on outcomes known at each test month) and reports,
per predicted quarter, what boxes actually returned after costs. Those realized results are the
numbers to show; the status is VALIDATED only when the BUY quarter beat the all-box average by at
least VALIDATED_EDGE after costs over at least VALIDATED_MONTHS test months and by the same margin over
the most recent RECENT_MONTHS test months, PROVISIONAL otherwise. (October 2026, with every box the live
model scores: the top quarter made +14.7% after costs vs +10.1% for all boxes over 12 test months,
but the whole edge came from 2025-02 to 2025-06 starts; over the last 6 test months it trailed.)
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
QUARTERS = 4
WF_MIN_TRAIN_MONTHS = 6
WF_MIN_TEST_BOXES = 8
VALIDATED_EDGE = 0.02
VALIDATED_MONTHS = 12
RECENT_MONTHS = 6
FIELDS = ["tcgplayer_product_id", "box_name", "as_of", "market_price", "low_price", "direct_low_price",
          "months_since_release", "in_sweet_spot", "trend_6m", "expected_return_6m", "expected_net_return_6m",
          "release_date", "call", "note", "rank", "ranked_products", "quarter", "calibrated_net_return_6m", "calibrated_net_p10_6m",
          "calibrated_net_p90_6m", "calibrated_share_profitable", "model_version"]


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


def features(prices: dict[str, float], month: str, panel_, rel, on: date | None = None):
    """Feature rows for the products priced in `month` that have a release date.

    Ages are measured at the start of the month (history) or at `on` (today's scoring), and
    boxes not yet released at that point are left out."""
    products = [p for p in prices if p in rel]
    first_day = on or date.fromisoformat(month + "-01")
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


def outcomes(panel_, rel):
    """(start month, product, features, 6-month forward return) for every known 6-month outcome."""
    months = sorted({m for _, m in panel_})
    out = []
    for month in months:
        later = _shift(month, HORIZON)
        prices = {p: v for (p, m), v in panel_.items() if m == month}
        for p, f in features(prices, month, panel_, rel).items():
            future = panel_.get((p, later))
            if future:
                forward = future / prices[p] - 1.0
                if -0.9 <= forward <= 5.0:
                    out.append((month, p, [f["sweet"], f["trend_r"], f["price_r"]], forward))
    return out


def calibrate(panel_, rel):
    known = outcomes(panel_, rel)
    if len(known) < MIN_ROWS:
        raise ValueError(f"only {len(known)} known 6-month outcomes; need {MIN_ROWS}")
    b = _solve([o[2] for o in known], [o[3] for o in known])
    return {"intercept": b[0], "sweet_spot": b[1], "trend_rank": b[2], "price_rank": b[3], "rows": len(known)}


def _net(gross: float) -> float:
    return (1 + gross) * (1 - SELL_COST) - 1


def _quarter(position: int, n: int) -> int:
    """Quarter 1 (highest expected return) .. 4 for the 0-based position among n ranked boxes."""
    return 1 + position * QUARTERS // n


def _quantile(values, q):
    s = sorted(values)
    if not s:
        return None
    x = q * (len(s) - 1)
    lo = int(x)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (x - lo)


def _ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2.0
        i = j + 1
    return out


def _spearman(a, b):
    ra, rb = _ranks(a), _ranks(b)
    n = len(ra)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va, vb = sum((x - ma) ** 2 for x in ra), sum((y - mb) ** 2 for y in rb)
    return cov / (va * vb) ** 0.5 if va > 0 and vb > 0 else 0.0


def _stats(nets, predicted=None):
    out = {"cases": len(nets), "avg_net_return": round(sum(nets) / len(nets), 4),
           "p10_net_return": round(_quantile(nets, 0.10), 4), "p50_net_return": round(_quantile(nets, 0.50), 4),
           "p90_net_return": round(_quantile(nets, 0.90), 4),
           "share_profitable": round(sum(1 for x in nets if x > 0) / len(nets), 4)}
    if predicted:
        out["avg_predicted_net_return"] = round(sum(predicted) / len(predicted), 4)
    return out


def walk_forward(panel_, rel):
    """Replay the model month by month, refitting only on outcomes known by each test month.

    Returns what each predicted quarter actually returned over 6 months after selling costs."""
    known = outcomes(panel_, rel)
    tested, ics, months_used = [], [], []
    for month in sorted({o[0] for o in known}):
        train = [o for o in known if _shift(o[0], HORIZON) <= month]
        test = [o for o in known if o[0] == month]
        if len(train) < MIN_ROWS or len({o[0] for o in train}) < WF_MIN_TRAIN_MONTHS or len(test) < WF_MIN_TEST_BOXES:
            continue
        try:
            b = _solve([o[2] for o in train], [o[3] for o in train])
        except ValueError:
            continue
        preds = [b[0] + sum(c * x for c, x in zip(b[1:], o[2])) for o in test]
        order = sorted(range(len(test)), key=lambda i: (-preds[i], test[i][1]))
        for position, i in enumerate(order):
            tested.append((_quarter(position, len(test)), _net(test[i][3]), _net(preds[i]), month))
        ics.append(_spearman(preds, [o[3] for o in test]))
        months_used.append(month)
    if not tested:
        return {"test_months": 0, "status": "NOT_VALIDATED", "quarters": {}}
    quarters = {}
    for q in range(1, QUARTERS + 1):
        rows = [t for t in tested if t[0] == q]
        if rows:
            quarters[str(q)] = _stats([t[1] for t in rows], [t[2] for t in rows])
    everything = _stats([t[1] for t in tested])
    top = quarters.get("1", {})
    edge = top.get("avg_net_return", 0.0) - everything["avg_net_return"]
    recent_months = set(months_used[-RECENT_MONTHS:])
    recent = [t for t in tested if t[3] in recent_months]
    recent_top = [t[1] for t in recent if t[0] == 1]
    recent_all = [t[1] for t in recent]
    recent_edge = (sum(recent_top) / len(recent_top) - sum(recent_all) / len(recent_all)) if recent_top else 0.0
    validated = len(months_used) >= VALIDATED_MONTHS and edge >= VALIDATED_EDGE and recent_edge >= VALIDATED_EDGE
    return {"test_months": len(months_used), "first_test_month": months_used[0], "last_test_month": months_used[-1],
            "horizon_months": HORIZON, "sell_cost": SELL_COST, "quarters": quarters, "all_boxes": everything,
            "buy_quarter_edge": round(edge, 4),
            "recent": {"test_months": len(recent_months), "first_test_month": min(recent_months), "last_test_month": max(recent_months),
                       "buy_quarter": _stats(recent_top) if recent_top else None, "all_boxes": _stats(recent_all),
                       "buy_quarter_edge": round(recent_edge, 4)},
            "rank_correlation": round(sum(ics) / len(ics), 4),
            "share_months_rank_positive": round(sum(1 for x in ics if x > 0) / len(ics), 4),
            "status": "VALIDATED" if validated else "PROVISIONAL"}


def latest_prices(rows):
    out = {}
    for r in rows:
        p = str(r.get("tcgplayer_product_id", "")).strip()
        market = _float(r.get("market_price"))
        if p and (p not in out or (market and not out[p]["market"])):
            out[p] = {"market": market, "low": _float(r.get("low_price")), "direct": _float(r.get("direct_low_price")),
                      "name": r.get("box_name", ""), "as_of": str(r.get("snapshot_date", ""))[:10]}
    return out


def score(latest, panel_, rel, model, history=None):
    as_of = max((v["as_of"] for v in latest.values() if v["as_of"]), default=date.today().isoformat())
    prices = {p: v["market"] for p, v in latest.items() if v["market"]}
    feats = features(prices, _month(as_of), panel_, rel, on=date.fromisoformat(as_of))
    quarters = (history or {}).get("quarters", {})
    rows = []
    for p, v in sorted(latest.items()):
        base = {"tcgplayer_product_id": p, "box_name": v["name"], "as_of": v["as_of"], "market_price": v["market"] or "",
                "low_price": v["low"] or "", "direct_low_price": v["direct"] or "", "model_version": MODEL_VERSION}
        f = feats.get(p)
        released = rel.get(p)
        base["release_date"] = released.isoformat() if released else ""
        if not v["market"] or not f:
            note = ("NO_CURRENT_PRICE" if not v["market"] else "NO_RELEASE_DATE" if not released
                    else "NOT_YET_RELEASED" if released > date.fromisoformat(as_of) else "NO_MODEL_FEATURES")
            rows.append({**base, "call": "NO_PRICE", "note": note})
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
        r["quarter"] = _quarter(n - 1, len(ranked))
        past = quarters.get(str(r["quarter"]))
        if past:
            r.update(calibrated_net_return_6m=past["avg_net_return"], calibrated_net_p10_6m=past["p10_net_return"],
                     calibrated_net_p90_6m=past["p90_net_return"], calibrated_share_profitable=past["share_profitable"])
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
    history = walk_forward(panel_, rel)
    latest = latest_prices(_rows(args.latest))
    if not latest:
        raise SystemExit("no latest Collector box prices")
    rows = score(latest, panel_, rel, model, history)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    calls = {c: sum(1 for r in rows if r["call"] == c) for c in ("BUY", "HOLD", "NO_PRICE")}
    summary = {"model_version": MODEL_VERSION, "as_of": max((r["as_of"] for r in rows if r.get("as_of")), default=""),
               "calibration": model, "buy_share": BUY_SHARE, "sell_cost": SELL_COST, "horizon_months": HORIZON,
               "sweet_spot_months": list(SWEET_SPOT), "calls": calls, "walk_forward": history}
    args.output.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    price_history = {}
    for (product, month), price in sorted(panel_.items()):
        price_history.setdefault(product, []).append([month, round(price, 2)])
    args.output.with_name("collector_v2_history.json").write_text(json.dumps(price_history, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"as_of": summary["as_of"], "calls": calls, "status": history.get("status"),
                      "test_months": history.get("test_months")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
