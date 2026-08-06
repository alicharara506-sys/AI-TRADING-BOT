from __future__ import annotations

import re

_WORD_PATTERN = re.compile(r"[a-zà-öø-ÿ]+")

# A small, fixed set of major languages relevant to global financial news,
# identified by stopword frequency -- the same honest-baseline approach
# used throughout this platform's AI-adjacent modules (RuleBasedReviewer,
# rule-based news classification): deterministic, auditable, and upgradable
# to a real statistical/ML language model later behind an unchanged
# call signature, rather than pretending to have one now.
_STOPWORDS: dict[str, frozenset[str]] = {
    "en": frozenset({
        "the", "and", "of", "to", "in", "a", "is", "that", "for", "on", "with",
        "as", "at", "from", "after", "amid", "over", "up", "down", "out", "no",
        "its", "it", "by", "was", "are", "be", "has", "have", "will", "than",
    }),
    "es": frozenset({
        "el", "la", "de", "y", "que", "en", "los", "del", "las", "un", "por",
        "con", "para", "su", "es", "se", "al", "como", "tras", "hasta",
    }),
    "fr": frozenset({
        "le", "la", "de", "et", "les", "des", "un", "une", "dans", "que", "pour",
        "sur", "avec", "son", "ses", "au", "aux", "est", "par", "nouvelles",
    }),
    "de": frozenset({
        "der", "die", "und", "das", "den", "ist", "von", "mit", "zu", "auf", "für",
        "im", "nach", "bei", "sich", "ein", "eine", "aus", "wird", "hat",
    }),
    "pt": frozenset({
        "o", "a", "de", "e", "que", "do", "da", "em", "os", "para", "com",
        "por", "as", "ao", "se", "no", "na", "sobre", "foi", "seu",
    }),
}


def detect_language(text: str) -> str:
    """Returns an ISO 639-1 code for the best-matching supported language,
    or 'unknown' when the text is too short to classify confidently or
    doesn't clearly match any supported language's stopword profile.
    """
    words = _WORD_PATTERN.findall(text.lower())
    if len(words) < 3:
        return "unknown"

    scores = {
        language: sum(1 for word in words if word in stopwords)
        for language, stopwords in _STOPWORDS.items()
    }
    best_language = max(scores, key=lambda language: scores[language])
    if scores[best_language] < 2:
        return "unknown"
    return best_language


__all__ = ["detect_language"]
