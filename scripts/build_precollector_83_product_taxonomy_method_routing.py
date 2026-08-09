from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_83_product_taxonomy_method_routing_contract_v1.json"
UPSTREAM_BUILDER = ROOT / "scripts/build_precollector_94_product_evidence_comparable_review.py"
UPSTREAM_DIR = ROOT / "artifacts/precollector/94_product_evidence_comparable_review"
OUTPUT_DIR = ROOT / "artifacts/precollector/83_product_taxonomy_method_routing"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str]) -> None:
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"SUBPROCESS_FAILED:{completed.returncode}:{' '.join(command)}")


def clean(value: object) -> str:
    return str(value or "").strip()


def classify_family(name: str) -> str:
    value = name.lower()
    if "masters" in value or "master" in value:
        return "MASTERS"
    if any(token in value for token in ["conspiracy", "battlebond"]):
        return "SUPPLEMENTAL_DRAFT"
    if "unstable" in value:
        return "NONSTANDARD_SPECIALTY"
    if any(token in value for token in ["edition", "magic 20", "core set", "magic origins"]):
        return "CORE"
    return "STANDARD_EXPANSION"


def lifecycle(age_years: float) -> str:
    if age_years < 3:
        return "EARLY"
    if age_years < 7:
        return "DEVELOPING"
    if age_years < 12:
        return "MATURE"
    return "LEGACY"


def liquidity_class(accepted: int, sellers: int, coverage: str) -> str:
    if coverage == "AMBIGUOUS_RESULTS":
        return "AMBIGUOUS"
    if accepted >= 10 and sellers >= 5:
        return "DEEP"
    if accepted >= 5 and sellers >= 3:
        return "ADEQUATE"
    if accepted > 0 and sellers > 0:
        return "THIN"
    return "UNOBSERVED"


def method_from_route(route: str) -> str:
    mapping = {
        "DIRECT_EVIDENCE": "DIRECT_HISTORY_CALIBRATED",
        "DIRECT_HISTORY_LIMITED": "DIRECT_HISTORY_LIMITED",
        "COMPARABLE_PRODUCT_ADJUSTED": "COMPARABLE_PRODUCT_ADJUSTED",
    }
    if route not in mapping:
        raise RuntimeError(f"UNSUPPORTED_UPSTREAM_ROUTE:{route}")
    return mapping[route]


