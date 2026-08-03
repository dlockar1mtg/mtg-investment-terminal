from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_universe_reconciliation_contract_v1.json"
CANDIDATE_BUILDER = ROOT / "scripts/build_precollector_candidate_universe.py"
OUTPUT_DIR = ROOT / "artifacts/precollector/universe_reconciliation"
CANDIDATE_OUTPUT_DIR = ROOT / "artifacts/precollector/candidate_universe"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_bytes(url: str, user_agent: str, timeout: int = 90) -> bytes:
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json,text/html,*/*"})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def extract_rows(payload: object, keys: tuple[str, ...]) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in keys:
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def first_value(row: dict, names: tuple[str, ...]) -> object:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def normalize(value: object) -> str:
    text = html.unescape(str(value or "")).casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def candidate_key(name: object) -> str:
    text = normalize(name)
    removals = (
        "magic the gathering", "mtg", "factory sealed", "sealed", "english",
        "booster display box", "booster display", "display box", "booster box",
    )
    for phrase in removals:
        text = re.sub(rf"\b{re.escape(phrase)}\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def ensure_candidate_inventory() -> pd.DataFrame:
    included = CANDIDATE_OUTPUT_DIR / "precollector_included_candidate_universe.csv"
    if not included.exists():
        import subprocess
        result = subprocess.run([sys.executable, str(CANDIDATE_BUILDER)], cwd=ROOT, check=False)
        if result.returncode != 0:
            raise RuntimeError("CERTIFIED_CANDIDATE_UNIVERSE_REBUILD_FAILED")
    frame = pd.read_csv(included, low_memory=False)
    if frame.empty:
        raise RuntimeError("CERTIFIED_INCLUDED_CANDIDATE_UNIVERSE_EMPTY")
    return frame


def collect_fresh_tcgcsv(contract: dict) -> tuple[pd.DataFrame, dict]:
    source = contract["sources"]
    base = source["tcgcsv_base_url"].rstrip("/")
    category_id = int(source["tcgcsv_magic_category_id"])
    user_agent = source["user_agent"]
    delay = float(source["tcgcsv_request_delay_seconds"])

    groups_url = f"{base}/{category_id}/groups"
    groups_bytes = fetch_bytes(groups_url, user_agent)
    groups_payload = json.loads(groups_bytes.decode("utf-8-sig"))
    group_rows = extract_rows(groups_payload, ("results", "data", "groups"))
    if not group_rows:
        raise RuntimeError("FRESH_TCGCSV_GROUP_PULL_EMPTY")

    products: list[dict] = []
    failures: list[dict] = []
    raw_hashes: list[dict] = [{"source_url": groups_url, "sha256": sha256_bytes(groups_bytes), "row_type": "groups"}]

    for position, group in enumerate(group_rows, start=1):
        group_id = first_value(group, ("groupId", "group_id", "id"))
        group_name = first_value(group, ("name", "groupName", "group_name"))
        if group_id is None:
            failures.append({"group_id": None, "group_name": group_name, "reason": "MISSING_GROUP_ID"})
            continue
        url = f"{base}/{category_id}/{group_id}/products"
        try:
            payload_bytes = fetch_bytes(url, user_agent)
            payload = json.loads(payload_bytes.decode("utf-8-sig"))
            rows = extract_rows(payload, ("results", "data", "products"))
            raw_hashes.append({"source_url": url, "sha256": sha256_bytes(payload_bytes), "row_type": "products"})
            for row in rows:
                enriched = dict(row)
                enriched["reconciliation_group_id"] = str(group_id)
                enriched["reconciliation_group_name"] = str(group_name or "")
                enriched["reconciliation_source_url"] = url
                products.append(enriched)
        except Exception as exc:
            failures.append({"group_id": str(group_id), "group_name": str(group_name or ""), "reason": type(exc).__name__, "detail": str(exc)[:500]})
        if position < len(group_rows):
            time.sleep(delay)

    if failures:
        failure_path = OUTPUT_DIR / "tcgcsv_group_pull_failures.csv"
        pd.DataFrame(failures).to_csv(failure_path, index=False)
        raise RuntimeError(f"FRESH_TCGCSV_GROUP_PULL_INCOMPLETE: {len(failures)} groups failed")
    if not products:
        raise RuntimeError("FRESH_TCGCSV_PRODUCT_PULL_EMPTY")

    frame = pd.DataFrame(products)
    product_id_col = next((c for c in ("productId", "product_id", "id") if c in frame.columns), None)
    product_name_col = next((c for c in ("name", "productName", "product_name") if c in frame.columns), None)
    if not product_id_col or not product_name_col:
        raise RuntimeError("FRESH_TCGCSV_PRODUCT_SEMANTICS_MISSING")
    frame["canonical_product_id"] = "tcgplayer:" + frame[product_id_col].astype(str)
    frame["product_name"] = frame[product_name_col].fillna("").astype(str)
    frame["normalized_candidate_key"] = frame["product_name"].map(candidate_key)
    manifest = {
        "groups_url": groups_url,
        "group_count": len(group_rows),
        "product_count": len(frame),
        "raw_source_hashes": raw_hashes,
    }
    return frame, manifest


def strip_html(source: str) -> str:
    source = re.sub(r"<script\b[^>]*>.*?</script>", " ", source, flags=re.I | re.S)
    source = re.sub(r"<style\b[^>]*>.*?</style>", " ", source, flags=re.I | re.S)
    source = re.sub(r"<[^>]+>", "\n", source)
    source = html.unescape(source)
    lines = [re.sub(r"\s+", " ", line).strip() for line in source.splitlines()]
    return "\n".join(line for line in lines if line)


def collect_wizards_release_authority(contract: dict) -> tuple[pd.DataFrame, dict]:
    user_agent = contract["sources"]["user_agent"]
    urls = [contract["sources"]["wizards_archive_url"], contract["sources"]["wizards_products_url"]]
    records: list[dict] = []
    source_manifest: list[dict] = []
    month_pattern = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}"

    for url in urls:
        payload = fetch_bytes(url, user_agent)
        source_manifest.append({"source_url": url, "sha256": sha256_bytes(payload), "bytes": len(payload)})
        text = strip_html(payload.decode("utf-8", errors="replace"))
        patterns = [
            re.compile(rf"Set Name\s+(.+?)\s+Release Date\s+({month_pattern})", re.I),
            re.compile(rf"({month_pattern})\s+([^\n]+)", re.I),
        ]
        for pattern_index, pattern in enumerate(patterns):
            for match in pattern.finditer(text):
                if pattern_index == 0:
                    release_name, date_text = match.group(1), match.group(2)
                else:
                    date_text, release_name = match.group(1), match.group(2)
                release_name = re.sub(r"\s+(Image)+.*$", "", release_name, flags=re.I).strip()
                parsed = pd.to_datetime(date_text, errors="coerce")
                if not release_name or pd.isna(parsed):
                    continue
                records.append({
                    "wizards_release_name": release_name,
                    "normalized_release_key": normalize(release_name),
                    "official_release_date": parsed.date().isoformat(),
                    "wizards_source_url": url,
                    "extraction_pattern": f"pattern_{pattern_index + 1}",
                })

    frame = pd.DataFrame(records)
    if frame.empty:
        raise RuntimeError("WIZARDS_RELEASE_AUTHORITY_EXTRACTION_EMPTY")
    frame = frame.drop_duplicates(["normalized_release_key", "official_release_date", "wizards_source_url"])
    conflicting = frame.groupby("normalized_release_key")["official_release_date"].nunique()
    conflict_keys = set(conflicting[conflicting > 1].index)
    frame["wizards_date_conflict_indicator"] = frame["normalized_release_key"].isin(conflict_keys)
    return frame.sort_values(["official_release_date", "wizards_release_name"]), {"sources": source_manifest, "records": len(frame)}


def reconcile(existing: pd.DataFrame, fresh: pd.DataFrame, wizards: pd.DataFrame) -> dict[str, pd.DataFrame]:
    existing = existing.copy()
    existing["normalized_candidate_key"] = existing["product_name"].map(candidate_key)
    fresh_ids = set(fresh["canonical_product_id"].astype(str))
    existing_ids = set(existing["canonical_product_id"].astype(str))

    fresh_box_mask = fresh["product_name"].str.casefold().str.contains("booster box|display box", regex=True, na=False)
    fresh_box = fresh[fresh_box_mask].copy()

    existing_review = existing.merge(
        fresh[["canonical_product_id", "product_name", "reconciliation_group_id", "reconciliation_group_name", "reconciliation_source_url"]],
        on="canonical_product_id", how="left", suffixes=("_august1", "_fresh"), indicator=True,
    )
    existing_review["fresh_catalog_status"] = existing_review["_merge"].map({"both": "PRESENT", "left_only": "MISSING", "right_only": "UNEXPECTED"})

    delta = pd.DataFrame({
        "canonical_product_id": sorted(existing_ids | fresh_ids),
    })
    delta["august1_present"] = delta["canonical_product_id"].isin(existing_ids)
    delta["fresh_present"] = delta["canonical_product_id"].isin(fresh_ids)
    delta["delta_status"] = delta.apply(lambda r: "UNCHANGED_MEMBERSHIP" if r.august1_present and r.fresh_present else "ADDED_SINCE_AUGUST1" if r.fresh_present else "MISSING_FROM_FRESH", axis=1)

    missing_august = fresh_box[~fresh_box["canonical_product_id"].isin(existing_ids)].copy()
    missing_fresh = existing[~existing["canonical_product_id"].isin(fresh_ids)].copy()

    wizard_unique = wizards.sort_values("wizards_source_url").drop_duplicates("normalized_release_key", keep=False)
    crosswalk = existing_review.copy()
    crosswalk["normalized_release_key"] = crosswalk["reconciliation_group_name"].map(normalize)
    crosswalk = crosswalk.merge(
        wizard_unique[["normalized_release_key", "wizards_release_name", "official_release_date", "wizards_source_url", "wizards_date_conflict_indicator"]],
        on="normalized_release_key", how="left",
    )

    crosswalk["reconciliation_status"] = "REQUIRES_RELEASE_DATE_REVIEW"
    crosswalk.loc[crosswalk["fresh_catalog_status"].eq("MISSING"), "reconciliation_status"] = "SOURCE_CONFLICT"
    crosswalk.loc[crosswalk["official_release_date"].notna(), "reconciliation_status"] = "CANONICAL_INCLUDED"
    crosswalk.loc[crosswalk["wizards_date_conflict_indicator"].fillna(False), "reconciliation_status"] = "SOURCE_CONFLICT"

    duplicate_keys = crosswalk[crosswalk["normalized_candidate_key"].ne("")].groupby("normalized_candidate_key")["canonical_product_id"].nunique()
    duplicate_keys = set(duplicate_keys[duplicate_keys > 1].index)
    duplicate_review = crosswalk[crosswalk["normalized_candidate_key"].isin(duplicate_keys)].copy()
    crosswalk.loc[crosswalk["normalized_candidate_key"].isin(duplicate_keys), "reconciliation_status"] = "DUPLICATE_LISTING"

    format_pattern = r"collector booster|draft booster|play booster"
    format_conflicts = crosswalk[
        crosswalk["product_name_august1"].fillna("").str.casefold().str.contains(format_pattern, regex=True)
        | crosswalk["product_name_fresh"].fillna("").str.casefold().str.contains(format_pattern, regex=True)
    ].copy()
    if not format_conflicts.empty:
        crosswalk.loc[crosswalk["canonical_product_id"].isin(format_conflicts["canonical_product_id"]), "reconciliation_status"] = "REQUIRES_FORMAT_REVIEW"

    date_conflicts = crosswalk[crosswalk["wizards_date_conflict_indicator"].fillna(False)].copy()
    reconciled = crosswalk.copy()

    return {
        "precollector_existing_candidate_review.csv": existing_review,
        "precollector_fresh_tcgcsv_products.csv": fresh,
        "precollector_tcgcsv_snapshot_delta.csv": delta,
        "precollector_wizards_release_authority.csv": wizards,
        "precollector_product_release_crosswalk.csv": crosswalk,
        "precollector_missing_from_august1.csv": missing_august,
        "precollector_missing_from_fresh_tcg.csv": missing_fresh,
        "precollector_release_date_conflicts.csv": date_conflicts,
        "precollector_format_conflicts.csv": format_conflicts,
        "precollector_duplicate_asset_review.csv": duplicate_review,
        "precollector_reconciled_candidate_universe.csv": reconciled,
    }


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    certified_source = ROOT / contract["sources"]["certified_august1_products"]
    if sha256_file(certified_source) != contract["sources"]["certified_august1_sha256"]:
        raise RuntimeError("CERTIFIED_AUGUST1_SOURCE_HASH_DRIFT")

    existing = ensure_candidate_inventory()
    fresh, tcg_manifest = collect_fresh_tcgcsv(contract)
    wizards, wizards_manifest = collect_wizards_release_authority(contract)
    outputs = reconcile(existing, fresh, wizards)

    for filename, frame in outputs.items():
        frame.to_csv(OUTPUT_DIR / filename, index=False)

    reconciled = outputs["precollector_reconciled_candidate_universe.csv"]
    statuses = reconciled["reconciliation_status"].value_counts().to_dict()
    summary = {
        "certification_status": "PASS_PRECOLLECTOR_UNIVERSE_RECONCILIATION_BUILD",
        "contract_id": contract["contract_id"],
        "contract_version": contract["contract_version"],
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "existing_candidate_rows": len(existing),
        "fresh_tcgcsv_product_rows": len(fresh),
        "wizards_release_rows": len(wizards),
        "reconciled_candidate_rows": len(reconciled),
        "status_counts": {str(k): int(v) for k, v in statuses.items()},
        "missing_from_august1_rows": len(outputs["precollector_missing_from_august1.csv"]),
        "missing_from_fresh_tcg_rows": len(outputs["precollector_missing_from_fresh_tcg.csv"]),
        "release_date_conflict_rows": len(outputs["precollector_release_date_conflicts.csv"]),
        "format_conflict_rows": len(outputs["precollector_format_conflicts.csv"]),
        "duplicate_review_rows": len(outputs["precollector_duplicate_asset_review.csv"]),
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
        "next_stage": contract["next_stage_if_certified"],
    }
    (OUTPUT_DIR / "precollector_universe_reconciliation_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "certified_august1_source": {"path": certified_source.relative_to(ROOT).as_posix(), "sha256": sha256_file(certified_source)},
        "tcgcsv": tcg_manifest,
        "wizards": wizards_manifest,
        "outputs": [
            {"path": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in sorted(OUTPUT_DIR.iterdir()) if path.is_file()
        ],
    }
    (OUTPUT_DIR / "precollector_universe_reconciliation_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_UNIVERSE_RECONCILIATION_BUILD")
    print(f"EXISTING_CANDIDATES={len(existing)}")
    print(f"FRESH_TCGCSV_PRODUCTS={len(fresh)}")
    print(f"WIZARDS_RELEASE_ROWS={len(wizards)}")
    print(f"RECONCILED_CANDIDATES={len(reconciled)}")
    print(f"CANONICAL_INCLUDED={statuses.get('CANONICAL_INCLUDED', 0)}")
    print(f"REVIEW_OR_CONFLICT={len(reconciled) - statuses.get('CANONICAL_INCLUDED', 0)}")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
