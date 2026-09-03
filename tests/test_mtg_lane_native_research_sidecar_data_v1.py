import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DATA = (
    ROOT
    / "docs"
    / "phase_9"
    / "uip_export"
    / "research_sidecars"
)


def rows(name: str) -> list[dict[str, str]]:
    with (DATA / name).open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle))


def by_id(
    records: list[dict[str, str]],
    canonical_id: str,
) -> dict[str, str]:
    matches = [
        row
        for row in records
        if row["canonical_product_id"] == canonical_id
    ]

    assert len(matches) == 1

    return matches[0]


def test_collector_product_sidecar() -> None:
    records = rows(
        "mtg_collector_research.csv"
    )

    assert len(records) == 50

    assert len(
        {
            row["canonical_product_id"]
            for row in records
        }
    ) == 50

    edge = by_id(
        records,
        "MTG-CANON-TCGPLAYER-619672",
    )

    assert edge["current_price"] == "717.61"
    assert edge["final_rank"] == "1"
    assert edge["rank_tier"] == "TIER_1"

    assert (
        edge["final_governed_score"]
        == "76.145833"
    )

    assert (
        edge["median_price_365"]
        == "1205.893871"
    )

    assert (
        edge["median_return_365"]
        == "0.6804306949457226"
    )

    assert (
        edge["probability_of_50pct_gain_365"]
        == "0.7309"
    )

    assert (
        edge["probability_of_doubling_365"]
        == "0.1684"
    )

    assert (
        edge["probability_of_loss_365"]
        == "0.0023"
    )

    assert edge["strong_entry_ceiling"] == "968.44"
    assert edge["candidate_entry_ceiling"] == "1065.28"

    assert (
        edge["purchase_status"]
        == "STRONG_PURCHASE_CANDIDATE"
    )
    lotr_special = by_id(
        records,
        "MTG-CANON-TCGPLAYER-515906",
    )

    assert lotr_special["current_price"] == "5828.6"

    assert lotr_special["final_rank"] == ""
    assert lotr_special["rank_tier"] == ""
    assert lotr_special["final_governed_score"] == ""

    assert lotr_special["median_price_365"] == ""
    assert lotr_special["median_return_365"] == ""

    assert (
        lotr_special["probability_of_50pct_gain_365"]
        == ""
    )

    assert (
        lotr_special["probability_of_doubling_365"]
        == ""
    )

    assert (
        lotr_special["probability_of_loss_365"]
        == ""
    )

    assert lotr_special["strong_entry_ceiling"] == ""
    assert lotr_special["candidate_entry_ceiling"] == ""
    assert lotr_special["purchase_status"] == ""
    assert lotr_special["purchase_basis"] == ""


def test_collector_horizon_sidecar() -> None:
    records = rows(
        "mtg_collector_forecast_horizon.csv"
    )

    assert len(records) == 294

    keys = {
        (
            row["canonical_product_id"],
            row["horizon_days"],
        )
        for row in records
    }

    assert len(keys) == 294

    edge = [
        row
        for row in records
        if (
            row["canonical_product_id"]
            == "MTG-CANON-TCGPLAYER-619672"
            and row["horizon_days"] == "365"
        )
    ]

    assert len(edge) == 1

    edge = edge[0]

    assert edge["current_price"] == "717.61"
    assert edge["median_price"] == "1205.893871"
    assert edge["p10_price"] == "952.247914"
    assert edge["p25_price"] == "1065.280195"
    assert edge["p75_price"] == "1362.616333"
    assert edge["p90_price"] == "1521.618244"
    assert edge["probability_of_loss"] == "0.0023"


def test_precollector_product_sidecar() -> None:
    records = rows(
        "mtg_precollector_research.csv"
    )

    assert len(records) == 131

    assert len(
        {
            row["canonical_product_id"]
            for row in records
        }
    ) == 131

    dominaria = by_id(
        records,
        "tcgplayer:158423",
    )

    assert dominaria["current_price"] == "207.54"

    assert (
        dominaria["current_price_evidence_status"]
        == "CERTIFIED_TCGCSV_LIVE_CURRENT_PRICE"
    )

    assert dominaria["source_name"] == "TCGCSV_LIVE"
    assert dominaria["observation_date"] == "2026-08-08"

    assert (
        dominaria["final_analysis_status"]
        == "RANKED_FORECASTABLE"
    )

    assert dominaria["purchase_rank"] == "1"

    assert (
        dominaria["investment_tier"]
        == "TIER_1_TOP_QUARTILE"
    )

    assert (
        dominaria["forecast_price_365d"]
        == "264.9992552776047"
    )

    assert (
        dominaria["combined_purchase_score"]
        == "93.8721014729951"
    )

    assert dominaria["accepted_listing_count"] == "52.0"
    assert dominaria["unique_seller_count"] == "46.0"
    assert dominaria["history_observation_count"] == "30.0"

    assert dominaria["current_price_gap_reason"] == ""


