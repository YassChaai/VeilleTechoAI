# Image de déploiement : alimente la base puis sert le dashboard (gunicorn).
FROM python:3.11-slim

WORKDIR /app

# uv pour installer depuis le lockfile.
RUN pip install --no-cache-dir uv

# Couche dépendances (mise en cache tant que pyproject/uv.lock ne changent pas).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Code applicatif.
COPY . .

ENV VEILLE_DB=/app/data/veille.db \
    PORT=8000
EXPOSE 8000

# Au démarrage : run du pipeline (données fraîches) puis serveur WSGI de prod.
CMD ["sh", "-c", "uv run python main.py; uv run gunicorn --bind 0.0.0.0:${PORT} dashboard.app:app"]
