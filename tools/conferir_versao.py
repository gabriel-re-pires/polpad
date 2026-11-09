"""Confere se a tag do release bate com a versão escrita no código.

    .venv/bin/python tools/conferir_versao.py v0.5.0

Roda no workflow antes de gerar os executáveis: ``pyproject.toml`` e
``src/polpad/__init__.py`` precisam concordar com a tag.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def versoes() -> dict[str, str]:
    pyproject = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    init = (RAIZ / "src" / "polpad" / "__init__.py").read_text(encoding="utf-8")
    achado = re.search(r'^__version__\s*=\s*"([^"]+)"', init, re.MULTILINE)
    return {
        "pyproject.toml": pyproject["project"]["version"],
        "src/polpad/__init__.py": achado.group(1) if achado else "(ausente)",
    }


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    esperada = argv[0].removeprefix("v")
    erradas = {arquivo: v for arquivo, v in versoes().items() if v != esperada}
    if erradas:
        for arquivo, versao in erradas.items():
            print(
                f"{arquivo} está em {versao}, mas a tag é {argv[0]}.", file=sys.stderr
            )
        print(
            "Atualize a versão nos dois arquivos e crie a tag de novo.", file=sys.stderr
        )
        return 1
    print(f"Versão {esperada} confere com a tag {argv[0]}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
