"""Inicialização automática com o sistema.

No Windows registra o aplicativo em ``HKCU\\...\\Run``; no Linux cria
``~/.config/autostart/polpad.desktop`` (padrão XDG, seguido por XFCE, GNOME,
KDE e outros). Nos dois casos com ``--minimized`` (inicia direto na
bandeja, sem janela) e sem privilégios de administrador.

O comando depende de como o aplicativo está rodando: no executável
empacotado é o próprio executável; a partir do código-fonte é o
``pythonw.exe`` do ambiente virtual (``python`` no Linux) com
``-m polpad``.
"""

from __future__ import annotations

import contextlib
import os
import re
import sys
from pathlib import Path

#: Nome do sistema nos textos da interface ("Iniciar com o Windows").
SYSTEM_NAME = "Windows" if sys.platform == "win32" else "sistema"

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "Polpad"

_DESKTOP_FILE = "polpad.desktop"


def _frozen() -> bool:
    """``True`` quando rodando a partir do executável do PyInstaller."""
    return getattr(sys, "frozen", False)


def _argv() -> list[str]:
    if _frozen():
        # sys.executable é o próprio aplicativo; "-m polpad" não existe aqui.
        return [sys.executable, "--minimized"]
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else python
    return [str(exe), "-m", "polpad", "--minimized"]


def _command() -> str:
    """Linha de comando gravada na chave Run do Windows."""
    exe, *args = _argv()
    return " ".join([f'"{exe}"', *args])


def apply(enabled: bool) -> None:
    """Cria ou remove a entrada de inicialização conforme a configuração."""
    if sys.platform == "win32":
        _apply_windows(enabled)
    elif sys.platform.startswith("linux"):
        _apply_xdg(enabled)


def is_enabled() -> bool:
    if sys.platform == "win32":
        return _is_enabled_windows()
    if sys.platform.startswith("linux"):
        return desktop_file().exists()
    return False


# ------------------------------------------------------------- Windows


def _apply_windows(enabled: bool) -> None:
    # Redundante para quem chama; diz ao mypy que o resto é do Windows.
    if sys.platform != "win32":
        return
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        if enabled:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _command())
        else:
            # Já ausente da chave Run: desabilitar é idempotente.
            with contextlib.suppress(FileNotFoundError):
                winreg.DeleteValue(key, _VALUE_NAME)


def _is_enabled_windows() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _VALUE_NAME)
            return True
    except FileNotFoundError:
        return False


# --------------------------------------------------------------- Linux


def desktop_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "autostart" / _DESKTOP_FILE


def _apply_xdg(enabled: bool) -> None:
    path = desktop_file()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(desktop_entry(), encoding="utf-8")
    else:
        path.unlink(missing_ok=True)


def desktop_entry() -> str:
    """Conteúdo do ``.desktop`` de inicialização automática."""
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Polpad\n"
        "Comment=Configurador do macropad (inicia na bandeja)\n"
        f"Exec={exec_line(_argv())}\n"
        "Icon=polpad\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


# Caracteres que obrigam a pôr o argumento entre aspas no campo Exec.
_EXEC_RESERVED = set(" \t\n\"'\\><~|&;$*?#()`")


def exec_line(argv: list[str]) -> str:
    """Monta o campo ``Exec`` conforme a Desktop Entry Specification."""
    parts = []
    for arg in argv:
        arg = arg.replace("%", "%%")
        if any(c in _EXEC_RESERVED for c in arg):
            arg = '"' + re.sub(r'(["`$\\])', r"\\\1", arg) + '"'
        # No arquivo .desktop a barra invertida também é escape.
        parts.append(arg.replace("\\", "\\\\"))
    return " ".join(parts)
