from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)

_LANGUAGE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("JAPANESE", ("japanese", "jpn", "jp version", "japanese version")),
    ("ENGLISH", ("english", "eng version", "english version")),
    ("GERMAN", ("german", "deutsch")),
    ("FRENCH", ("french", "francais", "français")),
    ("ITALIAN", ("italian", "italiano")),
    ("SPANISH", ("spanish", "espanol", "español")),
    ("KOREAN", ("korean",)),
    ("CHINESE", ("chinese", "simplified chinese", "traditional chinese")),
)

_FORM_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("EMPTY_PACKAGING", ("empty box", "box only", "wrapper only", "empty packaging")),
    ("ACCESSORY", ("deck box", "sleeves", "playmat", "binder", "storage box", "display stand")),
    ("SINGLE_CARD", ("single card", "individual card", "one card", "card only")),
    ("CASE", ("master case", "sealed case", "case of", "factory case")),
    ("LOOSE_PACK", ("single pack", "loose pack", "booster pack", "individual pack", "1 pack")),
    ("BOOSTER_DISPLAY", ("booster display", "booster box", "display box")),
    ("COMMANDER_DECK", ("commander deck",)),
    ("BUNDLE", ("bundle", "superdrop")),
    ("KIT", ("festival in a box", " kit ")),
    ("DROP", ("secret lair", " drop ")),
)

_SEALED_MARKERS = ("factory sealed", "new sealed", "brand new sealed", "unopened", "sealed")
_OPEN_MARKERS = ("opened", "open box", "unsealed", "resealed", "packs removed")
_DAMAGED_MARKERS = ("damaged", "crushed", "torn", "water damage", "for parts")
_INCOMPLETE_MARKERS = (
    "partial",
    "incomplete",
    "missing packs",
    "packs missing",
    "box plus packs",
    "packs plus box",
    "without packs",
)


@dataclass(frozen=True)
class ListingIdentity:
    language: str
    product_form: str
    seal_state: str
    completeness: str
    quantity: int | None


@dataclass(frozen=True)
class UniversalClassification:
    decision: str
    confidence: float
    hard_conflicts: tuple[str, ...]
    review_reasons: tuple[str, ...]
    audit_tags: tuple[str, ...]
    target_language: str
    listing_identity: ListingIdentity


def _normalize(value: object) -> str:
    return " " + " ".join(_TOKEN_RE.findall(str(value or "").lower())) + " "


def _contains_any(value_norm: str, phrases: Iterable[str]) -> bool:
    return any(" " + " ".join(_TOKEN_RE.findall(phrase.lower())) + " " in value_norm for phrase in phrases)


def detect_language(value: object) -> str:
    value_norm = _normalize(value)
    detected = [language for language, phrases in _LANGUAGE_PATTERNS if _contains_any(value_norm, phrases)]
    if not detected:
        return "UNSPECIFIED"
    if len(set(detected)) > 1:
        return "CONFLICTING"
    return detected[0]


def detect_product_form(value: object) -> str:
    raw = str(value or "").lower()
    value_norm = _normalize(value)
    for form, phrases in _FORM_PATTERNS:
        if any((phrase.strip() in raw) if phrase.startswith(" ") or phrase.endswith(" ") else _contains_any(value_norm, (phrase,)) for phrase in phrases):
            return form
    return "SEALED_PRODUCT"


def detect_seal_state(value: object) -> str:
    value_norm = _normalize(value)
    if _contains_any(value_norm, _DAMAGED_MARKERS):
        return "DAMAGED"
    if _contains_any(value_norm, _OPEN_MARKERS):
        return "OPEN"
    if _contains_any(value_norm, _SEALED_MARKERS):
        return "SEALED"
    return "UNSPECIFIED"


def detect_completeness(value: object) -> str:
    value_norm = _normalize(value)
    if _contains_any(value_norm, _INCOMPLETE_MARKERS):
        return "INCOMPLETE"
    return "UNSPECIFIED"


def _valid_listing_quantity(raw: str) -> int | None:
    try:
        quantity = int(raw)
    except ValueError:
        return None
    # Four-digit release years such as 2020 and 2022 were previously parsed as
    # quantities when they appeared immediately before "booster box". Marketplace
    # lot quantities above 200 are not actionable display counts and fail closed.
    if 1900 <= quantity <= 2099 or quantity < 1 or quantity > 200:
        return None
    return quantity


