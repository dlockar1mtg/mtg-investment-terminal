from __future__ import annotations

from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import time

import requests

try:
    from config import SOURCE_REQUEST_LOG_FILE
except Exception:
    SOURCE_REQUEST_LOG_FILE = None


def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def log_request(url, status_code=None, ok=None, source_name="", message="", elapsed_seconds=None):
    if SOURCE_REQUEST_LOG_FILE is None:
        return
    path = Path(SOURCE_REQUEST_LOG_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp",
                "source_name",
                "url",
                "status_code",
                "ok",
                "elapsed_seconds",
                "message",
            ],
        )
        if not exists:
            writer.writeheader()
        writer.writerow({
            "timestamp": now_utc(),
            "source_name": source_name,
            "url": url,
            "status_code": status_code,
            "ok": ok,
            "elapsed_seconds": elapsed_seconds,
            "message": str(message)[:500],
        })


def default_headers():
    return {
        "User-Agent": "MTGInvestmentTerminal/6.0 (personal project; dxlockard@gmail.com)",
        "Accept": "application/json;q=0.9,*/*;q=0.8",
    }


def safe_get_json(url, timeout=45, headers=None, source_name=""):
    request_headers = default_headers()
    if headers:
        request_headers.update(headers)

    started = time.time()
    try:
        response = requests.get(url, timeout=timeout, headers=request_headers)
        elapsed = round(time.time() - started, 3)
        log_request(
            url=url,
            status_code=response.status_code,
            ok=response.ok,
            source_name=source_name,
            elapsed_seconds=elapsed,
            message=response.text[:250] if not response.ok else "",
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        elapsed = round(time.time() - started, 3)
        log_request(
            url=url,
            status_code=getattr(getattr(exc, "response", None), "status_code", None),
            ok=False,
            source_name=source_name,
            elapsed_seconds=elapsed,
            message=exc,
        )
        raise


def save_raw_json(data, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def as_float(value):
    if value in [None, "", "null"]:
        return None
    try:
        return float(value)
    except Exception:
        return None
