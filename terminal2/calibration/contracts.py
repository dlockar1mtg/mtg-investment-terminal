from __future__ import annotations

from dataclasses import dataclass

from terminal2.warehouse_core import DatasetDefinition


@dataclass(frozen=True)
class CalibrationDatasetContract:
    name: str
    description: str
    primary_key: tuple[str, ...]
    required_columns: tuple[str, ...]
    snapshot: bool = True
    version: str = "1"

    def definition(self) -> DatasetDefinition:
        return DatasetDefinition(
            name=self.name,
            category="calibration",
            module="terminal2.calibration",
            description=self.description,
            primary_key=self.primary_key,
            expected_columns=self.required_columns,
            required=True,
            snapshot=self.snapshot,
            version=self.version,
        )


CALIBRATION_DATASET_CONTRACTS = {
    "calibration_forecast_vintages": CalibrationDatasetContract(
        name="calibration_forecast_vintages",
        description="Immutable forecast and recommendation observations preserved by run and horizon.",
        primary_key=(
            "forecast_run_id",
            "investment_product_id",
            "horizon_months",
        ),
        required_columns=(
            "forecast_run_id",
            "forecast_as_of_date",
            "investment_product_id",
            "horizon_months",
            "target_date",
            "forecast_price",
            "forecast_expected_return",
            "probability_of_loss",
            "forecast_confidence",
            "recommendation",
            "recommendation_score",
            "model_version",
        ),
        snapshot=False,
    ),
    "calibration_realized_outcomes": CalibrationDatasetContract(
        name="calibration_realized_outcomes",
        description="Realized prices and returns matched to matured forecast vintages.",
        primary_key=(
            "forecast_run_id",
            "investment_product_id",
            "horizon_months",
        ),
        required_columns=(
            "forecast_run_id",
            "investment_product_id",
            "horizon_months",
            "target_date",
            "realized_observation_date",
            "realized_price",
            "realized_return",
            "maturity_status",
        ),
        snapshot=False,
    ),
    "calibration_forecast_errors": CalibrationDatasetContract(
        name="calibration_forecast_errors",
        description="Forecast price, return, percentage, and directional errors.",
        primary_key=(
            "forecast_run_id",
            "investment_product_id",
            "horizon_months",
        ),
        required_columns=(
            "forecast_run_id",
            "investment_product_id",
            "horizon_months",
            "forecast_price",
            "realized_price",
            "absolute_price_error",
            "absolute_percentage_error",
            "return_error",
            "squared_price_error",
            "direction_correct",
        ),
        snapshot=False,
    ),
    "calibration_recommendation_performance": CalibrationDatasetContract(
        name="calibration_recommendation_performance",
        description="Realized return and success evaluation for historical recommendations.",
        primary_key=(
            "forecast_run_id",
            "investment_product_id",
            "horizon_months",
        ),
        required_columns=(
            "forecast_run_id",
            "investment_product_id",
            "horizon_months",
            "recommendation",
            "recommendation_score",
            "realized_return",
            "recommendation_success",
        ),
        snapshot=False,
    ),
    "calibration_probability_buckets": CalibrationDatasetContract(
        name="calibration_probability_buckets",
        description="Observed loss frequency and forecast accuracy by probability and confidence bucket.",
        primary_key=(
            "horizon_months",
            "probability_bucket",
            "confidence_bucket",
        ),
        required_columns=(
            "horizon_months",
            "probability_bucket",
            "confidence_bucket",
            "forecast_count",
            "average_predicted_loss_probability",
            "observed_loss_frequency",
            "calibration_gap",
            "directional_accuracy",
        ),
    ),
    "calibration_segment_performance": CalibrationDatasetContract(
        name="calibration_segment_performance",
        description="Calibration metrics by product type, forecast horizon, and model version.",
        primary_key=(
            "product_type",
            "horizon_months",
            "model_version",
        ),
        required_columns=(
            "product_type",
            "horizon_months",
            "model_version",
            "matured_forecast_count",
            "mean_absolute_error",
            "mean_absolute_percentage_error",
            "root_mean_squared_error",
            "directional_accuracy",
            "recommendation_hit_rate",
            "average_realized_return",
        ),
    ),
    "calibration_drift_monitor": CalibrationDatasetContract(
        name="calibration_drift_monitor",
        description="Recent-versus-prior performance comparison and model drift status.",
        primary_key=(
            "metric_name",
            "horizon_months",
        ),
        required_columns=(
            "metric_name",
            "horizon_months",
            "recent_value",
            "prior_value",
            "absolute_change",
            "relative_change",
            "drift_status",
            "recent_sample_size",
            "prior_sample_size",
        ),
    ),
    "calibration_executive_summary": CalibrationDatasetContract(
        name="calibration_executive_summary",
        description="One-row executive summary of calibration readiness and performance.",
        primary_key=("snapshot_date",),
        required_columns=(
            "snapshot_date",
            "archived_forecast_count",
            "matured_forecast_count",
            "pending_forecast_count",
            "mean_absolute_error",
            "mean_absolute_percentage_error",
            "root_mean_squared_error",
            "directional_accuracy",
            "recommendation_hit_rate",
            "calibration_status",
        ),
    ),
}


def get_calibration_contract(
    name: str,
) -> CalibrationDatasetContract:
    try:
        return CALIBRATION_DATASET_CONTRACTS[name]
    except KeyError as exc:
        raise KeyError(
            f"Unknown calibration dataset contract: {name}"
        ) from exc
