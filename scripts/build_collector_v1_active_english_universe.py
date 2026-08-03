"""Build the active English-only Collector V1 universe without mutating historical source artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_v1_active_english_universe"
POLICY = ROOT / "config/mtg/governance/collector_v1_product_exclusions.json"
PATHS = {
    "canonical_routes": ROOT / "data/governance/permanence/certification/collector_v1_canonical_inputs/collector_v1_canonical_forecast_routes.csv",
    "canonical_history": ROOT / "data/governance/permanence/certification/collector_v1_canonical_inputs/collector_v1_canonical_daily_price_history.csv",
    "scarcity": ROOT / "data/governance/permanence/certification/collector_supply_scarcity_index_v1/collector_supply_scarcity_index_v1.csv",
    "release": ROOT / "data/governance/permanence/certification/collector_official_release_date_authority/collector_official_release_date_authority.csv",
    "normalized": ROOT / "data/operations/collector_evidence_normalization/candidate_v1_0_0/collector_normalized_evidence.csv",
    "comparables": ROOT / "data/operations/collector_comparable_selection/candidate_v1_0_0/collector_selected_comparables.csv",
}


def load(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def row_contains_excluded(row: pd.Series, excluded_ids: set[str]) -> bool:
    values = {str(value).strip() for value in row.tolist()}
    return bool(values & excluded_ids)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    missing = [name for name, path in {"policy": POLICY, **PATHS}.items() if not path.is_file()]
    if missing:
        summary = {
            "block_name": "Collector V1 Active English Universe",
            "block_version": "1.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "missing_inputs": missing,
            "status": "FAIL_REQUIRED_INPUTS_MISSING",
        }
        (OUT / "collector_v1_active_english_universe_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1 if args.strict else 0

    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    exclusions = policy.get("excluded_products", [])
    excluded_ids = {
        str(item.get("tcgplayer_product_id", "")).strip()
        for item in exclusions
        if str(item.get("tcgplayer_product_id", "")).strip()
    } | {
        str(item.get("investment_product_id", "")).strip()
        for item in exclusions
        if str(item.get("investment_product_id", "")).strip()
    }

    outputs: dict[str, Path] = {}
    counts: dict[str, dict[str, int]] = {}

    for name, source_path in PATHS.items():
        frame = load(source_path)
        excluded_mask = frame.apply(lambda row: row_contains_excluded(row, excluded_ids), axis=1)
        active = frame.loc[~excluded_mask].copy()
        output_path = OUT / f"collector_v1_active_{name}.csv"
        active.to_csv(output_path, index=False)
        outputs[name] = output_path
        counts[name] = {
            "source_rows": int(len(frame)),
            "excluded_rows": int(excluded_mask.sum()),
            "active_rows": int(len(active)),
        }

    routes = load(outputs["canonical_routes"])
    scarcity = load(outputs["scarcity"])
    release = load(outputs["release"])

    route_ids = set(routes.get("tcgplayer_product_id", pd.Series(dtype=str)).astype(str).str.strip()) - {""}
    scarcity_ids = set(scarcity.get("tcgplayer_product_id", pd.Series(dtype=str)).astype(str).str.strip()) - {""}
    release_ids = set(release.get("tcgplayer_product_id", pd.Series(dtype=str)).astype(str).str.strip()) - {""}

    residual_occurrences = []
    for name, output_path in outputs.items():
        frame = load(output_path)
        matches = int(frame.apply(lambda row: row_contains_excluded(row, excluded_ids), axis=1).sum())
        if matches:
            residual_occurrences.append({"artifact": name, "matching_rows": matches})

    certified = (
        len(routes) == 50
        and len(route_ids) == 50
        and route_ids == scarcity_ids
        and route_ids == release_ids
        and not residual_occurrences
    )

    summary = {
        "block_name": "Collector V1 Active English Universe",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "language_policy": "ENGLISH_ONLY",
        "excluded_products": exclusions,
        "artifact_row_counts": counts,
        "active_route_rows": int(len(routes)),
        "active_unique_tcgplayer_ids": int(len(route_ids)),
        "active_scarcity_rows": int(len(scarcity)),
        "active_release_rows": int(len(release)),
        "route_ids_equal_scarcity_ids": bool(route_ids == scarcity_ids),
        "route_ids_equal_release_ids": bool(route_ids == release_ids),
        "residual_excluded_product_occurrences": residual_occurrences,
        "historical_source_artifacts_mutated": False,
        "active_universe_certified": bool(certified),
        "feature_matrix_authorized": bool(certified),
        "forecast_experiments_authorized": bool(certified),
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "artifact_hashes": {
            "policy": sha256(POLICY),
            **{name: sha256(path) for name, path in outputs.items()},
        },
        "status": "PASS_COLLECTOR_V1_ACTIVE_ENGLISH_UNIVERSE_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_ACTIVE_ENGLISH_UNIVERSE",
    }
    (OUT / "collector_v1_active_english_universe_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if certified else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
