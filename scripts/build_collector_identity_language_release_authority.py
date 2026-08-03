"""Build an evidence-only Collector identity, language, and release authority queue.

This script never infers English from the absence of a foreign-language marker.
It joins the current Collector price certification queue to the canonical MTG
registry by exact TCGplayer product ID and emits verified, unresolved, and
excluded outputs. It does not modify source registries or historical data.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE = ROOT / "data/governance/permanence/certification/tcgcsv_collector_current_prices/collector_current_price_language_queue.csv"
DEFAULT_REGISTRY = ROOT / "data/staging/phase_10/canonical_registry/canonical_mtg_product_registry_2026-07-22.csv"
DEFAULT_OUT = ROOT / "data/governance/permanence/certification/collector_identity_language_release"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build Collector language and release authority queue")
    p.add_argument("--language-queue", type=Path, default=DEFAULT_QUEUE)
    p.add_argument("--canonical-registry", type=Path, default=DEFAULT_REGISTRY)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--strict", action="store_true")
    return p


def text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def norm_id(value: object) -> str:
    raw = text(value)
    if raw.endswith(".0"):
        raw = raw[:-2]
    return raw


def main() -> int:
    args = parser().parse_args()
    queue_path = args.language_queue.resolve()
    registry_path = args.canonical_registry.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    if not queue_path.is_file():
        failures.append("language_queue_missing")
    if not registry_path.is_file():
        failures.append("canonical_registry_missing")
    if failures:
        summary = {
            "audit_name": "Collector Identity Language Release Authority",
            "audit_version": "1.0.0",
            "status": "FAIL",
            "failures": failures,
            "forecasting_resume_authorized": False,
            "historical_append_authorized": False,
            "purchase_recommendation_authorized": False,
        }
        (out / "collector_identity_language_release_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1

    queue = pd.read_csv(queue_path, dtype=str).fillna("")
    registry = pd.read_csv(registry_path, dtype=str).fillna("")

    required_queue = {"tcgplayer_product_id", "box_name", "market_price"}
    required_registry = {"tcgplayer_product_id", "language", "canonical_product_id", "canonical_product_name"}
    missing_queue = sorted(required_queue - set(queue.columns))
    missing_registry = sorted(required_registry - set(registry.columns))
    if missing_queue:
        failures.append("language_queue_schema_missing:" + ",".join(missing_queue))
    if missing_registry:
        failures.append("canonical_registry_schema_missing:" + ",".join(missing_registry))
    if failures:
        summary = {
            "audit_name": "Collector Identity Language Release Authority",
            "audit_version": "1.0.0",
            "status": "FAIL",
            "failures": failures,
            "forecasting_resume_authorized": False,
            "historical_append_authorized": False,
            "purchase_recommendation_authorized": False,
        }
        (out / "collector_identity_language_release_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1

    queue["tcgplayer_product_id"] = queue["tcgplayer_product_id"].map(norm_id)
    registry["tcgplayer_product_id"] = registry["tcgplayer_product_id"].map(norm_id)

    duplicate_registry_ids = sorted(
        registry.loc[registry["tcgplayer_product_id"].ne("")]
        .groupby("tcgplayer_product_id")
        .size()
        .loc[lambda s: s > 1]
        .index.tolist()
    )

    registry_unique = registry.loc[~registry["tcgplayer_product_id"].isin(duplicate_registry_ids)].copy()
    registry_unique = registry_unique.drop_duplicates("tcgplayer_product_id", keep="first")

    wanted = [
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
        "source_system",
        "source_lineage",
    ]
    for col in wanted:
        if col not in registry_unique.columns:
            registry_unique[col] = ""

    merged = queue.merge(registry_unique[wanted], on="tcgplayer_product_id", how="left", validate="many_to_one")

    release_candidates = [c for c in ("release_date", "group_published_on", "published_on") if c in registry.columns]
    release_map = pd.DataFrame(columns=["tcgplayer_product_id", "release_date_evidence"])
    if release_candidates:
        release_source = registry_unique[["tcgplayer_product_id"] + release_candidates].copy()
        release_source["release_date_evidence"] = release_source[release_candidates].apply(
            lambda r: next((text(v) for v in r if text(v)), ""), axis=1
        )
        release_map = release_source[["tcgplayer_product_id", "release_date_evidence"]]
        merged = merged.merge(release_map, on="tcgplayer_product_id", how="left", validate="many_to_one")
    else:
        merged["release_date_evidence"] = ""

    def classify(row: pd.Series) -> pd.Series:
        pid = text(row.get("tcgplayer_product_id"))
        language = text(row.get("language")).upper()
        canonical_id = text(row.get("canonical_product_id"))
        packaging = text(row.get("canonical_packaging_level")).upper()
        product_class = text(row.get("canonical_product_class")).upper()
        reasons: list[str] = []

        if pid in duplicate_registry_ids:
            reasons.append("DUPLICATE_CANONICAL_REGISTRY_PRODUCT_ID")
        if not canonical_id:
            reasons.append("CANONICAL_IDENTITY_NOT_FOUND")
        if language != "ENGLISH":
            reasons.append("EXPLICIT_ENGLISH_EVIDENCE_NOT_FOUND")
        if packaging and packaging not in {"SEALED_DISPLAY", "DISPLAY", "BOOSTER_DISPLAY"}:
            reasons.append("CANONICAL_PACKAGING_NOT_DISPLAY")
        if product_class and "COLLECTOR" not in product_class:
            reasons.append("CANONICAL_CLASS_NOT_COLLECTOR")

        release = text(row.get("release_date_evidence"))
        release_status = "RELEASE_DATE_VERIFIED" if release else "RELEASE_DATE_UNVERIFIED"

        authority_status = "IDENTITY_LANGUAGE_VERIFIED" if not reasons else "REVIEW_REQUIRED"
        return pd.Series({
            "authority_status": authority_status,
            "release_status": release_status,
            "authority_blocking_reasons": ";".join(reasons),
        })

    classified = merged.join(merged.apply(classify, axis=1))
    verified = classified.loc[classified["authority_status"].eq("IDENTITY_LANGUAGE_VERIFIED")].copy()
    unresolved = classified.loc[~classified["authority_status"].eq("IDENTITY_LANGUAGE_VERIFIED")].copy()

    classified.to_csv(out / "collector_identity_language_release_all.csv", index=False)
    verified.to_csv(out / "collector_identity_language_verified.csv", index=False)
    unresolved.to_csv(out / "collector_identity_language_review_queue.csv", index=False)

    summary = {
        "audit_name": "Collector Identity Language Release Authority",
        "audit_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_rows": int(len(queue)),
        "canonical_registry_rows": int(len(registry)),
        "duplicate_registry_product_id_count": int(len(duplicate_registry_ids)),
        "identity_language_verified_rows": int(len(verified)),
        "review_required_rows": int(len(unresolved)),
        "release_date_verified_rows": int(classified["release_status"].eq("RELEASE_DATE_VERIFIED").sum()),
        "release_date_unverified_rows": int(classified["release_status"].eq("RELEASE_DATE_UNVERIFIED").sum()),
        "historical_append_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "status": "PASS" if len(verified) == len(queue) and not duplicate_registry_ids else "REVIEW_REQUIRED",
        "failures": [],
    }
    (out / "collector_identity_language_release_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))

    if args.strict and summary["status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
