from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = ROOT / "scripts/build_precollector_final_universe_resolution.py"
PRODUCT_AUTHORITY_PATH = ROOT / "config/mtg/governance/precollector_product_specific_release_authority_v1.json"
MTGJSON_SETLIST_URL = "https://mtgjson.com/api/v5/SetList.json"
USER_AGENT = "UIP-MTG-PreCollector-Final-Universe/1.0"

SPEC = importlib.util.spec_from_file_location("final_universe_resolution_impl", IMPLEMENTATION)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("FINAL_UNIVERSE_RESOLUTION_IMPORT_FAILED")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def normalize(value: object) -> str:
    text = str(value or "").casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_full_mtgjson_setlist() -> pd.DataFrame:
    request = Request(MTGJSON_SETLIST_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=180) as response:
        payload = json.loads(response.read().decode("utf-8-sig"))
    rows = payload.get("data", [])
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("FULL_MTGJSON_SETLIST_EMPTY")
    frame = pd.DataFrame(rows)
    required = {"name", "releaseDate"}
    if not required.issubset(frame.columns):
        raise RuntimeError("FULL_MTGJSON_SETLIST_SEMANTICS_MISSING")
    result = pd.DataFrame({
        "secondary_release_name": frame["name"].fillna("").astype(str),
        "secondary_release_date": frame["releaseDate"].fillna("").astype(str),
        "secondary_set_code": frame["code"].fillna("").astype(str) if "code" in frame.columns else "",
    })
    result["target_key"] = result["secondary_release_name"].map(normalize)
    return result[result["secondary_release_date"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)].copy()


def resolve_alias_dates(owner: pd.DataFrame, alias_authority: dict, ignored_extract: pd.DataFrame):
    frame = owner.copy()
    alias_rows = pd.DataFrame(alias_authority["aliases"])
    alias_rows["source_key"] = alias_rows["source_release_name"].map(normalize)
    alias_rows["target_key"] = alias_rows["authoritative_release_name"].map(normalize)
    full_setlist = fetch_full_mtgjson_setlist().sort_values(["target_key", "secondary_release_date"]).drop_duplicates("target_key", keep="first")
    alias_rows = alias_rows.merge(
        full_setlist[["target_key", "secondary_release_name", "secondary_release_date", "secondary_set_code"]],
        on="target_key", how="left",
    )
    alias_map = alias_rows.set_index("source_key").to_dict("index")
    for idx, row in frame.iterrows():
        if str(row.get("owner_review_status", "")) != "REQUIRES_RELEASE_DATE_REVIEW":
            continue
        source_key = normalize(row.get("release_or_group_name", row.get("reconciliation_group_name", "")))
        alias = alias_map.get(source_key)
        if alias and alias.get("authority_type") == "MTGJSON_NAME_ALIAS" and str(alias.get("secondary_release_date", "")).strip():
            frame.at[idx, "secondary_release_name"] = alias.get("secondary_release_name", "")
            frame.at[idx, "secondary_release_date"] = alias.get("secondary_release_date", "")
            frame.at[idx, "secondary_set_code"] = alias.get("secondary_set_code", "")
            frame.at[idx, "release_date_authority"] = "MTGJSON_SECONDARY_ALIAS"
            frame.at[idx, "governed_release_date"] = alias.get("secondary_release_date", "")
            frame.at[idx, "owner_review_status"] = "READY_FOR_OWNER_REVIEW"
    return frame, alias_rows


def resolve_mystery_product_dates(owner: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    frame = owner.copy()
    authority = json.loads(PRODUCT_AUTHORITY_PATH.read_text(encoding="utf-8"))
    records = {row["canonical_product_id"]: row for row in authority["records"]}
    for idx, row in frame.iterrows():
        record = records.get(str(row.get("canonical_product_id", "")))
        if not record:
            continue
        frame.at[idx, "release_date_authority"] = record["authority_type"]
        frame.at[idx, "governed_release_date"] = record["governed_release_date"]
        frame.at[idx, "owner_review_status"] = "READY_FOR_OWNER_REVIEW"
    return frame


def classify_fresh_delta(delta: pd.DataFrame, full_fresh: pd.DataFrame) -> pd.DataFrame:
    frame = MODULE.classify_fresh_delta(delta, full_fresh)
    names = frame["product_name"].fillna("").str.casefold()
    foreign = names.str.contains(r"\b(french|german|italian|spanish|portuguese|japanese|korean|russian|chinese)\b", regex=True)
    frame.loc[foreign, "fresh_resolution_status"] = "OWNER_EXCLUSION_RECOMMENDED"
    frame.loc[foreign, "fresh_resolution_reason"] = "NON_ENGLISH_PRODUCT"
    return frame


def strict_validate(resolved: pd.DataFrame, fresh_resolution: pd.DataFrame) -> None:
    status_columns = [i for i, name in enumerate(resolved.columns) if name == "owner_review_status"]
    if not status_columns:
        raise RuntimeError("OWNER_DECISION_STATUS_MISSING")
    final_status = resolved.iloc[:, status_columns[-1]].astype(str)
    ready_mask = final_status.eq("OWNER_APPROVAL_READY")
    ready = resolved.loc[ready_mask]
    if ready.empty:
        raise RuntimeError("OWNER_APPROVAL_READY_UNIVERSE_EMPTY")
    if ready["governed_release_date"].fillna("").str.strip().eq("").any():
        raise RuntimeError("BLANK_RELEASE_DATE_IN_OWNER_APPROVAL_READY")
    if fresh_resolution["fresh_resolution_status"].ne("OWNER_EXCLUSION_RECOMMENDED").any():
        raise RuntimeError("FRESH_DELTA_REVIEW_REMAINS")


MODULE.resolve_alias_dates = resolve_alias_dates
MODULE.resolve_mystery_product_dates = resolve_mystery_product_dates
MODULE.classify_fresh_delta = classify_fresh_delta
MODULE.validate = strict_validate

if __name__ == "__main__":
    raise SystemExit(MODULE.main())
