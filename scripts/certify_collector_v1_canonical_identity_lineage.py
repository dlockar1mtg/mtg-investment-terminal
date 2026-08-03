from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/collector_canonical_identity_lineage_recertification_contract_v1.json"
LORWYN_CONTRACT_PATH = ROOT / "config/mtg/standards/collector_early_awareness_lorwyn_forecast_contract_v1.json"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_canonical_identity_lineage_recertification"


def clean(value: Any) -> str:
    return str(value or "").strip()


def norm(value: Any) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in clean(value)).split())


def num(value: Any) -> float | None:
    text = clean(value).replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        result = float(text)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def row_fingerprint(row: dict[str, Any], fields: list[str]) -> str:
    payload = "|".join(clean(row.get(field)) for field in fields)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def find_field(rows: list[dict[str, str]], candidates: list[str], required: bool = True) -> str | None:
    fields = set(rows[0].keys()) if rows else set()
    for candidate in candidates:
        if candidate in fields:
            return candidate
    if required:
        raise ValueError(f"MISSING_REQUIRED_FIELD:{'|'.join(candidates)}")
    return None


def identity_fields(rows: list[dict[str, str]]) -> tuple[str, str | None, str]:
    return (
        find_field(rows, ["canonical_product_id", "product_id", "asset_id"]),
        find_field(rows, ["tcgplayer_product_id", "resolved_tcgplayer_product_id"], required=False),
        find_field(rows, ["product_name", "name", "asset_name"]),
    )


def deterministic_seed(snapshot_id: str, canonical_id: str, horizon: int) -> int:
    digest = hashlib.sha256(f"{snapshot_id}|{canonical_id}|{horizon}|authority-bound".encode()).digest()
    return int.from_bytes(digest[:8], "big") % (2**32 - 1)


def monthly_log_returns(prices: list[float]) -> np.ndarray:
    values = np.asarray([price for price in prices if price > 0], dtype=float)
    if values.size < 2:
        return np.asarray([], dtype=float)
    returns = np.diff(np.log(values))
    lo, hi = np.quantile(returns, [0.05, 0.95]) if returns.size > 1 else (returns[0], returns[0])
    return np.clip(returns, lo, hi)


def scan_for_manual_identity_assertions(contract: dict[str, Any]) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    prohibited = set(contract["prohibited_identity_keys"])
    current_contract = CONTRACT_PATH.resolve()
    for pattern in contract["product_specific_contract_globs"]:
        for path in ROOT.glob(pattern):
            if path.resolve() == current_contract or not path.is_file():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            text = json.dumps(payload)
            product_specific = "requested_product_name" in text or "standalone" in path.name.lower() or "lorwyn" in path.name.lower()
            if not product_specific:
                continue

            def walk(value: Any, pointer: str = "$") -> None:
                if isinstance(value, dict):
                    for key, child in value.items():
                        child_pointer = f"{pointer}.{key}"
                        if key in prohibited:
                            violations.append({
                                "contract_path": str(path.relative_to(ROOT)).replace("\\", "/"),
                                "json_pointer": child_pointer,
                                "prohibited_key": key,
                                "asserted_value": clean(child),
                            })
                        walk(child, child_pointer)
                elif isinstance(value, list):
                    for index, child in enumerate(value):
                        walk(child, f"{pointer}[{index}]")

            walk(payload)
    return violations


