from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

STANDARD_PATH = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "mtg_forecasting_standard_v1.json"
)

TRACEABILITY_PATH = (
    ROOT
    / "data"
    / "governance"
    / "mtg"
    / "standards"
    / "mtg_requirements_traceability_v1.csv"
)

STANDARD_DOCUMENT = (
    ROOT
    / "docs"
    / "standards"
    / "mtg"
    / "MTG_FORECASTING_STANDARD.md"
)

COLLECTOR_DOCUMENT = (
    ROOT
    / "docs"
    / "standards"
    / "mtg"
    / "lanes"
    / "COLLECTOR_BOOSTER_METHOD_SPECIFICATION.md"
)

PRE_COLLECTOR_DOCUMENT = (
    ROOT
    / "docs"
    / "standards"
    / "mtg"
    / "lanes"
    / "PRE_COLLECTOR_BOOSTER_METHOD_SPECIFICATION.md"
)

SECRET_LAIR_DOCUMENT = (
    ROOT
    / "docs"
    / "standards"
    / "mtg"
    / "lanes"
    / "SECRET_LAIR_METHOD_SPECIFICATION.md"
)


STANDARD = {
    "standard_name": "MTG Forecasting and Decision Standard",
    "standard_version": "1.0.0",
    "standard_status": "CANONICAL_BASELINE",
    "change_control": {
        "method_changes_require_approval": True,
        "threshold_changes_require_approval": True,
        "weight_changes_require_approval": True,
        "source_hierarchy_changes_require_approval": True,
        "product_universe_changes_require_governance": True,
        "material_changes_require_recertification": True,
    },
    "governing_principles": [
        "Every governed product receives an explicit method route or deferral reason.",
        "Insufficient direct history does not automatically prohibit forecasting.",
        "Comparable products are approved forecast evidence.",
        "Comparable forecasts must identify the comparables and selection basis.",
        "Direct-history quarantine applies to the method, not automatically to the product.",
        "Identity and current-price failures remain fail-closed.",
        "Confidence and uncertainty must reflect the evidence actually used.",
        "Forecast outputs must disclose method, evidence, limitations, and version.",
        "Passing automated tests is necessary but not sufficient for certification.",
        "Purchase authorization remains separate from forecast generation.",
    ],
    "forecast_horizons_years": [1, 3, 5],
    "scenario_names": [
        "DOWNSIDE",
        "BASE",
        "UPSIDE",
    ],
    "required_eligibility_fields": [
        "direct_history_method_allowed",
        "comparable_method_allowed",
        "forecast_output_allowed",
        "purchase_analysis_allowed",
        "purchase_recommendation_authorized",
    ],
    "prohibited_ambiguous_interpretations": {
        "direct_history_method_allowed_false": (
            "Must not be interpreted as all forecasting prohibited."
        ),
        "history_quarantined": (
            "Must not be interpreted as permanent product rejection."
        ),
    },
    "common_methods": [
        "DIRECT_HISTORY_CALIBRATED",
        "DIRECT_HISTORY_LIMITED",
        "COMPARABLE_PRODUCT_ADJUSTED",
        "FUNDAMENTAL_COMPARABLE_HYBRID",
        "DEFERRED_IDENTITY",
        "DEFERRED_MISSING_PRICE",
        "DEFERRED_INSUFFICIENT_EVIDENCE",
    ],
    "lanes": {
        "COLLECTOR_BOOSTER": {
            "lane_status": "IMPLEMENTATION_IN_PROGRESS",
            "supported_methods": [
                "DIRECT_HISTORY_CALIBRATED",
                "DIRECT_HISTORY_LIMITED",
                "COMPARABLE_PRODUCT_ADJUSTED",
                "FUNDAMENTAL_COMPARABLE_HYBRID",
                "DEFERRED_IDENTITY",
                "DEFERRED_MISSING_PRICE",
                "DEFERRED_INSUFFICIENT_EVIDENCE",
            ],
            "comparable_factors": [
                "sealed_product_configuration",
                "release_era",
                "lifecycle_stage",
                "print_structure",
                "supply_profile",
                "franchise_strength",
                "gameplay_demand",
                "premium_contents",
                "initial_price_band",
                "current_price_band",
                "liquidity",
                "reprint_exposure",
                "historical_market_behavior",
            ],
        },
        "PRE_COLLECTOR_BOOSTER": {
            "lane_status": "SPECIFICATION_REQUIRED",
            "supported_methods": [
                "DIRECT_HISTORY_CALIBRATED",
                "SPARSE_HISTORY_ROBUST",
                "COMPARABLE_ERA_ADJUSTED",
                "SUPPLY_SCARCITY_HYBRID",
                "DEFERRED_IDENTITY",
                "DEFERRED_PRICE_QUALITY",
                "DEFERRED_INSUFFICIENT_EVIDENCE",
            ],
            "lane_specific_factors": [
                "sealed_supply_survival",
                "product_configuration",
                "release_era",
                "observation_sparsity",
                "liquidity",
                "reprint_exposure",
                "nostalgia_demand",
                "set_significance",
            ],
        },
        "SECRET_LAIR": {
            "lane_status": "SPECIFICATION_REQUIRED",
            "supported_methods": [
                "DIRECT_SECONDARY_HISTORY",
                "COMPARABLE_DROP_ADJUSTED",
                "SINGLES_VALUE_ANCHORED",
                "IP_PREMIUM_HYBRID",
                "ARTIST_PREMIUM_HYBRID",
                "DEFERRED_CONFIGURATION",
                "DEFERRED_PRICE_QUALITY",
                "DEFERRED_INSUFFICIENT_EVIDENCE",
            ],
            "lane_specific_factors": [
                "foil_configuration",
                "drop_type",
                "card_count",
                "intellectual_property",
                "artist",
                "purchase_window",
                "print_to_demand_status",
                "bundle_status",
                "bonus_card_uncertainty",
                "singles_equivalent_value",
                "reprint_exposure",
                "release_recency",
                "liquidity",
            ],
        },
    },
    "required_product_output_fields": [
        "investment_product_id",
        "product_name",
        "product_lane",
        "identity_status",
        "current_price",
        "current_price_date",
        "forecast_method",
        "forecast_method_version",
        "method_reason",
        "direct_history_status",
        "direct_history_quality_band",
        "direct_history_observations",
        "comparable_group_id",
        "comparable_products_used",
        "comparable_selection_basis",
        "direct_history_weight",
        "comparable_weight",
        "fundamental_weight",
        "forecast_1y",
        "forecast_3y",
        "forecast_5y",
        "downside_1y",
        "base_1y",
        "upside_1y",
        "downside_3y",
        "base_3y",
        "upside_3y",
        "downside_5y",
        "base_5y",
        "upside_5y",
        "confidence_score",
        "confidence_class",
        "uncertainty_width",
        "liquidity_class",
        "limitations",
        "source_summary",
        "direct_history_method_allowed",
        "comparable_method_allowed",
        "forecast_output_allowed",
        "purchase_analysis_allowed",
        "purchase_recommendation_authorized",
    ],
}


