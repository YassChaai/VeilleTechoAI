"""Bonus : recherche sémantique locale via sentence-transformers.

Optionnel et sans clé API. Désactivé par défaut : n'est actif que si
`SEMANTIC_SEARCH=1` ET que le paquet `sentence-transformers` est installé.
Le modèle `all-MiniLM-L6-v2` (~80 Mo) se télécharge au premier usage — à faire
tôt, jamais en soutenance.
"""

from __future__ import annotations

import os
import struct

from processing.dedup import strip_html

MODEL_NAME = "all-MiniLM-L6-v2"
_model = None


def available() -> bool:
    if os.getenv("SEMANTIC_SEARCH", "0") != "1":
        return False
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _serialize(vec) -> bytes:
    vec = [float(x) for x in vec]
    return struct.pack(f"{len(vec)}f", *vec)


def _deserialize(blob: bytes) -> list[float]:
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


def embed_text(text: str) -> bytes:
    vec = _get_model().encode(strip_html(text), normalize_embeddings=True)
    return _serialize(vec)


def _cosine(a: list[float], b: list[float]) -> float:
    # Vecteurs déjà normalisés -> le produit scalaire suffit.
    return sum(x * y for x, y in zip(a, b))


def search(conn, query: str, top_k: int = 30) -> list[int]:
    """Retourne les ids d'articles les plus proches de la requête (ordre décroissant)."""
    from storage import db

    q_vec = _deserialize(embed_text(query))
    scored: list[tuple[float, int]] = []
    for row in db.all_embeddings(conn):
        score = _cosine(q_vec, _deserialize(row["embedding"]))
        scored.append((score, row["id"]))
    scored.sort(reverse=True)
    return [aid for _, aid in scored[:top_k]]
