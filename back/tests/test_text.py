"""Fonctions texte partagées : nettoyage HTML et normalisation de titres."""

from processing.dedup import normalize_title, strip_html


def test_strip_html_removes_tags_and_unescapes():
    assert strip_html("<p>Hello&amp; world</p>") == "Hello& world"


def test_strip_html_handles_empty_and_none():
    assert strip_html("") == ""
    assert strip_html(None) == ""


def test_normalize_title_lowercases_strips_punct_and_stopwords():
    # "The" est un stopword ; la ponctuation disparaît.
    assert normalize_title("The New AI Model!") == "new ai model"


def test_normalize_title_is_stable_across_punctuation_variants():
    a = normalize_title("OpenAI releases GPT-5")
    b = normalize_title("openai releases gpt 5")
    assert a == b == "openai releases gpt 5"
