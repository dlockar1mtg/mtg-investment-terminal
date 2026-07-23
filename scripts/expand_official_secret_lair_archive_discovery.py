from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import deque
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATION_ROOT = ROOT / "data/validation/phase_10/premium_universe_eligibility"
CURRENT_SOURCE = VALIDATION_ROOT / "secret_lair_structural_candidates_2026-07-22.csv"
OUTPUT = VALIDATION_ROOT / "secret_lair_official_archive_inventory_expanded.csv"
MISSING_OUTPUT = VALIDATION_ROOT / "secret_lair_official_missing_from_candidates_expanded.csv"
MATCH_OUTPUT = VALIDATION_ROOT / "secret_lair_official_candidate_crosswalk_expanded.csv"
SUMMARY_OUTPUT = VALIDATION_ROOT / "secret_lair_official_archive_summary_expanded.csv"
SOURCE_OUTPUT = VALIDATION_ROOT / "secret_lair_official_discovery_sources.csv"
FAILURE_OUTPUT = VALIDATION_ROOT / "secret_lair_official_archive_failures_expanded.json"
CACHE_ROOT = VALIDATION_ROOT / "official_secret_lair_cache_expanded"

ALLOWED_HOST = "secretlair.wizards.com"
START_URLS = (
    "https://secretlair.wizards.com/us/en/past-sales",
    "https://secretlair.wizards.com/us/en",
)
SITEMAP_URLS = (
    "https://secretlair.wizards.com/sitemap.xml",
    "https://secretlair.wizards.com/sitemap_index.xml",
    "https://secretlair.wizards.com/sitemap-index.xml",
    "https://secretlair.wizards.com/product-sitemap.xml",
    "https://secretlair.wizards.com/products-sitemap.xml",
)
MAX_HTML_PAGES = 1500
MAX_SCRIPT_FILES = 120
REQUEST_DELAY_SECONDS = 0.25
USER_AGENT = (
    "Mozilla/5.0 (compatible; MTGInvestmentTerminal/1.0; "
    "+https://github.com/dlockar1mtg/mtg-investment-terminal)"
)
PRODUCT_URL_RE = re.compile(
    r"https?://secretlair\.wizards\.com/(?:us(?:/en)?/)?product/\d+/[a-zA-Z0-9%._~!$&'()*+,;=:@/-]+",
    re.I,
)
RELATIVE_PRODUCT_RE = re.compile(
    r"/(?:us(?:/en)?/)?product/\d+/[a-zA-Z0-9%._~!$&'()*+,;=:@/-]+",
    re.I,
)


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.script_sources: list[str] = []
        self.text_parts: list[str] = []
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self._capture_title = False
        self._capture_h1 = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.links.append(str(values["href"]))
        if tag == "script" and values.get("src"):
            self.script_sources.append(str(values["src"]))
        if tag == "title":
            self._capture_title = True
        if tag == "h1":
            self._capture_h1 = True
        if tag in {"p", "li", "h1", "h2", "h3", "h4", "h5", "div", "span"}:
            self.text_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._capture_title = False
        if tag == "h1":
            self._capture_h1 = False
        if tag in {"p", "li", "h1", "h2", "h3", "h4", "h5", "div", "span"}:
            self.text_parts.append(" ")

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if not value:
            return
        self.text_parts.append(value)
        if self._capture_title:
            self.title_parts.append(value)
        if self._capture_h1:
            self.h1_parts.append(value)


def clean(value: object) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").split())


