from __future__ import annotations

import pytest

from news_intelligence.sentiment import score_sentiment


def test_purely_positive_text_scores_positive_one() -> None:
    score, terms = score_sentiment("Stocks surge and rally as growth beats expectations")

    assert score == pytest.approx(1.0)
    assert "surge" in terms


def test_purely_negative_text_scores_negative_one() -> None:
    score, terms = score_sentiment("Markets crash as recession fears plunge stocks lower")

    assert score == pytest.approx(-1.0)
    assert "crash" in terms


def test_no_lexicon_terms_is_neutral_by_absence_not_a_guess() -> None:
    score, terms = score_sentiment("A quiet trading session with no notable moves")

    assert score == 0.0
    assert terms == ()


def test_mixed_terms_net_toward_the_majority_signal() -> None:
    score, terms = score_sentiment("Strong growth and rally offset by one weak decline")

    assert score > 0.0
    assert len(terms) >= 2


def test_equal_positive_and_negative_terms_net_to_zero() -> None:
    """Documented limitation: bag-of-words sentiment has no entity
    attribution, so a headline where a positive and negative term describe
    different things ('strong' the dollar, 'plunge' gold) still nets to
    neutral. This is expected, not a bug -- NewsSentimentModule treats
    sentiment as one Evidence source among many precisely because of this.
    """
    score, terms = score_sentiment(
        "Gold prices plunge as US dollar strengthens on strong jobs data"
    )

    assert score == pytest.approx(0.0)
    assert "plunge" in terms
    assert "strong" in terms
