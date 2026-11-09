#!/bin/sh
# Inicia o Polpad pelo código sem prender o terminal; log em ~/.config/Polpad/logs/.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
    echo "Ambiente virtual ausente. Crie com:" >&2
    echo "  python3 -m venv .venv && .venv/bin/python -m pip install -e ." >&2
    exit 1
fi
setsid -f .venv/bin/python -m polpad "$@" >/dev/null 2>&1
