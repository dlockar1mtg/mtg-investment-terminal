from scripts.run_universal_mtg_history_production import load_queries, production_readiness


def test_loads_all_152_approved_products():
    assert len(load_queries()) == 152


def test_readiness_is_fail_closed_without_credentials(monkeypatch):
    import scripts.run_universal_mtg_history_production as module
    monkeypatch.setattr(module, "credentials_present", lambda: False)
    result = production_readiness(152, 250)
    assert result["status"] == "NOT_READY"
    assert result["required_calls"] == 456
    assert result["live_execution_performed"] is False
