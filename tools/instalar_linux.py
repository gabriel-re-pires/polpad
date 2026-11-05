"""Põe o Polpad no menu de aplicativos do Linux (só para o usuário atual).

    .venv/bin/python tools/instalar_linux.py             # instala dist/Polpad
    .venv/bin/python tools/instalar_linux.py --remover   # desfaz

Copia o executável gerado por ``build_exe.py`` para ``~/.local/bin/polpad``,
o ícone do polvo para o tema ``hicolor`` e cria
``~/.local/share/applications/polpad.desktop``. Nada fora da pasta pessoal
é tocado, então não precisa de sudo.

O executável é copiado, e não apontado em dist/, para que gerar uma versão
nova não quebre o atalho: rode este script de novo para atualizar.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from polpad.core import autostart

ASSETS = RAIZ / "src" / "polpad" / "ui" / "assets"
TAMANHOS = (16, 24, 32, 48, 64, 128, 256)


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


BINARIO = Path.home() / ".local" / "bin" / "polpad"
DESKTOP = _data_home() / "applications" / "polpad.desktop"
ICONES = {
    n: _data_home() / "icons" / "hicolor" / f"{n}x{n}" / "apps" / "polpad.png"
    for n in TAMANHOS
}


def _desktop_entry(binario: Path) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Polpad\n"
        "GenericName=Configurador do macropad\n"
        "Comment=Teclas, perfis e display do macropad ESP32-C3\n"
        f"Exec={autostart.exec_line([str(binario)])}\n"
        "Icon=polpad\n"
        "Terminal=false\n"
        "Categories=Utility;\n"
        "Keywords=macropad;teclado;atalho;esp32;\n"
        "StartupNotify=true\n"
        "StartupWMClass=Polpad\n"
    )


def _copiar_executavel(origem: Path) -> None:
    BINARIO.parent.mkdir(parents=True, exist_ok=True)
    # Copia para um temporário e renomeia: sobrescrever direto falha com
    # "Text file busy" se a versão anterior estiver aberta.
    tmp = BINARIO.with_name(f".{BINARIO.name}.novo")
    shutil.copyfile(origem, tmp)
    tmp.chmod(0o755)
    tmp.replace(BINARIO)


def _atualizar_caches() -> None:
    """Avisa o menu e o tema de ícones (opcional: o menu também percebe sozinho)."""
    for argv in (
        ["update-desktop-database", str(DESKTOP.parent)],
        ["gtk-update-icon-cache", "-f", "-t", str(_data_home() / "icons" / "hicolor")],
    ):
        if shutil.which(argv[0]):
            subprocess.run(argv, capture_output=True, check=False)


def instalar(origem: Path) -> None:
    if not origem.is_file():
        raise SystemExit(
            f"{origem} não existe. Gere antes com: .venv/bin/python tools/build_exe.py"
        )
    _copiar_executavel(origem)
    for tamanho, destino in ICONES.items():
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ASSETS / f"polvo-roxo-{tamanho}.png", destino)
    DESKTOP.parent.mkdir(parents=True, exist_ok=True)
    DESKTOP.write_text(_desktop_entry(BINARIO), encoding="utf-8")
    _atualizar_caches()
    print(f"Instalado: {BINARIO}")
    print(f"Atalho do menu: {DESKTOP}")
    print("Procure por “Polpad” no menu de aplicativos.")


def _remover(alvos: list[Path]) -> None:
    for alvo in alvos:
        if alvo.exists():
            alvo.unlink()
            print(f"removido: {alvo}")


def remover() -> None:
    # A inicialização automática apontaria para o executável removido.
    _remover([BINARIO, DESKTOP, autostart.desktop_file(), *ICONES.values()])
    _atualizar_caches()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--executavel",
        type=Path,
        default=RAIZ / "dist" / "Polpad",
        help="executável a instalar (padrão: dist/Polpad)",
    )
    parser.add_argument(
        "--remover", action="store_true", help="desinstala o que este script criou"
    )
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        raise SystemExit("este instalador é só para Linux")
    if args.remover:
        remover()
    else:
        instalar(args.executavel.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
