"""Build strict official Wizards release-date authority for governed Collector products."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "config/mtg/governance/collector_official_release_date_registry_v1.csv"
DEFAULT_AUTHORITY = ROOT / "data/governance/permanence/certification/collector_current_authority/collector_current_authority_all.csv"
DEFAULT_OUT = ROOT / "data/governance/permanence/certification/collector_official_release_date_authority"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build official release-date authority")
    p.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    p.add_argument("--authority", type=Path, default=DEFAULT_AUTHORITY)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--strict", action="store_true")
    return p


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig", low_memory=False).fillna("")


def norm_id(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def main() -> int:
    args = parser().parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    for label, path in [("registry", args.registry), ("current_authority", args.authority)]:
        if not path.resolve().is_file():
            failures.append(f"{label}_missing")

    if failures:
        summary = {"status": "FAIL", "failures": failures, "release_date_authority_authorized": False}
        (out / "collector_official_release_date_authority_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1

    registry = read_csv(args.registry.resolve())
    authority = read_csv(args.authority.resolve())
    registry["tcgplayer_product_id"] = registry["tcgplayer_product_id"].map(norm_id)
    authority["tcgplayer_product_id"] = authority["tcgplayer_product_id"].map(norm_id)
    governed = authority.loc[authority["identity_authority_status"].eq("CURRENT_IDENTITY_AUTHORIZED")].copy()

    duplicate_registry_ids = registry.loc[registry.duplicated("tcgplayer_product_id", keep=False)].copy()
    missing_registry_ids = governed.loc[~governed["tcgplayer_product_id"].isin(set(registry["tcgplayer_product_id"]))].copy()
    extra_registry_ids = registry.loc[~registry["tcgplayer_product_id"].isin(set(governed["tcgplayer_product_id"]))].copy()

    required = ["official_release_date", "evidence_type", "source_url", "verification_status"]
    blank_registry = registry.loc[registry[required].apply(lambda s: s.astype(str).str.strip().eq("")).any(axis=1)].copy()
    invalid_status = registry.loc[~registry["verification_status"].eq("OFFICIAL_WIZARDS_VERIFIED")].copy()
    parsed_dates = pd.to_datetime(registry["official_release_date"], errors="coerce")
    invalid_dates = registry.loc[parsed_dates.isna()].copy()

    merged = governed.merge(
        registry,
        on="tcgplayer_product_id",
        how="left",
        suffixes=("_current", "_official"),
        validate="one_to_one" if not len(duplicate_registry_ids) else "many_to_many",
    )
    merged["release_date"] = merged["official_release_date"]
    merged["release_date_source_url"] = merged["source_url"]
    merged["release_date_evidence_type"] = merged["evidence_type"]
    merged["release_date_verification_status"] = merged["verification_status"]
    merged["release_date_authority_status"] = "OFFICIAL_RELEASE_DATE_AUTHORIZED"
    merged.loc[
        merged["release_date"].astype(str).str.strip().eq("")
        | ~merged["release_date_verification_status"].eq("OFFICIAL_WIZARDS_VERIFIED"),
        "release_date_authority_status",
    ] = "RELEASE_DATE_AUTHORITY_BLOCKED"

    unresolved = merged.loc[merged["release_date_authority_status"].ne("OFFICIAL_RELEASE_DATE_AUTHORIZED")].copy()
    comparison = merged[[
        "tcgplayer_product_id", "box_name", "raw_released_on", "official_release_date",
        "release_date_evidence_type", "release_date_source_url", "release_date_verification_status",
        "release_date_authority_status",
    ]].copy()
    comparison["prior_release_date_blank"] = comparison["raw_released_on"].astype(str).str.strip().eq("")
    comparison["prior_matches_official"] = pd.to_datetime(comparison["raw_released_on"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("").eq(comparison["official_release_date"])

    registry.to_csv(out / "collector_official_release_date_registry_snapshot.csv", index=False)
    merged.to_csv(out / "collector_official_release_date_authority.csv", index=False)
    comparison.to_csv(out / "collector_release_date_comparison_audit.csv", index=False)
    unresolved.to_csv(out / "collector_release_date_unresolved.csv", index=False)
    duplicate_registry_ids.to_csv(out / "collector_release_date_duplicate_registry_ids.csv", index=False)
    missing_registry_ids.to_csv(out / "collector_release_date_missing_registry_ids.csv", index=False)
    extra_registry_ids.to_csv(out / "collector_release_date_extra_registry_ids.csv", index=False)
    blank_registry.to_csv(out / "collector_release_date_blank_registry_fields.csv", index=False)
    invalid_status.to_csv(out / "collector_release_date_invalid_status.csv", index=False)
    invalid_dates.to_csv(out / "collector_release_date_invalid_dates.csv", index=False)

    unverified_count = int((~merged["release_date_verification_status"].eq("OFFICIAL_WIZARDS_VERIFIED")).sum())
    blocking = any([
        len(duplicate_registry_ids), len(missing_registry_ids), len(extra_registry_ids),
        len(blank_registry), len(invalid_status), len(invalid_dates), len(unresolved),
        len(registry) != len(governed),
    ])
    summary = {
        "block_name": "Collector Official Release Date Authority",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "governed_products": int(len(governed)),
        "registry_rows": int(len(registry)),
        "authorized_release_dates": int(merged["release_date_authority_status"].eq("OFFICIAL_RELEASE_DATE_AUTHORIZED").sum()),
        "blank_official_release_dates": int(merged["release_date"].astype(str).str.strip().eq("").sum()),
        "unverified_release_dates": unverified_count,
        "unresolved_rows": int(len(unresolved)),
        "duplicate_registry_ids": int(len(duplicate_registry_ids)),
        "missing_registry_ids": int(len(missing_registry_ids)),
        "extra_registry_ids": int(len(extra_registry_ids)),
        "invalid_date_rows": int(len(invalid_dates)),
        "prior_blank_dates_filled": int(comparison["prior_release_date_blank"].sum()),
        "release_date_authority_authorized": not blocking,
        "historical_append_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_OFFICIAL_RELEASE_DATE_AUTHORITY" if not blocking else "REVIEW_REQUIRED",
        "failures": [],
    }
    (out / "collector_official_release_date_authority_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if args.strict and blocking:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
