"""Persistência de perfis e configurações em JSON.

Os dados ficam em ``%APPDATA%/Polpad`` (ou ``~/.config`` em
outros sistemas). As imagens de ícone escolhidas pelo usuário são copiadas
para o subdiretório ``icons/`` para que o perfil continue funcionando caso
o arquivo original seja movido.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from . import icons, profile_io, secrets
from .models import Action, DisplayConfig, Profile, Settings

_CONFIG_FILE = "config.json"

# Campos de Settings que não devem ficar legíveis no config.json.
_SECRET_FIELDS = ("ha_token", "obs_password")

log = logging.getLogger(__name__)


class SecretVault(Protocol):
    """Cofre de credenciais (ver :mod:`polpad.core.secrets`).

    Injetável para que os testes não toquem no Credential Manager real.
    """

    def store(self, name: str, value: str) -> bool: ...
    def load(self, name: str) -> str | None: ...


def default_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "Polpad"


class Store:
    """Carrega e salva o estado do aplicativo de forma atômica."""

    def __init__(
        self,
        data_dir: Path | None = None,
        vault: SecretVault | None = None,
    ) -> None:
        self.data_dir = data_dir or default_data_dir()
        self._vault: SecretVault = vault if vault is not None else secrets
        self.icons_dir = self.data_dir / "icons"
        self.settings = Settings()
        self.profiles: list[Profile] = []
        self.active_profile_id: str | None = None
        # Definido pela raiz de composição para levar falhas de gravação à
        # interface; sem ele, restam apenas as mensagens no log.
        self.on_error: Callable[[str], None] | None = None
        # Serializa as gravações. save() é chamado tanto pela interface
        # quanto pelo caminho do dispositivo (tecla de modo), e duas
        # gravações simultâneas no mesmo temporário deixavam a
        # configuração pela metade.
        self._write_lock = threading.RLock()
        # Segredos que o cofre não deixou ler. Enquanto continuarem vazios
        # em memória, save() não os apaga do cofre.
        self._unreadable: set[str] = set()

    # ------------------------------------------------------------------ IO

    def load(self) -> None:
        """Carrega a configuração, aproveitando o máximo possível.

        Um arquivo parcialmente corrompido não deve custar todos os perfis
        do usuário: cada perfil inválido é descartado isoladamente e o
        arquivo original é preservado em ``.json.bak`` sempre que algo se
        perde. Falhar aqui nunca impede o aplicativo de abrir.
        """
        path = self.data_dir / _CONFIG_FILE
        if not path.exists():
            self._create_default()
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("configuração ilegível (%s); recomeçando do padrão", exc)
            self._backup(path)
            self._create_default()
            return
        if not isinstance(data, dict):
            log.warning("configuração não é um objeto JSON; recomeçando do padrão")
            self._backup(path)
            self._create_default()
            return

        self.settings, settings_ok = _settings_from_dict(data.get("settings"))
        # Versões anteriores tinham um display só, nas configurações: os
        # perfis salvos sem configuração própria herdam aquele.
        legado = DisplayConfig.from_legacy_settings(data.get("settings"))
        self.profiles, discarded = _profiles_from_dict(data.get("profiles"), legado)
        if not settings_ok or discarded:
            self._backup(path)

        self._load_secrets()

        active = data.get("active_profile_id")
        self.active_profile_id = active if isinstance(active, str) else None
        if not self.profiles:
            self._create_default_profile()
        if self.active_profile_id not in {p.id for p in self.profiles}:
            self.active_profile_id = self.profiles[0].id
        self._migrate_mode_switch_bindings()

    # ------------------------------------------------------ tecla de modo

    def mode_switch_conflicts(self, key: int) -> list[str]:
        """Perfis em que ``key`` tem uma ação que a tecla de modo esconderia."""
        return [
            p.name
            for p in self.profiles
            if (a := p.action_for(key)) is not None and a.type != "mode_switch"
        ]

    def promote_to_mode_key(self, key: int) -> None:
        """Faz de ``key`` a tecla de modo, válida em todos os perfis.

        A ação "Alternar perfil" presa a um perfil só criava um beco sem
        saída: no perfil seguinte a mesma tecla não tinha ação e não havia
        como voltar ao primeiro. A tecla de modo vale em todos os perfis e
        percorre a lista em ciclo (:meth:`next_profile`). As ações
        "Alternar perfil" daquela tecla saem (são redundantes); ações de
        outro tipo ficam guardadas e voltam se a tecla de modo mudar.
        """
        self.settings.mode_key = key
        for profile in self.profiles:
            action = profile.action_for(key)
            if action is not None and action.type == "mode_switch":
                del profile.bindings[key]

    def _migrate_mode_switch_bindings(self) -> None:
        """Converte "Alternar perfil" de versões anteriores em tecla de modo.

        Só quando não há tecla de modo e todas as ações "Alternar perfil"
        estão na mesma tecla — aí a intenção é inequívoca.
        """
        if self.settings.mode_key is not None:
            return
        keys = {
            key
            for p in self.profiles
            for key, action in p.bindings.items()
            if action.type == "mode_switch"
        }
        if len(keys) != 1:
            return
        (key,) = keys
        log.info("ação 'Alternar perfil' na tecla %d virou a tecla de modo", key + 1)
        self.promote_to_mode_key(key)
        self.save()

    # ---------------------------------------------------------- segredos

    def _load_secrets(self) -> None:
        """Completa as credenciais a partir do cofre do sistema.

        Um valor ainda presente no arquivo (instalação anterior à mudança)
        tem precedência e é migrado para o cofre no próximo ``save()``.
        """
        self._unreadable.clear()
        for campo in _SECRET_FIELDS:
            if not getattr(self.settings, campo):
                valor = self._vault.load(campo)
                if valor is None:
                    self._unreadable.add(campo)
                    valor = ""
                setattr(self.settings, campo, valor)

    def _store_secrets(self, data: dict[str, Any]) -> None:
        """Move as credenciais do dicionário a salvar para o cofre.

        O que for guardado no cofre sai do JSON; o que não puder ser
        guardado continua no arquivo, para não perder a configuração.
        """
        settings_data = data.get("settings")
        if not isinstance(settings_data, dict):
            return
        for campo in _SECRET_FIELDS:
            valor = getattr(self.settings, campo)
            if not valor and campo in self._unreadable:
                # Vazio só porque o cofre falhou na leitura: apagar agora
                # perderia o segredo que continua lá.
                continue
            if self._vault.store(campo, valor):
                settings_data[campo] = ""
                self._unreadable.discard(campo)

    def _backup(self, path: Path) -> None:
        """Preserva o arquivo original antes de sobrescrevê-lo.

        Se nem a cópia for possível, ainda é melhor abrir o aplicativo do
        que impedir seu uso.
        """
        with contextlib.suppress(OSError):
            shutil.copy(path, path.with_suffix(".json.bak"))

    def save(self) -> bool:
        """Grava a configuração de forma atômica. ``False`` se não conseguiu.

        Chamado a cada troca de perfil (inclusive pela tecla de modo), então
        uma falha de disco não pode derrubar o aplicativo: é registrada e
        reportada, e o macropad continua funcionando com o estado em
        memória.
        """
        data: dict[str, Any] = {
            "settings": self.settings.to_dict(),
            "active_profile_id": self.active_profile_id,
            "profiles": [p.to_dict() for p in self.profiles],
        }
        self._store_secrets(data)
        path = self.data_dir / _CONFIG_FILE
        tmp: Path | None = None
        # O temporário tem nome único. Com um nome fixo (.json.tmp), duas
        # gravações concorrentes escreviam no mesmo arquivo e o segundo
        # replace() promovia um JSON truncado a configuração oficial, ou
        # falhava com FileNotFoundError.
        with self._write_lock:
            try:
                self.data_dir.mkdir(parents=True, exist_ok=True)
                fd, nome = tempfile.mkstemp(
                    prefix=".config-", suffix=".tmp", dir=self.data_dir
                )
                tmp = Path(nome)
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=2)
                    fh.flush()
                    os.fsync(fh.fileno())
                tmp.replace(path)
                tmp = None
            except OSError as exc:
                log.error("falha ao salvar %s: %s", path, exc)
                # Não deixa para trás um arquivo temporário pela metade.
                if tmp is not None:
                    with contextlib.suppress(OSError):
                        tmp.unlink(missing_ok=True)
                if self.on_error is not None:
                    self.on_error(f"não foi possível salvar as configurações: {exc}")
                return False
        return True

    def _create_default(self) -> None:
        self.settings = Settings()
        # O config.json pode ter sumido ou estragado, mas os segredos no
        # cofre continuam valendo; sem isto o save() abaixo os apagaria.
        self._load_secrets()
        self.profiles = []
        self._create_default_profile()
        self.active_profile_id = self.profiles[0].id
        self.save()

    def reset_profiles(self) -> None:
        """Deixa só o perfil inicial e apaga os ícones (Zona de risco)."""
        self.profiles = []
        self._create_default_profile()
        self.active_profile_id = self.profiles[0].id
        shutil.rmtree(self.icons_dir, ignore_errors=True)
        self.save()

    def _create_default_profile(self) -> None:
        profile = Profile(name="Sistema")
        profile.bindings[0] = Action(
            type="hotkey", params={"keys": ["ctrl", "c"]}, label="Copiar"
        )
        profile.bindings[1] = Action(
            type="hotkey", params={"keys": ["ctrl", "v"]}, label="Colar"
        )
        self.profiles.append(profile)

    # ------------------------------------------------------------ profiles

    def profile_by_id(self, profile_id: str | None) -> Profile | None:
        for p in self.profiles:
            if p.id == profile_id:
                return p
        return None

    @property
    def active_profile(self) -> Profile | None:
        return self.profile_by_id(self.active_profile_id)

    def add_profile(self, name: str) -> Profile:
        profile = Profile(name=name)
        self.profiles.append(profile)
        self.save()
        return profile

    def remove_profile(self, profile_id: str) -> None:
        self.profiles = [p for p in self.profiles if p.id != profile_id]
        if not self.profiles:
            self._create_default_profile()
        if self.active_profile_id == profile_id:
            self.active_profile_id = self.profiles[0].id
        self.save()

    def next_profile(self) -> Profile:
        """Perfil seguinte na ordem da lista (usado pela tecla de modo)."""
        ids = [p.id for p in self.profiles]
        current = self.active_profile_id
        # Sem perfil ativo (ou apontando para um já excluído): começa do
        # primeiro da lista.
        idx = ids.index(current) if current in ids else -1
        profile = self.profiles[(idx + 1) % len(self.profiles)]
        self.active_profile_id = profile.id
        self.save()
        return profile

    # ------------------------------------------------- troca de perfis

    def export_profile(self, profile: Profile, destino: Path) -> None:
        """Grava o perfil em um arquivo de troca (com o ícone embutido)."""
        texto = profile_io.to_json(profile, profile.icon_path)
        Path(destino).write_text(texto, encoding="utf-8")

    def add_imported_profile(self, importado: profile_io.ImportedProfile) -> Profile:
        """Acrescenta um perfil lido de arquivo, gravando o ícone que veio junto."""
        profile = importado.profile
        if importado.icon_bytes:
            try:
                self.icons_dir.mkdir(parents=True, exist_ok=True)
                destino = self.icons_dir / f"{profile.id}{importado.icon_suffix}"
                destino.write_bytes(importado.icon_bytes)
                profile.icon_path = str(destino)
            except OSError as exc:
                # Sem o ícone o perfil ainda é útil: o display mostra o nome.
                log.warning("não foi possível gravar o ícone importado: %s", exc)
        self.profiles.append(profile)
        self.save()
        return profile

    #: Extensões aceitas como ícone. O filtro do QFileDialog é só
    #: sugestão: o usuário pode digitar qualquer nome de arquivo.
    ICON_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")

    def import_icon(self, source: str, profile: Profile) -> str:
        """Copia a imagem escolhida para o diretório de dados e a associa ao perfil.

        Valida a imagem ANTES de copiar. Levanta ``OSError`` ou
        ``ValueError`` quando o arquivo não serve; quem chama mostra a
        mensagem ao usuário.
        """
        ext = Path(source).suffix.lower()
        if ext not in self.ICON_SUFFIXES:
            raise ValueError(
                f"formato não suportado ({ext or 'sem extensão'}); "
                f"use {', '.join(self.ICON_SUFFIXES)}"
            )
        # Falha aqui, com o arquivo original, antes de sujar o diretório de
        # dados. O Pillow levanta tipos variados em imagem corrompida,
        # inclusive DecompressionBombError, que não é OSError nem
        # ValueError e escaparia dos tratamentos a jusante.
        try:
            icons.validar_imagem(source)
        except (OSError, ValueError):
            raise
        except Exception as exc:
            raise ValueError(f"não foi possível ler a imagem: {exc}") from exc

        anterior = profile.icon_path
        self.icons_dir.mkdir(parents=True, exist_ok=True)
        dest = self.icons_dir / f"{profile.id}{ext}"
        shutil.copy(source, dest)
        profile.icon_path = str(dest)
        self.save()
        # Trocar um .png por um .jpg deixava o arquivo antigo órfão.
        if anterior and Path(anterior) != dest:
            with contextlib.suppress(OSError):
                Path(anterior).unlink(missing_ok=True)
        return str(dest)


# ------------------------------------------------- desserialização tolerante


def _settings_from_dict(raw: Any) -> tuple[Settings, bool]:
    """Devolve (configurações, ``True`` se vieram intactas do arquivo)."""
    if raw is None:
        return Settings(), True
    if not isinstance(raw, dict):
        log.warning("bloco 'settings' inválido; usando os padrões")
        return Settings(), False
    try:
        return Settings.from_dict(raw), True
    except (TypeError, ValueError) as exc:
        log.warning("configurações inválidas (%s); usando os padrões", exc)
        return Settings(), False


def _profiles_from_dict(
    raw: Any, default_display: DisplayConfig | None = None
) -> tuple[list[Profile], int]:
    """Devolve (perfis válidos, quantidade descartada)."""
    if raw is None:
        return [], 0
    if not isinstance(raw, list):
        log.warning("bloco 'profiles' inválido; nenhum perfil carregado")
        return [], 1

    profiles: list[Profile] = []
    discarded = 0
    for index, item in enumerate(raw):
        try:
            profiles.append(Profile.from_dict(item, default_display))
        except (KeyError, TypeError, ValueError) as exc:
            discarded += 1
            log.warning("perfil na posição %d descartado (%s)", index, exc)
    return profiles, discarded
