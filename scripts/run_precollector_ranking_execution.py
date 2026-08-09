from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_ranking_execution_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/ranking_execution"


def clean(value: Any) -> str:
    return str(value or "").strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_csv_bytes(payload: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_package(package: dict[str, str], required: list[str], role: str) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    path = Path(tempfile.gettempdir()) / package["package_name"]
    if not path.is_file():
        raise RuntimeError(f"PACKAGE_MISSING:{path}")
    actual = sha256_file(path)
    if actual != package["sha256"]:
        raise RuntimeError(f"PACKAGE_HASH_DRIFT:{path.name}:expected={package['sha256']}:actual={actual}")
    payloads: dict[str, bytes] = {}
    lineage: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        available = {Path(item.filename).name: item for item in archive.infolist() if not item.is_dir()}
        for name in required:
            member = available.get(name)
            if member is None:
                raise RuntimeError(f"PACKAGE_MEMBER_MISSING:{path.name}:{name}")
            payload = archive.read(member)
            payloads[name] = payload
            lineage.append({
                "artifact_role": role,
                "package_name": path.name,
                "package_sha256": actual,
                "member_name": name,
                "member_sha256": sha256_bytes(payload),
                "row_count": len(read_csv_bytes(payload)) if name.endswith(".csv") else "",
            })
    return payloads, lineage


def percentile(series: pd.Series, higher_is_better: bool) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    ranked = numeric.rank(method="average", pct=True, ascending=higher_is_better)
    return ranked * 100.0


def main() -> int:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    architecture_required = [
        "precollector_ranking_component_policy.csv",
        "precollector_ranking_tie_break_policy.csv",
        "precollector_ranking_execution_plan.csv",
        "precollector_ranking_readiness_architecture_summary.json",
    ]
    forecast_required = [
        "precollector_governed_product_long_horizon_forecast_output.csv",
        "precollector_governed_product_output_readiness.csv",
        "precollector_forecast_output_execution_summary.json",
    ]
    architecture, lineage_a = load_package(contract["required_architecture_package"], architecture_required, "CERTIFIED_RANKING_ARCHITECTURE")
    forecast, lineage_f = load_package(contract["required_forecast_output_execution_package"], forecast_required, "CERTIFIED_FORECAST_OUTPUT_EXECUTION")

    rows = read_csv_bytes(forecast["precollector_governed_product_long_horizon_forecast_output.csv"])
    frame = pd.DataFrame(rows)
    failures: list[str] = []
    required_columns = {
        "tcgplayer_product_id", "product_name", "forecast_route", "horizon_code", "current_price",
        "terminal_value_q10", "annualized_return_median", "probability_of_loss",
    }
    missing_columns = sorted(required_columns - set(frame.columns))
    if missing_columns:
        raise RuntimeError(f"RANKING_INPUT_SCHEMA_UNSUPPORTED:{missing_columns}")

    frame = frame[frame["horizon_code"].isin(["Y3", "Y5"])].copy()
    for column in ["current_price", "terminal_value_q10", "annualized_return_median", "probability_of_loss"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame[list(required_columns - {"tcgplayer_product_id", "product_name", "forecast_route", "horizon_code"})].isna().any().any():
        failures.append("NONFINITE_RANKING_INPUT")

    wide = frame.pivot(index="tcgplayer_product_id", columns="horizon_code", values=[
        "product_name", "forecast_route", "current_price", "terminal_value_q10",
        "annualized_return_median", "probability_of_loss",
    ])
    wide.columns = [f"{field}_{horizon}" for field, horizon in wide.columns]
    wide = wide.reset_index()
    if len(wide) != contract["expected_counts"]["governed_products"]:
        failures.append(f"PRODUCT_COUNT_DRIFT:{len(wide)}")

    wide["product_name"] = wide.get("product_name_Y3", "")
    wide["forecast_route"] = wide.get("forecast_route_Y3", "")
    wide["Y3_MEDIAN_ANNUALIZED_RETURN"] = wide["annualized_return_median_Y3"]
    wide["Y5_MEDIAN_ANNUALIZED_RETURN"] = wide["annualized_return_median_Y5"]
    wide["Y3_Q10_TERMINAL_MULTIPLE"] = wide["terminal_value_q10_Y3"] / wide["current_price_Y3"]
    wide["Y5_Q10_TERMINAL_MULTIPLE"] = wide["terminal_value_q10_Y5"] / wide["current_price_Y5"]
    wide["Y3_PROBABILITY_OF_LOSS"] = wide["probability_of_loss_Y3"]
    wide["Y5_PROBABILITY_OF_LOSS"] = wide["probability_of_loss_Y5"]
    wide["mean_probability_of_loss"] = (wide["Y3_PROBABILITY_OF_LOSS"] + wide["Y5_PROBABILITY_OF_LOSS"]) / 2.0

    component_rows: list[dict[str, Any]] = []
    score = pd.Series(0.0, index=wide.index)
    for component in contract["ranking_policy"]["components"]:
        name = component["component"]
        weight = float(component["weight"])
        higher = bool(component["higher_is_better"])
        percentile_score = percentile(wide[name], higher)
        weighted = percentile_score * weight
        score = score + weighted
        for idx in wide.index:
            component_rows.append({
                "tcgplayer_product_id": wide.at[idx, "tcgplayer_product_id"],
                "component": name,
                "raw_value": wide.at[idx, name],
                "higher_is_better": higher,
                "percentile_score": percentile_score.at[idx],
                "weight": weight,
                "weighted_score": weighted.at[idx],
            })

    wide["ranking_score"] = score.clip(lower=0.0, upper=100.0)
    wide = wide.sort_values(
        ["ranking_score", "mean_probability_of_loss", "Y5_MEDIAN_ANNUALIZED_RETURN", "Y3_MEDIAN_ANNUALIZED_RETURN", "tcgplayer_product_id"],
        ascending=[False, True, False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    wide["governed_rank"] = range(1, len(wide) + 1)
    wide["short_horizon_product_values_used"] = False
    wide["forecast_recomputed"] = False
    wide["monte_carlo_recomputed"] = False
    wide["purchase_analysis_authorized"] = False
    wide["purchase_recommendation_authorized"] = False

    ranked_fields = [
        "governed_rank", "tcgplayer_product_id", "product_name", "forecast_route", "ranking_score",
        "Y3_MEDIAN_ANNUALIZED_RETURN", "Y5_MEDIAN_ANNUALIZED_RETURN",
        "Y3_Q10_TERMINAL_MULTIPLE", "Y5_Q10_TERMINAL_MULTIPLE",
        "Y3_PROBABILITY_OF_LOSS", "Y5_PROBABILITY_OF_LOSS", "mean_probability_of_loss",
        "short_horizon_product_values_used", "forecast_recomputed", "monte_carlo_recomputed",
        "purchase_analysis_authorized", "purchase_recommendation_authorized",
    ]
    ranked_rows = wide[ranked_fields].to_dict(orient="records")
    expected = contract["expected_counts"]
    if len(frame) != expected["long_horizon_output_rows"]:
        failures.append(f"LONG_HORIZON_ROW_COUNT_DRIFT:{len(frame)}")
    if len(ranked_rows) != expected["ranked_product_rows"]:
        failures.append(f"RANKED_PRODUCT_COUNT_DRIFT:{len(ranked_rows)}")
    if len(contract["ranking_policy"]["components"]) != expected["ranking_components"]:
        failures.append("RANKING_COMPONENT_COUNT_DRIFT")
    if not math.isclose(sum(float(item["weight"]) for item in contract["ranking_policy"]["components"]), 1.0, abs_tol=1e-12):
        failures.append("RANKING_WEIGHT_SUM_DRIFT")

    diagnostics = [{"severity": "BLOCKING", "code": failure, "detail": ""} for failure in failures]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["required_outputs"]
    lineage = lineage_a + lineage_f
    write_csv(OUTPUT_DIR / outputs["input_lineage_csv"], lineage, list(lineage[0].keys()))
    write_csv(OUTPUT_DIR / outputs["component_score_csv"], component_rows, list(component_rows[0].keys()))
    write_csv(OUTPUT_DIR / outputs["ranked_products_csv"], ranked_rows, ranked_fields)
    write_csv(OUTPUT_DIR / outputs["diagnostics_csv"], diagnostics, ["severity", "code", "detail"])

    status = "PASS" if not failures else "FAIL"
    summary = {
        "certification_status": status,
        "governed_products": len(wide),
        "long_horizon_output_rows": len(frame),
        "ranked_product_rows": len(ranked_rows),
        "ranking_components": len(contract["ranking_policy"]["components"]),
        "ranking_weight_sum": sum(float(item["weight"]) for item in contract["ranking_policy"]["components"]),
        "short_horizon_product_values_used": False,
        "forecast_recomputed": False,
        "monte_carlo_recomputed": False,
        "critical_failures": failures,
        "next_stage": contract["next_stage_if_certified"] if not failures else "REPAIR_PRECOLLECTOR_RANKING_EXECUTION",
        "purchase_analysis_authorized": False,
        "purchase_recommendation_authorized": False,
    }
    (OUTPUT_DIR / outputs["summary_json"]).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "outputs": [
            {"path": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in sorted(OUTPUT_DIR.iterdir())
            if path.is_file() and path.name != outputs["manifest_json"]
        ],
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_RANKING_EXECUTION" if not failures else "FAIL_PRECOLLECTOR_RANKING_EXECUTION")
    print(f"GOVERNED_PRODUCTS={len(wide)}")
    print(f"LONG_HORIZON_OUTPUT_ROWS={len(frame)}")
    print(f"RANKED_PRODUCT_ROWS={len(ranked_rows)}")
    print(f"RANKING_COMPONENTS={len(contract['ranking_policy']['components'])}")
    print(f"RANKING_WEIGHT_SUM={summary['ranking_weight_sum']:.6f}")
    print("SHORT_HORIZON_PRODUCT_VALUES_USED=FALSE")
    print("PURCHASE_ANALYSIS_AUTHORIZED=FALSE")
    print(f"NEXT_STAGE={summary['next_stage']}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
