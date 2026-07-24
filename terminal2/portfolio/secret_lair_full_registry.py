from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

FULL_MODEL = "FULL_MODEL"
PROVISIONAL_MODEL = "PROVISIONAL_MODEL"
STRUCTURAL_ONLY = "STRUCTURAL_ONLY"
SUPPORTED_TIERS = {FULL_MODEL, PROVISIONAL_MODEL, STRUCTURAL_ONLY}

HOLDINGS_COLUMNS = (
    "investment_product_id",
    "quantity",
    "acquisition_cost_total",
    "acquisition_date",
    "notes",
)

def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))

def write_csv(path: Path, rows: list[dict[str, object]], columns: list[str] | tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def number(value: object, default: float = 0.0) -> float:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().lower()
    text = text.replace("the last air bender", "the last airbender")
    text = re.sub(
        r"\b(secret lair|drop|edition|foil edition|nonfoil edition|traditional foil|rainbow foil|"
        r"non[- ]?foil|galaxy foil|etched foil|raised foil|standard edition|promo)\b",
        " ",
        text,
    )
    text = re.sub(r"^[x\s:.\-]+", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def finish_group(value: str, default_unspecified: str = "NONFOIL") -> str:
    text = str(value).lower()
    if "non-foil" in text or "nonfoil" in text:
        return "NONFOIL"
    if "rainbow foil" in text:
        return "RAINBOW_FOIL"
    if "galaxy foil" in text:
        return "GALAXY_FOIL"
    if "etched" in text:
        return "ETCHED_FOIL"
    if "raised foil" in text:
        return "RAISED_FOIL"
    if "traditional foil" in text or re.search(r"(^|\s)foil($|\s)", text):
        return "FOIL"
    return default_unspecified

def match_score(source_name: str, candidate_name: str) -> float:
    left = normalize_name(source_name)
    right = normalize_name(candidate_name)
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    overlap = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    score = 0.70 * SequenceMatcher(None, left, right).ratio() + 0.30 * overlap
    if len(left_tokens) >= 2 and left_tokens.issubset(right_tokens):
        score += 0.35
    return min(1.0, score)

@dataclass(frozen=True)
class MatchResult:
    status: str
    product_id: str
    canonical_name: str
    score: float
    second_score: float
    requested_finish: str
    canonical_finish: str
    reason: str

class FullRegistryMatcher:
    def __init__(self, registry_rows: list[dict[str, str]], default_unspecified_finish: str = "NONFOIL") -> None:
        self.rows = registry_rows
        self.default_finish = default_unspecified_finish
        self.by_id = {row["investment_product_id"].strip(): row for row in registry_rows}

    def _name_compatible(self, source_name: str, row: dict[str, str], requested_finish: str) -> bool:
        canonical = row.get("canonical_product_name", "")
        return (
            finish_group(canonical, "UNSPECIFIED") == requested_finish
            and match_score(source_name, canonical) >= 0.72
        )

    def match(self, source_name: str, supplied_id: str = "") -> MatchResult:
        requested_finish = finish_group(source_name, self.default_finish)
        supplied_id = supplied_id.strip()
        if supplied_id and supplied_id in self.by_id:
            row = self.by_id[supplied_id]
            canonical = row.get("canonical_product_name", "")
            if self._name_compatible(source_name, row, requested_finish):
                return MatchResult(
                    "PROVIDED_ID_VALIDATED",
                    supplied_id,
                    canonical,
                    1.0,
                    0.0,
                    requested_finish,
                    finish_group(canonical, "UNSPECIFIED"),
                    "Supplied ID exists and agrees with the source name and finish.",
                )

        candidates: list[tuple[float, dict[str, str]]] = []
        for row in self.rows:
            canonical = row.get("canonical_product_name", "")
            canonical_finish = finish_group(canonical, "UNSPECIFIED")
            if canonical_finish != requested_finish:
                continue
            candidates.append((match_score(source_name, canonical), row))
        candidates.sort(key=lambda item: item[0], reverse=True)
        if not candidates:
            return MatchResult("REVIEW_REQUIRED", "", "", 0.0, 0.0, requested_finish, "", "No candidates with the requested finish.")

        best_score, best = candidates[0]
        second_score = candidates[1][0] if len(candidates) > 1 else 0.0
        margin = best_score - second_score
        best_name = best.get("canonical_product_name", "")
        subset_match = set(normalize_name(source_name).split()).issubset(set(normalize_name(best_name).split()))
        accepted = best_score >= 0.72 or (subset_match and best_score >= 0.55) or (best_score >= 0.62 and margin >= 0.10)
        if not accepted:
            return MatchResult(
                "REVIEW_REQUIRED",
                "",
                best_name,
                round(best_score, 6),
                round(second_score, 6),
                requested_finish,
                finish_group(best_name, "UNSPECIFIED"),
                f"Best candidate did not satisfy automatic-match safeguards; margin={margin:.4f}.",
            )
        return MatchResult(
            "AUTO_MATCHED",
            best["investment_product_id"].strip(),
            best_name,
            round(best_score, 6),
            round(second_score, 6),
            requested_finish,
            finish_group(best_name, "UNSPECIFIED"),
            f"Finish-aware automatic match; margin={margin:.4f}.",
        )

def build_owned_portfolio(
    registry_path: Path,
    evaluation_path: Path,
    owned_source_path: Path,
    output_root: Path,
    default_unspecified_finish: str = "NONFOIL",
) -> dict[str, object]:
    registry = read_csv(registry_path)
    evaluation = read_csv(evaluation_path)
    owned = read_csv(owned_source_path)
    if len(registry) != 973:
        raise ValueError(f"Expected 973 registry products, received {len(registry)}")
    if len(evaluation) != 973:
        raise ValueError(f"Expected 973 evaluation products, received {len(evaluation)}")

    registry_ids = {row["investment_product_id"].strip() for row in registry}
    evaluation_by_id = {row["investment_product_id"].strip(): row for row in evaluation}
    if registry_ids != set(evaluation_by_id):
        raise ValueError("Registry and evaluation product IDs do not reconcile")

    matcher = FullRegistryMatcher(registry, default_unspecified_finish)
    crosswalk: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    consolidated: dict[str, dict[str, object]] = {}

    required = {"quantity", "acquisition_cost_total"}
    if owned and not required.issubset(owned[0]):
        raise ValueError(f"Owned source missing required columns: {sorted(required - set(owned[0]))}")

    for line_number, row in enumerate(owned, start=2):
        source_name = row.get("product_name", "").strip() or row.get("canonical_product_name", "").strip()
        supplied_id = row.get("investment_product_id", "").strip()
        quantity = number(row.get("quantity"), -1)
        cost = number(row.get("acquisition_cost_total"), -1)
        issues: list[str] = []
        if not source_name and not supplied_id:
            issues.append("MISSING_PRODUCT_NAME_AND_ID")
        if quantity <= 0:
            issues.append("INVALID_QUANTITY")
        if cost < 0:
            issues.append("INVALID_COST_BASIS")

        result = matcher.match(source_name, supplied_id) if source_name else MatchResult(
            "PROVIDED_ID_VALIDATED" if supplied_id in registry_ids else "REVIEW_REQUIRED",
            supplied_id if supplied_id in registry_ids else "",
            evaluation_by_id.get(supplied_id, {}).get("canonical_product_name", ""),
            1.0 if supplied_id in registry_ids else 0.0,
            0.0,
            "",
            "",
            "ID-only source row.",
        )
        if result.status == "REVIEW_REQUIRED":
            issues.append("PRODUCT_MATCH_REVIEW_REQUIRED")

        crosswalk.append({
            "source_line": line_number,
            "source_product_name": source_name,
            "supplied_product_id": supplied_id,
            "matched_product_id": result.product_id,
            "matched_canonical_name": result.canonical_name,
            "match_status": result.status,
            "match_score": result.score,
            "second_match_score": result.second_score,
            "requested_finish": result.requested_finish,
            "canonical_finish": result.canonical_finish,
            "match_reason": result.reason,
        })

        if issues:
            diagnostics.append({
                "source_line": line_number,
                "source_product_name": source_name,
                "supplied_product_id": supplied_id,
                "diagnostic_status": "REVIEW_REQUIRED",
                "diagnostic_codes": "|".join(issues),
                "best_candidate_name": result.canonical_name,
                "best_candidate_score": result.score,
            })
            continue

        product_id = result.product_id
        bucket = consolidated.setdefault(product_id, {
            "investment_product_id": product_id,
            "quantity": 0.0,
            "acquisition_cost_total": 0.0,
            "acquisition_date": row.get("acquisition_date", "").strip(),
            "notes": set(),
        })
        bucket["quantity"] = number(bucket["quantity"]) + quantity
        bucket["acquisition_cost_total"] = number(bucket["acquisition_cost_total"]) + cost
        date = row.get("acquisition_date", "").strip()
        if date and (not bucket["acquisition_date"] or date < str(bucket["acquisition_date"])):
            bucket["acquisition_date"] = date
        note = row.get("notes", "").strip()
        if note:
            bucket["notes"].add(note)

    holdings: list[dict[str, object]] = []
    for product_id in sorted(consolidated):
        row = consolidated[product_id]
        holdings.append({
            "investment_product_id": product_id,
            "quantity": round(number(row["quantity"]), 6),
            "acquisition_cost_total": round(number(row["acquisition_cost_total"]), 2),
            "acquisition_date": row["acquisition_date"],
            "notes": " | ".join(sorted(row["notes"])),
        })

    positions: list[dict[str, object]] = []
    owned_forecasts: list[dict[str, object]] = []
    owned_recommendations: list[dict[str, object]] = []
    universal: list[dict[str, object]] = []
    for holding in holdings:
        product_id = str(holding["investment_product_id"])
        model = evaluation_by_id[product_id]
        quantity = number(holding["quantity"])
        cost = number(holding["acquisition_cost_total"])
        price = number(model.get("evaluated_market_value_usd"))
        current_value = round(quantity * price, 2)
        gain = round(current_value - cost, 2)
        gain_pct = round(gain / cost * 100.0, 2) if cost > 0 else ""
        positions.append({
            "investment_product_id": product_id,
            "canonical_product_name": model.get("canonical_product_name", ""),
            "quantity": quantity,
            "acquisition_cost_total": cost,
            "acquisition_date": holding.get("acquisition_date", ""),
            "current_modeled_unit_value_usd": price,
            "current_modeled_value_usd": current_value,
            "unrealized_gain_usd": gain,
            "unrealized_gain_pct": gain_pct,
            "evaluation_tier": model.get("evaluation_tier", ""),
            "valuation_method": model.get("valuation_method", ""),
            "model_confidence_score": model.get("model_confidence_score", ""),
            "model_weight": model.get("model_weight", ""),
            "guarded_recommendation": model.get("guarded_recommendation", ""),
            "value_classification": {
                FULL_MODEL: "OBSERVED_GOVERNED",
                PROVISIONAL_MODEL: "PROVISIONAL_ESTIMATE",
                STRUCTURAL_ONLY: "STRUCTURAL_ESTIMATE",
            }.get(model.get("evaluation_tier", ""), "UNKNOWN"),
            "notes": holding.get("notes", ""),
        })
        owned_forecasts.append({
            "investment_product_id": product_id,
            "canonical_product_name": model.get("canonical_product_name", ""),
            "quantity": quantity,
            "evaluation_tier": model.get("evaluation_tier", ""),
            "forecast_low_unit_usd": model.get("forecast_low_usd", ""),
            "forecast_base_unit_usd": model.get("forecast_base_usd", ""),
            "forecast_high_unit_usd": model.get("forecast_high_usd", ""),
            "forecast_low_position_usd": round(quantity * number(model.get("forecast_low_usd")), 2),
            "forecast_base_position_usd": round(quantity * number(model.get("forecast_base_usd")), 2),
            "forecast_high_position_usd": round(quantity * number(model.get("forecast_high_usd")), 2),
            "forecast_status": model.get("forecast_status", ""),
            "model_confidence_score": model.get("model_confidence_score", ""),
        })
        owned_recommendations.append({
            "investment_product_id": product_id,
            "canonical_product_name": model.get("canonical_product_name", ""),
            "evaluation_tier": model.get("evaluation_tier", ""),
            "guarded_recommendation": model.get("guarded_recommendation", ""),
            "recommendation_status": model.get("recommendation_status", ""),
            "model_evaluation_score": model.get("model_evaluation_score", ""),
            "model_confidence_score": model.get("model_confidence_score", ""),
            "current_modeled_value_usd": current_value,
        })
        universal.append({
            "asset_id": product_id,
            "asset_name": model.get("canonical_product_name", ""),
            "asset_class": "collectibles",
            "asset_subclass": "mtg_secret_lair",
            "quantity": quantity,
            "unit_price": price,
            "market_value": current_value,
            "cost_basis": cost,
            "currency": "USD",
            "valuation_confidence": model.get("model_confidence_score", ""),
            "valuation_method": model.get("valuation_method", ""),
            "evaluation_tier": model.get("evaluation_tier", ""),
            "source_system": "mtg-investment-terminal",
        })

    tier_counts: dict[str, int] = defaultdict(int)
    for row in positions:
        tier_counts[str(row["evaluation_tier"])] += 1

    output_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "crosswalk": output_root / "secret_lair_owned_inventory_crosswalk.csv",
        "diagnostics": output_root / "secret_lair_owned_inventory_diagnostics.csv",
        "holdings": output_root / "secret_lair_holdings_full_registry.csv",
        "positions": output_root / "secret_lair_owned_portfolio_positions.csv",
        "forecasts": output_root / "secret_lair_owned_forecasts.csv",
        "recommendations": output_root / "secret_lair_owned_guarded_recommendations.csv",
        "universal_export": output_root / "secret_lair_owned_universal_positions.csv",
        "manifest": output_root / "secret_lair_full_registry_portfolio_manifest.json",
        "certification": output_root / "SECRET_LAIR_FULL_REGISTRY_PORTFOLIO_CERTIFICATION.md",
    }
    write_csv(paths["crosswalk"], crosswalk, list(crosswalk[0].keys()) if crosswalk else [])
    write_csv(paths["diagnostics"], diagnostics, list(diagnostics[0].keys()) if diagnostics else [
        "source_line", "source_product_name", "supplied_product_id", "diagnostic_status",
        "diagnostic_codes", "best_candidate_name", "best_candidate_score",
    ])
    write_csv(paths["holdings"], holdings, HOLDINGS_COLUMNS)
    write_csv(paths["positions"], positions, list(positions[0].keys()) if positions else [])
    write_csv(paths["forecasts"], owned_forecasts, list(owned_forecasts[0].keys()) if owned_forecasts else [])
    write_csv(paths["recommendations"], owned_recommendations, list(owned_recommendations[0].keys()) if owned_recommendations else [])
    write_csv(paths["universal_export"], universal, list(universal[0].keys()) if universal else [])

    checks = {
        "registry_rows_equal_973": len(registry) == 973,
        "evaluation_rows_equal_973": len(evaluation) == 973,
        "registry_and_evaluation_ids_match": registry_ids == set(evaluation_by_id),
        "all_source_rows_matched": len(diagnostics) == 0,
        "holdings_ids_unique": len(holdings) == len({row["investment_product_id"] for row in holdings}),
        "all_holdings_in_full_registry": all(row["investment_product_id"] in registry_ids for row in holdings),
        "positions_equal_holdings": len(positions) == len(holdings),
        "forecasts_equal_holdings": len(owned_forecasts) == len(holdings),
        "recommendations_equal_holdings": len(owned_recommendations) == len(holdings),
        "universal_export_equal_holdings": len(universal) == len(holdings),
        "all_tiers_supported": all(row["evaluation_tier"] in SUPPORTED_TIERS for row in positions),
        "all_modeled_values_positive": all(number(row["current_modeled_unit_value_usd"]) > 0 for row in positions),
        "quota_calls_zero": True,
    }
    status = "CERTIFIED" if all(checks.values()) else "REVIEW_REQUIRED"
    result = {
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_rows": len(owned),
        "crosswalk_rows": len(crosswalk),
        "diagnostic_rows": len(diagnostics),
        "holdings_rows": len(holdings),
        "full_model_holdings": tier_counts[FULL_MODEL],
        "provisional_model_holdings": tier_counts[PROVISIONAL_MODEL],
        "structural_only_holdings": tier_counts[STRUCTURAL_ONLY],
        "total_quantity": round(sum(number(row["quantity"]) for row in holdings), 6),
        "total_cost_basis_usd": round(sum(number(row["acquisition_cost_total"]) for row in holdings), 2),
        "total_modeled_value_usd": round(sum(number(row["current_modeled_value_usd"]) for row in positions), 2),
        "total_unrealized_gain_usd": round(sum(number(row["unrealized_gain_usd"]) for row in positions), 2),
        "quota_calls": 0,
        "checks": checks,
        "outputs": {key: str(path.resolve()) for key, path in paths.items()},
    }
    paths["manifest"].write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Secret Lair Full-Registry Portfolio Certification",
        "",
        f"**Status:** {status}",
        "",
        f"- Source rows: {len(owned)}",
        f"- Holdings rows: {len(holdings)}",
        f"- Full-model holdings: {tier_counts[FULL_MODEL]}",
        f"- Provisional-model holdings: {tier_counts[PROVISIONAL_MODEL]}",
        f"- Structural-only holdings: {tier_counts[STRUCTURAL_ONLY]}",
        f"- Total cost basis: ${result['total_cost_basis_usd']:,.2f}",
        f"- Total modeled value: ${result['total_modeled_value_usd']:,.2f}",
        f"- Total unrealized gain: ${result['total_unrealized_gain_usd']:,.2f}",
        "- API quota calls: 0",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in checks.items())
    paths["certification"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result
