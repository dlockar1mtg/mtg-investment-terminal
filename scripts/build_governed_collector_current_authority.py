"""Build the governed English Collector current-price authority and product map.

This block is evidence-only. It does not overwrite source registries, append to
history, resume forecasting, or authorize purchases.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config/mtg/governance/collector_current_authority_policy_v1.json"
DEFAULT_QUEUE = ROOT / "data/governance/permanence/certification/tcgcsv_collector_current_prices/collector_current_price_language_queue.csv"
DEFAULT_REGISTRY = ROOT / "data/staging/phase_10/canonical_registry/canonical_mtg_product_registry_2026-07-22.csv"
DEFAULT_DISCOVERED = ROOT / "data/discovered/collector_booster_boxes_discovered.csv"
DEFAULT_RAW = ROOT / "data/raw/tcgcsv"
DEFAULT_OUT = ROOT / "data/governance/permanence/certification/collector_current_authority"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build governed Collector current authority")
    p.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    p.add_argument("--language-queue", type=Path, default=DEFAULT_QUEUE)
    p.add_argument("--canonical-registry", type=Path, default=DEFAULT_REGISTRY)
    p.add_argument("--discovered-products", type=Path, default=DEFAULT_DISCOVERED)
    p.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--strict", action="store_true")
    return p.parse_args()


def txt(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def norm_id(value: object) -> str:
    value = txt(value)
    return value[:-2] if value.endswith(".0") else value


def first_present(row: pd.Series, names: list[str]) -> str:
    for name in names:
        if name in row.index and txt(row.get(name)):
            return txt(row.get(name))
    return ""


def load_raw_product_evidence(raw_dir: Path) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for path in sorted(raw_dir.glob("products_1_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        results = payload.get("results", []) if isinstance(payload, dict) else []
        for product in results:
            if not isinstance(product, dict):
                continue
            presale = product.get("presaleInfo") or {}
            rows.append(
                {
                    "tcgplayer_product_id": norm_id(product.get("productId")),
                    "raw_product_name": txt(product.get("name")),
                    "raw_group_id": norm_id(product.get("groupId")),
                    "raw_category_id": norm_id(product.get("categoryId")),
                    "raw_is_presale": str(bool(presale.get("isPresale", False))).lower(),
                    "raw_released_on": txt(presale.get("releasedOn")),
                    "raw_product_modified_on": txt(product.get("modifiedOn")),
                    "raw_product_source_file": path.name,
                }
            )
    if not rows:
        return pd.DataFrame(
            columns=[
                "tcgplayer_product_id",
                "raw_product_name",
                "raw_group_id",
                "raw_category_id",
                "raw_is_presale",
                "raw_released_on",
                "raw_product_modified_on",
                "raw_product_source_file",
            ]
        )
    frame = pd.DataFrame(rows)
    frame = frame.sort_values(["tcgplayer_product_id", "raw_product_modified_on", "raw_product_source_file"])
    return frame.drop_duplicates("tcgplayer_product_id", keep="last")


def main() -> int:
    args = parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    required_paths = [args.policy, args.language_queue, args.canonical_registry]
    missing = [str(path) for path in required_paths if not path.resolve().is_file()]
    if missing:
        summary = {
            "block_name": "Governed Collector Current Authority",
            "block_version": "1.0.0",
            "status": "FAIL",
            "missing_inputs": missing,
            "historical_append_authorized": False,
            "forecasting_resume_authorized": False,
            "purchase_recommendation_authorized": False,
        }
        (out / "collector_current_authority_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1

    policy = json.loads(args.policy.resolve().read_text(encoding="utf-8"))
    queue = pd.read_csv(args.language_queue.resolve(), dtype=str).fillna("")
    registry = pd.read_csv(args.canonical_registry.resolve(), dtype=str).fillna("")
    discovered = (
        pd.read_csv(args.discovered_products.resolve(), dtype=str).fillna("")
        if args.discovered_products.resolve().is_file()
        else pd.DataFrame()
    )
    raw = load_raw_product_evidence(args.raw_dir.resolve())

    queue["tcgplayer_product_id"] = queue["tcgplayer_product_id"].map(norm_id)
    registry["tcgplayer_product_id"] = registry["tcgplayer_product_id"].map(norm_id)
    if not discovered.empty and "tcgplayer_product_id" in discovered.columns:
        discovered["tcgplayer_product_id"] = discovered["tcgplayer_product_id"].map(norm_id)

    duplicate_registry_ids = set(
        registry.loc[registry["tcgplayer_product_id"].ne("")]
        .groupby("tcgplayer_product_id")
        .size()
        .loc[lambda s: s > 1]
        .index.tolist()
    )
    registry_unique = registry.loc[~registry["tcgplayer_product_id"].isin(duplicate_registry_ids)].copy()
    registry_unique = registry_unique.drop_duplicates("tcgplayer_product_id", keep="first")

    registry_columns = [
        "tcgplayer_product_id",
        "canonical_product_id",
        "canonical_product_name",
        "canonical_set_name",
        "canonical_product_class",
        "canonical_product_type",
        "canonical_packaging_level",
        "language",
        "canonical_identity_status",
        "identity_review_status",
        "investment_eligibility_status",
        "investment_approval_status",
        "tcgcsv_category_id",
        "tcgcsv_group_id",
        "source_system",
        "source_lineage",
    ]
    for col in registry_columns:
        if col not in registry_unique.columns:
            registry_unique[col] = ""

    merged = queue.merge(registry_unique[registry_columns], on="tcgplayer_product_id", how="left", validate="one_to_one")
    if not raw.empty:
        merged = merged.merge(raw, on="tcgplayer_product_id", how="left", validate="one_to_one")
    else:
        for col in ["raw_product_name", "raw_group_id", "raw_category_id", "raw_is_presale", "raw_released_on", "raw_product_modified_on", "raw_product_source_file"]:
            merged[col] = ""

    if not discovered.empty and "tcgplayer_product_id" in discovered.columns:
        keep = ["tcgplayer_product_id"] + [c for c in ["published_on", "release_date", "tcgcsv_category_id", "tcgcsv_group_id", "source_product_name", "source_group_name"] if c in discovered.columns]
        disc = discovered[keep].drop_duplicates("tcgplayer_product_id", keep="last")
        disc = disc.rename(columns={c: f"discovered_{c}" for c in keep if c != "tcgplayer_product_id"})
        merged = merged.merge(disc, on="tcgplayer_product_id", how="left", validate="one_to_one")

    language_policy = policy["language_policy"]
    accepted_language_values = {str(v).strip().lower() for v in language_policy["accepted_canonical_values"]}
    foreign_markers = [str(v).lower() for v in language_policy["foreign_language_markers"]]
    excluded_ids = {str(v) for v in language_policy["explicitly_excluded_product_ids"]}
    excluded_config_markers = [str(v).lower() for v in policy["configuration_policy"]["excluded_name_markers"]]
    owner_prices = {
        str(item["tcgplayer_product_id"]): float(item["market_price"])
        for item in policy["price_policy"]["owner_attested_current_prices"]
    }

    now = pd.Timestamp.now(tz="UTC")
    maturity_days = int(policy["release_policy"]["mature_after_days"])

    def classify(row: pd.Series) -> pd.Series:
        pid = txt(row.get("tcgplayer_product_id"))
        display_name = first_present(row, ["box_name", "canonical_product_name", "raw_product_name"])
        lower_name = display_name.lower()
        canonical_id = txt(row.get("canonical_product_id"))
        language = txt(row.get("language"))
        packaging = txt(row.get("canonical_packaging_level")).upper()
        product_class = txt(row.get("canonical_product_class")).upper()
        reasons: list[str] = []

        if pid in duplicate_registry_ids:
            reasons.append("DUPLICATE_CANONICAL_REGISTRY_PRODUCT_ID")
        if not canonical_id:
            reasons.append("CANONICAL_IDENTITY_NOT_FOUND")
        if pid in excluded_ids:
            reasons.append("EXPLICITLY_EXCLUDED_PRODUCT_ID")
        if any(marker in lower_name for marker in foreign_markers):
            reasons.append("FOREIGN_LANGUAGE_MARKER_PRESENT")
        if language.lower() not in accepted_language_values:
            reasons.append("CANONICAL_LANGUAGE_NOT_ACCEPTED")
        if any(marker in lower_name for marker in excluded_config_markers):
            reasons.append("EXCLUDED_CONFIGURATION_MARKER_PRESENT")
        if packaging and packaging not in {"SEALED_DISPLAY", "DISPLAY", "BOOSTER_DISPLAY", "SEALED_UNIT", ""}:
            reasons.append("CANONICAL_PACKAGING_CONTRADICTS_DISPLAY")
        if product_class and "COLLECTOR" not in product_class and product_class not in {"SEALED_PRODUCT", "SEALED"}:
            reasons.append("CANONICAL_CLASS_CONTRADICTS_COLLECTOR")

        category_id = first_present(row, ["tcgcsv_category_id_x", "tcgcsv_category_id", "raw_category_id", "discovered_tcgcsv_category_id"])
        group_id = first_present(row, ["tcgcsv_group_id_x", "tcgcsv_group_id", "raw_group_id", "discovered_tcgcsv_group_id"])
        if not category_id:
            reasons.append("TCGCSV_CATEGORY_ID_MISSING")
        if not group_id:
            reasons.append("TCGCSV_GROUP_ID_MISSING")

        release_date = first_present(row, ["raw_released_on", "discovered_release_date", "discovered_published_on"])
        is_presale = txt(row.get("raw_is_presale")).lower() == "true"
        release_state = "RELEASE_DATE_UNVERIFIED"
        release_age_days = ""
        if is_presale:
            release_state = "PRESALE"
        elif release_date:
            parsed = pd.to_datetime(release_date, utc=True, errors="coerce")
            if pd.notna(parsed):
                age = int((now - parsed).days)
                release_age_days = str(age)
                release_state = "RELEASED_MATURE" if age >= maturity_days else "RELEASED_EARLY_LIFECYCLE"

        market_price = pd.to_numeric(row.get("market_price"), errors="coerce")
        price_status = "SOURCE_PRICE_PRESENT"
        if pd.isna(market_price) or float(market_price) <= 0:
            price_status = "SOURCE_PRICE_INVALID"
            reasons.append("POSITIVE_MARKET_PRICE_REQUIRED")

        attested = pid in owner_prices
        attested_match = False
        if attested and pd.notna(market_price):
            attested_match = abs(float(market_price) - owner_prices[pid]) <= 0.01
        if attested and not attested_match:
            reasons.append("OWNER_ATTESTED_PRICE_MISMATCH")

        language_evidence = (
            "TCGPLAYER_DEFAULT_ENGLISH_CATALOG_IDENTITY"
            if language.lower() in accepted_language_values and pid not in excluded_ids and not any(marker in lower_name for marker in foreign_markers)
            else "UNRESOLVED"
        )
        identity_status = "CURRENT_IDENTITY_AUTHORIZED" if not reasons else "REVIEW_REQUIRED"
        current_price_status = "CURRENT_PRICE_CANDIDATE" if not reasons else "QUARANTINED"

        return pd.Series(
            {
                "governed_tcgcsv_category_id": category_id,
                "governed_tcgcsv_group_id": group_id,
                "governed_language": "ENGLISH" if language_evidence != "UNRESOLVED" else "UNRESOLVED",
                "language_evidence_code": language_evidence,
                "release_date_evidence": release_date,
                "release_state": release_state,
                "release_age_days": release_age_days,
                "price_evidence_status": price_status,
                "owner_attested_price": owner_prices.get(pid, ""),
                "owner_attested_price_match": str(attested_match).lower() if attested else "not_applicable",
                "identity_authority_status": identity_status,
                "current_price_authority_status": current_price_status,
                "authority_blocking_reasons": ";".join(reasons),
            }
        )

    classified = merged.join(merged.apply(classify, axis=1))
    authorized = classified.loc[classified["identity_authority_status"].eq("CURRENT_IDENTITY_AUTHORIZED")].copy()
    review = classified.loc[~classified["identity_authority_status"].eq("CURRENT_IDENTITY_AUTHORIZED")].copy()

    product_map = pd.DataFrame(
        {
            "box_name": authorized["box_name"],
            "tcgplayer_product_id": authorized["tcgplayer_product_id"],
            "tcgcsv_category_id": authorized["governed_tcgcsv_category_id"],
            "tcgcsv_group_id": authorized["governed_tcgcsv_group_id"],
            "scryfall_set_code": "",
            "source_product_name": authorized["canonical_product_name"],
            "source_url": "",
            "verified": "true",
            "notes": "Governed English Collector display identity; current-price collection only; historical append not authorized",
        }
    ).sort_values(["box_name", "tcgplayer_product_id"])

    classified.to_csv(out / "collector_current_authority_all.csv", index=False)
    authorized.to_csv(out / "collector_current_authority_authorized.csv", index=False)
    review.to_csv(out / "collector_current_authority_review_queue.csv", index=False)
    product_map.to_csv(out / "governed_collector_tcgcsv_product_map.csv", index=False)

    summary = {
        "block_name": "Governed Collector Current Authority",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_rows": int(len(classified)),
        "identity_authorized_rows": int(len(authorized)),
        "review_required_rows": int(len(review)),
        "governed_product_map_rows": int(len(product_map)),
        "presale_rows": int(classified["release_state"].eq("PRESALE").sum()),
        "released_early_lifecycle_rows": int(classified["release_state"].eq("RELEASED_EARLY_LIFECYCLE").sum()),
        "released_mature_rows": int(classified["release_state"].eq("RELEASED_MATURE").sum()),
        "release_date_unverified_rows": int(classified["release_state"].eq("RELEASE_DATE_UNVERIFIED").sum()),
        "owner_attested_price_rows": int(classified["owner_attested_price_match"].ne("not_applicable").sum()),
        "owner_attested_price_match_rows": int(classified["owner_attested_price_match"].eq("true").sum()),
        "historical_append_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "status": "PASS_CURRENT_IDENTITY_ONLY" if len(authorized) == len(classified) else "REVIEW_REQUIRED",
    }
    (out / "collector_current_authority_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))

    if args.strict and len(review):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
