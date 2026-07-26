from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


FINISH_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("DOUBLE_RAINBOW_FOIL", ("double rainbow foil",)),
    ("RAINBOW_FOIL", ("rainbow foil",)),
    ("TRADITIONAL_FOIL", ("traditional foil",)),
    ("GALAXY_FOIL", ("galaxy foil",)),
    ("CONFETTI_FOIL", ("confetti foil",)),
    ("ETCHED_FOIL", ("etched foil", "foil etched")),
    ("RAISED_FOIL", ("raised foil",)),
    ("NONFOIL", ("non foil", "nonfoil")),
)

FORM_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("BOOSTER_DISPLAY", ("booster display", "booster box", "display box")),
    ("BUNDLE", ("bundle", "superdrop")),
    ("COMMANDER_DECK", ("commander deck",)),
    ("DECK", (" deck ",)),
    ("KIT", (" kit ", "festival in a box")),
    ("DROP", (" drop ", "secret lair")),
)

GENERIC_IDENTITY_TERMS = {
    "magic", "the", "gathering", "mtg", "secret", "lair", "drop", "edition",
    "sealed", "standard", "foil", "nonfoil", "non", "traditional", "rainbow",
    "double", "galaxy", "etched", "raised", "confetti", "bundle", "deck", "kit",
    "booster", "box", "display", "collector", "draft", "set", "play",
}


@dataclass(frozen=True)
class EbayProductIdentity:
    product_family: str
    product_form: str
    finish: str
    required_tokens: tuple[str, ...]
    required_phrases: tuple[str, ...]
    forbidden_phrases: tuple[str, ...]


def normalize(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    return f" {' '.join(text.split())} "


def _contains_any(value_norm: str, phrases: Iterable[str]) -> bool:
    return any(f" {phrase.strip()} " in value_norm for phrase in phrases)


def detect_finish(value: object) -> str:
    value_norm = normalize(value)
    for finish, phrases in FINISH_PATTERNS:
        if _contains_any(value_norm, phrases):
            return finish
    if " foil " in value_norm:
        return "FOIL_UNSPECIFIED"
    return "UNSPECIFIED"


def detect_form(value: object, product_class: str = "") -> str:
    value_norm = normalize(value)
    class_norm = str(product_class or "").upper()
    if "BOOSTER" in class_norm:
        return "BOOSTER_DISPLAY"
    for form, phrases in FORM_PATTERNS:
        if _contains_any(value_norm, phrases):
            return form
    return "SEALED_PRODUCT"


def _identity_tokens(value: object) -> tuple[str, ...]:
    return tuple(sorted({
        token for token in normalize(value).split()
        if len(token) > 2 and token not in GENERIC_IDENTITY_TERMS
    }))


def _finish_requirements(finish: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if finish == "NONFOIL":
        return (("non foil",), ("traditional foil", "rainbow foil", "galaxy foil", "etched foil", "raised foil", "confetti foil"))
    if finish == "TRADITIONAL_FOIL":
        return (("traditional foil",), ("non foil", "nonfoil", "rainbow foil", "galaxy foil", "etched foil"))
    if finish == "DOUBLE_RAINBOW_FOIL":
        return (("double rainbow foil",), ("non foil", "nonfoil", "traditional foil", "galaxy foil"))
    if finish == "RAINBOW_FOIL":
        return (("rainbow foil",), ("non foil", "nonfoil", "traditional foil", "galaxy foil"))
    if finish == "GALAXY_FOIL":
        return (("galaxy foil",), ("non foil", "nonfoil", "traditional foil", "rainbow foil"))
    if finish == "ETCHED_FOIL":
        return (("etched foil",), ("non foil", "nonfoil", "traditional foil", "rainbow foil"))
    if finish == "RAISED_FOIL":
        return (("raised foil",), ("non foil", "nonfoil", "traditional foil"))
    if finish == "CONFETTI_FOIL":
        return (("confetti foil",), ("non foil", "nonfoil", "traditional foil"))
    if finish == "FOIL_UNSPECIFIED":
        return (("foil",), ("non foil", "nonfoil"))
    return ((), ())


def parse_product_identity(name: str, product_class: str = "") -> EbayProductIdentity:
    family = "SECRET_LAIR" if "SECRET_LAIR" in str(product_class).upper() or "secret lair" in name.lower() else "BOOSTER"
    form = detect_form(name, product_class)
    finish = detect_finish(name)
    required_phrases: list[str] = []
    forbidden_phrases: list[str] = []

    if form == "BOOSTER_DISPLAY":
        required_phrases.append("booster")
        forbidden_phrases.extend(("single pack", "booster pack", "loose pack", "case of", "master case"))
    elif form == "BUNDLE":
        required_phrases.append("bundle")
        forbidden_phrases.extend(("single card", "individual card", "single drop"))
    elif form == "COMMANDER_DECK":
        required_phrases.append("commander deck")
        forbidden_phrases.extend(("single card", "deck box", "sleeves"))
    elif form == "DECK":
        required_phrases.append("deck")
        forbidden_phrases.extend(("single card", "deck box", "sleeves"))
    elif form == "KIT":
        required_phrases.append("kit")
        forbidden_phrases.extend(("single card", "individual card"))
    elif form == "DROP":
        forbidden_phrases.extend(("single card", "individual card"))

    finish_required, finish_forbidden = _finish_requirements(finish)
    required_phrases.extend(finish_required)
    forbidden_phrases.extend(finish_forbidden)

    return EbayProductIdentity(
        product_family=family,
        product_form=form,
        finish=finish,
        required_tokens=_identity_tokens(name),
        required_phrases=tuple(dict.fromkeys(required_phrases)),
        forbidden_phrases=tuple(dict.fromkeys(forbidden_phrases)),
    )


def evaluate_title(identity: EbayProductIdentity, title: str) -> tuple[bool, list[str], float]:
    title_norm = normalize(title)
    reasons: list[str] = []

    for phrase in identity.required_phrases:
        if f" {phrase} " not in title_norm:
            reasons.append(f"missing_required_phrase:{phrase.replace(' ', '_')}")
    for phrase in identity.forbidden_phrases:
        if f" {phrase} " in title_norm:
            reasons.append(f"forbidden_phrase:{phrase.replace(' ', '_')}")

    present = [token for token in identity.required_tokens if f" {token} " in title_norm]
    coverage = len(present) / len(identity.required_tokens) if identity.required_tokens else 1.0
    if coverage < 0.70:
        reasons.append("insufficient_identity_token_coverage")

    return (not reasons, reasons, coverage)
