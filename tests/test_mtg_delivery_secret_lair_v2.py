import csv
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_mtg_hosted_uip_delivery.py"
spec = importlib.util.spec_from_file_location("mtg_delivery", SCRIPT)
delivery = importlib.util.module_from_spec(spec)
sys.modules["mtg_delivery"] = delivery
spec.loader.exec_module(delivery)

BASE = {"current_price_authority_available": "true", "forecast_authority_available": "true", "forecast_1y_price_usd": "40",
        "forecast_1y_return": "0.1", "native_rank_type": "SECRET_LAIR_V1_1_PRODUCTION_COMPETITION_RANK",
        "execution_ready_purchase_certified": "false", "automatic_purchase_execution": "false"}


def payload():
    def row(lane, native, price, rank, status, semantic, manual):
        return dict(BASE, mtg_lane=lane, native_asset_id=native, current_price_usd=price, native_rank=rank,
                    native_purchase_status=status, purchase_semantic=semantic, manual_execution_price_check_required=manual)
    return [row("SECRET_LAIR_V1_1", "SL-A", "30", "5", "WAIT_FOR_Q10_ENTRY", "MODEL_ENTRY_PRICE_CONDITION_NOT_SATISFIED", "false"),
            row("SECRET_LAIR_V1_1", "SL-B", "50", "1", "BUY_CANDIDATE_NOW", "MODEL_QUALIFIED_ENTRY_CANDIDATE", "true"),
            row("SECRET_LAIR_V1_1", "SL-C", "20", "9", "WAIT_FOR_Q10_ENTRY", "X", "false"),
            row("SECRET_LAIR_V1_1", "SL-UNSCORED", "11", "7", "WAIT_FOR_Q10_ENTRY", "X", "false"),
            row("COLLECTOR_V1", "SL-A", "99", "2", "WATCHLIST", "Y", "false")]


def decisions(tmp_path):
    path = tmp_path / "decisions.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["secret_lair_id", "market_price", "call", "rank"])
        writer.writeheader()
        writer.writerows([{"secret_lair_id": "SL-A", "market_price": "33.5", "call": "BUY", "rank": "1"},
                          {"secret_lair_id": "SL-B", "market_price": "48", "call": "WAIT", "rank": "2"},
                          {"secret_lair_id": "SL-C", "market_price": "", "call": "NO_PRICE", "rank": ""}])
    return path


def test_v2_calls_replace_the_august_calls_with_safety_semantics_kept(tmp_path):
    rows = payload()
    assert delivery.apply_secret_lair_v2(rows, decisions(tmp_path)) == 3
    a, b, c, unscored, collector = rows
    assert (a["native_purchase_status"], a["purchase_semantic"], a["manual_execution_price_check_required"]) == ("BUY_CANDIDATE_NOW", "MODEL_QUALIFIED_ENTRY_CANDIDATE", "true")
    assert (a["current_price_usd"], a["native_rank"], a["native_rank_type"]) == ("33.5", "1", "SECRET_LAIR_V2_EXPECTED_NET_RETURN_6M")
    assert (b["native_purchase_status"], b["purchase_semantic"], b["manual_execution_price_check_required"]) == ("WAIT_FOR_LISTING_DISCOUNT", "MODEL_ENTRY_PRICE_CONDITION_NOT_SATISFIED", "false")
    assert c["native_purchase_status"] == "NO_CURRENT_MARKET_PRICE" and c["native_rank"] == ""
    assert all(r["forecast_authority_available"] == "false" and r["forecast_1y_return"] == "" for r in (a, b, c))
    assert all(r["execution_ready_purchase_certified"] == "false" and r["automatic_purchase_execution"] == "false" for r in rows)
    assert unscored["native_purchase_status"] == "WAIT_FOR_Q10_ENTRY" and unscored["forecast_1y_return"] == "0.1"
    assert collector["native_purchase_status"] == "WATCHLIST" and collector["current_price_usd"] == "99"


def test_no_decisions_file_changes_nothing(tmp_path):
    rows = payload()
    assert delivery.apply_secret_lair_v2(rows, tmp_path / "missing.csv") == 0
    assert rows == payload()


def test_the_overlay_is_off_unless_enabled():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "os.environ.get(SECRET_LAIR_V2_ENV) == \"1\"" in source and delivery.SECRET_LAIR_V2_ENV == "MTG_SECRET_LAIR_V2"
