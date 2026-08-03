from __future__ import annotations

import ast
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/operations/collector_forecast_traceability/candidate_v1_0_0"

STANDARD_FILES = [
    ROOT / "docs/standards/mtg/MTG_FORECASTING_STANDARD.md",
    ROOT / "docs/standards/mtg/lanes/COLLECTOR_BOOSTER_METHOD_SPECIFICATION.md",
    ROOT / "config/mtg/standards/mtg_forecasting_standard_v1.json",
    ROOT / "config/mtg/governance/collector_control_traceability_v1.json",
]

CANDIDATE_SCRIPTS = [
    ROOT / "scripts/build_collector_booster_box_full_evaluation.py",
    ROOT / "scripts/build_tier_1_forward_scenarios.py",
    ROOT / "scripts/route_collector_forecast_methods.py",
    ROOT / "scripts/select_collector_comparables.py",
    ROOT / "scripts/normalize_collector_evidence.py",
    ROOT / "scripts/build_mtg_hosted_uip_delivery.py",
]


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def literal_text(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def inspect_script(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not path.exists():
        return [], [{"path": path.relative_to(ROOT).as_posix(), "issue": "MISSING_SCRIPT"}]
    text = path.read_text(encoding="utf-8-sig")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [], [{"path": path.relative_to(ROOT).as_posix(), "issue": f"SYNTAX_ERROR:{exc.lineno}"}]

    rows: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            rows.append({
                "path": path.relative_to(ROOT).as_posix(),
                "line": node.lineno,
                "element_type": "FUNCTION",
                "element_name": node.name,
                "expression": "",
                "authority_status": "REVIEW_REQUIRED",
                "standard_reference": "",
                "production_status": "UNDETERMINED",
            })
        elif isinstance(node, ast.Assign):
            names = [literal_text(t) for t in node.targets]
            value = literal_text(node.value)
            if any(token in ("rate", "weight", "score", "threshold", "penalty", "cap", "floor", "confidence", "uncertainty", "forecast", "projection") for token in (" ".join(names) + " " + value).lower().replace("_", " ").split()):
                rows.append({
                    "path": path.relative_to(ROOT).as_posix(),
                    "line": node.lineno,
                    "element_type": "ASSIGNMENT",
                    "element_name": "|".join(names),
                    "expression": value[:1000],
                    "authority_status": "REVIEW_REQUIRED",
                    "standard_reference": "",
                    "production_status": "UNDETERMINED",
                })
        elif isinstance(node, ast.Compare):
            expr = literal_text(node)
            if any(word in expr.lower() for word in ("forecast", "projection", "confidence", "uncertainty", "price", "history", "comparable", "count")):
                rows.append({
                    "path": path.relative_to(ROOT).as_posix(),
                    "line": getattr(node, "lineno", 0),
                    "element_type": "COMPARISON",
                    "element_name": "",
                    "expression": expr[:1000],
                    "authority_status": "REVIEW_REQUIRED",
                    "standard_reference": "",
                    "production_status": "UNDETERMINED",
                })
    return rows, []


def main() -> int:
    implementation_rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for path in CANDIDATE_SCRIPTS:
        rows, script_issues = inspect_script(path)
        implementation_rows.extend(rows)
        issues.extend(script_issues)

    standard_rows = []
    for path in STANDARD_FILES:
        standard_rows.append({
            "path": path.relative_to(ROOT).as_posix(),
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
        })
        if not path.exists():
            issues.append({"path": path.relative_to(ROOT).as_posix(), "issue": "MISSING_STANDARD"})

    write_csv(
        OUTPUT / "collector_forecast_implementation_inventory.csv",
        implementation_rows,
        ["path", "line", "element_type", "element_name", "expression", "authority_status", "standard_reference", "production_status"],
    )
    write_csv(
        OUTPUT / "collector_standard_source_inventory.csv",
        standard_rows,
        ["path", "exists", "size_bytes"],
    )
    write_csv(
        OUTPUT / "collector_traceability_review_required.csv",
        issues,
        ["path", "issue"],
    )

    summary = {
        "audit_name": "Collector Forecast Implementation Traceability",
        "audit_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "implementation_element_count": len(implementation_rows),
        "standard_source_count": len(standard_rows),
        "missing_or_parse_issue_count": len(issues),
        "methodology_changed": False,
        "projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "owner_approval_status": "NOT_REQUESTED",
        "status": "REVIEW_REQUIRED",
        "governing_note": "This audit inventories existing implementation behavior only. It does not approve, activate, alter, or invent any control.",
    }
    write_json(OUTPUT / "collector_forecast_traceability_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
