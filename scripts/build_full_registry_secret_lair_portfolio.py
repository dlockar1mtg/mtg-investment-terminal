from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from terminal2.portfolio.secret_lair_full_registry import build_owned_portfolio


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-registry", type=Path, required=True)
    parser.add_argument("--full-evaluation", type=Path, required=True)
    parser.add_argument("--owned-source", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--default-unspecified-finish",
        default="NONFOIL",
        choices=(
            "NONFOIL",
            "FOIL",
            "RAINBOW_FOIL",
            "GALAXY_FOIL",
            "ETCHED_FOIL",
            "RAISED_FOIL",
        ),
    )
    args = parser.parse_args()

    result = build_owned_portfolio(
        registry_path=args.full_registry,
        evaluation_path=args.full_evaluation,
        owned_source_path=args.owned_source,
        output_root=args.output_root,
        default_unspecified_finish=args.default_unspecified_finish,
    )

    print("SECRET LAIR FULL-REGISTRY PORTFOLIO INTEGRATION: COMPLETE")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
