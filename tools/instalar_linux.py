"""Põe o Polpad no menu de aplicativos do Linux (só para o usuário atual).

    .venv/bin/python tools/instalar_linux.py             # instala dist/linux/Polpad
    .venv/bin/python tools/instalar_linux.py --remover   # desfaz

A lógica fica em ``polpad.update.linux_install``, a mesma que o executável
usa ao se instalar sozinho (``Polpad --instalar-no-menu``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from polpad.update import linux_install


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--executavel",
        type=Path,
        default=RAIZ / "dist" / "linux" / "Polpad",
        help="executável a instalar (padrão: dist/linux/Polpad)",
    )
    parser.add_argument(
        "--remover", action="store_true", help="desinstala o que este script criou"
    )
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        raise SystemExit("este instalador é só para Linux")
    if args.remover:
        for caminho in linux_install.uninstall():
            print(f"removido: {caminho}")
        return 0
    origem = args.executavel.resolve()
    if not origem.is_file():
        raise SystemExit(
            f"{origem} não existe. Gere antes com: .venv/bin/python tools/build_exe.py"
        )
    linux_install.install(origem)
    print(f"Instalado: {linux_install.binary_path()}")
    print(f"Atalho do menu: {linux_install.desktop_path()}")
    print("Procure por “Polpad” no menu de aplicativos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
