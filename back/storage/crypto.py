"""Chiffrement réversible des secrets par compte (clé API Claude).

IMPORTANT : on **chiffre** (réversible), on ne **hashe pas**. Un mot de passe se hashe
car on le *vérifie* seulement ; une clé API doit être *rejouée telle quelle* vers l'API
Anthropic → il faut pouvoir la récupérer, donc chiffrement symétrique (Fernet/AES-128 +
HMAC), avec une clé dérivée de `SECRET_KEY`.

Dégradé-safe : si `cryptography` n'est pas installé, on stocke en clair (repli), pour
ne jamais casser le pipeline. Le préfixe `enc:` distingue chiffré / clair (rétro-compat).
"""

from __future__ import annotations

import base64
import hashlib
import os

_PREFIX = "enc:"  # marqueur d'une valeur chiffrée


def _fernet():
    """Instance Fernet dérivée de SECRET_KEY, ou None si `cryptography` absent."""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return None
    secret = os.getenv("SECRET_KEY") or "dev-le-guetteur-change-me"
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt(value: str | None) -> str | None:
    """Chiffre une valeur pour le stockage. Repli en clair si pas de backend crypto."""
    if not value:
        return None
    f = _fernet()
    if f is None:
        return value  # cryptography non installé → stockage en clair assumé
    return _PREFIX + f.encrypt(value.encode()).decode()


def decrypt(stored: str | None) -> str | None:
    """Déchiffre une valeur stockée. Tolère les valeurs en clair (repli / base ancienne)."""
    if not stored:
        return None
    if not stored.startswith(_PREFIX):
        return stored  # valeur en clair
    f = _fernet()
    if f is None:
        return None  # chiffré mais lib absente → illisible (sécurité > disponibilité)
    try:
        return f.decrypt(stored[len(_PREFIX):].encode()).decode()
    except Exception:
        return None
