from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _safe_extract(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as handle:
        root = destination.resolve()
        for member in handle.infolist():
            target = (destination / member.filename).resolve()
            if root not in target.parents and target != root:
                raise RuntimeError(f"Unsafe artifact member path: {member.filename}")
        handle.extractall(destination)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay the patched MTG live overlay against a preserved production artifact."
    )
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--expected-prices", type=int, default=161)
    parser.add_argument("--expected-decisions", type=int, default=49)
    args = parser.parse_args()

    artifact = args.artifact.resolve()
    if not artifact.is_file():
        raise SystemExit(f"Artifact does not exist: {artifact}")

    replay_root = Path(tempfile.mkdtemp(prefix="mtg-r2-live-overlay-replay-"))
    try:
        _safe_extract(artifact, replay_root)
        package = replay_root / "operations" / "mtg_uip_delivery" / "latest"
        market = replay_root / "operations" / "mtg_marketplace"

        required = [
            package / "package_summary.json",
            package / "asset_master.csv",
            package / "forecasts.csv",
            package / "recommendations.csv",
            package / "risk_metrics.csv",
            package / "platform_status.csv",
            package / "export_manifest.json",
            market / "consolidated_marketplace_prices.csv",
            market / "certified_marketplace_decisions.csv",
        ]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise SystemExit("Artifact is missing required replay evidence:\n" + "\n".join(missing))

        command = [
            sys.executable,
            str(ROOT / "scripts" / "apply_mtg_live_uip_overlay.py"),
            "--package",
            str(package),
            "--market-root",
            str(market),
        ]
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode != 0:
            raise SystemExit(
                f"Patched overlay replay failed with exit code {completed.returncode}."
            )

        summary = json.loads((package / "package_summary.json").read_text(encoding="utf-8"))
        overlay = summary.get("live_overlay") or {}

        observed = {
            "status": overlay.get("status"),
            "certified_price_rows_available": int(overlay.get("certified_price_rows_available", 0) or 0),
            "products_with_live_prices": int(overlay.get("products_with_live_prices", 0) or 0),
            "certified_decision_rows_available": int(overlay.get("certified_decision_rows_available", 0) or 0),
            "products_with_live_decisions": int(overlay.get("products_with_live_decisions", 0) or 0),
            "products_with_any_live_overlay": int(overlay.get("products_with_any_live_overlay", 0) or 0),
            "products_using_baseline_fallback": int(overlay.get("products_using_baseline_fallback", 0) or 0),
        }
        print(json.dumps(observed, indent=2, sort_keys=True))

        failures: list[str] = []
        if observed["status"] != "PASS":
            failures.append("live overlay status was not PASS")
        if observed["certified_price_rows_available"] != args.expected_prices:
            failures.append(
                "certified price rows differed from expected "
                f"{args.expected_prices}"
            )
        if observed["products_with_live_prices"] != args.expected_prices:
            failures.append(
                "not all certified price rows were applied: "
                f"{observed['products_with_live_prices']}/{args.expected_prices}"
            )
        if observed["certified_decision_rows_available"] != args.expected_decisions:
            failures.append(
                "certified decision rows differed from expected "
                f"{args.expected_decisions}"
            )
        if observed["products_with_live_decisions"] != args.expected_decisions:
            failures.append(
                "not all certified decision rows were applied: "
                f"{observed['products_with_live_decisions']}/{args.expected_decisions}"
            )

        if failures:
            raise SystemExit("MTG R2 LIVE OVERLAY REPLAY FAILED: " + "; ".join(failures))

        print("MTG_R2_LIVE_OVERLAY_REPLAY=PASS")
        print(f"CERTIFIED_PRICES={args.expected_prices}")
        print(f"APPLIED_LIVE_PRICES={args.expected_prices}")
        print(f"CERTIFIED_DECISIONS={args.expected_decisions}")
        print(f"APPLIED_LIVE_DECISIONS={args.expected_decisions}")
        print("NEW_LIVE_COLLECTION_EXECUTED=FALSE")
        return 0
    finally:
        shutil.rmtree(replay_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
