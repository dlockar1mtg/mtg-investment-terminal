from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.delivery.governed_publisher import (
    PublishArtifact,
    publish_package,
)

CONSUMPTION = (
    ROOT / "data/operations/mtg_governed_consumption_integration"
)
VALUATION = ROOT / "data/operations/mtg_universal_market_valuation"
OUTPUT = ROOT / "data/operations/mtg_terminal_delivery"

COMMON = (
    "canonical_product_id",
    "canonical_product_name",
    "valuation_state",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    parser.add_argument("--package-id")
    args = parser.parse_args()

    package_id = args.package_id or (
        "mtg-governed-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )

    artifacts = [
        PublishArtifact(
            CONSUMPTION / "universal_mtg_consumption_interface.csv",
            "universal_mtg_consumption_interface.csv",
            COMMON,
            1141,
        ),
        PublishArtifact(
            CONSUMPTION / "universal_mtg_dashboard_consumption.csv",
            "dashboard.csv",
            COMMON,
        ),
        PublishArtifact(
            CONSUMPTION / "universal_mtg_governed_forecasts.csv",
            "forecasts.csv",
            COMMON + ("governed_forecast_eligible",),
        ),
        PublishArtifact(
            CONSUMPTION / "universal_mtg_governed_recommendations.csv",
            "recommendations.csv",
            COMMON + ("governed_recommendation_eligible",),
        ),
        PublishArtifact(
            CONSUMPTION / "universal_mtg_guarded_ranking.csv",
            "rankings.csv",
            COMMON + ("guarded_rank", "guarded_rank_score"),
        ),
        PublishArtifact(
            CONSUMPTION / "universal_mtg_consumption_exclusions.csv",
            "exclusions.csv",
            COMMON + ("suppression_reason",),
        ),
        PublishArtifact(
            VALUATION / "universal_mtg_market_provenance.csv",
            "market_provenance.csv",
            ("canonical_product_id", "selected_source_type"),
            1141,
        ),
        PublishArtifact(
            CONSUMPTION / "universal_mtg_consumption_summary.json",
            "consumption_summary.json",
        ),
        PublishArtifact(
            VALUATION / "universal_mtg_market_valuation_summary.json",
            "valuation_summary.json",
        ),
    ]

    manifest = publish_package(
        args.output_root.resolve(),
        package_id,
        artifacts,
        {
            "interface_name": "mtg-governed-terminal-delivery",
            "interface_version": "1.0",
            "currency": "USD",
            "governed_product_count": 1141,
            "current_asking_is_sold_history": False,
            "current_asking_model_eligible": False,
        },
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
