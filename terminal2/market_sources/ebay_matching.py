from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
BOOSTER_SOURCE = ROOT / "data/validation/phase_10/historical_product_scope/historical_active_review_population_2026-07-22.csv"
SECRET_LAIR_SOURCE = ROOT / "data/validation/phase_10/premium_universe_eligibility/secret_lair_master_registry_ready_universe.csv"
OUTPUT_ROOT = ROOT / "data/validation/phase_10/ebay_matching"

COLLECTOR_ERA_START = "2019-10-04"
NEGATIVE_TERMS = (
    " single pack ", " booster pack ", " individual pack ", " pack only ",
    " lot of packs ", " loose pack ", " empty ", " empty box ", " opened ",
    " repack ", " resealed ", " re sealed ", " not factory sealed ",
    " proxy ", " damaged ", " case of ", " sealed case ", " master case ",
    " display box only ", " box only no packs ", " box topper only ",
    " wrapper ", " replica ", " custom ", " digital ", " arena code ",
)
NON_ENGLISH_TERMS = (
    " japanese ", " german ", " french ", " italian ", " spanish ",
    " portuguese ", " korean ", " chinese ", " russian ",
)
PRESALE_TERMS = (" presale ", " pre sale ", " presell ", " pre sell ", " preorder ", " pre order ", " pre aug ")
NUMBERED_EDITION_ALIASES = {
    "7th edition": ("seventh edition", "7e", "7ed"),
    "8th edition": ("eighth edition", "8e", "8ed"),
    "9th edition": ("ninth edition", "9e", "9ed"),
    "10th edition": ("tenth edition", "10e", "10ed"),
}


def _clean(value: object) -> str:
    return str(value or "").strip()


