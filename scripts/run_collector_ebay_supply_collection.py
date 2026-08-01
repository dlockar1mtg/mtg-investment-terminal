"""Run governed eBay capability, diagnostic, or shadow Collector supply collection.

Secrets are read only from EBAY_CLIENT_ID and EBAY_CLIENT_SECRET environment variables.
They are never written to output, logs, raw payloads, or Git.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "data/governance/permanence/certification/collector_ebay_supply_contracts/collector_ebay_search_contracts.csv"
PACKAGING = ROOT / "data/governance/permanence/certification/collector_packaging_normalization/collector_packaging_normalization.csv"
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_supply_collection"
RAW_ROOT = ROOT / "data/raw/ebay/collector_supply"
VAULT_ROOT = ROOT / "data_vault/raw/mtg/collector_booster/ebay_supply"
TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
BROWSE_ROOT = "https://api.ebay.com/buy/browse/v1"
SCOPE = "https://api.ebay.com/oauth/api_scope"
DEFAULT_PRODUCT_ID = "541238"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Collect governed eBay Collector supply")
    p.add_argument("--mode", choices=["capability", "diagnostic", "shadow"], required=True)
    p.add_argument("--product-id", default=DEFAULT_PRODUCT_ID)
    p.add_argument("--contracts", type=Path, default=CONTRACTS)
    p.add_argument("--packaging", type=Path, default=PACKAGING)
    p.add_argument("--output-dir", type=Path, default=OUT)
    p.add_argument("--page-limit", type=int, default=200)
    p.add_argument("--max-pages", type=int, default=20)
    p.add_argument("--detail-limit", type=int, default=400)
    p.add_argument("--request-delay", type=float, default=0.05)
    p.add_argument("--strict", action="store_true")
    return p


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def norm_id(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def safe_json(response: requests.Response) -> dict:
    try:
        value = response.json()
        return value if isinstance(value, dict) else {"value": value}
    except ValueError:
        return {"non_json_response": True, "status_code": response.status_code}


def write_summary(out: Path, name: str, payload: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


def get_token(client_id: str, client_secret: str) -> tuple[str, int]:
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    response = requests.post(
        TOKEN_URL,
        headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "scope": SCOPE},
        timeout=60,
    )
    if response.status_code != 200:
        body = safe_json(response)
        raise RuntimeError(f"EBAY_TOKEN_REQUEST_FAILED status={response.status_code} error={body.get('error', 'unknown')}")
    body = response.json()
    return str(body["access_token"]), int(body.get("expires_in", 0))


def headers(token: str, marketplace_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": marketplace_id,
        "Accept": "application/json",
    }


def persist_payload(raw: bytes, retrieval_id: str, logical_name: str) -> tuple[str, str, str]:
    sha = hashlib.sha256(raw).hexdigest()
    raw_dir = RAW_ROOT / retrieval_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / logical_name
    raw_path.write_bytes(raw)
    vault_dir = VAULT_ROOT / f"sha256-{sha[:16]}"
    vault_dir.mkdir(parents=True, exist_ok=True)
    vault_path = vault_dir / logical_name
    if not vault_path.exists():
        vault_path.write_bytes(raw)
    return (
        str(raw_path.relative_to(ROOT)).replace("\\", "/"),
        str(vault_path.relative_to(ROOT)).replace("\\", "/"),
        sha,
    )


def terms(value: object) -> list[str]:
    return [x.strip().lower() for x in str(value).split("|") if x.strip()]


def classify_title(title: str, contract: pd.Series) -> tuple[str, str]:
    lower = re.sub(r"\s+", " ", title.lower()).strip()
    exclusions = terms(contract.get("excluded_terms", ""))
    hit = next((x for x in exclusions if re.search(rf"\b{re.escape(x)}\b", lower)), "")
    if hit:
        return "REJECT", f"EXCLUDED_TERM:{hit}"
    if "collector booster" not in lower:
        return "REJECT", "MISSING_COLLECTOR_BOOSTER"
    if not ("box" in lower or "display" in lower):
        return "REJECT", "MISSING_BOX_OR_DISPLAY"
    if "sealed" not in lower and "new" not in lower and "factory" not in lower:
        return "QUARANTINE", "SEALED_CONDITION_NOT_EXPLICIT"
    return "ACCEPT", "TITLE_CONTRACT_PASS"


def quantity_fields(detail: dict) -> tuple[object, object, bool, object]:
    availabilities = detail.get("estimatedAvailabilities") or []
    first = availabilities[0] if isinstance(availabilities, list) and availabilities else {}
    if not isinstance(first, dict):
        first = {}
    threshold_type = first.get("availabilityThresholdType")
    threshold = first.get("availabilityThreshold")
    estimated = first.get("estimatedRemainingQuantity", first.get("estimatedAvailableQuantity"))
    if threshold_type == "MORE_THAN" and threshold is not None:
        return "", int(threshold) + 1, True, first.get("estimatedSoldQuantity", "")
    if estimated is not None:
        try:
            value = int(estimated)
            return value, value, False, first.get("estimatedSoldQuantity", "")
        except (TypeError, ValueError):
            pass
    return "", 1, False, first.get("estimatedSoldQuantity", "")


def delivered_price(summary: dict) -> float | None:
    price = summary.get("price") or {}
    try:
        base = float(price.get("value"))
    except (TypeError, ValueError):
        return None
    shipping = 0.0
    options = summary.get("shippingOptions") or []
    if isinstance(options, list) and options:
        cost = (options[0] or {}).get("shippingCost") or {}
        try:
            shipping = float(cost.get("value", 0) or 0)
        except (TypeError, ValueError):
            shipping = 0.0
    return base + shipping


def search_product(token: str, contract: pd.Series, args: argparse.Namespace, retrieval_id: str) -> tuple[list[dict], list[dict]]:
    marketplace = str(contract.get("marketplace_id", "EBAY_US"))
    query = str(contract.get("search_query", ""))
    summaries: dict[str, dict] = {}
    manifest: list[dict] = []
    next_url = f"{BROWSE_ROOT}/item_summary/search?q={quote(query)}&limit={args.page_limit}&offset=0"
    page = 0
    while next_url and page < args.max_pages:
        response = requests.get(next_url, headers=headers(token, marketplace), timeout=60)
        if response.status_code != 200:
            raise RuntimeError(f"EBAY_SEARCH_FAILED status={response.status_code} product={contract.get('tcgplayer_product_id', '')}")
        raw_path, vault_path, sha = persist_payload(response.content, retrieval_id, f"search_{contract.get('tcgplayer_product_id')}_page_{page:03d}.json")
        body = response.json()
        for item in body.get("itemSummaries") or []:
            item_id = str(item.get("itemId", "")).strip()
            if item_id:
                summaries[item_id] = item
        manifest.append({"request_type": "SEARCH", "product_id": contract.get("tcgplayer_product_id", ""), "page": page, "raw_path": raw_path, "vault_path": vault_path, "sha256": sha, "item_count": len(body.get("itemSummaries") or [])})
        nxt = body.get("next")
        next_url = str(nxt) if nxt else ""
        page += 1
        if args.request_delay:
            time.sleep(args.request_delay)
    return list(summaries.values()), manifest


def enrich_items(token: str, marketplace: str, product_id: str, summaries: list[dict], args: argparse.Namespace, retrieval_id: str) -> tuple[list[dict], list[dict]]:
    details: list[dict] = []
    manifest: list[dict] = []
    for index, summary in enumerate(summaries[: args.detail_limit]):
        item_id = str(summary.get("itemId", ""))
        response = requests.get(f"{BROWSE_ROOT}/item/{quote(item_id, safe='')}", headers=headers(token, marketplace), timeout=60)
        if response.status_code != 200:
            manifest.append({"request_type": "DETAIL_ERROR", "product_id": product_id, "item_id": item_id, "status_code": response.status_code})
            continue
        raw_path, vault_path, sha = persist_payload(response.content, retrieval_id, f"detail_{product_id}_{index:04d}.json")
        body = response.json()
        details.append(body)
        manifest.append({"request_type": "DETAIL", "product_id": product_id, "item_id": item_id, "raw_path": raw_path, "vault_path": vault_path, "sha256": sha})
        if args.request_delay:
            time.sleep(args.request_delay)
    return details, manifest


def main() -> int:
    args = parser().parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    generated = now_utc()
    retrieval_id = f"ebay-collector-{generated.strftime('%Y%m%dT%H%M%SZ')}"

    client_id = os.getenv("EBAY_CLIENT_ID", "").strip()
    client_secret = os.getenv("EBAY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        summary = {
            "block_name": "Collector eBay Supply Collection",
            "block_version": "1.0.0",
            "generated_at": generated.isoformat(),
            "mode": args.mode,
            "credential_environment_variables_present": False,
            "credentials_written_to_output": False,
            "credential_test_passed": False,
            "live_collection_executed": False,
            "status": "CREDENTIALS_REQUIRED",
        }
        write_summary(out, "collector_ebay_supply_collection_summary.json", summary)
        return 1 if args.strict else 0

    if not args.contracts.resolve().is_file():
        raise FileNotFoundError(args.contracts)
    contracts = pd.read_csv(args.contracts.resolve(), dtype=str, encoding="utf-8-sig").fillna("")
    contracts["tcgplayer_product_id"] = contracts["tcgplayer_product_id"].map(norm_id)

    try:
        token, expires_in = get_token(client_id, client_secret)
    except Exception as exc:
        summary = {
            "block_name": "Collector eBay Supply Collection",
            "block_version": "1.0.0",
            "generated_at": generated.isoformat(),
            "mode": args.mode,
            "credential_environment_variables_present": True,
            "credentials_written_to_output": False,
            "credential_test_passed": False,
            "live_collection_executed": False,
            "error_class": type(exc).__name__,
            "error": str(exc),
            "status": "CAPABILITY_TEST_FAILED",
        }
        write_summary(out, "collector_ebay_supply_collection_summary.json", summary)
        return 1

    if args.mode == "capability":
        summary = {
            "block_name": "Collector eBay Supply Collection",
            "block_version": "1.0.0",
            "generated_at": generated.isoformat(),
            "mode": args.mode,
            "credential_environment_variables_present": True,
            "credentials_written_to_output": False,
            "credential_test_passed": True,
            "token_expires_in_seconds": expires_in,
            "live_collection_executed": False,
            "status": "PASS_EBAY_CAPABILITY_TEST",
        }
        write_summary(out, "collector_ebay_supply_collection_summary.json", summary)
        return 0

    selected = contracts if args.mode == "shadow" else contracts[contracts["tcgplayer_product_id"] == norm_id(args.product_id)]
    if selected.empty:
        raise ValueError(f"No governed contract found for product {args.product_id}")

    item_rows: list[dict[str, object]] = []
    snapshot_rows: list[dict[str, object]] = []
    review_rows: list[dict[str, object]] = []
    manifest_rows: list[dict[str, object]] = []

    for _, contract in selected.iterrows():
        pid = norm_id(contract["tcgplayer_product_id"])
        marketplace = str(contract.get("marketplace_id", "EBAY_US"))
        summaries, search_manifest = search_product(token, contract, args, retrieval_id)
        details, detail_manifest = enrich_items(token, marketplace, pid, summaries, args, retrieval_id)
        manifest_rows.extend(search_manifest + detail_manifest)
        detail_by_id = {str(x.get("itemId", "")): x for x in details}
        accepted: list[dict[str, object]] = []

        for summary_item in summaries:
            item_id = str(summary_item.get("itemId", ""))
            title = str(summary_item.get("title", ""))
            decision, reason = classify_title(title, contract)
            detail = detail_by_id.get(item_id, {})
            exact_qty, lower_bound, thresholded, sold_qty = quantity_fields(detail)
            seller = summary_item.get("seller") or detail.get("seller") or {}
            seller_token = str(seller.get("username", seller.get("userId", "")))
            seller_hash = hashlib.sha256(seller_token.encode("utf-8")).hexdigest() if seller_token else ""
            delivered = delivered_price(summary_item)
            row = {
                "retrieval_id": retrieval_id,
                "observed_at": generated.isoformat(),
                "tcgplayer_product_id": pid,
                "governed_box_name": contract.get("governed_box_name", ""),
                "item_id": item_id,
                "legacy_item_id": summary_item.get("legacyItemId", ""),
                "title": title,
                "listing_marketplace_id": summary_item.get("listingMarketplaceId", ""),
                "item_creation_date": summary_item.get("itemCreationDate", ""),
                "item_origin_date": summary_item.get("itemOriginDate", ""),
                "item_end_date": summary_item.get("itemEndDate", detail.get("itemEndDate", "")),
                "buying_options_json": json.dumps(summary_item.get("buyingOptions", []), ensure_ascii=False, sort_keys=True),
                "price_value": (summary_item.get("price") or {}).get("value", ""),
                "price_currency": (summary_item.get("price") or {}).get("currency", ""),
                "delivered_price_estimate": delivered if delivered is not None else "",
                "seller_pseudonym_sha256": seller_hash,
                "seller_feedback_score": seller.get("feedbackScore", ""),
                "seller_feedback_percentage": seller.get("feedbackPercentage", ""),
                "estimated_quantity": exact_qty,
                "listed_quantity_lower_bound": lower_bound,
                "quantity_thresholded": thresholded,
                "estimated_sold_quantity_proxy": sold_qty,
                "bid_count": detail.get("bidCount", summary_item.get("bidCount", "")),
                "listing_decision": decision,
                "listing_decision_reason": reason,
            }
            item_rows.append(row)
            if decision == "ACCEPT":
                accepted.append(row)
            else:
                review_rows.append(row)

        prices = [float(x["delivered_price_estimate"]) for x in accepted if x["delivered_price_estimate"] not in ("", None)]
        sellers = {x["seller_pseudonym_sha256"] for x in accepted if x["seller_pseudonym_sha256"]}
        quantities = [int(x["listed_quantity_lower_bound"]) for x in accepted if str(x["listed_quantity_lower_bound"]).strip()]
        snapshot_rows.append({
            "retrieval_id": retrieval_id,
            "observed_at": generated.isoformat(),
            "tcgplayer_product_id": pid,
            "governed_box_name": contract.get("governed_box_name", ""),
            "raw_unique_item_ids": len({str(x.get('itemId', '')) for x in summaries if x.get('itemId')}),
            "accepted_active_listing_count": len(accepted),
            "unique_seller_count": len(sellers),
            "listed_quantity_lower_bound": sum(quantities),
            "median_delivered_asking_price": statistics.median(prices) if prices else "",
            "minimum_delivered_asking_price": min(prices) if prices else "",
            "maximum_delivered_asking_price": max(prices) if prices else "",
            "asking_price_iqr": (statistics.quantiles(prices, n=4)[2] - statistics.quantiles(prices, n=4)[0]) if len(prices) >= 4 else "",
            "accepted_listing_share": round(len(accepted) / len(summaries), 6) if summaries else 0,
            "review_or_rejected_count": len(summaries) - len(accepted),
            "snapshot_status": "SHADOW_REVIEW_REQUIRED" if args.mode == "shadow" else "DIAGNOSTIC_REVIEW_REQUIRED",
        })

    items_frame = pd.DataFrame(item_rows)
    snapshots_frame = pd.DataFrame(snapshot_rows)
    review_frame = pd.DataFrame(review_rows, columns=items_frame.columns)
    manifest_frame = pd.DataFrame(manifest_rows)
    items_frame.to_csv(out / "collector_ebay_listing_observations_shadow.csv", index=False)
    snapshots_frame.to_csv(out / "collector_ebay_product_supply_snapshot_shadow.csv", index=False)
    review_frame.to_csv(out / "collector_ebay_listing_review_queue.csv", index=False)
    manifest_frame.to_csv(out / "collector_ebay_raw_payload_manifest.csv", index=False)

    summary = {
        "block_name": "Collector eBay Supply Collection",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "retrieval_id": retrieval_id,
        "mode": args.mode,
        "credential_environment_variables_present": True,
        "credentials_written_to_output": False,
        "credential_test_passed": True,
        "products_requested": int(len(selected)),
        "products_with_snapshot_rows": int(len(snapshots_frame)),
        "listing_rows_observed": int(len(items_frame)),
        "accepted_listing_rows": int((items_frame["listing_decision"] == "ACCEPT").sum()) if len(items_frame) else 0,
        "review_or_rejected_rows": int(len(review_frame)),
        "raw_payloads_vaulted": int(len(manifest_frame[manifest_frame["request_type"].isin(["SEARCH", "DETAIL"])])) if len(manifest_frame) else 0,
        "full_shadow_snapshot_complete": args.mode == "shadow" and len(snapshots_frame) == len(selected),
        "certified_listing_supply_snapshot_written": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_DIAGNOSTIC_SHADOW_COLLECTION" if args.mode == "diagnostic" else "PASS_FULL_SHADOW_COLLECTION",
    }
    write_summary(out, "collector_ebay_supply_collection_summary.json", summary)
    if args.strict and args.mode == "shadow" and not summary["full_shadow_snapshot_complete"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
