from scripts.build_mtg_current_market_accumulation import (
    latest_complete_attempt,
)

def test_completed_attempt_is_discoverable():
    attempt = latest_complete_attempt()
    assert attempt.name.startswith("attempt_")
    assert (attempt / "attempt_summary.json").is_file()
    assert (attempt / "current_market_listings.csv").is_file()
