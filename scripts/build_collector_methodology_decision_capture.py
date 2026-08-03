from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_methodology_decision_capture_v1.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = load_json(CONFIG)
    sensitivity_root = ROOT / cfg["inputs"]["sensitivity_root"]
    owner_root = ROOT / cfg["inputs"]["owner_package_root"]
    out_dir = ROOT / cfg["output_directory"]
    out_dir.mkdir(parents=True, exist_ok=True)

    required = {
        "sensitivity": sensitivity_root / "collector_methodology_sensitivity_product_review.csv",
        "decisions": owner_root / "collector_methodology_owner_decision_register.csv",
        "recommended": owner_root / "collector_recommended_candidate_methodology.json",
    }
    failures = [f"missing_{name}:{path}" for name, path in required.items() if not path.exists()]
    if failures:
        result = {"status": "FAIL", "failure_count": len(failures), "failures": failures}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    sensitivity = pd.read_csv(required["sensitivity"], low_memory=False)
    decisions = pd.read_csv(required["decisions"], low_memory=False)
    recommended = load_json(required["recommended"])

    comparable = sensitivity[sensitivity["forecast_method_route"].astype(str) == "COMPARABLE_PRODUCT_ADJUSTED"].copy()
    comparable["baseline_base_annual_rate"] = pd.to_numeric(comparable["baseline_base_annual_rate"], errors="coerce")
    comparable["variant_baseline_weighted_mean"] = pd.to_numeric(comparable["variant_baseline_weighted_mean"], errors="coerce")
    comparable["unresolved_non_peer_adjustment"] = comparable["baseline_base_annual_rate"] - comparable["variant_baseline_weighted_mean"]
    comparable["adjustment_basis_status"] = "UNRESOLVED_SOURCE_DOCUMENTATION_REQUIRED"
    comparable["adjustment_authorized"] = False
    comparable[[
        "canonical_tcgplayer_product_id", "product_name", "forecast_method_route",
        "baseline_base_annual_rate", "variant_baseline_weighted_mean",
        "unresolved_non_peer_adjustment", "adjustment_basis_status", "adjustment_authorized"
    ]].to_csv(out_dir / "collector_comparable_baseline_adjustment_reconciliation.csv", index=False)

    grouped = comparable.assign(
        adjustment_rounded=comparable["unresolved_non_peer_adjustment"].round(4)
    ).groupby("adjustment_rounded", dropna=False).agg(
        product_count=("canonical_tcgplayer_product_id", "count"),
        product_examples=("product_name", lambda s: " | ".join(list(s.astype(str))[:5])),
    ).reset_index()
    grouped["source_status"] = "UNRESOLVED_SOURCE_DOCUMENTATION_REQUIRED"
    grouped.to_csv(out_dir / "collector_comparable_adjustment_groups.csv", index=False)

    ballot = decisions.copy()
    if "owner_decision_status" not in ballot.columns:
        ballot["owner_decision_status"] = "PENDING_OWNER_DECISION"
    ballot["owner_selected_option"] = ""
    ballot["owner_rationale"] = ""
    ballot["owner_decided_at_utc"] = ""
    ballot["activation_authorized"] = False
    ballot.to_csv(out_dir / "collector_methodology_owner_decision_ballot.csv", index=False)

    capture = dict(recommended)
    capture["status"] = "INACTIVE_OWNER_DECISION_REQUIRED"
    capture["all_six_owner_decisions_complete"] = False
    capture["baseline_adjustment_reconciled"] = False
    capture["candidate_projection_authorized"] = False
    capture["production_projection_authorized"] = False
    capture["purchase_recommendation_authorized"] = False
    capture["automatic_model_update_allowed"] = False
    (out_dir / "collector_methodology_decision_capture_specification.json").write_text(
        json.dumps(capture, indent=2, sort_keys=True), encoding="utf-8"
    )

    adjustment_values = sorted({round(float(v), 4) for v in comparable["unresolved_non_peer_adjustment"].dropna()})
    pending_count = int((ballot["owner_decision_status"].astype(str) != "OWNER_APPROVED").sum())
    summary = {
        "audit_name": "Collector Methodology Decision Capture",
        "audit_version": "1.0.0",
        "status": "PASS",
        "product_count": int(len(sensitivity)),
        "comparable_product_count": int(len(comparable)),
        "decision_count": int(len(ballot)),
        "pending_owner_decision_count": pending_count,
        "observed_unresolved_adjustment_values": adjustment_values,
        "baseline_adjustment_reconciled": False,
        "all_six_owner_decisions_complete": False,
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "failure_count": 0,
        "failures": [],
        "governing_note": "This batch records the six owner decisions and isolates the baseline-minus-peer-only adjustment without assigning it an unsupported meaning. No methodology is activated."
    }
    (out_dir / "collector_methodology_decision_capture_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
