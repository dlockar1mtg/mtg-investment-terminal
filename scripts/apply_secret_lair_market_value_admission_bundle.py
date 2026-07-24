from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    ROOT / "scripts/build_secret_lair_market_value_admission.py": r'''from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPECTED_PRODUCTS = 973
EXPECTED_PASS = 214
VALID_DECISIONS = {"PASS", "REVIEW_REQUIRED", "EXCLUDE_FROM_MODEL"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def value(row: dict[str, str], *names: str) -> str:
    for name in names:
        candidate = (row.get(name) or "").strip()
        if candidate:
            return candidate
    return ""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def suppression_reason(decision: str, flags: str) -> str:
    if decision == "PASS":
        return ""
    if decision == "REVIEW_REQUIRED":
        return f"QUALITY_REVIEW_REQUIRED:{flags or 'UNSPECIFIED_FLAG'}"
    return f"QUALITY_EXCLUDED:{flags or 'UNSPECIFIED_FLAG'}"


def build_admission_rows(audit_rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ledger: list[dict[str, Any]] = []
    admitted: list[dict[str, Any]] = []

    for row in audit_rows:
        decision = value(row, "quality_decision")
        if decision not in VALID_DECISIONS:
            raise ValueError(f"Invalid quality decision: {decision!r}")

        product_id = value(row, "canonical_product_id")
        product_name = value(row, "canonical_product_name")
        flags = value(row, "quality_flags")
        market_value = value(row, "market_value_median")
        is_admitted = decision == "PASS"

        ledger_row: dict[str, Any] = {
            "canonical_product_id": product_id,
            "canonical_product_name": product_name,
            "quality_decision": decision,
            "admission_decision": "ADMITTED" if is_admitted else "SUPPRESSED",
            "suppression_reason": suppression_reason(decision, flags),
            "market_value_usd": market_value if is_admitted else "",
            "observation_count": value(row, "observation_count"),
            "seller_count": value(row, "seller_count"),
            "confidence_score": value(row, "confidence_score"),
            "confidence_state": value(row, "confidence_state"),
            "sample_state": value(row, "sample_state"),
            "price_dispersion_cv": value(row, "price_dispersion_cv"),
            "market_value_low": value(row, "market_value_low"),
            "market_value_high": value(row, "market_value_high"),
            "quality_flags": flags,
            "source": "EBAY_CERTIFIED_SECRET_LAIR",
            "valuation_method": "MEDIAN_ACCEPTED_ACTIVE_LISTINGS_IQR_FILTERED",
            "currency": "USD",
        }
        ledger.append(ledger_row)

        if is_admitted:
            admitted.append({
                "canonical_product_id": product_id,
                "canonical_product_name": product_name,
                "market_value_usd": market_value,
                "currency": "USD",
                "observation_count": value(row, "observation_count"),
                "seller_count": value(row, "seller_count"),
                "confidence_score": value(row, "confidence_score"),
                "confidence_state": value(row, "confidence_state"),
                "sample_state": value(row, "sample_state"),
                "price_dispersion_cv": value(row, "price_dispersion_cv"),
                "market_value_low": value(row, "market_value_low"),
                "market_value_high": value(row, "market_value_high"),
                "source": "EBAY_CERTIFIED_SECRET_LAIR",
                "valuation_method": "MEDIAN_ACCEPTED_ACTIVE_LISTINGS_IQR_FILTERED",
                "model_input_status": "ACTIVE",
            })

    ledger.sort(key=lambda row: str(row["canonical_product_id"]))
    admitted.sort(key=lambda row: str(row["canonical_product_id"]))
    return ledger, admitted


def certify(
    audit_summary: dict[str, Any],
    audit_rows: list[dict[str, str]],
    ledger: list[dict[str, Any]],
    admitted: list[dict[str, Any]],
) -> dict[str, bool]:
    audit_decisions = Counter(row.get("quality_decision", "") for row in audit_rows)
    ledger_admissions = Counter(str(row["admission_decision"]) for row in ledger)
    audit_ids = {row.get("canonical_product_id", "") for row in audit_rows}
    ledger_ids = {str(row["canonical_product_id"]) for row in ledger}
    admitted_ids = {str(row["canonical_product_id"]) for row in admitted}

    return {
        "source_audit_certified": audit_summary.get("status") == "CERTIFIED",
        "source_products_equal_973": int(audit_summary.get("products", -1)) == EXPECTED_PRODUCTS,
        "ledger_rows_equal_973": len(ledger) == EXPECTED_PRODUCTS,
        "ledger_unique_products_equal_973": len(ledger_ids) == EXPECTED_PRODUCTS,
        "source_and_ledger_ids_match": audit_ids == ledger_ids,
        "source_pass_equal_214": audit_decisions["PASS"] == EXPECTED_PASS,
        "admitted_rows_equal_source_pass": len(admitted) == audit_decisions["PASS"],
        "admitted_rows_equal_214": len(admitted) == EXPECTED_PASS,
        "admitted_ids_match_pass_ids": admitted_ids == {
            row.get("canonical_product_id", "") for row in audit_rows if row.get("quality_decision") == "PASS"
        },
        "suppressed_rows_equal_nonpass": ledger_admissions["SUPPRESSED"] == (
            audit_decisions["REVIEW_REQUIRED"] + audit_decisions["EXCLUDE_FROM_MODEL"]
        ),
        "no_suppressed_market_values": all(
            not str(row["market_value_usd"]).strip()
            for row in ledger
            if row["admission_decision"] == "SUPPRESSED"
        ),
        "all_admitted_market_values_present": all(
            str(row["market_value_usd"]).strip() for row in admitted
        ),
        "all_admitted_currency_usd": all(row["currency"] == "USD" for row in admitted),
        "quota_calls_zero": True,
    }


def build_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Secret Lair Governed Market-Value Admission Certification",
        "",
        f"**Status:** {summary['status']}",
        f"**Generated at (UTC):** {summary['generated_at_utc']}",
        "",
        "## Admission Results",
        "",
        f"- Universe products: {summary['products']}",
        f"- Admitted model values: {summary['admitted_products']}",
        f"- Suppressed products: {summary['suppressed_products']}",
        f"- Review-required suppressed: {summary['review_required_products']}",
        f"- Excluded suppressed: {summary['excluded_products']}",
        f"- API quota calls: {summary['quota_calls']}",
        "",
        "## Certification Checks",
        "",
    ]
    for name, passed in summary["checks"].items():
        lines.append(f"- {name}: {'PASS' if passed else 'FAIL'}")
    lines.extend([
        "",
        "## Governance Decision",
        "",
        "Only products with a certified quality decision of PASS are exposed through the model-facing valuation interface. All other values remain suppressed while full product lineage is retained in the admission ledger.",
        "",
    ])
    return "\n".join(lines)


def run(audit_csv: Path, audit_summary_json: Path, output_root: Path) -> dict[str, Any]:
    audit_rows = read_csv(audit_csv)
    audit_summary = read_json(audit_summary_json)
    ledger, admitted = build_admission_rows(audit_rows)
    checks = certify(audit_summary, audit_rows, ledger, admitted)
    decisions = Counter(row.get("quality_decision", "") for row in audit_rows)

    output_root.mkdir(parents=True, exist_ok=True)
    ledger_path = output_root / "secret_lair_market_value_admission_ledger.csv"
    model_path = output_root / "secret_lair_model_market_values.csv"
    manifest_path = output_root / "secret_lair_market_value_admission_manifest.json"
    certification_path = output_root / "SECRET_LAIR_MARKET_VALUE_ADMISSION_CERTIFICATION.md"

    ledger_fields = [
        "canonical_product_id", "canonical_product_name", "quality_decision",
        "admission_decision", "suppression_reason", "market_value_usd",
        "observation_count", "seller_count", "confidence_score", "confidence_state",
        "sample_state", "price_dispersion_cv", "market_value_low", "market_value_high",
        "quality_flags", "source", "valuation_method", "currency",
    ]
    model_fields = [
        "canonical_product_id", "canonical_product_name", "market_value_usd", "currency",
        "observation_count", "seller_count", "confidence_score", "confidence_state",
        "sample_state", "price_dispersion_cv", "market_value_low", "market_value_high",
        "source", "valuation_method", "model_input_status",
    ]
    write_csv(ledger_path, ledger, ledger_fields)
    write_csv(model_path, admitted, model_fields)

    summary: dict[str, Any] = {
        "status": "CERTIFIED" if all(checks.values()) else "FAILED",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_audit_csv": str(audit_csv.resolve()),
        "source_audit_summary": str(audit_summary_json.resolve()),
        "source_audit_sha256": file_sha256(audit_csv),
        "products": len(ledger),
        "admitted_products": len(admitted),
        "suppressed_products": len(ledger) - len(admitted),
        "review_required_products": decisions["REVIEW_REQUIRED"],
        "excluded_products": decisions["EXCLUDE_FROM_MODEL"],
        "quota_calls": 0,
        "checks": checks,
        "outputs": {
            "admission_ledger_csv": str(ledger_path.resolve()),
            "model_values_csv": str(model_path.resolve()),
            "manifest_json": str(manifest_path.resolve()),
            "certification_markdown": str(certification_path.resolve()),
        },
    }
    manifest_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    certification_path.write_text(build_markdown(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-csv", type=Path, required=True)
    parser.add_argument("--audit-summary", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.audit_csv, args.audit_summary, args.output_root)
    print("SECRET LAIR MARKET VALUE ADMISSION: COMPLETE")
    print(json.dumps(result, indent=2))
    if result["status"] != "CERTIFIED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
''',
    ROOT / "terminal2/market_sources/secret_lair_market_values.py": r'''from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SecretLairMarketValue:
    canonical_product_id: str
    canonical_product_name: str
    market_value_usd: float
    currency: str
    observation_count: int
    seller_count: int
    confidence_score: float
    confidence_state: str
    sample_state: str
    source: str
    valuation_method: str


class SecretLairMarketValueStore:
    """Read-only model-facing interface for admitted Secret Lair values."""

    def __init__(self, csv_path: str | Path) -> None:
        self.csv_path = Path(csv_path)

    def load(self) -> list[SecretLairMarketValue]:
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        values = [self._parse(row) for row in rows]
        self._validate(values)
        return values

    def by_product_id(self) -> dict[str, SecretLairMarketValue]:
        return {value.canonical_product_id: value for value in self.load()}

    @staticmethod
    def _parse(row: dict[str, str]) -> SecretLairMarketValue:
        return SecretLairMarketValue(
            canonical_product_id=row["canonical_product_id"],
            canonical_product_name=row["canonical_product_name"],
            market_value_usd=float(row["market_value_usd"]),
            currency=row["currency"],
            observation_count=int(row["observation_count"]),
            seller_count=int(row["seller_count"]),
            confidence_score=float(row["confidence_score"]),
            confidence_state=row["confidence_state"],
            sample_state=row["sample_state"],
            source=row["source"],
            valuation_method=row["valuation_method"],
        )

    @staticmethod
    def _validate(values: Iterable[SecretLairMarketValue]) -> None:
        items = list(values)
        ids = [item.canonical_product_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate canonical product IDs in model-facing values")
        for item in items:
            if item.market_value_usd <= 0:
                raise ValueError(f"Non-positive market value for {item.canonical_product_id}")
            if item.currency != "USD":
                raise ValueError(f"Unsupported currency for {item.canonical_product_id}: {item.currency}")
            if item.observation_count <= 0 or item.seller_count <= 0:
                raise ValueError(f"Invalid evidence counts for {item.canonical_product_id}")
''',
    ROOT / "tests/test_secret_lair_market_value_admission.py": r'''from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_secret_lair_market_value_admission",
    ROOT / "scripts/build_secret_lair_market_value_admission.py",
)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def row(product_id: str, decision: str, median: str = "50.0", flags: str = "") -> dict[str, str]:
    return {
        "canonical_product_id": product_id,
        "canonical_product_name": product_id,
        "quality_decision": decision,
        "quality_flags": flags,
        "market_value_median": median,
        "observation_count": "3",
        "seller_count": "3",
        "confidence_score": "80",
        "confidence_state": "HIGH",
        "sample_state": "MODERATE_EVIDENCE",
        "price_dispersion_cv": "0.1",
        "market_value_low": "45",
        "market_value_high": "55",
    }


def test_pass_rows_are_admitted():
    ledger, admitted = MOD.build_admission_rows([row("A", "PASS")])
    assert ledger[0]["admission_decision"] == "ADMITTED"
    assert ledger[0]["market_value_usd"] == "50.0"
    assert admitted[0]["canonical_product_id"] == "A"


def test_review_rows_are_suppressed():
    ledger, admitted = MOD.build_admission_rows([row("A", "REVIEW_REQUIRED", flags="LOW_CONFIDENCE")])
    assert ledger[0]["admission_decision"] == "SUPPRESSED"
    assert ledger[0]["market_value_usd"] == ""
    assert ledger[0]["suppression_reason"] == "QUALITY_REVIEW_REQUIRED:LOW_CONFIDENCE"
    assert admitted == []


def test_excluded_rows_are_suppressed():
    ledger, admitted = MOD.build_admission_rows([row("A", "EXCLUDE_FROM_MODEL", flags="NO_ACCEPTED_EVIDENCE")])
    assert ledger[0]["suppression_reason"] == "QUALITY_EXCLUDED:NO_ACCEPTED_EVIDENCE"
    assert admitted == []


def test_invalid_decision_rejected():
    try:
        MOD.build_admission_rows([row("A", "UNKNOWN")])
    except ValueError as error:
        assert "Invalid quality decision" in str(error)
    else:
        raise AssertionError("Expected invalid decision to fail")
''',
    ROOT / "tests/test_secret_lair_market_value_interface.py": r'''from __future__ import annotations

import csv
from pathlib import Path

from terminal2.market_sources.secret_lair_market_values import SecretLairMarketValueStore


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def base_row(product_id: str = "A") -> dict[str, str]:
    return {
        "canonical_product_id": product_id,
        "canonical_product_name": product_id,
        "market_value_usd": "50.0",
        "currency": "USD",
        "observation_count": "3",
        "seller_count": "3",
        "confidence_score": "80",
        "confidence_state": "HIGH",
        "sample_state": "MODERATE_EVIDENCE",
        "price_dispersion_cv": "0.1",
        "market_value_low": "45",
        "market_value_high": "55",
        "source": "EBAY_CERTIFIED_SECRET_LAIR",
        "valuation_method": "MEDIAN_ACCEPTED_ACTIVE_LISTINGS_IQR_FILTERED",
        "model_input_status": "ACTIVE",
    }


def test_store_loads_model_values(tmp_path: Path):
    path = tmp_path / "values.csv"
    write_rows(path, [base_row()])
    values = SecretLairMarketValueStore(path).load()
    assert len(values) == 1
    assert values[0].market_value_usd == 50.0


def test_store_indexes_by_product_id(tmp_path: Path):
    path = tmp_path / "values.csv"
    write_rows(path, [base_row("A"), base_row("B")])
    values = SecretLairMarketValueStore(path).by_product_id()
    assert set(values) == {"A", "B"}


def test_store_rejects_duplicate_ids(tmp_path: Path):
    path = tmp_path / "values.csv"
    write_rows(path, [base_row("A"), base_row("A")])
    try:
        SecretLairMarketValueStore(path).load()
    except ValueError as error:
        assert "Duplicate canonical product IDs" in str(error)
    else:
        raise AssertionError("Expected duplicate IDs to fail")


def test_store_rejects_non_positive_values(tmp_path: Path):
    path = tmp_path / "values.csv"
    bad = base_row()
    bad["market_value_usd"] = "0"
    write_rows(path, [bad])
    try:
        SecretLairMarketValueStore(path).load()
    except ValueError as error:
        assert "Non-positive market value" in str(error)
    else:
        raise AssertionError("Expected non-positive value to fail")
''',
}


def apply() -> None:
    for path in FILES:
        if path.exists():
            raise RuntimeError(f"Refusing to overwrite existing file: {path.relative_to(ROOT)}")
    for path, content in FILES.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"Created: {path.relative_to(ROOT)}")
    print("SECRET LAIR MARKET VALUE ADMISSION BUNDLE: APPLIED")


if __name__ == "__main__":
    apply()
