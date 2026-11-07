"""Ações da Zona de risco das Configurações.

Cada uma copia antes os perfis (a mesma cópia das trocas de versão), que
pode ser restaurada em "Versão e atualizações". O token e a senha das
integrações ficam no cofre do sistema, fora da cópia.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime

from ..update import backup
from .models import Settings
from .store import Store


def reset_settings(
    store: Store, current: str, now: datetime | None = None
) -> backup.Backup:
    """Volta as configurações ao padrão; os perfis ficam.

    As escolhas de atualização ficam: elas moram em "Versão e
    atualizações", não na página que tem o botão.
    """
    made = backup.create(
        store.data_dir, current, "configurações padrão", now, kind=backup.RISK
    )
    old = store.settings
    new = Settings(
        update_notify=old.update_notify,
        update_auto=old.update_auto,
        linux_install_prompt=old.linux_install_prompt,
    )
    # No lugar, e não um objeto novo: o contexto das ações (app.py) guarda
    # a referência a store.settings e ficaria com a URL e o token antigos.
    for campo in dataclasses.fields(Settings):
        setattr(old, campo.name, getattr(new, campo.name))
    store.save()
    return made


def reset_profiles(
    store: Store, current: str, now: datetime | None = None
) -> backup.Backup:
    """Apaga os perfis e os ícones; fica só o perfil inicial."""
    made = backup.create(
        store.data_dir, current, "perfis apagados", now, kind=backup.RISK
    )
    store.reset_profiles()
    return made
