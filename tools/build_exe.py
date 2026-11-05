"""Gera o executável distribuível do Polpad.

    .venv\\Scripts\\python tools\\build_exe.py      (Windows)
    .venv/bin/python tools/build_exe.py           (Linux)

Produz ``dist/Polpad.exe`` no Windows e ``dist/Polpad`` no Linux — um
arquivo único, sem console, que roda sem Python instalado. É o que se
leva para a apresentação. No Linux, ``tools/instalar_linux.py`` coloca o
executável no menu de aplicativos, com o ícone.

Com o aplicativo aberto, o Windows não deixa sobrescrever o ``.exe`` em
execução e o PyInstaller falha com "Acesso negado". Feche o aplicativo
(menu da bandeja → Sair) ou gere em outra pasta::

    .venv\\Scripts\\python tools\\build_exe.py --destino build\\teste

Detalhes que o empacotamento exige:

* ``keyring`` e ``pynput`` escolhem seu backend em tempo de execução,
  importando módulos que o PyInstaller não vê na análise estática; por
  isso são coletados por inteiro (no Linux também o ``Xlib``, que o
  backend xorg do pynput e a detecção do app em foco usam). No Linux o
  backend xorg do pynput vai também por ``--hidden-import``: coletá-lo
  exige importar o pynput, o que sem servidor X falha.
* O ícone (``polvo-roxo.ico``) é copiado antes para build/ e os PNGs
  da janela vão junto com ``--add-data`` (ver ``make_icon.py``). O ícone
  embutido no arquivo só existe no Windows; no Linux quem mostra o ícone
  é o ``.desktop`` instalado.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ICONE = RAIZ / "build" / "polpad.ico"
NOME = "Polpad"
WINDOWS = sys.platform == "win32"
# Backend X11 do pynput, que ele escolhe em tempo de execução (ver main()).
_PYNPUT_XORG = (
    "pynput.keyboard._xorg",
    "pynput.mouse._xorg",
    "pynput._util.xorg",
    "pynput._util.xorg_keysyms",
)


def _run(argv: list[str], descricao: str) -> None:
    print(f"\n>>> {descricao}")
    resultado = subprocess.run(argv, cwd=RAIZ)
    if resultado.returncode != 0:
        raise SystemExit(f"falhou: {descricao} (código {resultado.returncode})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--destino",
        type=Path,
        default=RAIZ / "dist",
        help=(
            "pasta onde gravar o executável (padrão: dist/). Útil quando o "
            "aplicativo está aberto: o Windows não deixa sobrescrever um .exe "
            "em execução, e o PyInstaller falha com “Acesso negado”."
        ),
    )
    args = parser.parse_args()
    destino = args.destino.resolve()

    if importlib.util.find_spec("PyInstaller") is None:
        raise SystemExit(
            'PyInstaller não encontrado. Instale com: pip install -e ".[dev]"'
        )

    # Separador origem/destino do --add-data: ";" no Windows, ":" no Linux.
    assets = RAIZ / "src" / "polpad" / "ui" / "assets"
    add_assets = f"{assets}{os.pathsep}polpad/ui/assets"
    por_plataforma: list[str] = []
    if WINDOWS:
        _run([sys.executable, str(RAIZ / "tools" / "make_icon.py")], "gerando o ícone")
        por_plataforma += ["--icon", str(ICONE)]
    else:
        por_plataforma += ["--collect-submodules", "Xlib"]
        # O --collect-submodules do pynput precisa importá-lo, e no Linux
        # importar o pynput exige um servidor X. Sem tela (CI, SSH) a coleta
        # falha com só um aviso e o executável sai sem o backend xorg, que
        # fecha ao abrir. --hidden-import analisa sem importar.
        for modulo in _PYNPUT_XORG:
            por_plataforma += ["--hidden-import", modulo]

    _run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--windowed",
            "--name",
            NOME,
            "--distpath",
            str(destino),
            # Intermediários e o .spec ficam em build/, não na raiz do projeto.
            "--workpath",
            str(RAIZ / "build" / "pyinstaller"),
            "--specpath",
            str(RAIZ / "build"),
            "--paths",
            str(RAIZ / "src"),
            # Ícones do aplicativo (janela, bandeja e barra superior).
            "--add-data",
            add_assets,
            # Backends resolvidos em tempo de execução.
            "--collect-submodules",
            "keyring.backends",
            "--collect-submodules",
            "pynput",
            # O esptool resolve a classe do chip pelo nome e lê o stub de
            # gravação de arquivos JSON de dados — nada disso aparece na
            # análise estática do PyInstaller.
            "--collect-submodules",
            "esptool",
            "--collect-data",
            "esptool",
            *por_plataforma,
            # Módulos Qt pesados que o aplicativo não usa.
            "--exclude-module",
            "PySide6.QtWebEngineCore",
            "--exclude-module",
            "PySide6.QtWebEngineWidgets",
            "--exclude-module",
            "PySide6.Qt3DCore",
            "--exclude-module",
            "PySide6.QtMultimedia",
            "--exclude-module",
            "tkinter",
            str(RAIZ / "tools" / "entrypoint.py"),
        ],
        "empacotando com o PyInstaller",
    )

    exe = destino / (f"{NOME}.exe" if WINDOWS else NOME)
    if not exe.exists():
        raise SystemExit("o PyInstaller terminou sem produzir o executável")
    print(f"\nPronto: {exe} ({exe.stat().st_size / 1024 / 1024:.1f} MB)")
    if not WINDOWS:
        print("Para pôr no menu: .venv/bin/python tools/instalar_linux.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
