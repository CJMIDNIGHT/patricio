#!/usr/bin/env bash
# Arranca la API Flask con el entorno virtual del proyecto.
cd "$(dirname "$0")/.." || exit 1

if [[ ! -d .venv ]]; then
  echo "Creando entorno virtual (.venv)..."
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

echo "Patricio API → http://0.0.0.0:5000"
exec .venv/bin/python patricio_api.py
