"""Detecção do aplicativo em primeiro plano (Windows e Linux/X11).

Usada pela troca automática de perfil: quando o executável em foco muda
e corresponde ao ``auto_apps`` de um perfil, esse perfil é ativado.

A detecção é *edge-triggered* (só reage à MUDANÇA de foco), de modo que
uma troca manual pela tecla de modo prevalece até o usuário focar outro
aplicativo vinculado.

No Linux o aplicativo é identificado pela classe da janela (``WM_CLASS``,
ex.: ``code``, ``firefox``, ``obs``) e não pelo executável: apps Electron,
Java ou Python rodam todos sob o mesmo interpretador, e o PID de um app
Flatpak é o de dentro da sandbox. Numa sessão Wayland só as janelas que
rodam via XWayland são vistas.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from ctypes import wintypes
from typing import Any

from ..core.models import Profile

log = logging.getLogger(__name__)

if sys.platform == "win32":
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def _foreground_windows() -> str | None:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return None
        handle = _kernel32.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
        )
        if not handle:
            return None
        try:
            buffer = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(len(buffer))
            if not _kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)
            ):
                return None
            path = buffer.value
        finally:
            _kernel32.CloseHandle(handle)
        return path.rsplit("\\", 1)[-1].lower() if path else None


#: Exemplo de nome para os textos da interface.
EXAMPLE = "code.exe" if sys.platform == "win32" else "code"


def foreground_exe() -> str | None:
    """Nome do aplicativo em foco, em minúsculas (``code.exe`` / ``code``)."""
    if sys.platform == "win32":
        return _foreground_windows()
    if sys.platform.startswith("linux"):
        return _foreground_x11()
    return None


# Conexão com o servidor X, aberta na primeira consulta e reaproveitada (a
# consulta roda uma vez por segundo). Só a thread da interface a usa.
_x_display: Any = None
_x_unavailable = False


def _x11_display() -> Any:
    global _x_display, _x_unavailable
    if _x_display is None and not _x_unavailable:
        if not os.environ.get("DISPLAY"):
            _x_unavailable = True
            log.info("sem servidor X; troca automática de perfil indisponível")
            return None
        try:
            from Xlib import display

            _x_display = display.Display()
        except Exception as exc:  # python-xlib ausente, X recusou a conexão...
            _x_unavailable = True
            log.info("sem acesso ao X11 (%s); troca automática indisponível", exc)
    return _x_display


def _foreground_x11() -> str | None:
    global _x_display
    disp = _x11_display()
    if disp is None:
        return None
    from Xlib import X
    from Xlib.error import ConnectionClosedError, XError

    try:
        root = disp.screen().root
        active = root.get_full_property(
            disp.intern_atom("_NET_ACTIVE_WINDOW"), X.AnyPropertyType
        )
        if active is None or not active.value or not active.value[0]:
            return None
        window = disp.create_resource_object("window", int(active.value[0]))
        wm_class = window.get_wm_class()
    except ConnectionClosedError:
        # Servidor X reiniciado: reconecta na próxima consulta.
        _x_display = None
        return None
    except XError:
        # A janela fechou entre as duas consultas.
        return None
    return wm_class_name(wm_class)


def wm_class_name(wm_class: tuple[str, str] | None) -> str | None:
    """Nome do app a partir do ``WM_CLASS`` (instância, classe).

    A classe identifica o aplicativo (``firefox``); a instância às vezes é
    só o papel da janela (o Firefox usa ``Navigator``).
    """
    if not wm_class:
        return None
    instance, klass = wm_class
    name = klass or instance
    return name.lower() if name else None


def match_profile(profiles: list[Profile], exe: str | None) -> Profile | None:
    """Encontra o primeiro perfil vinculado ao executável dado."""
    if not exe:
        return None
    exe = exe.lower()
    for profile in profiles:
        if exe in profile.auto_apps:
            return profile
    return None
