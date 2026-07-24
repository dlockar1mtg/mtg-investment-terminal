from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
from collections import deque
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATION_ROOT = ROOT / "data/validation/phase_10/premium_universe_eligibility"
CURRENT_SOURCE = VALIDATION_ROOT / "secret_lair_structural_candidates_2026-07-22.csv"
OUTPUT = VALIDATION_ROOT / "secret_lair_official_archive_inventory.csv"
MISSING_OUTPUT = VALIDATION_ROOT / "secret_lair_official_missing_from_candidates.csv"
SUMMARY_OUTPUT = VALIDATION_ROOT / "secret_lair_official_archive_summary.csv"
CACHE_ROOT = VALIDATION_ROOT / "official_secret_lair_cache"

START_URL = "https://secretlair.wizards.com/us/en/past-sales"
ALLOWED_HOST = "secretlair.wizards.com"
MAX_PAGES = 600
REQUEST_DELAY_SECONDS = 0.35
USER_AGENT = "Mozilla/5.0 (compatible; MTGInvestmentTerminal/1.0; +https://github.com/dlockar1mtg/mtg-investment-terminal)"


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.text_parts: list[str] = []
        self._capture_title = False
        self._capture_h1 = False
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "a" and attrs_dict.get("href"):
            self.links.append(str(attrs_dict["href"]))
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


def cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return CACHE_ROOT / f"{digest}.html"


def fetch(url: str) -> str:
    path = cache_path(url)
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = response.read().decode("utf-8", errors="replace")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    time.sleep(REQUEST_DELAY_SECONDS)
    return payload


def normalize_url(base_url: str, href: str) -> str | None:
    absolute = urllib.parse.urljoin(base_url, html.unescape(href))
    parsed = urllib.parse.urlsplit(absolute)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != ALLOWED_HOST:
        return None
    path = re.sub(r"/+", "/", parsed.path)
    if not path.startswith("/us/en/"):
        return None
    if not (path == "/us/en/past-sales" or path.startswith("/us/en/product/")):
        return None
    return urllib.parse.urlunsplit(("https", ALLOWED_HOST, path.rstrip("/"), "", ""))


def identify_finish(name: str) -> str:
    value = norm(name)
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
    if "traditional foil" in value or "foil edition" in value or value.endswith(" foil"):
        return "traditional_foil"
    if "non foil" in value or "nonfoil" in value:
        return "non_foil"
    return "unspecified"


def identify_packaging(name: str, page_text: str) -> str:
    value = norm(f"{name} {page_text[:1000]}")
    if "commander deck" in value or "deck" in norm(name):
        return "deck"
    if "bundle" in norm(name):
        return "bundle"
    if "countdown kit" in value or " kit " in f" {norm(name)} ":
        return "kit"
    return "individual_drop"


def extract_product_id(url: str) -> str:
    match = re.search(r"/product/(\d+)/", url)
    return match.group(1) if match else ""


def read_current_candidates() -> list[dict[str, str]]:
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


def main() -> None:
    candidates = read_current_candidates()
    candidate_names = {
        norm(row.get("canonical_product_name"))
        for row in candidates
        if norm(row.get("canonical_product_name"))
    }

    queue: deque[str] = deque([START_URL])
    visited: set[str] = set()
    product_rows: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []

    while queue and len(visited) < MAX_PAGES:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        try:
            payload = fetch(url)
        except Exception as exc:  # noqa: BLE001
            failures.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
            continue

        parser = PageParser()
        parser.feed(payload)
        for href in parser.links:
            normalized = normalize_url(url, href)
            if normalized and normalized not in visited:
                queue.append(normalized)

        if "/product/" not in urllib.parse.urlsplit(url).path:
            continue

        page_text = clean(" ".join(parser.text_parts))
        title = clean(" ".join(parser.h1_parts)) or clean(" ".join(parser.title_parts))
        title = re.sub(r"\s*\|\s*Secret Lair.*$", "", title, flags=re.I).strip()
        if not title:
            continue

        normalized_title = norm(title)
        candidate_status = (
            "IN_CURRENT_CANDIDATES"
            if normalized_title in candidate_names
            else "MISSING_FROM_CURRENT_CANDIDATES"
        )
        product_rows.append(
            {
                "official_product_id": extract_product_id(url),
                "official_product_name": title,
                "normalized_product_name": normalized_title,
                "finish": identify_finish(title),
                "packaging_level": identify_packaging(title, page_text),
                "official_product_url": url,
                "candidate_status": candidate_status,
                "matched_by_name": normalized_title in candidate_names,
                "page_mentions_contents": " contents " in f" {norm(page_text)} ",
                "page_text_preview": page_text[:500],
            }
        )

    deduped: dict[str, dict[str, object]] = {}
    for row in product_rows:
        key = str(row["official_product_id"] or row["official_product_url"])
        deduped.setdefault(key, row)

    rows = sorted(
        deduped.values(),
        key=lambda row: (str(row["packaging_level"]), str(row["official_product_name"])),
    )
    missing = [row for row in rows if row["candidate_status"] == "MISSING_FROM_CURRENT_CANDIDATES"]

    fields = [
        "official_product_id",
        "official_product_name",
        "normalized_product_name",
        "finish",
        "packaging_level",
        "official_product_url",
        "candidate_status",
        "matched_by_name",
        "page_mentions_contents",
        "page_text_preview",
    ]
    write_csv(OUTPUT, rows, fields)
    write_csv(MISSING_OUTPUT, missing, fields)

    summary = [
        {"metric": "current_candidate_rows", "value": len(candidates)},
        {"metric": "official_product_pages", "value": len(rows)},
        {"metric": "missing_from_current_candidates", "value": len(missing)},
        {"metric": "pages_visited", "value": len(visited)},
        {"metric": "fetch_failures", "value": len(failures)},
    ]
    for packaging in sorted({str(row["packaging_level"]) for row in rows}):
        summary.append({
            "metric": f"packaging_{packaging}",
            "value": sum(1 for row in rows if row["packaging_level"] == packaging),
        })
    for finish in sorted({str(row["finish"]) for row in rows}):
        summary.append({
            "metric": f"finish_{finish}",
            "value": sum(1 for row in rows if row["finish"] == finish),
        })
    write_csv(SUMMARY_OUTPUT, summary, ["metric", "value"])

    if failures:
        (VALIDATION_ROOT / "secret_lair_official_archive_failures.json").write_text(
            json.dumps(failures, indent=2), encoding="utf-8"
        )

    print("SECRET LAIR OFFICIAL ARCHIVE CRAWL: COMPLETE")
    print(f"Current candidate rows: {len(candidates)}")
    print(f"Official product pages: {len(rows)}")
    print(f"Missing from current candidates: {len(missing)}")
    print(f"Pages visited: {len(visited)}")
    print(f"Fetch failures: {len(failures)}")
    print(f"Inventory: {OUTPUT.relative_to(ROOT)}")
    print(f"Missing: {MISSING_OUTPUT.relative_to(ROOT)}")
    print(f"Summary: {SUMMARY_OUTPUT.relative_to(ROOT)}")
    print("Active eBay universe source was not changed.")


if __name__ == "__main__":
    main()