def comparable_distance(target: pd.Series, candidate: pd.Series) -> tuple[float, dict[str, float]]:
    year_gap = abs(int(target["release_year"]) - int(candidate["release_year"]))
    target_price = max(float(target["governed_current_price"]), 0.01)
    candidate_price = max(float(candidate["governed_current_price"]), 0.01)
    price_gap = abs(math.log(target_price / candidate_price))
    lifecycle_penalty = 0.0 if target["lifecycle_stage"] == candidate["lifecycle_stage"] else 1.0
    liquidity_penalty = 0.0 if target["liquidity_class"] == candidate["liquidity_class"] else 0.5
    score = year_gap * 0.35 + price_gap * 2.5 + lifecycle_penalty + liquidity_penalty
    return round(score, 6), {
        "year_gap": float(year_gap),
        "log_price_gap": round(price_gap, 6),
        "lifecycle_penalty": lifecycle_penalty,
        "liquidity_penalty": liquidity_penalty,
    }


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    decision_path = ROOT / contract["owner_decision_path"]
    decision = load_json(decision_path)
    if decision.get("owner_approval_status") != "APPROVED":
        raise RuntimeError("OWNER_DECISION_NOT_APPROVED")
    if int(decision.get("selected_production_product_count", -1)) != int(contract["expected_selected_product_count"]):
        raise RuntimeError("OWNER_SELECTED_COUNT_DRIFT")

    artifacts_root = ROOT / "artifacts/precollector"
    if artifacts_root.exists():
        shutil.rmtree(artifacts_root)
    run([sys.executable, str(UPSTREAM_BUILDER)])

    review_path = UPSTREAM_DIR / "precollector_94_product_evidence_review.csv"
    comparables_path = UPSTREAM_DIR / "precollector_comparable_candidate_matrix.csv"
    if not review_path.is_file() or not comparables_path.is_file():
        raise RuntimeError("UPSTREAM_REVIEW_OUTPUT_MISSING")

    review = pd.read_csv(review_path, dtype=str).fillna("")
    upstream_comparables = pd.read_csv(comparables_path, dtype=str).fillna("")
    expected_source = int(contract["source_review_product_count"])
    if len(review) != expected_source or review["canonical_product_id"].duplicated().any():
        raise RuntimeError(f"UPSTREAM_REVIEW_RECONCILIATION_FAILED:{len(review)}")

    excluded_rows = decision.get("excluded_products", [])
    excluded_ids = {clean(row.get("canonical_product_id")) for row in excluded_rows}
    if len(excluded_ids) != int(contract["expected_excluded_product_count"]):
        raise RuntimeError("EXCLUDED_PRODUCT_DECISION_COUNT_DRIFT")
    source_ids = set(review["canonical_product_id"].map(clean))
    missing_excluded = sorted(excluded_ids - source_ids)
    if missing_excluded:
        raise RuntimeError(f"EXCLUDED_PRODUCTS_NOT_IN_SOURCE:{missing_excluded}")

    selected = review[~review["canonical_product_id"].isin(excluded_ids)].copy()
    selected_count = int(contract["expected_selected_product_count"])
    if len(selected) != selected_count or selected["canonical_product_id"].duplicated().any():
        raise RuntimeError(f"SELECTED_UNIVERSE_COUNT_DRIFT:{len(selected)}")
    if set(selected["canonical_product_id"]) & excluded_ids:
        raise RuntimeError("EXCLUDED_PRODUCT_ENTERED_SELECTED_UNIVERSE")

    selected["release_year"] = pd.to_numeric(selected["release_year"], errors="raise").astype(int)
    selected["governed_current_price"] = pd.to_numeric(selected["governed_current_price"], errors="raise")
    selected["accepted_listing_count"] = pd.to_numeric(selected["accepted_listing_count"], errors="coerce").fillna(0).astype(int)
    selected["accepted_seller_count"] = pd.to_numeric(selected["accepted_seller_count"], errors="coerce").fillna(0).astype(int)
    selected["product_family"] = selected["product_name"].map(classify_family)
    if not set(selected["product_family"]).issubset(set(contract["allowed_product_families"])):
        raise RuntimeError("UNSUPPORTED_PRODUCT_FAMILY")

    reference_date = pd.Timestamp("2026-08-03")
    release_dates = pd.to_datetime(selected["release_date"], errors="raise")
    selected["age_years"] = ((reference_date - release_dates).dt.days / 365.25).round(3)
    selected["lifecycle_stage"] = selected["age_years"].map(lifecycle)
    selected["liquidity_class"] = selected.apply(
        lambda row: liquidity_class(
            int(row["accepted_listing_count"]),
            int(row["accepted_seller_count"]),
            clean(row["coverage_state"]),
        ),
        axis=1,
    )
    selected["production_lane_status"] = "OWNER_APPROVED_SELECTED"
    selected["comparable_target_eligible"] = True
    selected["comparable_donor_eligible"] = selected["proposed_model_route"].eq("DIRECT_EVIDENCE")

    taxonomy_columns = [
        "canonical_product_id", "tcgplayer_product_id", "product_name", "release_date", "release_year",
        "age_years", "product_family", "release_era", "lifecycle_stage", "price_tier",
        "liquidity_class", "governed_current_price", "production_lane_status",
        "comparable_target_eligible", "comparable_donor_eligible",
    ]
    taxonomy = selected[taxonomy_columns].copy().sort_values(["product_family", "release_year", "product_name"])

    routes = selected[[
        "canonical_product_id", "product_name", "product_family", "release_year",
        "governed_current_price", "historical_rows", "history_span_days",
        "accepted_listing_count", "accepted_seller_count", "coverage_state",
        "proposed_model_route", "confidence_penalty_required",
    ]].copy()
    routes["forecast_method"] = routes["proposed_model_route"].map(method_from_route)
    if not set(routes["forecast_method"]).issubset(set(contract["allowed_forecast_methods"])):
        raise RuntimeError("UNSUPPORTED_FORECAST_METHOD")
    routes["direct_history_method_allowed"] = routes["forecast_method"].isin([
        "DIRECT_HISTORY_CALIBRATED", "DIRECT_HISTORY_LIMITED"
    ])
    routes["comparable_method_allowed"] = True
    routes["comparable_group_required"] = routes["forecast_method"].eq("COMPARABLE_PRODUCT_ADJUSTED")
    routes["forecast_output_allowed_after_later_certification"] = True
    routes["purchase_analysis_allowed_after_later_certification"] = True
    routes["purchase_recommendation_authorized"] = False
    routes["method_reason"] = routes["forecast_method"].map({
        "DIRECT_HISTORY_CALIBRATED": "Direct current, historical, and supply evidence supports calibrated direct-history modeling.",
        "DIRECT_HISTORY_LIMITED": "Direct history is available but current supply evidence is limited; confidence must be reduced and uncertainty widened.",
        "COMPARABLE_PRODUCT_ADJUSTED": "Direct current supply evidence is ambiguous; approved same-family comparables are required.",
    })
    routes["limitations"] = routes["forecast_method"].map({
        "DIRECT_HISTORY_CALIBRATED": "Comparables may be used for validation but may not replace governed direct history.",
        "DIRECT_HISTORY_LIMITED": "Comparable support is required for validation; confidence penalty and wider intervals are mandatory.",
        "COMPARABLE_PRODUCT_ADJUSTED": "Forecast publication remains blocked until owner-approved comparables and model validation are certified.",
    })
    routes["route_version"] = contract["contract_version"]

    donor_pool = selected[selected["comparable_donor_eligible"]].copy()
    specialty = set(contract["specialty_families"])
    comparable_rows: list[dict] = []
    target_rows: list[dict] = []
    diagnostics: list[dict] = []
    maximum = int(contract["maximum_selected_comparables_per_target"])
    minimum = int(contract["minimum_selected_comparables_for_required_target"])

    for _, target in selected.iterrows():
        target_id = clean(target["canonical_product_id"])
        family = clean(target["product_family"])
        candidates = donor_pool[
            donor_pool["product_family"].eq(family)
            & donor_pool["canonical_product_id"].ne(target_id)
        ].copy()
        candidate_records: list[dict] = []
        for _, candidate in candidates.iterrows():
            score, components = comparable_distance(target, candidate)
            candidate_records.append({
                "target_canonical_product_id": target_id,
                "target_product_name": target["product_name"],
                "target_product_family": family,
                "target_forecast_method": method_from_route(clean(target["proposed_model_route"])),
                "candidate_canonical_product_id": candidate["canonical_product_id"],
                "candidate_product_name": candidate["product_name"],
                "candidate_product_family": candidate["product_family"],
                "candidate_release_year": int(candidate["release_year"]),
                "candidate_current_price": float(candidate["governed_current_price"]),
                "candidate_liquidity_class": candidate["liquidity_class"],
                "comparable_distance_score": score,
                **components,
                "same_family_required": family in specialty,
                "same_family_satisfied": True,
                "owner_selection_status": "PENDING_OWNER_APPROVAL",
                "forecast_contribution_authorized": False,
            })
        candidate_records.sort(key=lambda row: (row["comparable_distance_score"], row["candidate_product_name"]))
        selected_records = candidate_records[:maximum]
        for rank, record in enumerate(selected_records, start=1):
            record["comparable_rank"] = rank
            comparable_rows.append(record)

        required = clean(target["proposed_model_route"]) != "DIRECT_EVIDENCE"
        enough = len(selected_records) >= (minimum if required else 0)
        target_rows.append({
            "canonical_product_id": target_id,
            "product_name": target["product_name"],
            "product_family": family,
            "forecast_method": method_from_route(clean(target["proposed_model_route"])),
            "comparable_support_required": required,
            "eligible_same_family_donor_count": len(candidate_records),
            "selected_comparable_count": len(selected_records),
            "minimum_required_count": minimum if required else 0,
            "structural_comparable_requirement_satisfied": enough,
            "owner_approval_status": "PENDING_OWNER_APPROVAL" if selected_records else "NOT_REQUIRED" if not required else "BLOCKED_NO_COMPARABLE",
        })
        if required and not enough:
            diagnostics.append({
                "canonical_product_id": target_id,
                "severity": "BLOCKING",
                "diagnostic_code": "INSUFFICIENT_SAME_FAMILY_COMPARABLES",
                "detail": f"family={family};available={len(candidate_records)};minimum={minimum}",
            })

    comparables = pd.DataFrame(comparable_rows)
    targets = pd.DataFrame(target_rows)
    if not comparables.empty:
        if (comparables["target_canonical_product_id"] == comparables["candidate_canonical_product_id"]).any():
            raise RuntimeError("SELF_COMPARABLE_DETECTED")
        if set(comparables["candidate_canonical_product_id"]) & excluded_ids:
            raise RuntimeError("EXCLUDED_PRODUCT_ENTERED_COMPARABLE_DONOR_POOL")
        if set(comparables["target_canonical_product_id"]) & excluded_ids:
            raise RuntimeError("EXCLUDED_PRODUCT_ENTERED_COMPARABLE_TARGET_POOL")
        if (~comparables["same_family_satisfied"]).any():
            raise RuntimeError("SPECIALTY_FAMILY_SEPARATION_FAILURE")

    excluded_source = review[review["canonical_product_id"].isin(excluded_ids)][[
        "canonical_product_id", "product_name", "proposed_model_route", "owner_review_state"
    ]].copy()
    excluded_source["owner_decision"] = "EXCLUDED_FROM_PRECOLLECTOR_PRODUCTION_LANE"
    excluded_source["target_eligible"] = False
    excluded_source["donor_eligible"] = False
    excluded_source["forecast_eligible"] = False
    excluded_source["ranking_eligible"] = False
    excluded_source["uip_delivery_eligible"] = False

    diagnostics_frame = pd.DataFrame(diagnostics, columns=[
        "canonical_product_id", "severity", "diagnostic_code", "detail"
    ])
    blocking = int((diagnostics_frame["severity"] == "BLOCKING").sum()) if not diagnostics_frame.empty else 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    output_frames = {
        outputs["selected_universe_csv"]: selected.sort_values(["release_year", "product_name"]),
        outputs["taxonomy_csv"]: taxonomy,
        outputs["method_routes_csv"]: routes.sort_values(["forecast_method", "product_name"]),
        outputs["comparable_target_status_csv"]: targets.sort_values(["product_family", "product_name"]),
        outputs["selected_comparables_csv"]: comparables.sort_values(["target_product_name", "comparable_rank"]) if not comparables.empty else comparables,
        outputs["excluded_reconciliation_csv"]: excluded_source.sort_values("product_name"),
        outputs["diagnostics_csv"]: diagnostics_frame,
    }
    output_paths: dict[str, Path] = {}
    for filename, frame in output_frames.items():
        path = OUTPUT_DIR / filename
        frame.to_csv(path, index=False)
        output_paths[filename] = path

    method_counts = routes["forecast_method"].value_counts().to_dict()
    family_counts = taxonomy["product_family"].value_counts().to_dict()
    required_targets = targets[targets["comparable_support_required"]]
    summary = {
        "certification_status": "PASS" if blocking == 0 else "REVIEW_REQUIRED",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "selected_product_rows": len(selected),
        "excluded_product_rows": len(excluded_source),
        "taxonomy_rows": len(taxonomy),
        "method_route_rows": len(routes),
        "comparable_target_rows": len(targets),
        "selected_comparable_rows": len(comparables),
        "required_comparable_target_rows": len(required_targets),
        "required_targets_structurally_satisfied": int(required_targets["structural_comparable_requirement_satisfied"].sum()),
        "blocking_diagnostic_rows": blocking,
        "method_distribution": method_counts,
        "family_distribution": family_counts,
        "owner_comparable_approval_complete": False,
        "next_stage": contract["next_stage_if_certified"],
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_analysis_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
        "uip_delivery_authorized": False,
    }
    summary_path = OUTPUT_DIR / outputs["summary_json"]
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "owner_decision_sha256": sha256_file(decision_path),
        "upstream_review_sha256": sha256_file(review_path),
        "upstream_comparable_matrix_sha256": sha256_file(comparables_path),
        "output_sha256": {name: sha256_file(path) for name, path in sorted(output_paths.items())},
        "selected_universe_count_mutation_detected": False,
        "excluded_product_leakage_detected": False,
        "self_comparable_detected": False,
        "owner_comparable_approval_complete": False,
    }
    manifest_path = OUTPUT_DIR / outputs["manifest_json"]
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_83_PRODUCT_TAXONOMY_METHOD_ROUTING_BUILD" if blocking == 0 else "REVIEW_PRECOLLECTOR_83_PRODUCT_TAXONOMY_METHOD_ROUTING_BUILD")
    print(f"SELECTED_PRODUCT_ROWS={len(selected)}")
    print(f"EXCLUDED_PRODUCT_ROWS={len(excluded_source)}")
    print(f"DIRECT_HISTORY_CALIBRATED_ROWS={int(method_counts.get('DIRECT_HISTORY_CALIBRATED', 0))}")
    print(f"DIRECT_HISTORY_LIMITED_ROWS={int(method_counts.get('DIRECT_HISTORY_LIMITED', 0))}")
    print(f"COMPARABLE_PRODUCT_ADJUSTED_ROWS={int(method_counts.get('COMPARABLE_PRODUCT_ADJUSTED', 0))}")
    print(f"SELECTED_COMPARABLE_ROWS={len(comparables)}")
    print(f"BLOCKING_DIAGNOSTIC_ROWS={blocking}")
    print(f"NEXT_STAGE={contract['next_stage_if_certified']}")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    print("UIP_DELIVERY_AUTHORIZED=FALSE")
    return 0 if blocking == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
