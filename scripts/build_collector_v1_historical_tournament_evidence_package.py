from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOTS = [
    Path(r"C:\Users\DevonLockard\InvestmentPlatform-MTG-Reconciliation"),
    Path(r"C:\Users\DevonLockard\mtg_investment"),
    Path(r"C:\Users\DevonLockard\mtg-source"),
    Path(r"C:\Users\DevonLockard\UIP_MTG_Historical_Reconstruction_Evidence"),
]

TEXT_EXTENSIONS = {
    ".py", ".csv", ".json", ".jsonl", ".md", ".txt", ".log", ".yaml", ".yml", ".toml", ".html", ".js"
}
COPY_EXTENSIONS = TEXT_EXTENSIONS | {".parquet", ".feather", ".xlsx", ".xls", ".db", ".sqlite", ".sqlite3", ".duckdb", ".pkl", ".pickle", ".joblib"}
EXCLUDED_PARTS = {".git", ".venv", "venv", "env", "node_modules", "__pycache__", ".pytest_cache", "site-packages", "dist", "build", "cache", "tmp", "temp"}

CONCEPTS = {
    "short_horizon_backtest": [r"\b90\s*day\b", r"\b90d\b", r"\b180\s*day\b", r"\b180d\b", r"\b365\s*day\b", r"\b365d\b", r"walk[- ]forward", r"out[- ]of[- ]sample", r"backtest"],
    "model_tournament": [r"model tournament", r"candidate model", r"champion model", r"winning model", r"model registry", r"leaderboard", r"scorecard", r"hyperparameter"],
    "comparable_selection": [r"comparable product", r"similarity score", r"nearest neighbor", r"peer set", r"analog product", r"comparison cohort"],
    "breakout_validation": [r"breakout", r"early buy", r"pre[- ]growth", r"before.*growth", r"opportunity recall", r"top[- ]k precision"],
    "monte_carlo": [r"monte carlo", r"simulation path", r"terminal value", r"percentile", r"probability of gain", r"3[- ]year", r"5[- ]year"],
    "supply_demand": [r"supply", r"demand", r"listing count", r"seller concentration", r"liquidity", r"inventory", r"scarcity", r"reprint"],
    "forecast_results": [r"forecast", r"prediction", r"actual", r"mae", r"rmse", r"directional accuracy", r"interval coverage", r"calibration"],
    "ranking_results": [r"ranking", r"rank correlation", r"decile", r"precision@", r"top[- ]k", r"priority score"],
}

RESULT_HINTS = ("result", "output", "score", "winner", "leader", "backtest", "prediction", "forecast", "simulation", "calibration", "evaluation", "report", "summary")
IMPLEMENTATION_HINTS = ("engine", "model", "service", "runner", "pipeline", "registry", "contract", "test_")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_read(path: Path, limit: int = 2_000_000) -> str:
    try:
        with path.open("rb") as handle:
            raw = handle.read(limit)
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def excluded(path: Path) -> bool:
    return any(part.lower() in EXCLUDED_PARTS for part in path.parts)


def classify(path: Path, content: str, concepts: list[str]) -> str:
    lower = str(path).lower()
    suffix = path.suffix.lower()
    if suffix in {".csv", ".json", ".jsonl", ".parquet", ".feather", ".xlsx", ".xls", ".db", ".sqlite", ".sqlite3", ".duckdb"}:
        if any(hint in lower for hint in RESULT_HINTS) or len(concepts) >= 2:
            return "EXECUTED_OR_GENERATED_EVIDENCE"
        return "DATA_OR_STATE_ARTIFACT"
    if suffix == ".py":
        return "IMPLEMENTATION_OR_TEST"
    if suffix in {".md", ".txt", ".log", ".html"}:
        if any(hint in lower for hint in RESULT_HINTS) and re.search(r"\b(pass|winner|selected|mae|rmse|accuracy|percentile|simulation)\b", content, re.I):
            return "RESULT_REPORT_OR_CERTIFICATION"
        return "DOCUMENTATION_OR_LOG"
    return "OTHER_RELEVANT_ARTIFACT"


