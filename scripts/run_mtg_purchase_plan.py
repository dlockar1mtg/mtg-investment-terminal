from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.market_sources.marketplace_purchase_planning import PurchasePolicy, write_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a whole-box MTG monthly purchase plan")
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--model-input", type=Path, required=True)
    parser.add_argument("--holdings", type=Path, default=ROOT / "data" / "terminal2" / "portfolio_holdings.csv")
    parser.add_argument("--monthly-capital", type=float, default=600.0)
    parser.add_argument("--reserve-pct", type=float, default=10.0)
    parser.add_argument("--max-units-per-product", type=int, default=2)
    parser.add_argument("--max-product-weight-pct", type=float, default=35.0)
    parser.add_argument("--bootstrap-max-product-weight-pct", type=float, default=100.0)
    parser.add_argument("--bootstrap-threshold", type=float, default=1200.0)
    parser.add_argument("--plan-output", type=Path, required=True)
    parser.add_argument("--projection-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    missing = [str(path.resolve()) for path in (args.decisions, args.model_input) if not path.is_file()]
    if missing:
        payload = {
            "status": "FAILED",
            "missing_inputs": missing,
            "reason_codes": ["MTG_PURCHASE_PLAN_INPUT_NOT_AVAILABLE"],
        }
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 1

    if args.monthly_capital < 0 or not 0 <= args.reserve_pct < 100:
        payload = {
            "status": "FAILED",
            "reason_codes": ["MTG_PURCHASE_PLAN_POLICY_INVALID"],
        }
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 1

    policy = PurchasePolicy(
        monthly_capital=args.monthly_capital,
        reserve_pct=args.reserve_pct,
        max_units_per_product=max(0, args.max_units_per_product),
        max_projected_product_weight_pct=args.max_product_weight_pct,
        bootstrap_max_projected_product_weight_pct=args.bootstrap_max_product_weight_pct,
        bootstrap_portfolio_value_threshold=args.bootstrap_threshold,
    )
    payload = write_outputs(
        args.decisions.resolve(),
        args.model_input.resolve(),
        args.holdings.resolve(),
        args.plan_output.resolve(),
        args.projection_output.resolve(),
        args.summary_output.resolve(),
        policy,
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("status") in {"PASS", "NO_ACTION"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
