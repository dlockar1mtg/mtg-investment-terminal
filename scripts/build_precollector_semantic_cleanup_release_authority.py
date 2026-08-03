from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_semantic_cleanup_release_authority_contract_v1.json"
RECONCILIATION_SCRIPT = ROOT / "scripts/build_precollector_universe_reconciliation.py"
RECONCILIATION_OUTPUT = ROOT / "artifacts/precollector/universe_reconciliation"
OUTPUT_DIR = ROOT / "artifacts/precollector/semantic_cleanup_release_authority"
MTGJSON_SETLIST_URL = "https://mtgjson.com/api/v5/SetList.json"
USER_AGENT = "UIP-MTG-PreCollector-Reconciliation/1.0"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def normalize(value: object) -> str:
    text = str(value or "").casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def ensure_reconciliation_outputs() -> None:
    required = RECONCILIATION_OUTPUT / "precollector_reconciled_candidate_universe.csv"
    if required.exists():
        return
    spec = importlib.util.spec_from_file_location("precollector_reconciliation", RECONCILIATION_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("RECONCILIATION_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.main()
    if result != 0 or not required.exists():
        raise RuntimeError("RECONCILIATION_REBUILD_FAILED")


def semantic_classification(product_name: object) -> tuple[str, str]:
    name = normalize(product_name)
    if not name:
        return "REQUIRES_IDENTITY_REVIEW", "BLANK_PRODUCT_NAME"
    if "booster box case" in name or re.search(r"\bcase\b", name):
        return "EXCLUDED_CONFIGURATION", "BOOSTER_BOX_CASE"
    forbidden_displays = (
        "theme booster display",
        "planeswalker deck display",
        "battle pack display",
        "starter deck display",
        "commander deck display",
        "deck display",
    )
    if any(term in name for term in forbidden_displays):
        return "EXCLUDED_CONFIGURATION", "NON_BOOSTER_DISPLAY"
    if "booster box" in name or "booster display" in name:
        return "SEMANTIC_CANDIDATE", "INDIVIDUAL_BOOSTER_BOX"
    return "REQUIRES_IDENTITY_REVIEW", "BOOSTER_BOX_IDENTITY_UNCLEAR"


def fetch_mtgjson_setlist() -> tuple[pd.DataFrame, dict]:
    request = Request(MTGJSON_SETLIST_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=180) as response:
        payload = response.read()
    raw = json.loads(payload.decode("utf-8-sig"))
    rows = raw.get("data", raw if isinstance(raw, list) else [])
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("MTGJSON_SETLIST_EMPTY")
    frame = pd.DataFrame(rows)
    name_col = next((c for c in ("name", "setName") if c in frame.columns), None)
    date_col = next((c for c in ("releaseDate", "release_date") if c in frame.columns), None)
    code_col = next((c for c in ("code", "keyruneCode") if c in frame.columns), None)
    if not name_col or not date_col:
        raise RuntimeError("MTGJSON_SETLIST_SEMANTICS_MISSING")
    authority = pd.DataFrame({
        "secondary_release_name": frame[name_col].fillna("").astype(str),
        "secondary_release_date": frame[date_col].fillna("").astype(str),
        "secondary_set_code": frame[code_col].fillna("").astype(str) if code_col else "",
    })
    authority["normalized_release_key"] = authority["secondary_release_name"].map(normalize)
    authority = authority[
        authority["secondary_release_name"].str.strip().ne("")
        & authority["secondary_release_date"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)
    ].drop_duplicates(["normalized_release_key", "secondary_release_date"])
    manifest = {
        "source_url": MTGJSON_SETLIST_URL,
        "sha256": sha256_bytes(payload),
        "bytes": len(payload),
        "rows": len(authority),
    }
    return authority, manifest


def build_release_authority(reconciled: pd.DataFrame, mtgjson: pd.DataFrame) -> pd.DataFrame:
    frame = reconciled.copy()
    group_col = "reconciliation_group_name"
    if group_col not in frame.columns:
        raise RuntimeError("RECONCILIATION_GROUP_NAME_MISSING")
    frame["normalized_release_key"] = frame[group_col].map(normalize)
    frame = frame.merge(mtgjson, on="normalized_release_key", how="left")

    wizards_date = frame.get("official_release_date", pd.Series(index=frame.index, dtype="object"))
    secondary_date = frame.get("secondary_release_date", pd.Series(index=frame.index, dtype="object"))
    frame["release_date_authority"] = "UNRESOLVED"
    frame["governed_release_date"] = ""
    frame.loc[wizards_date.notna() & wizards_date.astype(str).str.strip().ne(""), "release_date_authority"] = "WIZARDS_OFFICIAL"
    frame.loc[wizards_date.notna() & wizards_date.astype(str).str.strip().ne(""), "governed_release_date"] = wizards_date.astype(str)

    secondary_only = (
        frame["release_date_authority"].eq("UNRESOLVED")
        & secondary_date.notna()
        & secondary_date.astype(str).str.strip().ne("")
    )
    frame.loc[secondary_only, "release_date_authority"] = "MTGJSON_SECONDARY"
    frame.loc[secondary_only, "governed_release_date"] = secondary_date.astype(str)

    conflict = (
        wizards_date.notna()
        & secondary_date.notna()
        & wizards_date.astype(str).str.strip().ne("")
        & secondary_date.astype(str).str.strip().ne("")
        & wizards_date.astype(str).ne(secondary_date.astype(str))
    )
    frame["release_date_conflict_indicator"] = conflict
    frame.loc[conflict, "release_date_authority"] = "SOURCE_CONFLICT"
    frame.loc[conflict, "governed_release_date"] = ""
    return frame


def validate_outputs(owner_review: pd.DataFrame, excluded: pd.DataFrame) -> None:
    if owner_review.empty:
        raise RuntimeError("OWNER_REVIEW_UNIVERSE_EMPTY")
    if owner_review["semantic_status"].eq("EXCLUDED_CONFIGURATION").any():
        raise RuntimeError("EXCLUDED_CONFIGURATION_IN_OWNER_REVIEW")
    names = owner_review["product_name_august1"].fillna("").str.casefold()
    if names.str.contains(r"\bcase\b", regex=True).any():
        raise RuntimeError("CASE_PRODUCT_IN_OWNER_REVIEW")
    if excluded.empty:
        raise RuntimeError("EXPECTED_CONFIGURATION_EXCLUSIONS_MISSING")
    if owner_review["semantic_reason"].fillna("").str.strip().eq("").any():
        raise RuntimeError("BLANK_SEMANTIC_REASON")


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    ensure_reconciliation_outputs()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    reconciled = pd.read_csv(RECONCILIATION_OUTPUT / "precollector_reconciled_candidate_universe.csv", low_memory=False)
    delta = pd.read_csv(RECONCILIATION_OUTPUT / "precollector_missing_from_august1.csv", low_memory=False)
    if len(reconciled) != 186:
        raise RuntimeError(f"RECONCILED_CANDIDATE_COUNT_DRIFT: {len(reconciled)}")

    decisions = reconciled["product_name_august1"].map(semantic_classification)
    reconciled["semantic_status"] = [item[0] for item in decisions]
    reconciled["semantic_reason"] = [item[1] for item in decisions]

    mtgjson, mtgjson_manifest = fetch_mtgjson_setlist()
    authority = build_release_authority(reconciled, mtgjson)

    excluded = authority[authority["semantic_status"].eq("EXCLUDED_CONFIGURATION")].copy()
    semantic_candidates = authority[authority["semantic_status"].eq("SEMANTIC_CANDIDATE")].copy()
    identity_review = authority[authority["semantic_status"].eq("REQUIRES_IDENTITY_REVIEW")].copy()

    semantic_candidates["owner_review_status"] = "READY_FOR_OWNER_REVIEW"
    semantic_candidates.loc[
        semantic_candidates["release_date_authority"].eq("UNRESOLVED"),
        "owner_review_status",
    ] = "REQUIRES_RELEASE_DATE_REVIEW"
    semantic_candidates.loc[
        semantic_candidates["release_date_authority"].eq("SOURCE_CONFLICT"),
        "owner_review_status",
    ] = "SOURCE_CONFLICT"

    owner_review = pd.concat([semantic_candidates, identity_review], ignore_index=True, sort=False)
    owner_review.loc[
        owner_review["semantic_status"].eq("REQUIRES_IDENTITY_REVIEW"),
        "owner_review_status",
    ] = "REQUIRES_IDENTITY_REVIEW"

    delta_decisions = delta.get("product_name", pd.Series(index=delta.index, dtype="object")).map(semantic_classification)
    delta["scope_review_status"] = [item[0] for item in delta_decisions]
    delta["scope_review_reason"] = [item[1] for item in delta_decisions]

    validate_outputs(owner_review, excluded)

    date_review = owner_review[owner_review["owner_review_status"].eq("REQUIRES_RELEASE_DATE_REVIEW")].copy()
    conflicts = owner_review[owner_review["owner_review_status"].eq("SOURCE_CONFLICT")].copy()

    outputs = contract["outputs"]
    authority.to_csv(OUTPUT_DIR / outputs["semantic_review_csv"], index=False)
    excluded.to_csv(OUTPUT_DIR / outputs["excluded_configuration_csv"], index=False)
    authority[[
        "canonical_product_id", "reconciliation_group_name", "normalized_release_key",
        "official_release_date", "secondary_release_name", "secondary_release_date",
        "release_date_authority", "governed_release_date", "release_date_conflict_indicator",
    ]].to_csv(OUTPUT_DIR / outputs["release_authority_csv"], index=False)
    owner_review.to_csv(OUTPUT_DIR / outputs["owner_review_csv"], index=False)
    date_review.to_csv(OUTPUT_DIR / outputs["date_review_csv"], index=False)
    conflicts.to_csv(OUTPUT_DIR / outputs["date_conflict_csv"], index=False)
    delta.to_csv(OUTPUT_DIR / outputs["fresh_delta_review_csv"], index=False)

    summary = {
        "certification_status": "PASS_PRECOLLECTOR_SEMANTIC_CLEANUP_RELEASE_AUTHORITY_BUILD",
        "contract_id": contract["contract_id"],
        "contract_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_reconciled_candidates": len(reconciled),
        "semantic_candidates": len(semantic_candidates),
        "excluded_configurations": len(excluded),
        "identity_review_rows": len(identity_review),
        "owner_review_rows": len(owner_review),
        "wizards_date_rows": int(authority["release_date_authority"].eq("WIZARDS_OFFICIAL").sum()),
        "mtgjson_secondary_date_rows": int(authority["release_date_authority"].eq("MTGJSON_SECONDARY").sum()),
        "release_date_review_rows": len(date_review),
        "release_date_conflict_rows": len(conflicts),
        "fresh_delta_rows": len(delta),
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
        "next_stage": contract["next_stage_if_certified"],
    }
    (OUTPUT_DIR / outputs["summary_json"]).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "mtgjson": mtgjson_manifest,
        "reconciliation_input": "artifacts/precollector/universe_reconciliation/precollector_reconciled_candidate_universe.csv",
        "source_hierarchy": contract["source_hierarchy"],
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_SEMANTIC_CLEANUP_RELEASE_AUTHORITY_BUILD")
    for key in (
        "input_reconciled_candidates", "semantic_candidates", "excluded_configurations",
        "identity_review_rows", "owner_review_rows", "wizards_date_rows",
        "mtgjson_secondary_date_rows", "release_date_review_rows",
        "release_date_conflict_rows", "fresh_delta_rows",
    ):
        print(f"{key.upper()}={summary[key]}")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