def main() -> int:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    lorwyn_contract = json.loads(LORWYN_CONTRACT_PATH.read_text(encoding="utf-8"))
    authority_paths = {name: ROOT / relative for name, relative in contract["authorities"].items()}
    failures: list[str] = []

    missing = [name for name, path in authority_paths.items() if not path.is_file()]
    if missing:
        raise SystemExit("MISSING_REQUIRED_AUTHORITY:" + ";".join(missing))

    source_hashes = {name: sha256_file(path) for name, path in authority_paths.items()}
    current_rows = read_csv(authority_paths["product_and_current_price"])
    release_rows = read_csv(authority_paths["release_date"])
    history_rows = read_csv(authority_paths["historical_observations"])
    comparable_rows = read_csv(authority_paths["comparable_pool"])
    supply_rows = read_csv(authority_paths["current_supply"])
    base_rows = read_csv(authority_paths["base_probabilistic_forecasts"])
    coverage_rows = read_csv(authority_paths["base_coverage_registry"])
    truth_rows = read_csv(authority_paths["early_awareness_truth"])
    prediction_rows = read_csv(authority_paths["early_awareness_predictions"])

    cid_field, tcg_field, name_field = identity_fields(current_rows)
    price_field = find_field(current_rows, ["current_price", "market_price", "selected_price"])
    current_by_id: dict[str, dict[str, str]] = {}
    duplicate_authority_ids: list[str] = []
    for row in current_rows:
        cid = clean(row.get(cid_field))
        if cid in current_by_id:
            duplicate_authority_ids.append(cid)
        current_by_id[cid] = row

    if len(current_rows) != int(contract["required_governed_products"]):
        failures.append(f"CURRENT_AUTHORITY_ROW_COUNT:{len(current_rows)}")
    if len(current_by_id) != int(contract["required_governed_products"]):
        failures.append(f"CURRENT_AUTHORITY_UNIQUE_ID_COUNT:{len(current_by_id)}")
    if duplicate_authority_ids:
        failures.append("CURRENT_AUTHORITY_DUPLICATE_IDS")

    authority_ids = set(current_by_id)
    authority_name_to_ids: dict[str, list[str]] = defaultdict(list)
    for cid, row in current_by_id.items():
        authority_name_to_ids[norm(row.get(name_field))].append(cid)

    manual_identity_violations = scan_for_manual_identity_assertions(contract)
    if manual_identity_violations:
        failures.append("PRODUCT_SPECIFIC_CONTRACT_MANUAL_IDENTITY_ASSERTION")

    dataset_specs = {
        "release_date": release_rows,
        "historical_observations": history_rows,
        "current_supply": supply_rows,
        "base_probabilistic_forecasts": base_rows,
        "early_awareness_truth": truth_rows,
        "early_awareness_predictions": prediction_rows,
    }
    dataset_ids: dict[str, set[str]] = {}
    dataset_name_by_id: dict[str, dict[str, str]] = {}
    unknown_identity_rows: list[dict[str, str]] = []
    name_mismatch_rows: list[dict[str, str]] = []

    for dataset_name, rows in dataset_specs.items():
        ds_cid, _, ds_name = identity_fields(rows)
        ids: set[str] = set()
        names: dict[str, str] = {}
        for row in rows:
            cid = clean(row.get(ds_cid))
            if not cid:
                continue
            ids.add(cid)
            supplied_name = clean(row.get(ds_name))
            names[cid] = supplied_name
            if cid not in authority_ids:
                unknown_identity_rows.append({
                    "dataset": dataset_name,
                    "canonical_product_id": cid,
                    "product_name": supplied_name,
                    "failure": "UNKNOWN_ID_NOT_IN_CERTIFIED_AUTHORITY",
                })
            elif supplied_name and norm(supplied_name) != norm(current_by_id[cid].get(name_field)):
                name_mismatch_rows.append({
                    "dataset": dataset_name,
                    "canonical_product_id": cid,
                    "authority_product_name": clean(current_by_id[cid].get(name_field)),
                    "dataset_product_name": supplied_name,
                    "failure": "NAME_ID_SEMANTIC_MISMATCH",
                })
        dataset_ids[dataset_name] = ids
        dataset_name_by_id[dataset_name] = names

    if unknown_identity_rows:
        failures.append("UNKNOWN_IDENTITIES_ACROSS_AUTHORITATIVE_DATASETS")
    if name_mismatch_rows:
        failures.append("NAME_ID_MISMATCH_ACROSS_AUTHORITATIVE_DATASETS")

    target_field = find_field(comparable_rows, ["target_canonical_product_id", "canonical_product_id"])
    member_field = find_field(comparable_rows, ["comparable_canonical_product_id", "member_canonical_product_id"])
    comparable_unknown: list[dict[str, str]] = []
    comparable_by_target: dict[str, list[str]] = defaultdict(list)
    for row in comparable_rows:
        target = clean(row.get(target_field))
        member = clean(row.get(member_field))
        if target:
            comparable_by_target[target].append(member)
        for role, cid in (("TARGET", target), ("MEMBER", member)):
            if cid and cid not in authority_ids:
                comparable_unknown.append({
                    "role": role,
                    "canonical_product_id": cid,
                    "failure": "COMPARABLE_ID_NOT_IN_CERTIFIED_AUTHORITY",
                })
    if comparable_unknown:
        failures.append("UNKNOWN_COMPARABLE_IDENTITIES")

    reconciliation_rows: list[dict[str, Any]] = []
    history_counts = Counter(clean(row.get(identity_fields(history_rows)[0])) for row in history_rows)
    forecast_counts = Counter(clean(row.get(identity_fields(base_rows)[0])) for row in base_rows)
    truth_counts = Counter(clean(row.get(identity_fields(truth_rows)[0])) for row in truth_rows)
    prediction_counts = Counter(clean(row.get(identity_fields(prediction_rows)[0])) for row in prediction_rows)

    for cid, authority_row in sorted(current_by_id.items(), key=lambda item: clean(item[1].get(name_field))):
        reconciliation_rows.append({
            "canonical_product_id": cid,
            "tcgplayer_product_id": clean(authority_row.get(tcg_field)) if tcg_field else "",
            "product_name": clean(authority_row.get(name_field)),
            "authority_row_fingerprint": row_fingerprint(authority_row, [cid_field, tcg_field or cid_field, name_field, price_field]),
            "current_price": num(authority_row.get(price_field)),
            "release_authority_present": cid in dataset_ids["release_date"],
            "history_observation_rows": history_counts[cid],
            "supply_authority_present": cid in dataset_ids["current_supply"],
            "certified_comparable_members": len({member for member in comparable_by_target.get(cid, []) if member}),
            "base_forecast_rows": forecast_counts[cid],
            "early_awareness_truth_rows": truth_counts[cid],
            "early_awareness_prediction_rows": prediction_counts[cid],
            "identity_reconciled": not any(row["canonical_product_id"] == cid for row in unknown_identity_rows + name_mismatch_rows),
        })

    base_cid, _, base_name = identity_fields(base_rows)
    base_price = find_field(base_rows, ["current_price"])
    base_horizon = find_field(base_rows, ["horizon_days"])
    base_method = find_field(base_rows, ["explicit_method_id"])
    base_simulations = find_field(base_rows, ["simulation_count"])
    base_ids = {clean(row.get(base_cid)) for row in base_rows}
    base_keys: Counter[tuple[str, int]] = Counter()
    base_forecast_audit: list[dict[str, Any]] = []

    for row in base_rows:
        cid = clean(row.get(base_cid))
        horizon = int(float(clean(row.get(base_horizon)) or 0))
        base_keys[(cid, horizon)] += 1
        authority_row = current_by_id.get(cid)
        authority_price = num(authority_row.get(price_field)) if authority_row else None
        forecast_price = num(row.get(base_price))
        name_match = bool(authority_row) and norm(row.get(base_name)) == norm(authority_row.get(name_field))
        price_match = authority_price is not None and forecast_price is not None and abs(authority_price - forecast_price) <= 0.01
        valid = (
            authority_row is not None
            and name_match
            and price_match
            and horizon in contract["required_horizons_days"]
            and clean(row.get(base_method))
            and "GENERIC" not in clean(row.get(base_method)).upper()
            and int(float(clean(row.get(base_simulations)) or 0)) == int(contract["simulation_count"])
        )
        base_forecast_audit.append({
            "canonical_product_id": cid,
            "product_name": clean(row.get(base_name)),
            "horizon_days": horizon,
            "authority_product_name": clean(authority_row.get(name_field)) if authority_row else "",
            "forecast_current_price": forecast_price,
            "authority_current_price": authority_price,
            "name_match": name_match,
            "price_match": price_match,
            "explicit_method_id": clean(row.get(base_method)),
            "simulation_count": int(float(clean(row.get(base_simulations)) or 0)),
            "forecast_row_fingerprint": row_fingerprint(row, [base_cid, base_name, base_horizon, base_method, base_price]),
            "recertified": valid,
        })

    if len(base_rows) != int(contract["required_base_forecast_rows"]):
        failures.append(f"BASE_FORECAST_ROW_COUNT:{len(base_rows)}")
    if len(base_ids) != int(contract["required_base_forecast_products"]):
        failures.append(f"BASE_FORECAST_PRODUCT_COUNT:{len(base_ids)}")
    if len(base_keys) != int(contract["required_base_forecast_rows"]) or any(count != 1 for count in base_keys.values()):
        failures.append("BASE_FORECAST_PRODUCT_HORIZON_KEY_FAILURE")
    if any(not row["recertified"] for row in base_forecast_audit):
        failures.append("BASE_FORECAST_IDENTITY_PRICE_METHOD_RECERTIFICATION_FAILED")

    early_audit_rows: list[dict[str, Any]] = []
    for dataset_name, rows in (("TRUTH", truth_rows), ("PREDICTION", prediction_rows)):
        ds_cid, _, ds_name = identity_fields(rows)
        for row in rows:
            cid = clean(row.get(ds_cid))
            authority_row = current_by_id.get(cid)
            valid = bool(authority_row) and norm(row.get(ds_name)) == norm(authority_row.get(name_field))
            early_audit_rows.append({
                "dataset": dataset_name,
                "canonical_product_id": cid,
                "product_name": clean(row.get(ds_name)),
                "authority_product_name": clean(authority_row.get(name_field)) if authority_row else "",
                "identity_reconciled": valid,
                "row_fingerprint": row_fingerprint(row, [ds_cid, ds_name]),
            })
    if any(not row["identity_reconciled"] for row in early_audit_rows):
        failures.append("EARLY_AWARENESS_IDENTITY_RECERTIFICATION_FAILED")

    invalidation_rows: list[dict[str, Any]] = []
    for relative in contract["invalidated_outputs"]:
        path = ROOT / relative
        existed = path.is_file()
        prior_hash = sha256_file(path) if existed else ""
        if existed:
            path.unlink()
        invalidation_rows.append({
            "invalidated_path": relative,
            "existed_before_invalidation": existed,
            "sha256_before_deletion": prior_hash,
            "deleted": existed and not path.exists(),
            "reason": "INVALID_MANUALLY_ASSERTED_LORWYN_IDENTITY_OR_DERIVED_INTEGRATION",
        })

    lorwyn_cfg = lorwyn_contract["lorwyn"]
    prohibited_present = any(key in lorwyn_cfg for key in contract["prohibited_identity_keys"])
    requested_name = clean(lorwyn_cfg.get("requested_product_name"))
    resolved_candidates = [current_by_id[cid] for cid in authority_name_to_ids.get(norm(requested_name), [])]
    semantic_failures: list[str] = []
    if prohibited_present:
        semantic_failures.append("MANUAL_IDENTITY_ASSERTION_PRESENT_IN_PRODUCT_SPECIFIC_CONTRACT")
    if len(resolved_candidates) != 1:
        semantic_failures.append(f"AUTHORITY_NAME_RESOLUTION_COUNT:{len(resolved_candidates)}")

    resolved_row = resolved_candidates[0] if len(resolved_candidates) == 1 else None
    resolved_id = clean(resolved_row.get(cid_field)) if resolved_row else ""
    resolved_tcgplayer_id = clean(resolved_row.get(tcg_field)) if resolved_row and tcg_field else ""
    resolved_price = num(resolved_row.get(price_field)) if resolved_row else None
    release_present = resolved_id in dataset_ids["release_date"]
    collision_with_base = resolved_id in base_ids if resolved_id else False
    certified_members = sorted({member for member in comparable_by_target.get(resolved_id, []) if member})
    members_with_history = [member for member in certified_members if history_counts[member] >= 2]

    if not resolved_id or not resolved_tcgplayer_id:
        semantic_failures.append("RESOLVED_IDENTITY_INCOMPLETE")
    if resolved_price is None or resolved_price <= 0:
        semantic_failures.append("RESOLVED_CURRENT_PRICE_INVALID")
    if not release_present:
        semantic_failures.append("RESOLVED_RELEASE_AUTHORITY_ROW_MISSING")
    if collision_with_base:
        semantic_failures.append("RESOLVED_PRODUCT_ALREADY_IN_BASE_FORECAST_UNIVERSE")
    if len(members_with_history) < int(lorwyn_cfg["minimum_comparable_products"]):
        semantic_failures.append(f"CERTIFIED_COMPARABLE_HISTORY_INSUFFICIENT:{len(members_with_history)}")

    semantic_certification = {
        "certification_name": "Lorwyn Authority-Bound Pre-Simulation Semantic Certification",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "requested_product_name": requested_name,
        "identity_resolution_authority": contract["authorities"]["product_and_current_price"],
        "identity_resolution_authority_sha256": source_hashes["product_and_current_price"],
        "resolution_mode": clean(lorwyn_cfg.get("identity_resolution_mode")),
        "resolved_canonical_product_id": resolved_id,
        "resolved_tcgplayer_product_id": resolved_tcgplayer_id,
        "resolved_product_name": clean(resolved_row.get(name_field)) if resolved_row else "",
        "resolved_current_price": resolved_price,
        "authority_row_fingerprint": row_fingerprint(resolved_row, [cid_field, tcg_field or cid_field, name_field, price_field]) if resolved_row else "",
        "release_authority_present": release_present,
        "base_forecast_collision": collision_with_base,
        "certified_comparable_members": certified_members,
        "certified_comparable_members_with_history": members_with_history,
        "manual_identity_assertion_present": prohibited_present,
        "semantic_failures": semantic_failures,
        "simulation_authorized": not semantic_failures,
        "production_forecast_authorized": False,
        "ranking_authorized": False,
        "purchase_recommendations_authorized": False,
        "status": "PASS_LORWYN_PRE_SIMULATION_SEMANTIC_CERTIFICATION" if not semantic_failures else "FAIL_LORWYN_PRE_SIMULATION_SEMANTIC_CERTIFICATION",
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    semantic_path = OUTPUT / "collector_lorwyn_pre_simulation_semantic_certification.json"
    semantic_path.write_text(json.dumps(semantic_certification, indent=2), encoding="utf-8")

    history_cid = identity_fields(history_rows)[0]
    history_date = find_field(history_rows, ["observation_date", "date"])
    history_price = find_field(history_rows, ["market_price", "selected_price", "price"])
    history_by_id: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in history_rows:
        cid = clean(row.get(history_cid))
        price = num(row.get(history_price))
        date = clean(row.get(history_date))
        if cid and price and price > 0 and date:
            history_by_id[cid].append((date, price))
    for values in history_by_id.values():
        values.sort(key=lambda value: value[0])

    lorwyn_rows: list[dict[str, Any]] = []
    lorwyn_lineage: list[dict[str, Any]] = []
    if semantic_certification["simulation_authorized"]:
        return_parts = [monthly_log_returns([price for _, price in history_by_id[member]]) for member in members_with_history]
        distribution = np.concatenate([part for part in return_parts if part.size])
        if distribution.size == 0:
            failures.append("LORWYN_CERTIFIED_COMPARABLE_RETURN_DISTRIBUTION_EMPTY")
        else:
            drift = float(np.median(distribution))
            for horizon in lorwyn_cfg["horizons_days"]:
                method = lorwyn_cfg["method_ids"][str(horizon)]
                simulations = int(lorwyn_cfg["simulation_count"])
                steps = max(1, int(math.ceil(int(horizon) / 30.4375)))
                rng = np.random.default_rng(deterministic_seed(contract["snapshot_id"], resolved_id, int(horizon)))
                draws = rng.choice(distribution, size=(simulations, steps), replace=True)
                decay_scale = {90: 18.0, 180: 15.0, 365: 12.0, 730: 10.0, 1095: 8.0, 1825: 6.0}[int(horizon)]
                regime_scale = {90: 1.00, 180: 0.95, 365: 0.90, 730: 0.78, 1095: 0.67, 1825: 0.55}[int(horizon)]
                decay = np.exp(-np.arange(steps, dtype=float) / decay_scale)
                terminal = float(resolved_price) * np.exp(((draws - drift) + drift * decay * regime_scale).sum(axis=1))
                q10, q25, q50, q75, q90 = np.quantile(terminal, [0.10, 0.25, 0.50, 0.75, 0.90])
                forecast_row = {
                    "canonical_product_id": resolved_id,
                    "tcgplayer_product_id": resolved_tcgplayer_id,
                    "product_name": clean(resolved_row.get(name_field)),
                    "horizon_days": int(horizon),
                    "explicit_method_id": method,
                    "current_price": round(float(resolved_price), 6),
                    "p10_price": round(float(q10), 6),
                    "p25_price": round(float(q25), 6),
                    "median_price": round(float(q50), 6),
                    "p75_price": round(float(q75), 6),
                    "p90_price": round(float(q90), 6),
                    "mean_price": round(float(np.mean(terminal)), 6),
                    "median_expected_return": round(float(q50 / float(resolved_price) - 1.0), 6),
                    "probability_of_loss": round(float(np.mean(terminal < float(resolved_price))), 6),
                    "probability_of_50pct_gain": round(float(np.mean(terminal >= float(resolved_price) * 1.5)), 6),
                    "probability_of_doubling": round(float(np.mean(terminal >= float(resolved_price) * 2.0)), 6),
                    "simulation_count": simulations,
                    "comparable_products_used": len(members_with_history),
                    "comparable_product_ids": "|".join(members_with_history),
                    "supply_status": lorwyn_cfg["supply_status"],
                    "supply_overlay_status": lorwyn_cfg["supply_overlay_status"],
                    "forecast_status": lorwyn_cfg["forecast_status"],
                    "current_ebay_data_used": False,
                    "semantic_certification_status": semantic_certification["status"],
                    "production_forecast_authorized": False,
                    "ranking_authorized": False,
                    "purchase_recommendation_authorized": False,
                }
                lorwyn_rows.append(forecast_row)
                lorwyn_lineage.append({
                    "canonical_product_id": resolved_id,
                    "product_name": clean(resolved_row.get(name_field)),
                    "horizon_days": int(horizon),
                    "forecast_source": "AUTHORITY_BOUND_LORWYN_REBUILD",
                    "forecast_row_fingerprint": row_fingerprint(forecast_row, ["canonical_product_id", "horizon_days", "explicit_method_id", "current_price", "median_price"]),
                    "identity_authority_path": contract["authorities"]["product_and_current_price"],
                    "identity_authority_sha256": source_hashes["product_and_current_price"],
                    "authority_row_fingerprint": semantic_certification["authority_row_fingerprint"],
                    "current_price_authority_path": contract["authorities"]["product_and_current_price"],
                    "current_price_authority_sha256": source_hashes["product_and_current_price"],
                    "history_authority_path": contract["authorities"]["historical_observations"],
                    "history_authority_sha256": source_hashes["historical_observations"],
                    "comparable_authority_path": contract["authorities"]["comparable_pool"],
                    "comparable_authority_sha256": source_hashes["comparable_pool"],
                    "semantic_certification_path": str(semantic_path.relative_to(ROOT)).replace("\\", "/"),
                    "semantic_certification_sha256": sha256_file(semantic_path),
                    "join_key": "canonical_product_id",
                    "standard_version": "MTG_FORECASTING_STANDARD_1.0.0",
                    "lineage_closed": True,
                })
    else:
        failures.append("LORWYN_PRE_SIMULATION_SEMANTIC_CERTIFICATION_FAILED")

    if len(lorwyn_rows) != 6:
        failures.append(f"LORWYN_FORECAST_ROW_COUNT:{len(lorwyn_rows)}")

    integrated = [dict(row) for row in base_rows] + [dict(row) for row in lorwyn_rows]
    integrated_keys = Counter((clean(row.get("canonical_product_id")), int(float(clean(row.get("horizon_days")) or 0))) for row in integrated)
    integrated_ids = {key[0] for key in integrated_keys}
    if len(integrated) != int(contract["required_final_forecast_rows"]):
        failures.append(f"FINAL_FORECAST_ROW_COUNT:{len(integrated)}")
    if len(integrated_ids) != int(contract["required_final_forecast_products"]):
        failures.append(f"FINAL_FORECAST_PRODUCT_COUNT:{len(integrated_ids)}")
    if len(integrated_keys) != int(contract["required_final_forecast_rows"]) or any(count != 1 for count in integrated_keys.values()):
        failures.append("FINAL_PRODUCT_HORIZON_KEY_FAILURE")

    base_lineage: list[dict[str, Any]] = []
    for audit_row in base_forecast_audit:
        cid = audit_row["canonical_product_id"]
        authority_row = current_by_id[cid]
        base_lineage.append({
            "canonical_product_id": cid,
            "product_name": audit_row["product_name"],
            "horizon_days": audit_row["horizon_days"],
            "forecast_source": "RECERTIFIED_BASE_PROBABILISTIC_FORECAST",
            "forecast_row_fingerprint": audit_row["forecast_row_fingerprint"],
            "identity_authority_path": contract["authorities"]["product_and_current_price"],
            "identity_authority_sha256": source_hashes["product_and_current_price"],
            "authority_row_fingerprint": row_fingerprint(authority_row, [cid_field, tcg_field or cid_field, name_field, price_field]),
            "current_price_authority_path": contract["authorities"]["product_and_current_price"],
            "current_price_authority_sha256": source_hashes["product_and_current_price"],
            "history_authority_path": contract["authorities"]["historical_observations"],
            "history_authority_sha256": source_hashes["historical_observations"],
            "comparable_authority_path": contract["authorities"]["comparable_pool"],
            "comparable_authority_sha256": source_hashes["comparable_pool"],
            "semantic_certification_path": "BASE_FORECAST_RECERTIFICATION_AUDIT",
            "semantic_certification_sha256": "",
            "join_key": "canonical_product_id",
            "standard_version": "MTG_FORECASTING_STANDARD_1.0.0",
            "lineage_closed": audit_row["recertified"],
        })

    lineage_rows = base_lineage + lorwyn_lineage
    if len(lineage_rows) != int(contract["required_final_forecast_rows"]):
        failures.append(f"LINEAGE_ROW_COUNT:{len(lineage_rows)}")
    if any(not bool(row["lineage_closed"]) for row in lineage_rows):
        failures.append("FORECAST_LINEAGE_NOT_CLOSED")

    blocked = [row for row in coverage_rows if clean(row.get("coverage_status")) == "GOVERNED_BLOCKED_NO_FORECAST"]
    blocked_final = [row for row in blocked if norm(row.get("product_name")) != norm(requested_name)]
    if len(blocked_final) != int(contract["required_blocked_rows"]):
        failures.append(f"FINAL_BLOCKED_ROW_COUNT:{len(blocked_final)}")

    write_csv(OUTPUT / "collector_50_product_identity_reconciliation.csv", reconciliation_rows)
    write_csv(OUTPUT / "collector_unknown_identity_rows.csv", unknown_identity_rows)
    write_csv(OUTPUT / "collector_name_identity_mismatches.csv", name_mismatch_rows)
    write_csv(OUTPUT / "collector_comparable_identity_failures.csv", comparable_unknown)
    write_csv(OUTPUT / "collector_product_specific_contract_identity_violations.csv", manual_identity_violations)
    write_csv(OUTPUT / "collector_base_48_forecast_identity_recertification.csv", base_forecast_audit)
    write_csv(OUTPUT / "collector_early_awareness_identity_recertification.csv", early_audit_rows)
    write_csv(OUTPUT / "collector_invalidated_output_ledger.csv", invalidation_rows)
    write_csv(OUTPUT / "collector_authority_bound_lorwyn_forecasts.csv", lorwyn_rows)
    write_csv(OUTPUT / "collector_final_authority_bound_49_product_forecasts.csv", integrated)
    write_csv(OUTPUT / "collector_final_authority_bound_blocked_horizons.csv", blocked_final)
    write_csv(OUTPUT / "collector_final_forecast_source_identity_lineage_manifest.csv", lineage_rows)

    status = contract["expected_status"] if not failures else "FAIL_COLLECTOR_CANONICAL_IDENTITY_LINEAGE_RECERTIFICATION"
    summary = {
        "contract_name": contract["contract_name"],
        "contract_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "governed_products": len(current_by_id),
        "products_reconciled": sum(bool(row["identity_reconciled"]) for row in reconciliation_rows),
        "manual_identity_assertion_violations": len(manual_identity_violations),
        "unknown_identity_rows": len(unknown_identity_rows),
        "name_identity_mismatches": len(name_mismatch_rows),
        "base_forecast_products": len(base_ids),
        "base_forecast_rows": len(base_rows),
        "base_forecast_rows_recertified": sum(bool(row["recertified"]) for row in base_forecast_audit),
        "early_awareness_rows_audited": len(early_audit_rows),
        "early_awareness_rows_recertified": sum(bool(row["identity_reconciled"]) for row in early_audit_rows),
        "invalidated_outputs_deleted": sum(bool(row["deleted"]) for row in invalidation_rows),
        "lorwyn_resolved_canonical_product_id": resolved_id,
        "lorwyn_pre_simulation_semantic_status": semantic_certification["status"],
        "lorwyn_forecast_rows": len(lorwyn_rows),
        "final_forecast_products": len(integrated_ids),
        "final_forecast_rows": len(integrated),
        "blocked_rows": len(blocked_final),
        "coverage_rows": len(integrated) + len(blocked_final),
        "lineage_rows": len(lineage_rows),
        "lineage_rows_closed": sum(bool(row["lineage_closed"]) for row in lineage_rows),
        "source_hashes": source_hashes,
        "production_forecast_authorized": False,
        "ranking_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": status,
    }
    (OUTPUT / "collector_canonical_identity_lineage_recertification_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
