"""Extraction des termes pour la détection de tendances."""

from processing import trends


def test_terms_keeps_meaningful_words():
    terms = trends._terms("The new AI model from OpenAI abstract arxiv")
    assert "openai" in terms
    assert "model" in terms


def test_terms_filters_stopwords_and_boilerplate():
    terms = trends._terms("The new AI model from OpenAI abstract arxiv")
    assert "the" not in terms        # stopword + trop court
    assert "new" not in terms        # bruit fréquent (_EXTRA_STOP)
    assert "arxiv" not in terms      # boilerplate arXiv
    assert "abstract" not in terms   # boilerplate arXiv


def test_terms_drops_short_tokens_and_digits():
    terms = trends._terms("ai ml 2026 gpu")
    assert "ai" not in terms          # < 4 caractères
    assert "2026" not in terms        # purement numérique
    assert "gpu" not in terms         # < 4 caractères
