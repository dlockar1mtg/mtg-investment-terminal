from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.build_secret_lair_terminal_integration import build
from scripts.manage_secret_lair_holdings import certify_holdings


def refresh(model_values: Path, admission_manifest: Path, holdings: Path, output_root: Path) -> dict[str, object]:
    integration_root = output_root / "terminal_integration"
    holdings_cert_root = output_root / "holdings_certification"
    valuation_universe = integration_root / "secret_lair_terminal_valuation_universe.csv"

    first = build(model_values, admission_manifest, integration_root)
    holdings_cert = certify_holdings(holdings, valuation_universe, holdings_cert_root)
    if holdings_cert["status"] != "CERTIFIED":
        result = {"status": "FAILED", "holdings_certification": holdings_cert, "initial_integration": first}
        print("SECRET LAIR PORTFOLIO REFRESH: FAILED")
        print(json.dumps(result, indent=2))
        return result

    final = build(model_values, admission_manifest, integration_root, holdings)
    status = "CERTIFIED" if final["status"] == "CERTIFIED" and holdings_cert["status"] == "CERTIFIED" else "FAILED"
    result = {
        "status": status,
        "holdings_certification": holdings_cert,
        "terminal_integration": final,
        "published_outputs": final["outputs"],
        "quota_calls": 0,
    }
    (output_root / "secret_lair_portfolio_refresh_manifest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("SECRET LAIR PORTFOLIO REFRESH: COMPLETE")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-values", type=Path, required=True)
    parser.add_argument("--admission-manifest", type=Path, required=True)
    parser.add_argument("--holdings", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    refresh(args.model_values, args.admission_manifest, args.holdings, args.output_root)


if __name__ == "__main__":
    main()