REQUIREMENTS = [
    {
        "requirement_id": "MTG-STD-001",
        "lane": "ALL",
        "requirement": (
            "Every governed product must receive an explicit "
            "forecast method or deferred reason."
        ),
        "implementation_status": "NOT_IMPLEMENTED",
        "blocking": "true",
    },
    {
        "requirement_id": "MTG-STD-002",
        "lane": "ALL",
        "requirement": (
            "Comparable-product methodology is an approved "
            "forecast method."
        ),
        "implementation_status": "PARTIALLY_IMPLEMENTED",
        "blocking": "true",
    },
    {
        "requirement_id": "MTG-STD-003",
        "lane": "ALL",
        "requirement": (
            "Comparable forecasts must identify products used "
            "and the selection basis."
        ),
        "implementation_status": "NOT_IMPLEMENTED",
        "blocking": "true",
    },
    {
        "requirement_id": "MTG-STD-004",
        "lane": "ALL",
        "requirement": (
            "Direct-history eligibility must be distinct from "
            "total forecast eligibility."
        ),
        "implementation_status": "IMPLEMENTED_INCORRECTLY",
        "blocking": "true",
    },
    {
        "requirement_id": "MTG-STD-005",
        "lane": "ALL",
        "requirement": (
            "Forecast outputs must disclose method, version, "
            "confidence, limitations, and evidence."
        ),
        "implementation_status": "NOT_IMPLEMENTED",
        "blocking": "true",
    },
    {
        "requirement_id": "MTG-STD-006",
        "lane": "ALL",
        "requirement": (
            "Forecasts must provide 1-year, 3-year, and 5-year "
            "horizons."
        ),
        "implementation_status": "PARTIALLY_IMPLEMENTED",
        "blocking": "true",
    },
    {
        "requirement_id": "MTG-STD-007",
        "lane": "ALL",
        "requirement": (
            "Forecasts must provide downside, base, and upside "
            "scenarios."
        ),
        "implementation_status": "PARTIALLY_IMPLEMENTED",
        "blocking": "true",
    },
    {
        "requirement_id": "MTG-STD-008",
        "lane": "ALL",
        "requirement": (
            "Identity and executable current-price failures "
            "must remain fail-closed."
        ),
        "implementation_status": "PARTIALLY_IMPLEMENTED",
        "blocking": "true",
    },
    {
        "requirement_id": "MTG-STD-009",
        "lane": "ALL",
        "requirement": (
            "Purchase authorization must remain separate from "
            "forecast generation."
        ),
        "implementation_status": "IMPLEMENTED",
        "blocking": "true",
    },
    {
        "requirement_id": "MTG-STD-010",
        "lane": "ALL",
        "requirement": (
            "Every material implementation requirement must map "
            "to policy, code, tests, production gates, and evidence."
        ),
        "implementation_status": "NOT_IMPLEMENTED",
        "blocking": "true",
    },
    {
        "requirement_id": "COL-STD-001",
        "lane": "COLLECTOR_BOOSTER",
        "requirement": (
            "Collector display universe must exclude cases, "
            "packs, bundles, and unsupported configurations."
        ),
        "implementation_status": "IMPLEMENTED",
        "blocking": "true",
    },
    {
        "requirement_id": "COL-STD-002",
        "lane": "COLLECTOR_BOOSTER",
        "requirement": (
            "Collector registry identities must reconcile to "
            "the active Collector model universe."
        ),
        "implementation_status": "IMPLEMENTED",
        "blocking": "true",
    },
    {
        "requirement_id": "COL-STD-003",
        "lane": "COLLECTOR_BOOSTER",
        "requirement": (
            "Collector direct-history quality must be certified "
            "before direct-history methods are used."
        ),
        "implementation_status": "IMPLEMENTED",
        "blocking": "true",
    },
    {
        "requirement_id": "COL-STD-004",
        "lane": "COLLECTOR_BOOSTER",
        "requirement": (
            "Collector products with unusable or insufficient "
            "direct history must be evaluated for comparable routing."
        ),
        "implementation_status": "NOT_IMPLEMENTED",
        "blocking": "true",
    },
    {
        "requirement_id": "COL-STD-005",
        "lane": "COLLECTOR_BOOSTER",
        "requirement": (
            "All governed Collector products must appear in the "
            "final method-routing output."
        ),
        "implementation_status": "NOT_IMPLEMENTED",
        "blocking": "true",
    },
    {
        "requirement_id": "PRE-STD-001",
        "lane": "PRE_COLLECTOR_BOOSTER",
        "requirement": (
            "Pre-Collector methodology must use lane-specific "
            "history, scarcity, era, and liquidity rules."
        ),
        "implementation_status": "NOT_IMPLEMENTED",
        "blocking": "true",
    },
    {
        "requirement_id": "SL-STD-001",
        "lane": "SECRET_LAIR",
        "requirement": (
            "Secret Lair methodology must distinguish drop, foil, "
            "bundle, IP, artist, print, and singles-value structures."
        ),
        "implementation_status": "NOT_IMPLEMENTED",
        "blocking": "true",
    },
]


