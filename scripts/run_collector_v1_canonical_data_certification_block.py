"""Run canonical Collector V1 input construction and coherence certification."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_v1_canonical_data_certification"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    steps = []
    commands = [
        [sys.executable, "scripts/build_collector_v1_canonical_inputs.py", "--strict"],
        [sys.executable, "scripts/certify_collector_v1_canonical_data_coherence.py", "--strict"],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, check=False)
        steps.append({"command": command, "return_code": result.returncode, "passed": result.returncode == 0})
        if result.returncode != 0:
            break
    coherence_path = ROOT / "data/governance/permanence/certification/collector_v1_canonical_data_coherence/collector_v1_canonical_data_coherence_summary.json"
    coherence = json.loads(coherence_path.read_text(encoding="utf-8")) if coherence_path.is_file() else {}
    passed = len(steps) == 2 and all(step["passed"] for step in steps) and coherence.get("data_coherence_certified") is True
    summary = {
        "block_name": "Collector V1 Canonical Data Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
        "data_coherence_certified": passed,
        "feature_matrix_authorized": passed,
        "forecast_experiments_authorized": passed,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "next_large_step": "Build the governed Collector V1 feature matrix" if passed else "Inspect canonical input or coherence failures",
        "status": "PASS_COLLECTOR_V1_CANONICAL_DATA_CERTIFICATION" if passed else "FAIL_COLLECTOR_V1_CANONICAL_DATA_CERTIFICATION",
    }
    (OUT / "collector_v1_canonical_data_certification_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
