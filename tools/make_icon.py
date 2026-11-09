"""Copia o ``polvo-roxo.ico`` feito à mão para o executável.

Não é gerado reduzindo a maior imagem: os tamanhos pequenos usam um polvo
simplificado.

    .venv\\Scripts\\python tools\\make_icon.py [destino.ico]
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORIGEM = RAIZ / "src" / "polpad" / "ui" / "assets" / "polvo-roxo.ico"
DEFAULT_OUTPUT = RAIZ / "build" / "polpad.ico"


def main() -> int:
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ORIGEM, destino)
    print(f"ícone gravado em {destino} ({destino.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