def norm(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", clean(value).lower())
    return " ".join(text.split())


def identity_norm(value: object) -> str:
    tokens = norm(value).split()
    ignored = {
        "secret", "lair", "drop", "series", "edition", "bundle", "superdrop",
        "the", "traditional", "rainbow", "etched", "galaxy", "gilded", "textured",
        "foil", "non", "nonfoil", "en", "english",
    }
    return " ".join(token for token in tokens if token not in ignored)


def token_similarity(left: object, right: object) -> float:
    a = set(identity_norm(left).split())
    b = set(identity_norm(right).split())
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def identify_finish(name: str, page_text: str = "") -> str:
    value = norm(f"{name} {page_text[:1500]}")
    if "rainbow foil" in value:
        return "rainbow_foil"
    if "foil etched" in value or "etched foil" in value:
        return "etched_foil"
    if "galaxy foil" in value:
        return "galaxy_foil"
    if "gilded foil" in value:
        return "gilded_foil"
    if "textured foil" in value:
        return "textured_foil"
    if "traditional foil" in value or "foil edition" in value or norm(name).endswith(" foil"):
        return "traditional_foil"
    if "non foil" in value or "nonfoil" in value:
        return "non_foil"
    return "unspecified"


def identify_packaging(name: str, page_text: str) -> str:
    name_norm = norm(name)
    value = norm(f"{name} {page_text[:1200]}")
    if "commander deck" in value or " deck " in f" {name_norm} ":
        return "deck"
    if "bundle" in name_norm:
        return "bundle"
    if "countdown kit" in value or " kit " in f" {name_norm} ":
        return "kit"
    return "individual_drop"


def canonical_product_url(url: str) -> str | None:
    parsed = urllib.parse.urlsplit(html.unescape(url))
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != ALLOWED_HOST:
        return None
    match = re.search(r"/(?:us(?:/en)?/)?product/(\d+)/([^/?#]+)", parsed.path, re.I)
    if not match:
        return None
    return f"https://{ALLOWED_HOST}/us/en/product/{match.group(1)}/{match.group(2).rstrip('/')}"


def cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    suffix = ".xml" if "sitemap" in url.lower() else ".txt"
    return CACHE_ROOT / f"{digest}{suffix}"


def fetch(url: str) -> str:
    path = cache_path(url)
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml,text/xml,*/*"},
    )
    with urllib.request.urlopen(request, timeout=50) as response:
        payload = response.read().decode("utf-8", errors="replace")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    time.sleep(REQUEST_DELAY_SECONDS)
    return payload


def discover_urls_from_text(payload: str, base_url: str) -> set[str]:
    urls: set[str] = set()
    decoded = html.unescape(payload).replace("\\/", "/")
    for match in PRODUCT_URL_RE.findall(decoded):
        canonical = canonical_product_url(match)
        if canonical:
            urls.add(canonical)
    for match in RELATIVE_PRODUCT_RE.findall(decoded):
        absolute = urllib.parse.urljoin(base_url, match)
        canonical = canonical_product_url(absolute)
        if canonical:
            urls.add(canonical)
    return urls


def parse_sitemap(payload: str) -> tuple[set[str], set[str]]:
    product_urls: set[str] = set()
    child_sitemaps: set[str] = set()
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return product_urls, child_sitemaps
    for element in root.iter():
        if not element.tag.lower().endswith("loc") or not element.text:
            continue
        value = clean(element.text)
        canonical = canonical_product_url(value)
        if canonical:
            product_urls.add(canonical)
        elif "sitemap" in value.lower() and urllib.parse.urlsplit(value).netloc.lower() == ALLOWED_HOST:
            child_sitemaps.add(value)
    return product_urls, child_sitemaps


def read_candidates() -> list[dict[str, str]]:
    if not CURRENT_SOURCE.exists():
        return []
    with CURRENT_SOURCE.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def extract_title(payload: str) -> tuple[str, str, PageParser]:
    parser = PageParser()
    parser.feed(payload)
    page_text = clean(" ".join(parser.text_parts))
    title = clean(" ".join(parser.h1_parts)) or clean(" ".join(parser.title_parts))
    title = re.sub(r"\s*\|\s*Secret Lair.*$", "", title, flags=re.I).strip()
    return title, page_text, parser


def extract_product_id(url: str) -> str:
    match = re.search(r"/product/(\d+)/", url)
    return match.group(1) if match else ""


def main() -> None:
    candidates = read_candidates()
    candidate_names = [clean(row.get("canonical_product_name")) for row in candidates]
    candidate_exact = {norm(name): name for name in candidate_names if norm(name)}

    discovered_urls: dict[str, set[str]] = {}
    failures: list[dict[str, str]] = []
    source_rows: list[dict[str, object]] = []

    def register(url: str, source: str) -> None:
        canonical = canonical_product_url(url)
        if canonical:
            discovered_urls.setdefault(canonical, set()).add(source)

    sitemap_queue: deque[str] = deque(SITEMAP_URLS)
    visited_sitemaps: set[str] = set()
    while sitemap_queue:
        sitemap_url = sitemap_queue.popleft()
        if sitemap_url in visited_sitemaps:
            continue
        visited_sitemaps.add(sitemap_url)
        try:
            payload = fetch(sitemap_url)
            products, children = parse_sitemap(payload)
            for url in products:
                register(url, f"sitemap:{sitemap_url}")
            for child in children:
                if child not in visited_sitemaps:
                    sitemap_queue.append(child)
            source_rows.append({"source_type": "sitemap", "source_url": sitemap_url, "status": "SUCCESS", "products_found": len(products), "details": f"child_sitemaps={len(children)}"})
        except Exception as exc:  # noqa: BLE001
            failures.append({"url": sitemap_url, "stage": "sitemap", "error": f"{type(exc).__name__}: {exc}"})
            source_rows.append({"source_type": "sitemap", "source_url": sitemap_url, "status": "FAILED", "products_found": 0, "details": f"{type(exc).__name__}: {exc}"})

    html_queue: deque[str] = deque(START_URLS)
    visited_html: set[str] = set()
    script_urls: set[str] = set()
    while html_queue and len(visited_html) < MAX_HTML_PAGES:
        url = html_queue.popleft()
        if url in visited_html:
            continue
        visited_html.add(url)
        try:
            payload = fetch(url)
        except Exception as exc:  # noqa: BLE001
            failures.append({"url": url, "stage": "html", "error": f"{type(exc).__name__}: {exc}"})
            continue

        title, page_text, parser = extract_title(payload)
        for product_url in discover_urls_from_text(payload, url):
            register(product_url, f"embedded:{url}")
        for href in parser.links:
            absolute = urllib.parse.urljoin(url, html.unescape(href))
            canonical = canonical_product_url(absolute)
            if canonical:
                register(canonical, f"href:{url}")
                if canonical not in visited_html:
                    html_queue.append(canonical)
        for src in parser.script_sources:
            absolute = urllib.parse.urljoin(url, html.unescape(src))
            parsed = urllib.parse.urlsplit(absolute)
            if parsed.scheme in {"http", "https"} and parsed.netloc.lower() == ALLOWED_HOST:
                script_urls.add(absolute)
        if canonical_product_url(url):
            register(url, "html_crawl")

    for index, script_url in enumerate(sorted(script_urls)):
        if index >= MAX_SCRIPT_FILES:
            break
        try:
            payload = fetch(script_url)
            found = discover_urls_from_text(payload, script_url)
            for product_url in found:
                register(product_url, f"script:{script_url}")
            source_rows.append({"source_type": "script", "source_url": script_url, "status": "SUCCESS", "products_found": len(found), "details": ""})
        except Exception as exc:  # noqa: BLE001
            failures.append({"url": script_url, "stage": "script", "error": f"{type(exc).__name__}: {exc}"})
            source_rows.append({"source_type": "script", "source_url": script_url, "status": "FAILED", "products_found": 0, "details": f"{type(exc).__name__}: {exc}"})

    product_rows: list[dict[str, object]] = []
    crosswalk_rows: list[dict[str, object]] = []
    for url in sorted(discovered_urls):
        try:
            payload = fetch(url)
            title, page_text, _ = extract_title(payload)
        except Exception as exc:  # noqa: BLE001
            failures.append({"url": url, "stage": "product", "error": f"{type(exc).__name__}: {exc}"})
            continue
        if not title:
            continue

        exact_name = candidate_exact.get(norm(title), "")
        best_name = ""
        best_similarity = 0.0
        for candidate_name in candidate_names:
            score = token_similarity(title, candidate_name)
            if score > best_similarity:
                best_similarity = score
                best_name = candidate_name

        official_finish = identify_finish(title, page_text)
        candidate_finish = identify_finish(best_name) if best_name else ""
        finish_compatible = (
            not best_name
            or official_finish == "unspecified"
            or candidate_finish == "unspecified"
            or official_finish == candidate_finish
        )
        if exact_name:
            status = "MATCHED_EXACT"
        elif best_similarity >= 0.82 and finish_compatible:
            status = "MATCHED_RELAXED_REVIEW"
        else:
            status = "MISSING_FROM_CURRENT_CANDIDATES"

        row = {
            "official_product_id": extract_product_id(url),
            "official_product_name": title,
            "normalized_product_name": norm(title),
            "identity_normalized_name": identity_norm(title),
            "finish": official_finish,
            "packaging_level": identify_packaging(title, page_text),
            "official_product_url": url,
            "candidate_status": status,
            "best_candidate_name": best_name,
            "name_similarity": round(best_similarity, 4),
            "candidate_finish": candidate_finish,
            "finish_compatible": finish_compatible,
            "discovery_sources": "|".join(sorted(discovered_urls[url])),
            "page_mentions_contents": " contents " in f" {norm(page_text)} ",
            "page_text_preview": page_text[:500],
        }
        product_rows.append(row)
        crosswalk_rows.append(row.copy())

    deduped: dict[str, dict[str, object]] = {}
    for row in product_rows:
        key = str(row["official_product_id"] or row["official_product_url"])
        deduped.setdefault(key, row)
    rows = sorted(deduped.values(), key=lambda row: (str(row["packaging_level"]), str(row["official_product_name"]), str(row["finish"])))
    missing = [row for row in rows if row["candidate_status"] == "MISSING_FROM_CURRENT_CANDIDATES"]

    fields = [
        "official_product_id", "official_product_name", "normalized_product_name",
        "identity_normalized_name", "finish", "packaging_level", "official_product_url",
        "candidate_status", "best_candidate_name", "name_similarity", "candidate_finish",
        "finish_compatible", "discovery_sources", "page_mentions_contents", "page_text_preview",
    ]
    write_csv(OUTPUT, rows, fields)
    write_csv(MISSING_OUTPUT, missing, fields)
    write_csv(MATCH_OUTPUT, rows, fields)
    write_csv(SOURCE_OUTPUT, source_rows, ["source_type", "source_url", "status", "products_found", "details"])

    summary: list[dict[str, object]] = [
        {"metric": "current_candidate_rows", "value": len(candidates)},
        {"metric": "unique_official_product_pages", "value": len(rows)},
        {"metric": "matched_exact", "value": sum(1 for row in rows if row["candidate_status"] == "MATCHED_EXACT")},
        {"metric": "matched_relaxed_review", "value": sum(1 for row in rows if row["candidate_status"] == "MATCHED_RELAXED_REVIEW")},
        {"metric": "missing_from_current_candidates", "value": len(missing)},
        {"metric": "sitemaps_attempted", "value": len(visited_sitemaps)},
        {"metric": "html_pages_visited", "value": len(visited_html)},
        {"metric": "script_files_discovered", "value": len(script_urls)},
        {"metric": "fetch_failures", "value": len(failures)},
    ]
    for packaging in sorted({str(row["packaging_level"]) for row in rows}):
        summary.append({"metric": f"packaging_{packaging}", "value": sum(1 for row in rows if row["packaging_level"] == packaging)})
    for finish in sorted({str(row["finish"]) for row in rows}):
        summary.append({"metric": f"finish_{finish}", "value": sum(1 for row in rows if row["finish"] == finish)})
    write_csv(SUMMARY_OUTPUT, summary, ["metric", "value"])

    FAILURE_OUTPUT.write_text(json.dumps(failures, indent=2), encoding="utf-8")

    print("SECRET LAIR OFFICIAL ARCHIVE EXPANSION: COMPLETE")
    print(f"Current candidate rows: {len(candidates)}")
    print(f"Unique official product pages: {len(rows)}")
    print(f"Matched exact: {sum(1 for row in rows if row['candidate_status'] == 'MATCHED_EXACT')}")
    print(f"Matched relaxed review: {sum(1 for row in rows if row['candidate_status'] == 'MATCHED_RELAXED_REVIEW')}")
    print(f"Missing from current candidates: {len(missing)}")
    print(f"Sitemaps attempted: {len(visited_sitemaps)}")
    print(f"HTML pages visited: {len(visited_html)}")
    print(f"Script files discovered: {len(script_urls)}")
    print(f"Fetch failures: {len(failures)}")
    print(f"Inventory: {OUTPUT.relative_to(ROOT)}")
    print(f"Missing: {MISSING_OUTPUT.relative_to(ROOT)}")
    print(f"Crosswalk: {MATCH_OUTPUT.relative_to(ROOT)}")
    print(f"Sources: {SOURCE_OUTPUT.relative_to(ROOT)}")
    print("Active eBay universe source was not changed.")


if __name__ == "__main__":
    main()
