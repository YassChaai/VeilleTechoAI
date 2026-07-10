"""Filtre qualité à l'ingestion : rejeter les entrées sans valeur ajoutée."""

import pytest

from ingestion import has_value


@pytest.fixture(autouse=True)
def _fixed_threshold(monkeypatch):
    # Seuil déterministe, indépendant de l'environnement.
    monkeypatch.setenv("MIN_CONTENT_CHARS", "120")


def test_rejects_thin_content():
    assert has_value({"title": "Un titre", "content": "trop court"}) is False


def test_rejects_empty_content():
    assert has_value({"title": "Un titre", "content": ""}) is False
    assert has_value({"title": "Un titre", "content": None}) is False


def test_accepts_rich_content():
    content = "Ceci est un contenu suffisamment long pour être exploité par le résumé. " * 3
    assert has_value({"title": "Titre", "content": content}) is True


def test_rejects_content_equal_to_title():
    # Titre long (> seuil) recopié à l'identique en « contenu » → aucune matière.
    long_title = (
        "Une phrase de titre volontairement tres longue pour depasser le seuil "
        "minimal de contenu impose par le filtre qualite de la plateforme aujourd hui"
    )
    assert len(long_title) >= 120
    assert has_value({"title": long_title, "content": long_title}) is False
