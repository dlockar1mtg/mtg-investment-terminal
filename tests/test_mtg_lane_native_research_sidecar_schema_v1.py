import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COLLECTOR = (
    ROOT
    / "config"
    / "mtg"
    / "governance"
    / "mtg_collector_research_sidecar_schema_v1.json"
)

PRE = (
    ROOT
    / "config"
    / "mtg"
    / "governance"
    / "mtg_precollector_research_sidecar_schema_v1.json"
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_collector_research_sidecar_contract() -> None:
    doc = load(COLLECTOR)

    assert doc["status"] == "AUTHORIZED_FOR_BOUNDED_SIDECAR_ASSEMBLY"
    assert doc["lane"] == "COLLECTOR_V1"

    assert doc["common_interface"]["mtg_v1_field_count"] == 23
    assert doc["common_interface"]["remains_frozen"] is True
    assert doc["common_interface"]["schema_expansion_authorized"] is False

    assert (
        doc["authority"]["forecast"]["sha256"]
        == "ba78970c401068b9387755d0ad052d1d5c6a9bc9ffe59302eb82f4a22973313e"
    )

    assert (
        doc["authority"]["ranking"]["sha256"]
        == "0f609fe2770b01f080ab02039adade3fe8679072792c35a0e7b8aa7cf48fb48c"
    )

    assert (
        doc["authority"]["purchase"]["sha256"]
        == "363358aeb269f9acb04fb489fe614d6cc1db39587f0a53decebca01a4330de7e"
    )

    horizons = doc["forecast_horizon_record"]["authorized_horizons_days"]
    assert horizons == [90, 180, 365, 730, 1095, 1825]

    fields = set(doc["forecast_horizon_record"]["fields"])

    for required in {
        "p10_price",
        "p25_price",
        "median_price",
        "p75_price",
        "p90_price",
        "probability_of_50pct_gain",
        "probability_of_doubling",
        "probability_of_loss",
    }:
        assert required in fields

    prohibited = set(doc["prohibitions"])

    assert "NO_SYNTHETIC_FORECAST_DISTRIBUTION" in prohibited
    assert "NO_CROSS_LANE_RANK" in prohibited
    assert "NO_AUTOMATIC_PURCHASE_EXECUTION" in prohibited
    assert "MISSING_VALUES_REMAIN_MISSING" in prohibited


def test_precollector_research_sidecar_contract() -> None:
    doc = load(PRE)

    assert doc["status"] == "AUTHORIZED_FOR_BOUNDED_SIDECAR_ASSEMBLY"
    assert doc["lane"] == "PRE_COLLECTOR_V1"

    assert doc["common_interface"]["mtg_v1_field_count"] == 23
    assert doc["common_interface"]["remains_frozen"] is True
    assert doc["common_interface"]["schema_expansion_authorized"] is False

    assert (
        doc["authority"]["certified_package"]["sha256"]
        == "47be599f92999fbdede603dc3aee7d720dd0eef01ca68d328e36abda3e256261"
    )

    assert (
        doc["authority"]["current_price_package"]["sha256"]
        == "cab2c351a167e5a5c02b58c411355d58c18d0f075f282a05e85083412cb3f3c6"
    )
    assert (
        doc["authority"]["current_price_coverage"]["member"]
        == "precollector_current_price_coverage_v2.csv"
    )

    assert doc["authority"]["current_price_coverage"]["sha256"]

    assert (
        doc["authority"]["current_price_gaps"]["member"]
        == "precollector_current_price_gaps_v2.csv"
    )

    assert doc["authority"]["current_price_gaps"]["sha256"]

    product_fields = set(doc["product_record"]["fields"])

    assert "current_price_gap_reason" in product_fields

    presentation = set(doc["presentation_authorizations"])

    assert "CURRENT_PRICE_GAP_EXPLANATION" in presentation


    assert (
        doc["scenario_horizon_record"]["authorized_horizons_years"]
        == [3, 5]
    )

    fields = set(doc["scenario_horizon_record"]["fields"])

    for required in {
        "terminal_price_p10",
        "terminal_price_p25",
        "terminal_price_median",
        "terminal_price_p75",
        "terminal_price_p90",
        "probability_positive_return",
        "probability_capital_loss",
        "return_cvar10",
        "median_max_drawdown",
        "evidence_quality_score",
        "liquidity_score",
    }:
        assert required in fields

    semantics = set(doc["semantic_requirements"])

    assert (
        "MISSING_CURRENT_PRICE_MAY_USE_CERTIFIED_GAP_REASON_ONLY"
        in semantics
    )

    assert (
        "CURRENT_PRICE_EVIDENCE_STATUS_MUST_COME_FROM_CERTIFIED_COVERAGE_MEMBER"
        in semantics
    )

    assert (
        "THREE_YEAR_MUST_BE_LABELED_SCENARIO_NOT_DIRECTLY_BACKTESTED"
        in semantics
    )

    assert (
        "FIVE_YEAR_MUST_BE_LABELED_SCENARIO_NOT_DIRECTLY_BACKTESTED"
        in semantics
    )

    prohibited = set(doc["prohibitions"])

    assert "NO_SECRET_LAIR_Q10_POLICY" in prohibited
    assert "NO_COLLECTOR_THRESHOLD_REUSE" in prohibited
    assert "NO_CROSS_LANE_RANK" in prohibited
    assert "NO_AUTOMATIC_PURCHASE_EXECUTION" in prohibited
    assert "MISSING_VALUES_REMAIN_MISSING" in prohibited


def test_lane_native_sidecars_do_not_create_common_model() -> None:
    collector = load(COLLECTOR)
    pre = load(PRE)

    assert collector["lane"] != pre["lane"]

    assert (
        collector["product_record"]["record_type"]
        != pre["product_record"]["record_type"]
    )

    assert (
        collector["forecast_horizon_record"]["record_type"]
        != pre["scenario_horizon_record"]["record_type"]
    )

    assert (
        "NO_CRYPTO_BEAR_BASE_BULL_MAPPING"
        in collector["prohibitions"]
    )

    assert (
        "NO_CRYPTO_BEAR_BASE_BULL_MAPPING"
        in pre["prohibitions"]
    )


def test_k3g4br2_exact_native_detail_enrichment_contract() -> None:
    collector = load(COLLECTOR)
    pre = load(PRE)

    assert collector["contract_version"] == "1.1.0"
    assert pre["contract_version"] == "1.1.0"

    assert collector["product_record"]["fields"][-5:] == [
        "calibration_status_365",
        "calibration_status_1095",
        "limitations",
        "purchase_eligible_at_this_stage",
        "weighted_score_before_penalty",
    ]

    assert pre["product_record"]["fields"][-2:] == [
        "high_confidence_rank",
        "speculative_rank",
    ]

    assert pre["scenario_horizon_record"]["fields"][-1:] == [
        "model_rank",
    ]

    assert (
        pre["authority"]["model_return_ranking"]["sha256"]
        == "3a59415e6abb08c5accc99ea3224bed29af665b3408dfe5acfb80ed5b4926500"
    )

    assert (
        pre["authority"]["high_confidence_subset"]["sha256"]
        == "f597745b14c7e7767ff2cfb6dee179de31b53b7f2db757ea55ff50e5e7a44ad6"
    )

    assert (
        pre["authority"]["speculative_subset"]["sha256"]
        == "c754af3bc70da31c5767d4708b0318ac1f9be2b2c23a2befbaaf7272417a1113"
    )

    assert (
        collector["common_interface"]["mtg_v1_field_count"]
        == 23
    )

    assert (
        pre["common_interface"]["mtg_v1_field_count"]
        == 23
    )

    assert (
        "purchase_recommendations_authorized"
        in collector[
            "bounded_native_detail_enrichment"
        ][
            "explicit_exclusions"
        ]
    )

    assert (
        "high_confidence_status"
        in pre[
            "bounded_native_detail_enrichment"
        ][
            "explicit_non_fields"
        ]
    )

    assert (
        "speculative_classification"
        in pre[
            "bounded_native_detail_enrichment"
        ][
            "explicit_non_fields"
        ]
    )
