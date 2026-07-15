from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent


def update(path: str, transform) -> bool:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    changed = transform(text)
    if changed == text:
        return False
    target.write_text(changed, encoding="utf-8")
    return True


def ensure_import(text: str, anchor: str, addition: str) -> str:
    if addition.strip() in text:
        return text
    if anchor not in text:
        raise RuntimeError(f"Import anchor not found: {anchor}")
    return text.replace(anchor, anchor + addition, 1)


def pricing(text: str) -> str:
    text = ensure_import(
        text,
        "import pandas as pd\n",
        "\nfrom terminal2.secret_lair.datetime_utils import (\n"
        "    date_string_series,\n"
        "    to_utc_naive_scalar,\n"
        "    to_utc_naive_series,\n"
        ")\n",
    )
    text = re.sub(
        r'frame\["_date"\]\s*=\s*\(\s*pd\.to_datetime\(\s*'
        r'frame\["observation_date"\],\s*errors="coerce",\s*utc=True,\s*'
        r'\)\s*\.dt\.tz_convert\(None\)\s*\)',
        'frame["_date"] = to_utc_naive_series(\n'
        '        frame["observation_date"]\n'
        '    )',
        text,
        count=1,
        flags=re.S,
    )
    text = re.sub(
        r'latest_date\s*=\s*pd\.to_datetime\(\s*'
        r'latest\["observation_date"\],\s*errors="coerce",\s*utc=True,\s*'
        r'\)\s*if pd\.notna\(latest_date\):\s*'
        r'latest_date\s*=\s*latest_date\.tz_convert\(None\)',
        'latest_date = to_utc_naive_scalar(\n'
        '            latest["observation_date"]\n'
        '        )',
        text,
        count=1,
        flags=re.S,
    )
    text = re.sub(
        r'release\s*=\s*pd\.to_datetime\(\s*'
        r'(group\["release_date"\]\.dropna\(\)\.iloc\[0\]\s*'
        r'if group\["release_date"\]\.notna\(\)\.any\(\)\s*'
        r'else group\["_date"\]\.min\(\)),\s*'
        r'errors="coerce",\s*utc=True,\s*\)\s*'
        r'if pd\.notna\(release\):\s*release\s*=\s*release\.tz_convert\(None\)',
        'release = to_utc_naive_scalar(\n'
        '            \\1\n'
        '        )',
        text,
        count=1,
        flags=re.S,
    )
    # Other date-string conversions in pricing.
    text = re.sub(
        r'pd\.to_datetime\(([^,\n]+),\s*errors="coerce"\)'
        r'\.dt\.date\.astype\("string"\)',
        r'date_string_series(\1)',
        text,
    )
    return text


def intelligence(text: str) -> str:
    text = ensure_import(
        text,
        "from terminal2.secret_lair.pricing import PRICE_PATH,build_secret_lair_pricing_datasets\n",
        "from terminal2.secret_lair.datetime_utils import "
        "to_utc_naive_series,utc_naive_today\n",
    )
    old = (
        "rel=pd.to_datetime(f['release_date'],errors='coerce');"
        "f['product_age_months']=((pd.Timestamp.now().normalize()-rel).dt.days/30.4375)"
        ".clip(lower=0);"
    )
    new = (
        "rel=to_utc_naive_series(f['release_date']);"
        "f['product_age_months']=((utc_naive_today()-rel).dt.days/30.4375)"
        ".clip(lower=0);"
    )
    if old not in text and new not in text:
        raise RuntimeError("Intelligence release-age pattern not found.")
    text = text.replace(old, new, 1)
    text = text.replace(
        "start=pd.to_datetime(f['sale_start_date'],errors='coerce');"
        "end=pd.to_datetime(f['sale_end_date'],errors='coerce');",
        "start=to_utc_naive_series(f['sale_start_date']);"
        "end=to_utc_naive_series(f['sale_end_date']);",
        1,
    )
    return text


def population(text: str) -> str:
    anchor = "from terminal2.secret_lair.pricing import build_secret_lair_pricing_datasets\n"
    if anchor not in text:
        # Support minified import ordering.
        anchor = "from terminal2.secret_lair.pricing import build_secret_lair_pricing_datasets\r\n"
    addition = (
        "from terminal2.secret_lair.datetime_utils import "
        "date_string_series,to_utc_naive_series\n"
    )
    if "from terminal2.secret_lair.datetime_utils import" not in text:
        if anchor not in text:
            raise RuntimeError("Population import anchor not found.")
        text = text.replace(anchor, anchor + addition, 1)
    text = text.replace(
        'o["observation_date"]=pd.to_datetime(o["observation_date"],errors="coerce");',
        'o["observation_date"]=to_utc_naive_series(o["observation_date"]);',
        1,
    )
    text = text.replace(
        'f["latest_observation_date"]=pd.to_datetime('
        'f["latest_observation_date"],errors="coerce").dt.date.astype("string").fillna("")',
        'f["latest_observation_date"]=date_string_series('
        'f["latest_observation_date"]).fillna("")',
        1,
    )
    return text


def registry(text: str) -> str:
    text = ensure_import(
        text,
        "from .identifiers import normalize_text, stable_key\n",
        "from .datetime_utils import (\n"
        "    date_string_series,\n"
        "    to_utc_naive_scalar,\n"
        "    to_utc_naive_series,\n"
        ")\n",
    )
    text = re.sub(
        r'release\s*=\s*pd\.to_datetime\(\s*'
        r'row\.get\("release_date"\),\s*errors="coerce",\s*\)',
        'release = to_utc_naive_scalar(row.get("release_date"))',
        text,
        count=1,
        flags=re.S,
    )
    text = re.sub(
        r'pd\.to_datetime\(([^,\n]+),\s*errors="coerce"\)'
        r'\.dt\.date\.astype\("string"\)',
        r'date_string_series(\1)',
        text,
    )
    # Calendar date series.
    text = re.sub(
        r'pd\.to_datetime\(\s*frame\["([^"]+)"\],\s*errors="coerce",\s*\)',
        r'to_utc_naive_series(frame["\1"])',
        text,
    )
    return text


def promotion(text: str) -> str:
    anchor = "from terminal2.secret_lair.metadata import VALID_FINISHES\n"
    text = ensure_import(
        text,
        anchor,
        "from terminal2.secret_lair.datetime_utils import date_string_series\n",
    )
    text = re.sub(
        r'prices\["observation_date"\]\s*=\s*pd\.to_datetime\(\s*'
        r'prices\["observation_date"\],\s*errors="coerce"\s*'
        r'\)\.dt\.date\.astype\("string"\)',
        'prices["observation_date"] = date_string_series(\n'
        '        prices["observation_date"]\n'
        '    )',
        text,
        count=1,
        flags=re.S,
    )
    return text


def main() -> None:
    operations = [
        ("terminal2/secret_lair/pricing.py", pricing),
        ("terminal2/secret_lair/intelligence_expansion/engine.py", intelligence),
        ("terminal2/secret_lair/population/engine.py", population),
        ("terminal2/secret_lair/registry.py", registry),
        ("terminal2/secret_lair/promotion/engine.py", promotion),
    ]
    changed = []
    for path, transform in operations:
        if update(path, transform):
            changed.append(path)

    print("Terminal 2.9.8b datetime standardization applied.")
    if changed:
        print("Updated files:")
        for path in changed:
            print(f"  {path}")
    else:
        print("No changes required; the standardization was already present.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
