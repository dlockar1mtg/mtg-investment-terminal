from __future__ import annotations

import json
from pathlib import Path

from scripts import run_daily_ebay_collection as entrypoint


def test_dry_run_never_calls_live_collector(monkeypatch, tmp_path: Path) -> None:
    called = False

    def fail_if_called(**_: object) -> dict[str, object]:
        nonlocal called
        called = True
        raise AssertionError("live collector must not run during dry-run")

    monkeypatch.setattr(entrypoint, "run_coverage", fail_if_called)
    output = tmp_path / "summary.json"

    result = entrypoint.main([
        "--dry-run",
        "--limit-per-product",
        "15",
        "--max-products",
        "3",
        "--summary-output",
        str(output),
    ])

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert result == 0
    assert called is False
    assert payload["status"] == "DRY_RUN"
    assert payload["live_api_called"] is False
    assert payload["limit_per_product"] == 15
    assert payload["max_products"] == 3


def test_live_mode_delegates_to_existing_coverage(monkeypatch, tmp_path: Path) -> None:
    received: dict[str, object] = {}

    def fake_run_coverage(*, limit_per_product: int, max_products: int | None) -> dict[str, object]:
        received.update(
            limit_per_product=limit_per_product,
            max_products=max_products,
        )
        print("[1/2] Example product: LIMITED_MATCH_COVERAGE")
        return {"run_id": "EBAYTEST", "products": 2, "credentials_printed": False}

    monkeypatch.setattr(entrypoint, "run_coverage", fake_run_coverage)
    output = tmp_path / "summary.json"

    result = entrypoint.main([
        "--limit-per-product",
        "10",
        "--max-products",
        "2",
        "--summary-output",
        str(output),
    ])

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert result == 0
    assert received == {"limit_per_product": 10, "max_products": 2}
    assert payload["status"] == "PASS"
    assert payload["live_api_called"] is True
    assert payload["credentials_printed"] is False
    assert payload["progress_log"] == ["[1/2] Example product: LIMITED_MATCH_COVERAGE"]