def detect_quantity(value: object) -> int | None:
    text = str(value or "").lower()
    patterns = (
        r"\bcase\s+of\s+(\d+)\b",
        r"\blot\s+of\s+(\d+)\b",
        r"\b(?:x|qty\s*)?(\d+)\s*(?:x\s*)?(?:booster\s+)?(?:boxes|box|displays|display|packs|pack)\b",
        r"\b(?:boxes|box|displays|display)\s*[x×]\s*(\d+)\b",
        r"\b[x×](\d+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            quantity = _valid_listing_quantity(match.group(1))
            if quantity is not None:
                return quantity
    return None


def parse_listing_identity(title: object) -> ListingIdentity:
    return ListingIdentity(
        language=detect_language(title),
        product_form=detect_product_form(title),
        seal_state=detect_seal_state(title),
        completeness=detect_completeness(title),
        quantity=detect_quantity(title),
    )


def target_language(product_name: object) -> str:
    return detect_language(product_name)


def _expected_form(product_class: object, product_name: object) -> str:
    class_name = str(product_class or "").upper()
    name = str(product_name or "")
    if "BOOSTER" in class_name:
        return "BOOSTER_DISPLAY"
    if "SECRET_LAIR" in class_name:
        form = detect_product_form(name)
        return form if form != "SEALED_PRODUCT" else "DROP"
    return detect_product_form(name)


def classify_listing_identity(product_name: object, product_class: object, title: object) -> UniversalClassification:
    listing = parse_listing_identity(title)
    expected_language = target_language(product_name)
    expected_form = _expected_form(product_class, product_name)

    hard: list[str] = []
    review: list[str] = []
    audit: list[str] = [
        f"universal_target_language:{expected_language.lower()}",
        f"universal_listing_language:{listing.language.lower()}",
        f"universal_listing_form:{listing.product_form.lower()}",
        f"universal_seal_state:{listing.seal_state.lower()}",
        f"universal_completeness:{listing.completeness.lower()}",
    ]
    if listing.quantity is not None:
        audit.append(f"universal_quantity:{listing.quantity}")

    if listing.product_form in {"EMPTY_PACKAGING", "ACCESSORY", "SINGLE_CARD"}:
        hard.append(f"universal_excluded_form:{listing.product_form.lower()}")

    if listing.seal_state in {"OPEN", "DAMAGED"}:
        hard.append(f"universal_condition_conflict:{listing.seal_state.lower()}")

    if listing.completeness == "INCOMPLETE":
        hard.append("universal_incomplete_product")

    if expected_form == "BOOSTER_DISPLAY":
        if listing.product_form == "CASE":
            hard.append("universal_quantity_form_conflict:case_for_display")
        elif listing.product_form == "LOOSE_PACK":
            hard.append("universal_quantity_form_conflict:pack_for_display")
        elif listing.product_form not in {"BOOSTER_DISPLAY", "SEALED_PRODUCT"}:
            hard.append(f"universal_product_form_conflict:{listing.product_form.lower()}")
        elif listing.product_form == "SEALED_PRODUCT":
            review.append("universal_missing_form_qualifier:booster_display")
        if listing.quantity is not None and listing.quantity > 1:
            hard.append("universal_quantity_conflict:multi_display_listing")

    if expected_language != "UNSPECIFIED":
        if listing.language == "UNSPECIFIED":
            review.append(f"universal_missing_language:{expected_language.lower()}")
        elif listing.language == "CONFLICTING":
            hard.append("universal_conflicting_language_markers")
        elif listing.language != expected_language:
            hard.append(
                f"universal_language_conflict:expected_{expected_language.lower()}_observed_{listing.language.lower()}"
            )
    elif listing.language not in {"UNSPECIFIED", "ENGLISH"}:
        review.append(f"universal_explicit_nondefault_language:{listing.language.lower()}")

    if listing.seal_state == "UNSPECIFIED":
        review.append("universal_missing_sealed_condition")

    if hard:
        decision = "REJECTED"
        confidence = 0.99
    elif review:
        decision = "REVIEW"
        confidence = 0.75
    else:
        decision = "ACCEPTED"
        confidence = 0.95

    return UniversalClassification(
        decision=decision,
        confidence=confidence,
        hard_conflicts=tuple(dict.fromkeys(hard)),
        review_reasons=tuple(dict.fromkeys(review)),
        audit_tags=tuple(dict.fromkeys(audit)),
        target_language=expected_language,
        listing_identity=listing,
    )
