from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "phase_8" / "mtg_intelligence_recovery" / "permanent_producer_repair"

FILES = {
    "producer": ROOT / "terminal2" / "market_sources" / "collector_box_evaluation.py",
    "unified": ROOT / "scripts" / "build_unified_mtg_intelligence.py",
    "hosted": ROOT / "scripts" / "build_mtg_hosted_uip_delivery.py",
}

for path in FILES.values():
    ast.parse(path.read_text(encoding="utf-8"))

producer = FILES["producer"].read_text(encoding="utf-8")
unified = FILES["unified"].read_text(encoding="utf-8")
hosted = FILES["hosted"].read_text(encoding="utf-8")

checks = {
    "producer_no_tier_scenario_constant": "SCENARIOS =" not in producer,
    "producer_native_method_present": "NATIVE_MONTE_CARLO_RANGE" in producer,
    "producer_observed_only_method_present": "OBSERVED_VALUE_ONLY" in producer,
    "producer_horizons_fail_closed": '"horizon_model_certified": "NO"' in producer,
    "unified_native_fields_mapped": '"native_forecast_base_usd": clean(forecast.get("native_forecast_base_usd"))' in unified,
    "unified_horizons_require_certification": 'normalize_bool(forecast.get("horizon_model_certified")) == "YES"' in unified,
    "hosted_current_value_precedence_fixed": hosted.find('"current_market_value_usd"') < hosted.find('"evaluated_market_value_usd"'),
    "hosted_horizons_require_certification": "horizon_certified" in hosted,
}

status = "CERTIFIED" if all(checks.values()) else "FAILED"
OUTPUT.mkdir(parents=True, exist_ok=True)
result = {
    "status": status,
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "checks": checks,
}
(OUTPUT / "PHASE_8_2_1B_3_CERTIFICATION.json").write_text(
    json.dumps(result, indent=2) + "\n",
    encoding="utf-8",
)

print("=" * 78)
print("PHASE 8.2.1B.3 — PERMANENT PRODUCER REPAIR CERTIFICATION")
print("=" * 78)
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} | {name}")
print(f"PHASE 8.2.1B.3 CERTIFICATION: {status}")
raise SystemExit(0 if status == "CERTIFIED" else 1)
