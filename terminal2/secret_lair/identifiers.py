from __future__ import annotations

import hashlib
import re
import unicodedata


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    return re.sub(r"\s+", " ", text)


def slug(value: object) -> str:
    text = normalize_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def stable_secret_lair_id(
    *,
    drop_name: object,
    variant_name: object,
    finish: object,
    source_record_id: object = "",
) -> str:
    source = normalize_text(source_record_id)
    identity = "|".join(
        [
            source or slug(drop_name),
            slug(variant_name),
            slug(finish),
        ]
    )
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:10]
    return f"SL{digest.upper()}"


def stable_key(prefix: str, value: object) -> str:
    digest = hashlib.sha1(
        normalize_text(value).lower().encode("utf-8")
    ).hexdigest()[:12]
    return f"{prefix}{digest.upper()}"