def test_precollector_scenario_sidecar() -> None:
    records = rows(
        "mtg_precollector_scenario_horizon.csv"
    )

    assert len(records) == 190

    keys = {
        (
            row["canonical_product_id"],
            row["monte_carlo_horizon_years"],
        )
        for row in records
    }

    assert len(keys) == 190

    dominaria_3y = [
        row
        for row in records
        if (
            row["canonical_product_id"]
            == "tcgplayer:158423"
            and row["monte_carlo_horizon_years"] == "3"
        )
    ]

    dominaria_5y = [
        row
        for row in records
        if (
            row["canonical_product_id"]
            == "tcgplayer:158423"
            and row["monte_carlo_horizon_years"] == "5"
        )
    ]

    assert len(dominaria_3y) == 1
    assert len(dominaria_5y) == 1

    d3 = dominaria_3y[0]
    d5 = dominaria_5y[0]

    assert d3["terminal_price_median"] == "519.0385268507684"

    assert d5["terminal_price_median"] == "954.2956816938436"

    assert d3["probability_positive_return"] == "0.985"

    assert d5["probability_positive_return"] == "0.9964"

    assert d3["probability_capital_loss"] == "0.015"

    assert d5["probability_capital_loss"] == "0.0036"

    assert (
        d3["scenario_classification"]
        == "THREE_YEAR_SCENARIO_NOT_DIRECTLY_BACKTESTED"
    )

    assert (
        d5["scenario_classification"]
        == "FIVE_YEAR_SCENARIO_NOT_DIRECTLY_BACKTESTED"
    )

    assert d3["directly_backtested_at_this_horizon"] == "false"
    assert d5["directly_backtested_at_this_horizon"] == "false"


def test_missing_values_are_not_synthesized() -> None:
    records = rows(
        "mtg_precollector_research.csv"
    )

    unranked = [
        row
        for row in records
        if row["final_analysis_status"] != "RANKED_FORECASTABLE"
    ]

    assert unranked

    for row in unranked:
        assert row["purchase_rank"] == ""
        assert row["forecast_price_365d"] == ""


def test_k3g4br2_exact_native_detail_enrichment_data() -> None:
    import csv
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]

    output = (
        root
        / "docs"
        / "phase_9"
        / "uip_export"
        / "research_sidecars"
    )

    def read(name: str) -> list[dict[str, str]]:
        with (
            output / name
        ).open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            return list(
                csv.DictReader(handle)
            )

    collector = read(
        "mtg_collector_research.csv"
    )

    horizons = read(
        "mtg_collector_forecast_horizon.csv"
    )

    pre = read(
        "mtg_precollector_research.csv"
    )

    scenarios = read(
        "mtg_precollector_scenario_horizon.csv"
    )

    assert len(collector) == 50
    assert len(horizons) == 294
    assert len(pre) == 131
    assert len(scenarios) == 190

    assert list(collector[0])[-5:] == [
        "calibration_status_365",
        "calibration_status_1095",
        "limitations",
        "purchase_eligible_at_this_stage",
        "weighted_score_before_penalty",
    ]

    assert list(pre[0])[-2:] == [
        "high_confidence_rank",
        "speculative_rank",
    ]

    assert list(scenarios[0])[-1:] == [
        "model_rank",
    ]

    lotr = next(
        row
        for row in collector
        if row["canonical_product_id"]
        == "MTG-CANON-TCGPLAYER-515906"
    )

    for field in {
        "calibration_status_365",
        "calibration_status_1095",
        "limitations",
        "purchase_eligible_at_this_stage",
        "weighted_score_before_penalty",
    }:
        assert lotr[field] == ""

    assert (
        sum(
            bool(row["high_confidence_rank"])
            for row in pre
        )
        == 88
    )

    assert (
        sum(
            bool(row["speculative_rank"])
            for row in pre
        )
        == 6
    )

    assert (
        sum(
            bool(row["model_rank"])
            for row in scenarios
        )
        == 190
    )

    dominaria = next(
        row
        for row in pre
        if row["canonical_product_id"]
        == "tcgplayer:158423"
    )

    assert dominaria["purchase_rank"] == "1"
    assert dominaria["high_confidence_rank"] == "1"

    dominaria_scenarios = {
        row["monte_carlo_horizon_years"]: row
        for row in scenarios
        if row["canonical_product_id"]
        == "tcgplayer:158423"
    }

    assert dominaria_scenarios["3"]["model_rank"] == "5"
    assert dominaria_scenarios["5"]["model_rank"] == "5"

    assert (
        dominaria_scenarios["3"][
            "directly_backtested_at_this_horizon"
        ]
        == "false"
    )

    assert (
        dominaria_scenarios["5"][
            "directly_backtested_at_this_horizon"
        ]
        == "false"
    )