def _norm(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", _clean(value).lower())
    return f" {' '.join(text.split())} "


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _load_dotenv(path: Path | None = None) -> None:
    source = path or ROOT / ".env"
    if not source.exists():
        return
    for raw in source.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class CanonicalProduct:
    canonical_product_id: str
    canonical_product_name: str
    canonical_set_name: str
    product_class: str
    tcgplayer_product_id: str
    release_date: str
    ebay_query: str


@dataclass(frozen=True)
class MatchResult:
    canonical_product_id: str
    canonical_product_name: str
    product_class: str
    ebay_query: str
    ebay_item_id: str
    title: str
    item_url: str
    price: float | None
    shipping: float | None
    landed_price: float | None
    currency: str
    seller_hash: str
    buying_options: str
    condition: str
    match_score: float
    match_state: str
    exclusion_reasons: str
    source_run_id: str
    observed_at_utc: str


def classify_booster(row: Mapping[str, str]) -> str | None:
    name = _clean(row.get("canonical_product_name") or row.get("selected_sealed_name"))
    date = _clean(row.get("governed_release_date") or row.get("set_release_date"))
    normal = _norm(name)
    if " collector booster box " in normal or " collector booster display " in normal:
        return "COLLECTOR_BOOSTER_BOX"
    if " booster box " not in normal and " booster display " not in normal:
        return None
    if date and date < COLLECTOR_ERA_START:
        return "PRE_COLLECTOR_BOOSTER_BOX"
    return None


def _clean_product_name(name: str) -> str:
    cleaned = re.sub(r"\s+-\s+", " ", name).strip()
    return re.sub(r"\bMagic:\s*The Gathering\b", "", cleaned, flags=re.I).strip()


def build_query(name: str, product_class: str) -> str:
    cleaned = _clean_product_name(name)
    if product_class == "SEALED_SECRET_LAIR":
        return f'Magic The Gathering Secret Lair "{cleaned}" sealed'
    return f'Magic The Gathering "{cleaned}" sealed'


def build_query_ladder(product: CanonicalProduct) -> list[str]:
    cleaned = _clean_product_name(product.canonical_product_name)
    base = re.sub(r"\b(Collector\s+)?Booster\s+(Box|Display)\b", "", cleaned, flags=re.I).strip()
    queries = [product.ebay_query]

    if product.product_class == "SEALED_SECRET_LAIR":
        queries.extend([
            f'MTG Secret Lair {cleaned} sealed',
            f'Secret Lair {cleaned}',
        ])
    elif product.product_class == "COLLECTOR_BOOSTER_BOX":
        queries.extend([
            f'MTG {base} Collector Booster Box sealed',
            f'MTG {base} Collector Booster Display sealed',
            f'{base} Collector Booster Box',
        ])
    else:
        queries.extend([
            f'MTG {base} Booster Box sealed',
            f'MTG {base} Booster Display sealed',
            f'{base} factory sealed booster box',
        ])
        normal_base = _norm(base)
        for key, aliases in NUMBERED_EDITION_ALIASES.items():
            if f" {key} " in normal_base:
                for alias in aliases:
                    queries.extend([
                        f'MTG {alias} Booster Box sealed',
                        f'MTG {alias} Booster Display sealed',
                    ])

    unique: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = " ".join(query.split()).lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(" ".join(query.split()))
    return unique


def build_universe() -> list[CanonicalProduct]:
    products: dict[str, CanonicalProduct] = {}
    for row in _read_csv(BOOSTER_SOURCE):
        product_class = classify_booster(row)
        if not product_class:
            continue
        product_id = _clean(row.get("canonical_product_id"))
        name = _clean(row.get("canonical_product_name") or row.get("selected_sealed_name"))
        if not product_id or not name:
            continue
        products[product_id] = CanonicalProduct(
            product_id,
            name,
            _clean(row.get("canonical_set_name") or row.get("selected_set_name")),
            product_class,
            _clean(row.get("tcgplayer_product_id") or row.get("selected_sealed_tcgplayer_product_id")),
            _clean(row.get("governed_release_date") or row.get("set_release_date")),
            build_query(name, product_class),
        )

    for row in _read_csv(SECRET_LAIR_SOURCE):
        # The certified master export uses Secret Lair-native field names.
        # Legacy aliases remain supported so historical snapshots can still load.
        governance_status = _clean(row.get("governance_status")).upper()
        ebay_allowed = _clean(row.get("ebay_matching_allowed")).lower()
        if governance_status and governance_status != "REGISTRY_READY":
            continue
        if ebay_allowed and ebay_allowed not in {"true", "1", "yes"}:
            continue

        name = _clean(row.get("product_name") or row.get("canonical_product_name"))
        product_id = _clean(row.get("secret_lair_id") or row.get("canonical_product_id"))
        tcgplayer_product_id = _clean(row.get("tcgplayer_product_id"))
        set_name = _clean(
            row.get("superdrop_name")
            or row.get("drop_name")
            or row.get("canonical_set_name")
        )
        if not product_id or not name or not tcgplayer_product_id:
            continue

        # Master release_date currently contains source-publication timestamps for
        # many TCGCSV records, so it is intentionally not used for age analytics.
        products[product_id] = CanonicalProduct(
            product_id,
            name,
            set_name,
            "SEALED_SECRET_LAIR",
            tcgplayer_product_id,
            "",
            build_query(name, "SEALED_SECRET_LAIR"),
        )
    return sorted(products.values(), key=lambda value: (value.product_class, value.canonical_product_name))


def _tokens(name: str) -> set[str]:
    ignored = {
        "magic", "the", "gathering", "mtg", "sealed", "factory", "booster",
        "box", "display", "secret", "lair", "drop", "edition",
    }
    return {part for part in _norm(name).split() if len(part) > 2 and part not in ignored}


def match_listing(product: CanonicalProduct, item: Mapping[str, object], run_id: str, observed: str) -> MatchResult:
    title = _clean(item.get("title"))
    title_norm = _norm(title)
    reasons: list[str] = []
    if any(term in title_norm for term in NEGATIVE_TERMS):
        reasons.append("excluded_product_form")
    if any(term in title_norm for term in NON_ENGLISH_TERMS):
        reasons.append("non_english")
    if any(term in title_norm for term in PRESALE_TERMS):
        reasons.append("presale")

    required = _tokens(product.canonical_product_name)
    present = {token for token in required if f" {token} " in title_norm}
    coverage = len(present) / len(required) if required else 1.0
    score = 0.25 + 0.55 * coverage

    if product.product_class == "COLLECTOR_BOOSTER_BOX":
        score += 0.10 if " collector " in title_norm else -0.25
        score += 0.10 if (" booster box " in title_norm or " booster display " in title_norm) else -0.15
    elif product.product_class == "PRE_COLLECTOR_BOOSTER_BOX":
        product_form = " booster box " in title_norm or " booster display " in title_norm or " factory sealed box " in title_norm
        score += 0.10 if product_form else -0.15
        score -= 0.20 if " collector " in title_norm else 0.0
    else:
        score += 0.10 if " secret lair " in title_norm else -0.25
        score += 0.05 if " sealed " in title_norm else 0.0

    if reasons:
        score = min(score, 0.49)
    score = max(0.0, min(1.0, score))
    state = "ACCEPTED" if score >= 0.82 else "REVIEW" if score >= 0.62 else "REJECTED"

    price_obj = item.get("price") if isinstance(item.get("price"), Mapping) else {}
    shipping_options = item.get("shippingOptions") if isinstance(item.get("shippingOptions"), list) else []
    shipping = None
    if shipping_options:
        cost = shipping_options[0].get("shippingCost") or {}
        try:
            shipping = float(cost.get("value"))
        except (TypeError, ValueError):
            shipping = None
    try:
        price = float(price_obj.get("value"))
    except (TypeError, ValueError):
        price = None
    landed = None if price is None else price + (shipping or 0.0)
    seller = item.get("seller") if isinstance(item.get("seller"), Mapping) else {}
    seller_name = _clean(seller.get("username"))
    seller_hash = hashlib.sha256(seller_name.encode("utf-8")).hexdigest()[:16] if seller_name else ""
    options = item.get("buyingOptions") if isinstance(item.get("buyingOptions"), list) else []

    return MatchResult(
        product.canonical_product_id, product.canonical_product_name, product.product_class,
        product.ebay_query, _clean(item.get("itemId")), title, _clean(item.get("itemWebUrl")),
        price, shipping, landed, _clean(price_obj.get("currency")), seller_hash,
        "|".join(_clean(value) for value in options), _clean(item.get("condition")),
        round(score, 4), state, "|".join(reasons), run_id, observed,
    )




class EbayRateLimitError(RuntimeError):
    def __init__(self, message: str, retry_after: str = ""):
        super().__init__(message)
        self.retry_after = retry_after


class EbayBrowseClient:
    def __init__(self, timeout: int = 30):
        _load_dotenv()
        self.client_id = os.getenv("EBAY_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("EBAY_CLIENT_SECRET", "").strip()
        self.marketplace = os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US").strip()
        self.timeout = timeout
        self._token = ""
        self._expires_at = 0.0
        if not self.client_id or not self.client_secret:
            raise RuntimeError("EBAY_CLIENT_ID and EBAY_CLIENT_SECRET are required")

    def token(self) -> str:
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        body = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        }).encode()
        request = urllib.request.Request(
            "https://api.ebay.com/identity/v1/oauth2/token", data=body, method="POST",
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.load(response)
        self._token = payload["access_token"]
        self._expires_at = time.time() + int(payload.get("expires_in", 7200))
        return self._token

    def search(self, query: str, limit: int = 20) -> list[dict[str, object]]:
        params = urllib.parse.urlencode({"q": query, "limit": max(1, min(limit, 200))})
        request = urllib.request.Request(
            f"https://api.ebay.com/buy/browse/v1/item_summary/search?{params}",
            headers={"Authorization": f"Bearer {self.token()}", "X-EBAY-C-MARKETPLACE-ID": self.marketplace, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
                raise EbayRateLimitError(
                    "eBay Browse API rate limit reached",
                    retry_after=retry_after,
                ) from exc
            raise
        return list(payload.get("itemSummaries") or [])

    def search_product(self, product: CanonicalProduct, limit: int = 20) -> tuple[list[dict[str, object]], int]:
        collected: dict[str, dict[str, object]] = {}
        queries_used = 0
        for query in build_query_ladder(product):
            if len(collected) >= limit:
                break
            queries_used += 1
            remaining = max(1, limit - len(collected))
            for item in self.search(query, remaining):
                item_id = _clean(item.get("itemId"))
                dedupe_key = item_id or hashlib.sha256(_clean(item.get("title")).encode("utf-8")).hexdigest()
                collected.setdefault(dedupe_key, item)
                if len(collected) >= limit:
                    break
        return list(collected.values())[:limit], queries_used


def run_coverage(limit_per_product: int = 20, max_products: int | None = None) -> dict[str, object]:
    universe = build_universe()
    if max_products is not None:
        universe = universe[:max_products]
    client = EbayBrowseClient()
    observed = datetime.now(timezone.utc).isoformat()
    run_id = datetime.now(timezone.utc).strftime("EBAY%Y%m%dT%H%M%SZ")
    results: list[MatchResult] = []
    coverage_rows: list[dict[str, object]] = []

    for index, product in enumerate(universe, start=1):
        queries_used = 0
        try:
            items, queries_used = client.search_product(product, limit_per_product)
            matches = [match_listing(product, item, run_id, observed) for item in items]
            error = ""
        except EbayRateLimitError as exc:
            matches = []
            error = f"{type(exc).__name__}: {exc}"
            results.extend(matches)
            coverage_rows.append({
                **asdict(product), "queries_used": queries_used, "results_found": 0,
                "accepted_listing_count": 0, "review_listing_count": 0,
                "rejected_listing_count": 0,
                "median_accepted_landed_price": "",
                "lowest_accepted_landed_price": "",
                "accepted_seller_count": 0,
                "coverage_state": "SOURCE_ERROR",
                "source_error": error,
            })
            print(
                f"[{index}/{len(universe)}] {product.canonical_product_name}: SOURCE_ERROR "
                f"(0 accepted, 0 found, {queries_used} queries)"
            )
            print(
                "EBAY RATE LIMIT REACHED: aborting batch immediately"
                + (f"; retry_after={exc.retry_after}" if exc.retry_after else "")
            )
            break
        except Exception as exc:
            matches = []
            error = f"{type(exc).__name__}: {exc}"
        results.extend(matches)
        accepted = [row for row in matches if row.match_state == "ACCEPTED"]
        review = [row for row in matches if row.match_state == "REVIEW"]
        rejected = [row for row in matches if row.match_state == "REJECTED"]
        prices = [row.landed_price for row in accepted if row.landed_price is not None]
        sellers = {row.seller_hash for row in accepted if row.seller_hash}
        if error:
            state = "SOURCE_ERROR"
        elif len(accepted) >= 5:
            state = "STRONG_MATCH_COVERAGE"
        elif accepted:
            state = "LIMITED_MATCH_COVERAGE"
        elif review:
            state = "AMBIGUOUS_RESULTS"
        else:
            state = "NO_MATCHES"
        coverage_rows.append({
            **asdict(product), "queries_used": queries_used, "results_found": len(matches),
            "accepted_listing_count": len(accepted), "review_listing_count": len(review),
            "rejected_listing_count": len(rejected),
            "median_accepted_landed_price": round(median(prices), 2) if prices else "",
            "lowest_accepted_landed_price": round(min(prices), 2) if prices else "",
            "accepted_seller_count": len(sellers), "coverage_state": state, "source_error": error,
        })
        print(
            f"[{index}/{len(universe)}] {product.canonical_product_name}: {state} "
            f"({len(accepted)} accepted, {len(matches)} found, {queries_used} queries)"
        )

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc).date().isoformat()
    universe_rows = [asdict(row) for row in universe]
    result_rows = [asdict(row) for row in results]
    _write_csv(OUTPUT_ROOT / f"ebay_canonical_match_universe_{date}.csv", universe_rows, CanonicalProduct.__dataclass_fields__.keys())
    _write_csv(OUTPUT_ROOT / f"ebay_listing_match_results_{date}.csv", result_rows, MatchResult.__dataclass_fields__.keys())
    coverage_fields = list(CanonicalProduct.__dataclass_fields__.keys()) + [
        "queries_used", "results_found", "accepted_listing_count", "review_listing_count",
        "rejected_listing_count", "median_accepted_landed_price", "lowest_accepted_landed_price",
        "accepted_seller_count", "coverage_state", "source_error",
    ]
    _write_csv(OUTPUT_ROOT / f"ebay_product_coverage_{date}.csv", coverage_rows, coverage_fields)
    manual = [row for row in result_rows if row["match_state"] == "REVIEW"]
    _write_csv(OUTPUT_ROOT / f"ebay_manual_review_{date}.csv", manual, MatchResult.__dataclass_fields__.keys())
    summary = {
        "run_id": run_id,
        "observed_at_utc": observed,
        "products": len(coverage_rows),
        "expected_products": len(universe),
        "aborted_early": len(coverage_rows) < len(universe),
        "listing_rows": len(results),
        "queries_used": sum(int(row["queries_used"]) for row in coverage_rows),
        "accepted_rows": sum(row.match_state == "ACCEPTED" for row in results),
        "review_rows": sum(row.match_state == "REVIEW" for row in results),
        "rejected_rows": sum(row.match_state == "REJECTED" for row in results),
        "coverage_states": {
            state: sum(row["coverage_state"] == state for row in coverage_rows)
            for state in sorted({row["coverage_state"] for row in coverage_rows})
        },
        "credentials_printed": False,
    }
    (OUTPUT_ROOT / f"ebay_matching_summary_{date}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