def write_json() -> None:
    STANDARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    STANDARD_PATH.write_text(
        json.dumps(STANDARD, indent=2),
        encoding="utf-8",
    )


def write_traceability() -> None:
    TRACEABILITY_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fields = [
        "requirement_id",
        "lane",
        "requirement",
        "implementation_status",
        "blocking",
        "policy_file",
        "implementation_file",
        "test_file",
        "production_gate",
        "evidence_artifact",
        "review_notes",
    ]

    rows = []

    for requirement in REQUIREMENTS:
        row = dict(requirement)

        for field in fields:
            row.setdefault(field, "")

        rows.append(row)

    with TRACEABILITY_PATH.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )
        writer.writeheader()
        writer.writerows(rows)


def write_documents() -> None:
    STANDARD_DOCUMENT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    STANDARD_DOCUMENT.write_text(
        """# MTG Forecasting and Decision Standard

## Status

Canonical baseline version 1.0.0.

## Governing rule

Implementation must conform to this standard. The standard must not be
weakened merely to accommodate existing code or data.

## Core requirements

1. Every governed product receives an explicit forecast method or an
   explicit deferred reason.
2. Comparable-product analysis is an approved forecasting method.
3. Insufficient direct history does not automatically prohibit forecasting.
4. Direct-history quarantine applies to the historical method and does not
   automatically reject the product.
5. Identity and executable-price failures remain fail-closed.
6. Forecast outputs disclose method, evidence, confidence, uncertainty,
   limitations, source information, and standard version.
7. Required horizons are one, three, and five years.
8. Required scenarios are downside, base, and upside.
9. Forecast generation and purchase authorization remain separate.
10. Automated tests are necessary but do not replace production semantic
    certification.

## Change control

Changes to methods, weights, thresholds, source hierarchy, product universe,
or eligibility rules require approval, a version change, and recertification.
""",
        encoding="utf-8",
    )

    COLLECTOR_DOCUMENT.write_text(
        """# Collector Booster Method Specification

## Supported routes

- DIRECT_HISTORY_CALIBRATED
- DIRECT_HISTORY_LIMITED
- COMPARABLE_PRODUCT_ADJUSTED
- FUNDAMENTAL_COMPARABLE_HYBRID
- DEFERRED_IDENTITY
- DEFERRED_MISSING_PRICE
- DEFERRED_INSUFFICIENT_EVIDENCE

## Direct-history interpretation

A quarantined historical series cannot be used directly. The product must
still be evaluated for an approved comparable or hybrid method when identity
and current pricing are valid.

## Comparable requirements

Comparables must be selected using configuration, release era, lifecycle,
print and supply structure, franchise strength, gameplay demand, premium
contents, price band, liquidity, reprint exposure, and historical behavior.

Every comparable forecast must record the comparable identities, scores,
selection basis, exclusions, weights, confidence penalty, and limitations.
""",
        encoding="utf-8",
    )

    PRE_COLLECTOR_DOCUMENT.write_text(
        """# Pre-Collector Booster Method Specification

## Status

Lane-specific specification and certification are required before publication.

## Required distinctions

The methodology must account for older product structures, sparse observations,
surviving sealed supply, era effects, liquidity, nostalgia demand, reprint
exposure, and set significance. Collector-era observation-frequency rules must
not be copied without validation.
""",
        encoding="utf-8",
    )

    SECRET_LAIR_DOCUMENT.write_text(
        """# Secret Lair Method Specification

## Status

Lane-specific specification and certification are required before publication.

## Required distinctions

The methodology must distinguish foil and nonfoil configurations, drop type,
card count, intellectual property, artist, purchase window, print-to-demand
status, bundle inclusion, bonus-card uncertainty, singles-equivalent value,
reprint exposure, recency, and liquidity.
""",
        encoding="utf-8",
    )


def main() -> None:
    write_json()
    write_traceability()
    write_documents()

    print("MTG standards foundation generated.")
    print(f"Standard: {STANDARD_PATH}")
    print(f"Traceability: {TRACEABILITY_PATH}")
    print(f"Requirements: {len(REQUIREMENTS)}")


if __name__ == "__main__":
    main()