from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
MANIFEST = ROOT / "data/governance/permanence/snapshots" / SNAPSHOT_ID / "collector_snapshot_manifest.json"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_august1_price_observation_lineage"
KEYS = ("investment_product_id", "product_id", "collector_product_id", "canonical_product_id", "tcgplayer_product_id", "tcgcsv_product_id")
PRICES = ("current_price", "market_price", "certified_current_price", "price")
TIMES = (
    "source_observation_at_utc",
    "observed_at_utc",
    "observation_at_utc",
    "observation_date",
    "latest_price_date",
    "captured_at_utc",
    "retrieved_at_utc",
    "collected_at",
    "collected_at_utc",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def one(columns: set[str], aliases: tuple[str, ...], label: str) -> str:
    found = [x for x in aliases if x in columns]
    if len(found) != 1:
        raise RuntimeError(f"Expected exactly one {label}; found {found}")
    return found[0]


def unique_key(candidate_rows: list[dict[str, str]], observation_rows: list[dict[str, str]]) -> str:
    valid = []
    for key in KEYS:
        if not candidate_rows or not observation_rows or key not in candidate_rows[0] or key not in observation_rows[0]:
            continue
        left = [str(r.get(key, "")).strip() for r in candidate_rows]
        right = [str(r.get(key, "")).strip() for r in observation_rows]
        if all(left) and all(right) and len(left) == len(set(left)) and len(right) == len(set(right)) and set(left) == set(right):
            valid.append(key)
    if len(valid) != 1:
        raise RuntimeError(f"Expected one common complete unique key; found {valid}")
    return valid[0]


def number(value: str) -> float:
    return float(str(value).strip().replace("$", "").replace(",", ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    checks: dict[str, bool] = {}
    failures: list[str] = []
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
        by_role = {str(x.get("role")): x for x in manifest.get("files", []) if isinstance(x, dict)}
        cand_meta = by_role["live_price_candidates"]
        obs_meta = by_role["live_price_observations"]
        cand_path = ROOT / str(cand_meta["path"])
        obs_path = ROOT / str(obs_meta["path"])
        checks["candidate_hash_matches"] = sha256(cand_path) == cand_meta.get("sha256")
        checks["observation_hash_matches"] = sha256(obs_path) == obs_meta.get("sha256")
        candidate_rows = rows(cand_path)
        observation_rows = rows(obs_path)
        checks["candidate_rows_50"] = len(candidate_rows) == 50
        checks["observation_rows_50"] = len(observation_rows) == 50
        key = unique_key(candidate_rows, observation_rows)
        candidate_price = one(set(candidate_rows[0]), PRICES, "candidate price column")
        observation_price = one(set(observation_rows[0]), PRICES, "observation price column")
        observation_time = one(set(observation_rows[0]), TIMES, "observation timestamp column")
        observation_by_key = {str(r[key]).strip(): r for r in observation_rows}
        generated = datetime.now(timezone.utc).isoformat()
        output_rows = []
        for row in candidate_rows:
            product = str(row[key]).strip()
            obs = observation_by_key.get(product)
            if obs is None:
                raise RuntimeError(f"Missing observation for {product}")
            if abs(number(row[candidate_price]) - number(obs[observation_price])) > 0.000001:
                raise RuntimeError(f"Price mismatch for {product}")
            observed = str(obs.get(observation_time, "")).strip()
            if not observed:
                raise RuntimeError(f"Blank observation timestamp for {product}")
            enriched = dict(row)
            enriched["source_observation_at_utc"] = observed
            enriched["source_snapshot_id"] = SNAPSHOT_ID
            enriched["source_bundle_sha256"] = str(manifest.get("source_bundle_sha256", ""))
            enriched["source_price_authority_sha256"] = str(cand_meta.get("sha256", ""))
            enriched["source_price_observation_authority_sha256"] = str(obs_meta.get("sha256", ""))
            enriched["model_generated_at_utc"] = generated
            output_rows.append(enriched)
        checks["all_50_prices_reconciled"] = len(output_rows) == 50
        checks["all_observation_timestamps_present"] = all(r["source_observation_at_utc"] for r in output_rows)
        checks["all_snapshot_ids_present"] = all(r["source_snapshot_id"] == SNAPSHOT_ID for r in output_rows)
        OUT.mkdir(parents=True, exist_ok=True)
        out_csv = OUT / "collector_v1_august1_lineage_enriched_price_authority.csv"
        with out_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(output_rows[0]))
            writer.writeheader()
            writer.writerows(output_rows)
        failures = [k for k, v in checks.items() if not v]
        passed = not failures
        summary = {
            "block_name": "Collector V1 August 1 Price Observation Lineage Reconciliation",
            "block_version": "1.0.1",
            "generated_at_utc": generated,
            "source_snapshot_id": SNAPSHOT_ID,
            "source_bundle_sha256": manifest.get("source_bundle_sha256"),
            "source_price_authority_sha256": cand_meta.get("sha256"),
            "source_price_observation_authority_sha256": obs_meta.get("sha256"),
            "lineage_enriched_price_authority_path": str(out_csv.relative_to(ROOT)),
            "lineage_enriched_price_authority_sha256": sha256(out_csv),
            "product_key": key,
            "price_column": candidate_price,
            "observation_timestamp_column": observation_time,
            "checks": checks,
            "critical_failures": failures,
            "model_rebuild_authorized": passed,
            "purchase_recommendations_authorized": False,
            "status": "PASS_COLLECTOR_V1_AUGUST1_PRICE_OBSERVATION_LINEAGE" if passed else "FAIL_COLLECTOR_V1_AUGUST1_PRICE_OBSERVATION_LINEAGE",
        }
    except Exception as exc:
        passed = False
        summary = {
            "block_name": "Collector V1 August 1 Price Observation Lineage Reconciliation",
            "block_version": "1.0.1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_snapshot_id": SNAPSHOT_ID,
            "checks": checks,
            "critical_failures": [str(exc)],
            "model_rebuild_authorized": False,
            "purchase_recommendations_authorized": False,
            "status": "FAIL_COLLECTOR_V1_AUGUST1_PRICE_OBSERVATION_LINEAGE",
        }
        OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "collector_v1_august1_price_observation_lineage_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
