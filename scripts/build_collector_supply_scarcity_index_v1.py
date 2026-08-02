"""Build Collector Supply Scarcity Index V1 from the certified current eBay snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline"
SNAPSHOT = BASE / "collector_ebay_day_one_product_supply_snapshot.csv"
BASELINE_SUMMARY = BASE / "collector_ebay_day_one_supply_baseline_summary.json"
POLICY = ROOT / "config/mtg/governance/collector_supply_scarcity_index_v1.json"
OUT = ROOT / "data/governance/permanence/certification/collector_supply_scarcity_index_v1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inverse_percentile(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").fillna(0)
    return (1.0 - numeric.rank(method="average", pct=True)) * 100.0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build Collector Supply Scarcity Index V1")
    p.add_argument("--strict", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    missing = [str(p) for p in (SNAPSHOT, BASELINE_SUMMARY, POLICY) if not p.is_file()]
    if missing:
        payload = {"status": "REQUIRED_INPUT_MISSING", "missing_inputs": missing}
        print(json.dumps(payload, indent=2))
        return 1 if args.strict else 0

    summary = json.loads(BASELINE_SUMMARY.read_text(encoding="utf-8"))
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    frame = pd.read_csv(SNAPSHOT, dtype=str, encoding="utf-8-sig").fillna("")
    if len(frame) != 50:
        raise RuntimeError(f"Expected 50 governed products; found {len(frame)}")
    if summary.get("baseline_promoted") is not True:
        raise RuntimeError("Current eBay baseline is not promoted")

    for column in (
        "accepted_listing_count",
        "review_listing_count",
        "cross_product_ambiguity_excluded_count",
        "observable_seller_count",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)

    frame["accepted_listing_scarcity_component"] = inverse_percentile(frame["accepted_listing_count"])
    frame["observable_seller_scarcity_component"] = inverse_percentile(frame["observable_seller_count"])

    denominator = (
        frame["accepted_listing_count"]
        + frame["review_listing_count"]
        + frame["cross_product_ambiguity_excluded_count"]
    ).clip(lower=1)
    frame["review_ratio"] = frame["review_listing_count"] / denominator
    frame["ambiguity_ratio"] = frame["cross_product_ambiguity_excluded_count"] / denominator

    weights = policy["components"]
    raw = (
        frame["accepted_listing_scarcity_component"] * weights["accepted_listing_scarcity"]["weight"]
        + frame["observable_seller_scarcity_component"] * weights["observable_seller_scarcity"]["weight"]
    )
    weight_sum = (
        weights["accepted_listing_scarcity"]["weight"]
        + weights["observable_seller_scarcity"]["weight"]
    )
    frame["supply_scarcity_index_v1"] = (raw / weight_sum).clip(0, 100)

    zero_mask = frame["accepted_listing_count"] == 0
    frame.loc[zero_mask, "supply_scarcity_index_v1"] = policy["zero_accepted_listing_rule"]["scarcity_score"]

    confidence = (
        policy["confidence"]["base"]
        - frame["review_ratio"] * policy["confidence"]["review_row_penalty_per_ratio_point"]
        - frame["ambiguity_ratio"] * policy["confidence"]["ambiguity_row_penalty_per_ratio_point"]
    ).clip(policy["confidence"]["minimum"], policy["confidence"]["maximum"])
    confidence.loc[zero_mask] = confidence.loc[zero_mask].clip(upper=policy["zero_accepted_listing_rule"]["confidence_cap"])
    frame["scarcity_confidence"] = confidence
    frame["scarcity_adjusted_score"] = frame["supply_scarcity_index_v1"] * frame["scarcity_confidence"]
    frame["scarcity_tier"] = pd.cut(
        frame["supply_scarcity_index_v1"],
        bins=[-0.01, 20, 40, 60, 80, 100],
        labels=["ABUNDANT", "AVAILABLE", "BALANCED", "SCARCE", "VERY_SCARCE"],
        include_lowest=True,
    ).astype(str)
    frame["index_version"] = policy["policy_version"]
    frame["continuity_required"] = False
    frame["interpretation"] = "POINT_IN_TIME_OBSERVABLE_MARKETPLACE_SUPPLY_SCARCITY"

    output_columns = [
        "baseline_id",
        "baseline_observed_at_utc",
        "tcgplayer_product_id",
        "governed_box_name",
        "accepted_listing_count",
        "observable_seller_count",
        "review_listing_count",
        "cross_product_ambiguity_excluded_count",
        "accepted_listing_scarcity_component",
        "observable_seller_scarcity_component",
        "review_ratio",
        "ambiguity_ratio",
        "supply_scarcity_index_v1",
        "scarcity_confidence",
        "scarcity_adjusted_score",
        "scarcity_tier",
        "index_version",
        "continuity_required",
        "interpretation",
    ]
    output = frame[output_columns].copy()
    output_path = OUT / "collector_supply_scarcity_index_v1.csv"
    output.to_csv(output_path, index=False)

    generated = datetime.now(timezone.utc).isoformat()
    certification = {
        "block_name": "Collector Supply Scarcity Index V1",
        "block_version": "1.0.0",
        "generated_at": generated,
        "governed_product_rows": len(output),
        "continuity_required": False,
        "future_continuity_role": "OPTIONAL_V2_TEMPORAL_ENHANCEMENT",
        "current_snapshot_authorized": True,
        "forecast_experiment_feature_authorized": True,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "zero_accepted_listing_products": int(zero_mask.sum()),
        "score_min": float(output["supply_scarcity_index_v1"].min()),
        "score_max": float(output["supply_scarcity_index_v1"].max()),
        "score_mean": float(output["supply_scarcity_index_v1"].mean()),
        "artifact_hashes": {
            "snapshot_sha256": sha256_file(SNAPSHOT),
            "baseline_summary_sha256": sha256_file(BASELINE_SUMMARY),
            "policy_sha256": sha256_file(POLICY),
            "output_sha256": sha256_file(output_path),
        },
        "status": "PASS_SUPPLY_SCARCITY_INDEX_V1_CURRENT_SNAPSHOT_CERTIFIED",
    }
    summary_path = OUT / "collector_supply_scarcity_index_v1_summary.json"
    summary_path.write_text(json.dumps(certification, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(certification, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
