#!/usr/bin/env bash
# Lance le back Flask (:5000) et le front Next.js (:3000) en parallèle pour la démo.
# Ctrl-C arrête les deux. Le front proxifie /api vers le back.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "→ Back Flask (API + dashboard Jinja) sur http://127.0.0.1:5000"
( cd "$ROOT/back" && uv run --no-sync python main.py serve ) &

echo "→ Front Next.js sur http://localhost:3000"
( cd "$ROOT/front" && npm run dev ) &

wait
