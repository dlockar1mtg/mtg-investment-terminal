from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.build_full_secret_lair_model_evaluation import build as build_full_evaluation
from terminal2.portfolio.secret_lair_full_registry import build_owned_portfolio


def run_refresh(
    admission_ledger: Path,
    owned_source: Path,
    output_root: Path,
    default_unspecified_finish: str = "NONFOIL",
) -> dict[str, object]:
    evaluation_root = output_root / "full_model_evaluation"
    portfolio_root = output_root / "owned_portfolio"

    evaluation = build_full_evaluation(admission_ledger, evaluation_root)
    if evaluation.get("status") != "CERTIFIED":
        result = {
            "status": "FAILED",
            "stage": "FULL_MODEL_EVALUATION",
            "evaluation": evaluation,
            "quota_calls": 0,
        }
    else:
        portfolio = build_owned_portfolio(
            registry_path=evaluation_root / "secret_lair_full_product_registry.csv",
            evaluation_path=evaluation_root / "secret_lair_full_model_evaluation.csv",
            owned_source_path=owned_source,
            output_root=portfolio_root,
            default_unspecified_finish=default_unspecified_finish,
        )
        result = {
            "status": "CERTIFIED" if portfolio.get("status") == "CERTIFIED" else "FAILED",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "evaluation": evaluation,
            "portfolio": portfolio,
            "quota_calls": 0,
            "outputs": {
                "evaluation_root": str(evaluation_root.resolve()),
                "portfolio_root": str(portfolio_root.resolve()),
            },
        }

    output_root.mkdir(parents=True, exist_ok=True)
    manifest = output_root / "secret_lair_production_refresh_manifest.json"
    manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("SECRET LAIR PRODUCTION REFRESH: COMPLETE")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admission-ledger", type=Path, required=True)
    parser.add_argument("--owned-source", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--default-unspecified-finish",
        default="NONFOIL",
        choices=("NONFOIL", "FOIL", "RAINBOW_FOIL", "GALAXY_FOIL", "ETCHED_FOIL", "RAISED_FOIL"),
    )
    args = parser.parse_args()
    run_refresh(
        admission_ledger=args.admission_ledger,
        owned_source=args.owned_source,
        output_root=args.output_root,
        default_unspecified_finish=args.default_unspecified_finish,
    )


if __name__ == "__main__":
    main()
