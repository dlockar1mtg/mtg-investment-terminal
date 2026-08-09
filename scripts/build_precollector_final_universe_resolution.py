from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_final_universe_resolution_contract_v1.json"
ALIAS_PATH = ROOT / "config/mtg/governance/precollector_release_alias_authority_v1.json"
SEMANTIC_SCRIPT = ROOT / "scripts/build_precollector_semantic_cleanup_release_authority.py"
SEMANTIC_OUTPUT = ROOT / "artifacts/precollector/semantic_cleanup_release_authority"
RECON_OUTPUT = ROOT / "artifacts/precollector/universe_reconciliation"
OUTPUT_DIR = ROOT / "artifacts/precollector/final_universe_resolution"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(value: object) -> str:
    text = str(value or "").casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_semantic_outputs() -> None:
    required = SEMANTIC_OUTPUT / "precollector_owner_review_universe.csv"
    if required.exists():
        return
    spec = importlib.util.spec_from_file_location("semantic_cleanup", SEMANTIC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("SEMANTIC_CLEANUP_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.main() != 0 or not required.exists():
        raise RuntimeError("SEMANTIC_CLEANUP_REBUILD_FAILED")


def parse_product_release_date(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    payload = value
    if isinstance(value, str):
        try:
            payload = ast.literal_eval(value)
        except Exception:
            return ""
    if not isinstance(payload, dict):
        return ""
    released = payload.get("releasedOn")
    parsed = pd.to_datetime(released, errors="coerce", utc=True)
    return "" if pd.isna(parsed) else parsed.date().isoformat()


def resolve_alias_dates(owner: pd.DataFrame, alias_authority: dict, mtgjson: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = owner.copy()
    alias_rows = pd.DataFrame(alias_authority["aliases"])
    alias_rows["source_key"] = alias_rows["source_release_name"].map(normalize)
    alias_rows["target_key"] = alias_rows["authoritative_release_name"].map(normalize)
    mtg = mtgjson.copy()
    mtg["target_key"] = mtg["secondary_release_name"].map(normalize)
    mtg = mtg.sort_values(["target_key", "secondary_release_date"]).drop_duplicates("target_key", keep="first")
    alias_rows = alias_rows.merge(
        mtg[["target_key", "secondary_release_name", "secondary_release_date", "secondary_set_code"]],
        on="target_key", how="left",
    )

    alias_map = alias_rows.set_index("source_key").to_dict("index")
    for idx, row in frame.iterrows():
        if str(row.get("owner_review_status", "")) != "REQUIRES_RELEASE_DATE_REVIEW":
            continue
        source_key = normalize(row.get("release_or_group_name", row.get("reconciliation_group_name", "")))
        alias = alias_map.get(source_key)
        if not alias:
            continue
        if alias["authority_type"] == "MTGJSON_NAME_ALIAS" and str(alias.get("secondary_release_date", "")).strip():
            frame.at[idx, "secondary_release_name"] = alias.get("secondary_release_name", "")
            frame.at[idx, "secondary_release_date"] = alias.get("secondary_release_date", "")
            frame.at[idx, "secondary_set_code"] = alias.get("secondary_set_code", "")
            frame.at[idx, "release_date_authority"] = "MTGJSON_SECONDARY_ALIAS"
            frame.at[idx, "governed_release_date"] = alias.get("secondary_release_date", "")
            frame.at[idx, "owner_review_status"] = "READY_FOR_OWNER_REVIEW"

    unresolved_mystery = frame[
        frame["owner_review_status"].eq("REQUIRES_RELEASE_DATE_REVIEW")
        & frame["product_name_august1"].fillna("").str.contains("Mystery Booster", case=False, regex=False)
    ].copy()
    return frame, alias_rows


def resolve_mystery_product_dates(owner: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    frame = owner.copy()
    fresh_dates = fresh[["canonical_product_id", "presaleInfo"]].copy()
    fresh_dates["product_release_date"] = fresh_dates["presaleInfo"].map(parse_product_release_date)
    fresh_dates = fresh_dates.drop_duplicates("canonical_product_id")
    frame = frame.merge(fresh_dates[["canonical_product_id", "product_release_date"]], on="canonical_product_id", how="left")
    mask = (
        frame["owner_review_status"].eq("REQUIRES_RELEASE_DATE_REVIEW")
        & frame["product_name_august1"].fillna("").str.contains("Mystery Booster", case=False, regex=False)
        & frame["product_release_date"].fillna("").str.match(r"^\d{4}-\d{2}-\d{2}$")
    )
    frame.loc[mask, "release_date_authority"] = "TCGCSV_PRODUCT_RELEASE_SECONDARY"
    frame.loc[mask, "governed_release_date"] = frame.loc[mask, "product_release_date"]
    frame.loc[mask, "owner_review_status"] = "READY_FOR_OWNER_REVIEW"
    return frame


def classify_fresh_delta(delta: pd.DataFrame, full_fresh: pd.DataFrame) -> pd.DataFrame:
    frame = delta.copy()
    names = frame["product_name"].fillna("").astype(str)
    normalized = names.map(normalize)
    full_names = full_fresh["product_name"].fillna("").astype(str)
    collector_groups = set(
        full_fresh.loc[full_names.str.contains("collector booster", case=False, regex=False), "reconciliation_group_id"].astype(str)
    )
    frame["fresh_resolution_status"] = "OWNER_EXCLUSION_RECOMMENDED"
    frame["fresh_resolution_reason"] = "NOT_APPROVED_PRECOLLECTOR_FORMAT"
    frame["collector_option_indicator_reconciled"] = frame["reconciliation_group_id"].astype(str).isin(collector_groups)

    case_mask = normalized.str.contains(r"\bcase\b", regex=True)
    collector_mask = normalized.str.contains("collector booster", regex=False)
    draft_mask = normalized.str.contains("draft booster", regex=False)
    play_mask = normalized.str.contains("play booster", regex=False)
    non_booster_display = normalized.str.contains("theme booster display|deck display|battle pack display", regex=True)
    box_mask = normalized.str.contains("booster box|booster display", regex=True)

    frame.loc[case_mask, "fresh_resolution_reason"] = "BOOSTER_BOX_CASE"
    frame.loc[collector_mask, "fresh_resolution_reason"] = "COLLECTOR_BOOSTER_PRODUCT"
    frame.loc[draft_mask, "fresh_resolution_reason"] = "DRAFT_BOOSTER_PRODUCT"
    frame.loc[play_mask, "fresh_resolution_reason"] = "PLAY_BOOSTER_PRODUCT"
    frame.loc[non_booster_display, "fresh_resolution_reason"] = "NON_BOOSTER_DISPLAY"

    candidate = box_mask & ~case_mask & ~collector_mask & ~draft_mask & ~play_mask & ~non_booster_display
    collector_option = candidate & frame["collector_option_indicator_reconciled"]
    frame.loc[collector_option, "fresh_resolution_reason"] = "RELEASE_HAS_COLLECTOR_OPTION"
    candidate = candidate & ~frame["collector_option_indicator_reconciled"]
    frame.loc[candidate, "fresh_resolution_status"] = "REQUIRES_FORMAT_REVIEW"
    frame.loc[candidate, "fresh_resolution_reason"] = "FRESH_ONLY_BOX_REQUIRES_OWNER_AND_FORMAT_CONFIRMATION"
    return frame


def deduplicate_existing(owner: pd.DataFrame) -> pd.DataFrame:
    frame = owner.copy()
    frame["governed_asset_key"] = (
        frame["release_or_group_name"].map(normalize)
        + "|"
        + frame["product_name_august1"].map(normalize)
    )
    duplicates = frame.groupby("governed_asset_key")["canonical_product_id"].transform("nunique").gt(1)
    frame.loc[duplicates, "owner_review_status"] = "DUPLICATE_LISTING"
    return frame


def validate(resolved: pd.DataFrame, fresh_resolution: pd.DataFrame) -> None:
    names = resolved["product_name_august1"].fillna("").str.casefold()
    ready = resolved[resolved["owner_review_status"].eq("OWNER_APPROVAL_READY")]
    if ready.empty:
        raise RuntimeError("OWNER_APPROVAL_READY_UNIVERSE_EMPTY")
    if names[resolved["owner_review_status"].eq("OWNER_APPROVAL_READY")].str.contains(r"\bcase\b", regex=True).any():
        raise RuntimeError("CASE_IN_OWNER_APPROVAL_READY")
    if ready["governed_release_date"].fillna("").str.strip().eq("").any():
        raise RuntimeError("BLANK_RELEASE_DATE_IN_OWNER_APPROVAL_READY")
    prohibited = fresh_resolution[
        fresh_resolution["fresh_resolution_status"].ne("OWNER_EXCLUSION_RECOMMENDED")
        & fresh_resolution["fresh_resolution_reason"].isin([
            "COLLECTOR_BOOSTER_PRODUCT", "DRAFT_BOOSTER_PRODUCT", "PLAY_BOOSTER_PRODUCT",
            "BOOSTER_BOX_CASE", "NON_BOOSTER_DISPLAY", "RELEASE_HAS_COLLECTOR_OPTION",
        ])
    ]
    if not prohibited.empty:
        raise RuntimeError("PROHIBITED_FRESH_PRODUCT_NOT_EXCLUDED")


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    aliases = load_json(ALIAS_PATH)
    ensure_semantic_outputs()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    owner = pd.read_csv(SEMANTIC_OUTPUT / "precollector_owner_review_universe.csv", low_memory=False)
    fresh_delta = pd.read_csv(SEMANTIC_OUTPUT / "precollector_fresh_delta_scope_review.csv", low_memory=False)
    mtgjson = pd.read_csv(SEMANTIC_OUTPUT / "precollector_release_date_authority.csv", low_memory=False)
    full_fresh = pd.read_csv(RECON_OUTPUT / "precollector_fresh_tcgcsv_products.csv", low_memory=False)

    resolved, alias_rows = resolve_alias_dates(owner, aliases, mtgjson)
    resolved = resolve_mystery_product_dates(resolved, full_fresh)
    resolved = deduplicate_existing(resolved)
    resolved["owner_decision_status"] = resolved["owner_review_status"].replace({"READY_FOR_OWNER_REVIEW": "OWNER_APPROVAL_READY"})

    fresh_resolution = classify_fresh_delta(fresh_delta, full_fresh)
    ready = resolved[resolved["owner_decision_status"].eq("OWNER_APPROVAL_READY")].copy()
    exclusions = fresh_resolution[fresh_resolution["fresh_resolution_status"].eq("OWNER_EXCLUSION_RECOMMENDED")].copy()
    review = pd.concat([
        resolved[~resolved["owner_decision_status"].eq("OWNER_APPROVAL_READY")],
        fresh_resolution[~fresh_resolution["fresh_resolution_status"].eq("OWNER_EXCLUSION_RECOMMENDED")],
    ], ignore_index=True, sort=False)

    validate(resolved.rename(columns={"owner_decision_status": "owner_review_status"}), fresh_resolution)

    outputs = contract["outputs"]
    resolved.to_csv(OUTPUT_DIR / outputs["resolved_existing_universe"], index=False)
    fresh_resolution.to_csv(OUTPUT_DIR / outputs["fresh_delta_resolution"], index=False)
    ready.to_csv(OUTPUT_DIR / outputs["owner_approval_ready"], index=False)
    exclusions.to_csv(OUTPUT_DIR / outputs["owner_exclusion_recommended"], index=False)
    review.to_csv(OUTPUT_DIR / outputs["owner_review_queue"], index=False)
    alias_rows.to_csv(OUTPUT_DIR / outputs["release_alias_authority"], index=False)

    counts = resolved["owner_decision_status"].value_counts().to_dict()
    fresh_counts = fresh_resolution["fresh_resolution_status"].value_counts().to_dict()
    summary = {
        "certification_status": "PASS_PRECOLLECTOR_FINAL_UNIVERSE_RESOLUTION_BUILD",
        "contract_id": contract["contract_id"],
        "contract_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "resolved_existing_rows": len(resolved),
        "owner_approval_ready_rows": int(counts.get("OWNER_APPROVAL_READY", 0)),
        "existing_review_or_conflict_rows": int(len(resolved) - counts.get("OWNER_APPROVAL_READY", 0)),
        "fresh_delta_rows": len(fresh_resolution),
        "fresh_exclusion_recommended_rows": int(fresh_counts.get("OWNER_EXCLUSION_RECOMMENDED", 0)),
        "fresh_review_rows": int(len(fresh_resolution) - fresh_counts.get("OWNER_EXCLUSION_RECOMMENDED", 0)),
        "unresolved_release_date_rows": int(resolved["governed_release_date"].fillna("").str.strip().eq("").sum()),
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
        "next_stage": contract["next_stage_if_certified"],
    }
    (OUTPUT_DIR / outputs["summary"]).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "alias_authority_sha256": sha256_file(ALIAS_PATH),
        "semantic_summary_sha256": sha256_file(SEMANTIC_OUTPUT / "precollector_semantic_cleanup_summary.json"),
        "owner_approval_required_before_freeze": True,
    }
    (OUTPUT_DIR / outputs["manifest"]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_FINAL_UNIVERSE_RESOLUTION_BUILD")
    for key, value in summary.items():
        if key.endswith("_rows"):
            print(f"{key.upper()}={value}")
    print("NEXT_STAGE=OWNER_DECISION_ON_FINAL_PRECOLLECTOR_UNIVERSE")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
