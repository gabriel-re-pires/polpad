"""Token do Home Assistant e senha do OBS no cofre do sistema (``keyring``).

Sem cofre, as funções devolvem ``False`` e o
:class:`~polpad.core.store.Store` mantém o segredo no ``config.json``.
"""

from __future__ import annotations

import contextlib
import logging

SERVICE = "Polpad"

log = logging.getLogger(__name__)

_unavailable_logged = False


def _keyring():
    """Devolve o módulo keyring, ou ``None`` se não houver cofre utilizável."""
    global _unavailable_logged
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring
    except ImportError:
        if not _unavailable_logged:
            _unavailable_logged = True
            log.warning("keyring não instalado; segredos ficarão no config.json")
        return None
    if isinstance(keyring.get_keyring(), FailKeyring):
        if not _unavailable_logged:
            _unavailable_logged = True
            log.warning("nenhum cofre disponível; segredos ficarão no config.json")
        return None
    return keyring


def available() -> bool:
    return _keyring() is not None


def store(name: str, value: str) -> bool:
    """Grava (ou apaga, se ``value`` for vazio) um segredo. ``False`` se falhou."""
    keyring = _keyring()
    if keyring is None:
        return False
    try:
        if value:
            keyring.set_password(SERVICE, name, value)
        else:
            _delete(keyring, name)
    except Exception as exc:  # o backend pode falhar por vários motivos
        log.warning("não foi possível guardar %r no cofre: %s", name, exc)
        return False
    return True


def load(name: str) -> str | None:
    """Lê um segredo: ``""`` se não houver, ``None`` se a leitura falhar.

    Falha não é "apagado", senão o próximo ``save()`` o apagaria do cofre.
    """
    keyring = _keyring()
    if keyring is None:
        return ""
    try:
        return keyring.get_password(SERVICE, name) or ""
    except Exception as exc:
        log.warning("não foi possível ler %r do cofre: %s", name, exc)
        return None


def _delete(keyring, name: str) -> None:
    from keyring.errors import PasswordDeleteError

    with contextlib.suppress(PasswordDeleteError):
        keyring.delete_password(SERVICE, name)
