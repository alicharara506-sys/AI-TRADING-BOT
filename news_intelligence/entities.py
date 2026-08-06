from __future__ import annotations

import re

# Domain-specific entity extraction for a forex-focused platform: ISO
# currency codes, major central banks, and the commodities that most
# directly move currency pairs (oil for CAD/NOK, gold as a USD hedge).
# Not a general-purpose NER model -- a small, auditable dictionary/regex
# match, upgradable later behind the same call signature.
_CURRENCY_CODES = frozenset({"EUR", "USD", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF", "CNY"})
_CENTRAL_BANKS: dict[str, str] = {
    "federal reserve": "FED",
    "fomc": "FED",
    "european central bank": "ECB",
    "bank of england": "BOE",
    "bank of japan": "BOJ",
    "people's bank of china": "PBOC",
    "reserve bank of australia": "RBA",
    "reserve bank of new zealand": "RBNZ",
    "swiss national bank": "SNB",
}
_COMMODITIES: dict[str, str] = {
    "crude oil": "OIL",
    "gold": "XAU",
    "silver": "XAG",
    "natural gas": "NATGAS",
}

_UPPER_WORD_PATTERN = re.compile(r"\b[A-Z]{3}\b")


def extract_entities(text: str) -> tuple[str, ...]:
    found: set[str] = set()

    upper_words = set(_UPPER_WORD_PATTERN.findall(text))
    found.update(code for code in _CURRENCY_CODES if code in upper_words)

    lowered = text.lower()
    for phrase, symbol in _CENTRAL_BANKS.items():
        if phrase in lowered:
            found.add(symbol)
    for phrase, symbol in _COMMODITIES.items():
        if phrase in lowered:
            found.add(symbol)

    return tuple(sorted(found))


__all__ = ["extract_entities"]
