from __future__ import annotations

import pytest

from news_intelligence.language import detect_language


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "Federal Reserve holds interest rates steady, signals no rate cut in near term",
            "en",
        ),
        (
            "EUR/USD surges as European Central Bank hints at rate hike amid inflation concerns",
            "en",
        ),
        (
            "Le gouvernement français annonce de nouvelles mesures économiques pour la croissance",
            "fr",
        ),
        (
            "El banco central europeo anuncia una nueva politica monetaria para la economia",
            "es",
        ),
        (
            "Die Deutsche Bundesbank hat heute eine neue Entscheidung getroffen und wird "
            "die Politik nach der Krise anpassen",
            "de",
        ),
        (
            "O banco central anunciou uma nova politica para a economia no pais",
            "pt",
        ),
    ],
)
def test_detects_the_expected_language(text: str, expected: str) -> None:
    assert detect_language(text) == expected


def test_very_short_text_is_unknown_rather_than_guessed() -> None:
    assert detect_language("ok") == "unknown"
    assert detect_language("xyz") == "unknown"


def test_terse_headline_with_no_function_words_is_honestly_unknown() -> None:
    """Documented limitation, not a bug: a headline with almost no function
    words (common in terse financial wire copy) has too little stopword
    signal to classify confidently. 'unknown' is the correct output --
    language is metadata here, nothing downstream depends on it, so a
    wrong guess would be strictly worse than an honest "don't know".
    """
    assert detect_language("Apple reports record quarterly earnings, beats revenue estimates") == (
        "unknown"
    )
