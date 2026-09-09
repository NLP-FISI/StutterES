#!/usr/bin/env bash
# Anotador web. Reconstruye el indice si falta y levanta el servidor.
set -euo pipefail
cd "$(dirname "$0")"
PY=".venv/bin/python"
[ -f src/web/dataset.json ] || $PY src/web/build_dataset.py
exec $PY src/web/app.py