def score(path: Path, content: str, concepts: list[str], category: str) -> int:
    value = len(concepts) * 10
    lower = str(path).lower()
    if category == "EXECUTED_OR_GENERATED_EVIDENCE":
        value += 35
    elif category == "RESULT_REPORT_OR_CERTIFICATION":
        value += 25
    elif category == "DATA_OR_STATE_ARTIFACT":
        value += 15
    if any(hint in lower for hint in RESULT_HINTS):
        value += 10
    if re.search(r"\b(mae|rmse|directional accuracy|winner|selected model|percentile|probability|backtest)\b", content, re.I):
        value += 15
    if path.stat().st_size > 0:
        value += 1
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(Path.home() / "Desktop" / "MTG_Targeted_Historical_Tournament_Evidence.zip"))
    parser.add_argument("--max-package-mb", type=int, default=75)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    generated = datetime.now(timezone.utc).isoformat()
    staging = Path(r"C:\MTGPKG\targeted_tournament_evidence")
    if staging.exists():
        shutil.rmtree(staging)
    payload = staging / "files"
    payload.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    scanned = 0
    errors: list[dict[str, str]] = []

    compiled = {name: [re.compile(pattern, re.I) for pattern in patterns] for name, patterns in CONCEPTS.items()}

    for root in ROOTS:
        if not root.exists():
            errors.append({"path": str(root), "error": "ROOT_NOT_FOUND"})
            continue
        for path in root.rglob("*"):
            if not path.is_file() or excluded(path) or path.suffix.lower() not in COPY_EXTENSIONS:
                continue
            scanned += 1
            try:
                content = safe_read(path) if path.suffix.lower() in TEXT_EXTENSIONS else ""
                search_text = f"{path.name}\n{path.relative_to(root)}\n{content}"
                concepts = [name for name, patterns in compiled.items() if any(pattern.search(search_text) for pattern in patterns)]
                if not concepts:
                    continue
                category = classify(path, content, concepts)
                evidence_score = score(path, content, concepts, category)
                rows.append({
                    "project_name": root.name,
                    "project_root": str(root),
                    "source_path": str(path),
                    "relative_path": str(path.relative_to(root)),
                    "extension": path.suffix.lower(),
                    "size_bytes": path.stat().st_size,
                    "modified_at_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                    "sha256": sha256(path),
                    "classification": category,
                    "concepts": "|".join(sorted(concepts)),
                    "evidence_score": evidence_score,
                })
            except Exception as exc:
                errors.append({"path": str(path), "error": str(exc)})

    rows.sort(key=lambda row: (-int(row["evidence_score"]), int(row["size_bytes"]), str(row["source_path"])))

    package_limit = args.max_package_mb * 1024 * 1024
    copied = 0
    copied_bytes = 0
    for index, row in enumerate(rows, start=1):
        source = Path(str(row["source_path"]))
        priority = row["classification"] in {"EXECUTED_OR_GENERATED_EVIDENCE", "RESULT_REPORT_OR_CERTIFICATION"}
        if not priority and int(row["evidence_score"]) < 35:
            row["packaged"] = False
            row["packaged_path"] = ""
            continue
        if source.stat().st_size > 15 * 1024 * 1024 or copied_bytes + source.stat().st_size > package_limit:
            row["packaged"] = False
            row["packaged_path"] = ""
            continue
        name = f"{index:05d}_{hashlib.sha256(str(source).encode()).hexdigest()[:16]}{source.suffix.lower()}"
        destination = payload / name
        shutil.copy2(source, destination)
        row["packaged"] = True
        row["packaged_path"] = str(Path("files") / name)
        copied += 1
        copied_bytes += source.stat().st_size

    fieldnames = [
        "project_name", "project_root", "source_path", "relative_path", "extension", "size_bytes",
        "modified_at_utc", "sha256", "classification", "concepts", "evidence_score", "packaged", "packaged_path"
    ]
    with (staging / "historical_tournament_evidence_inventory.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with (staging / "scan_errors.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "error"])
        writer.writeheader()
        writer.writerows(errors)

    classification_counts = Counter(str(row["classification"]) for row in rows)
    concept_counts = Counter(concept for row in rows for concept in str(row["concepts"]).split("|") if concept)
    project_counts = Counter(str(row["project_name"]) for row in rows)
    summary = {
        "block_name": "Collector V1 Targeted Historical Tournament Evidence Recovery",
        "block_version": "1.0.0",
        "generated_at_utc": generated,
        "roots_reviewed": [str(root) for root in ROOTS],
        "files_scanned": scanned,
        "relevant_files_identified": len(rows),
        "files_packaged": copied,
        "packaged_bytes": copied_bytes,
        "classification_counts": dict(classification_counts),
        "concept_counts": dict(concept_counts),
        "project_counts": dict(project_counts),
        "scan_error_count": len(errors),
        "fixed_weights_required": False,
        "evidence_based_horizons_required": ["90_day", "180_day", "365_day", "3_year", "5_year"],
        "purchase_recommendations_authorized": False,
        "status": "PASS_TARGETED_HISTORICAL_TOURNAMENT_EVIDENCE_PACKAGE" if rows and copied else "FAIL_TARGETED_HISTORICAL_TOURNAMENT_EVIDENCE_PACKAGE",
    }
    (staging / "historical_tournament_evidence_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in staging.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(staging))

    summary["output_zip"] = str(output)
    summary["output_zip_bytes"] = output.stat().st_size
    summary["output_zip_sha256"] = sha256(output)
    print(json.dumps(summary, indent=2))
    passed = summary["status"].startswith("PASS")
    return 0 if passed or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
