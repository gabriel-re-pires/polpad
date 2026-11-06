"""Põe o Polpad no menu de aplicativos do Linux (só para o usuário atual).

Copia o executável para ``~/.local/bin/polpad``, o ícone do polvo para o
tema ``hicolor`` e cria ``~/.local/share/applications/polpad.desktop``.
Nada fora da pasta pessoal é tocado, então não precisa de sudo. Funciona a
partir do executável baixado: os ícones vêm de dentro do pacote.

Os caminhos são calculados na chamada (``HOME``/``XDG_DATA_HOME`` podem
mudar, por exemplo nos testes).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..core import autostart

ASSETS = Path(__file__).resolve().parent.parent / "ui" / "assets"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def binary_path() -> Path:
    return Path.home() / ".local" / "bin" / "polpad"


def desktop_path() -> Path:
    return _data_home() / "applications" / "polpad.desktop"


def icon_paths() -> dict[int, Path]:
    return {
        n: _data_home() / "icons" / "hicolor" / f"{n}x{n}" / "apps" / "polpad.png"
        for n in SIZES
    }


def desktop_entry(binary: Path) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Polpad\n"
        "GenericName=Configurador do macropad\n"
        "Comment=Teclas, perfis e display do macropad ESP32-C3\n"
        f"Exec={autostart.exec_line([str(binary)])}\n"
        "Icon=polpad\n"
        "Terminal=false\n"
        "Categories=Utility;\n"
        "Keywords=macropad;teclado;atalho;esp32;\n"
        "StartupNotify=true\n"
        "StartupWMClass=Polpad\n"
    )


def install(source: Path) -> None:
    """Instala ``source`` (o executável) no menu."""
    binary = binary_path()
    binary.parent.mkdir(parents=True, exist_ok=True)
    # Copia para um temporário e renomeia: sobrescrever direto falha com
    # "Text file busy" se a versão anterior estiver aberta.
    tmp = binary.with_name(f".{binary.name}.novo")
    shutil.copyfile(source, tmp)
    tmp.chmod(0o755)
    tmp.replace(binary)
    for size, destination in icon_paths().items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ASSETS / f"polvo-roxo-{size}.png", destination)
    desktop = desktop_path()
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(desktop_entry(binary), encoding="utf-8")
    _refresh_caches()


def uninstall() -> list[Path]:
    """Remove o que ``install`` criou e a inicialização automática."""
    removed = []
    targets = [binary_path(), desktop_path(), autostart.desktop_file()]
    for target in [*targets, *icon_paths().values()]:
        if target.exists():
            target.unlink()
            removed.append(target)
    _refresh_caches()
    return removed


def is_installed() -> bool:
    return binary_path().is_file() and desktop_path().is_file()


def running_from_menu() -> bool:
    return os.path.abspath(sys.executable) == os.path.abspath(binary_path())


def _refresh_caches() -> None:
    """Avisa o menu e o tema de ícones (opcional: o menu percebe sozinho)."""
    for argv in (
        ["update-desktop-database", str(desktop_path().parent)],
        ["gtk-update-icon-cache", "-f", "-t", str(_data_home() / "icons" / "hicolor")],
    ):
        if shutil.which(argv[0]):
            subprocess.run(argv, capture_output=True, check=False)  # noqa: S603
