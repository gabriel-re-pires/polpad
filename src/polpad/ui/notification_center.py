"""Guarda os avisos do Polpad na central de notificações do Windows.

O aviso do canto da tela já aparece por 5 s; aqui ele vai para a central
**sem** abrir um segundo banner (``SuppressPopup``), para quem quiser
ver depois. Cada aviso novo substitui o anterior (mesma ``tag``), então
abrir o Polpad várias vezes não enche a central de cópias.

O Windows só aceita notificações de um aplicativo registrado: o nome e o
ícone ficam em ``HKCU\\Software\\Classes\\AppUserModelId\\Polpad.Polpad``
(sem precisar de administrador). Fora do Windows, ou sem o pacote
``winrt``, as funções não fazem nada e devolvem ``False``.
"""

from __future__ import annotations

import logging
import sys
from xml.sax.saxutils import escape

from .. import APP_NAME
from . import app_icon

log = logging.getLogger(__name__)

AUMID = "Polpad.Polpad"
TAG = "atualizacao"
GROUP = "polpad"
REG_KEY = rf"Software\Classes\AppUserModelId\{AUMID}"

_ENTITIES = {'"': "&quot;", "'": "&apos;"}


def toast_xml(title: str, body: str) -> str:
    """O conteúdo da notificação no formato que o Windows espera."""
    texts = [title] + ([body] if body else [])
    lines = "".join(f"<text>{escape(t, _ENTITIES)}</text>" for t in texts)
    return (
        "<toast><visual><binding template='ToastGeneric'>"
        f"{lines}</binding></visual></toast>"
    )


def _register() -> None:
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(
            key, "IconUri", 0, winreg.REG_SZ, str(app_icon.ASSETS / "polvo-roxo-256.png")
        )


def post(title: str, body: str) -> bool:
    """Põe o aviso na central, sem banner. ``True`` se o Windows aceitou."""
    if sys.platform != "win32":
        return False
    try:
        from winrt.windows.data.xml.dom import XmlDocument
        from winrt.windows.ui.notifications import (
            ToastNotification,
            ToastNotificationManager,
        )

        _register()
        doc = XmlDocument()
        doc.load_xml(toast_xml(title, body))
        toast = ToastNotification(doc)
        toast.suppress_popup = True
        toast.tag = TAG
        toast.group = GROUP
        ToastNotificationManager.create_toast_notifier_with_id(AUMID).show(toast)
    except Exception:  # um aviso a menos nunca pode derrubar o Polpad
        log.debug("não foi possível guardar o aviso na central", exc_info=True)
        return False
    return True


def clear() -> bool:
    """Tira da central os avisos do Polpad (a atualização já começou)."""
    if sys.platform != "win32":
        return False
    try:
        from winrt.windows.ui.notifications import ToastNotificationManager

        ToastNotificationManager.history.clear_with_id(AUMID)
    except Exception:
        log.debug("não foi possível limpar a central", exc_info=True)
        return False
    return True
