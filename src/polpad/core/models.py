"""Modelos de domínio: :class:`Profile` liga cada tecla a uma :class:`Action`.

Ações são tipo + parâmetros, para novos tipos não mexerem no modelo (ver
``actions/``).
"""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# Layout físico conforme o PCB (o ESP32-C3 e o display ocupam as duas
# primeiras posições). Numeração igual à do firmware (docs/PROTOCOLO.md):
#
#               [ 0] [ 1] [ 2]
#     [ 3] [ 4] [ 5] [ 6] [ 7]
#     [ 8] [ 9] [10] [11] [12]
#     [13] [14] [15] [16] [17]
#
# Única fonte de verdade do layout (interface, simulador, ícone do app).
GRID_ROWS = 4
GRID_COLS = 5
KEY_LAYOUT: tuple[tuple[int, int], ...] = (
    (0, 2), (0, 3), (0, 4),
    (1, 0), (1, 1), (1, 2), (1, 3), (1, 4),
    (2, 0), (2, 1), (2, 2), (2, 3), (2, 4),
    (3, 0), (3, 1), (3, 2), (3, 3), (3, 4),
)
KEY_COUNT = len(KEY_LAYOUT)

# Abreviação de uma tecla no mapa do display: 5 colunas x 3 caracteres
# (fonte 6 px) + 4 espaços = 19 caracteres, que cabem nos 21 do display.
SHORT_LABEL_MAX = 3


def key_at(row: int, col: int) -> int | None:
    """Índice da tecla na posição da grade, ou ``None`` se a posição é vazia."""
    try:
        return KEY_LAYOUT.index((row, col))
    except ValueError:
        return None


# Resolução do display OLED 0,96" (SSD1306).
SCREEN_W = 128
SCREEN_H = 64


@dataclass
class Action:
    """Ação associada a uma tecla.

    ``type`` é o executor registrado; ``label``, o nome na tecla do
    configurador. ``short`` era do mapa do display (que saiu) e fica para não
    perder o que já está nos arquivos.
    """

    type: str
    params: dict[str, Any] = field(default_factory=dict)
    label: str = ""
    short: str = ""

    @property
    def display_short(self) -> str:
        """Abreviação efetiva para o display (``short`` ou derivada do rótulo)."""
        if self.short:
            return _ascii(self.short)[:SHORT_LABEL_MAX] or "?"
        return short_label(self.label or self.type)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": self.type,
            "params": self.params,
            "label": self.label,
        }
        if self.short:
            data["short"] = self.short
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Action:
        return cls(
            type=data["type"],
            params=dict(data.get("params", {})),
            label=str(data.get("label", "") or ""),
            short=str(data.get("short", "") or "")[:SHORT_LABEL_MAX],
        )


def short_label(text: str) -> str:
    """Abreviação de até 3 caracteres ASCII maiúsculos (``Edição`` -> ``EDI``).

    Palavras compostas usam as iniciais (``Ctrl+Shift+P`` -> ``CSP``).
    """
    words = [w for w in re.split(r"[\s+_\-/.:→]+", _ascii(text)) if w]
    if not words:
        return "?"
    if len(words) >= 2:
        initials = "".join(w[0] for w in words)[:SHORT_LABEL_MAX]
        if len(initials) >= 2:
            return initials.upper()
    return words[0][:SHORT_LABEL_MAX].upper()


def _ascii(text: str) -> str:
    """Remove acentos (a fonte do display só tem ASCII)."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


DISPLAY_MODES = ("icone", "personalizado")


@dataclass
class DisplayConfig:
    """O que o display mostra enquanto o perfil está ativo (um por perfil).

    ``icon_splash``: no modo personalizado, mostra o ícone ao entrar no perfil.
    """

    mode: str = "icone"
    icon_splash: bool = True
    show_time: bool = True
    show_date: bool = True
    show_profile: bool = True
    text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "icon_splash": self.icon_splash,
            "show_time": self.show_time,
            "show_date": self.show_date,
            "show_profile": self.show_profile,
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data: Any) -> DisplayConfig:
        if not isinstance(data, dict):
            return cls()
        return cls(
            # "mapa" (versões anteriores) não existe mais: vira "icone".
            mode="personalizado" if data.get("mode") == "personalizado" else "icone",
            icon_splash=bool(data.get("icon_splash", True)),
            show_time=bool(data.get("show_time", True)),
            show_date=bool(data.get("show_date", True)),
            show_profile=bool(data.get("show_profile", True)),
            text=str(data.get("text", "") or ""),
        )

    @classmethod
    def from_legacy_settings(cls, data: Any) -> DisplayConfig:
        """Converte o bloco global das versões em que o display era um só."""
        if not isinstance(data, dict):
            return cls()
        return cls.from_dict(
            {
                "mode": data.get("display_mode"),
                "icon_splash": data.get("icon_splash", True),
                "show_time": data.get("custom_time", True),
                "show_date": data.get("custom_date", True),
                "show_profile": data.get("custom_profile", True),
                "text": data.get("custom_text", ""),
            }
        )

    def copy(self) -> DisplayConfig:
        return DisplayConfig.from_dict(self.to_dict())


@dataclass
class Profile:
    """Conjunto nomeado de atalhos, selecionável pela tecla de modo.

    ``auto_apps``: executáveis (ex.: ``code.exe``) que ativam o perfil ao ganhar foco.
    """

    name: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    icon_path: str | None = None
    bindings: dict[int, Action] = field(default_factory=dict)
    auto_apps: list[str] = field(default_factory=list)
    display: DisplayConfig = field(default_factory=DisplayConfig)

    def action_for(self, key: int) -> Action | None:
        return self.bindings.get(key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "icon_path": self.icon_path,
            "bindings": {str(k): a.to_dict() for k, a in self.bindings.items()},
            "auto_apps": self.auto_apps,
            "display": self.display.to_dict(),
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], default_display: DisplayConfig | None = None
    ) -> Profile:
        """Reconstrói o perfil. Lança ``KeyError`` se não houver nome.

        Teclas e apps inválidos são descartados um a um, sem perder o perfil.
        Perfis anteriores ao display por perfil recebem ``default_display``.
        """
        name = data["name"]
        if "display" in data:
            display = DisplayConfig.from_dict(data["display"])
        elif default_display is not None:
            display = default_display.copy()
        else:
            display = DisplayConfig()
        return cls(
            name=name,
            id=data.get("id") or uuid.uuid4().hex,
            icon_path=data.get("icon_path"),
            bindings=_bindings_from_dict(data.get("bindings"), name),
            auto_apps=_auto_apps_from_dict(data.get("auto_apps"), name),
            display=display,
        )


def _bindings_from_dict(raw: Any, profile_name: Any) -> dict[int, Action]:
    if not isinstance(raw, dict):
        return {}
    bindings: dict[int, Action] = {}
    for key, action in raw.items():
        try:
            bindings[int(key)] = Action.from_dict(action)
        except (KeyError, TypeError, ValueError):
            log.warning(
                "perfil %r: tecla %r descartada (definição inválida)",
                profile_name,
                key,
            )
    return bindings


def _auto_apps_from_dict(raw: Any, profile_name: Any) -> list[str]:
    # Uma string aqui seria iterada caractere a caractere; só lista serve.
    if not isinstance(raw, list):
        if raw is not None:
            log.warning("perfil %r: apps vinculados descartados", profile_name)
        return []
    return [str(app).lower() for app in raw]


@dataclass
class Settings:
    """Configurações globais do aplicativo (independem de perfil)."""

    # Índice (0..17) da tecla que alterna o perfil ativo; None = desabilitado.
    mode_key: int | None = None
    # Porta serial preferida (ex.: "COM5"); None = detecção automática.
    serial_port: str | None = None
    auto_switch_enabled: bool = False
    start_with_windows: bool = False
    ha_url: str = ""
    ha_token: str = ""
    # OBS Studio (obs-websocket v5).
    obs_host: str = "localhost"
    obs_port: int = 4455
    obs_password: str = ""
    update_notify: bool = True
    update_auto: bool = False
    # Linux: perguntar se o Polpad deve se instalar no menu de aplicativos.
    linux_install_prompt: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode_key": self.mode_key,
            "serial_port": self.serial_port,
            "auto_switch_enabled": self.auto_switch_enabled,
            "start_with_windows": self.start_with_windows,
            "ha_url": self.ha_url,
            "ha_token": self.ha_token,
            "obs_host": self.obs_host,
            "obs_port": self.obs_port,
            "obs_password": self.obs_password,
            "update_notify": self.update_notify,
            "update_auto": self.update_auto,
            "linux_install_prompt": self.linux_install_prompt,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        return cls(
            mode_key=data.get("mode_key"),
            serial_port=data.get("serial_port"),
            auto_switch_enabled=bool(data.get("auto_switch_enabled", False)),
            start_with_windows=bool(data.get("start_with_windows", False)),
            ha_url=data.get("ha_url", ""),
            ha_token=data.get("ha_token", ""),
            obs_host=data.get("obs_host", "localhost"),
            obs_port=int(data.get("obs_port", 4455)),
            obs_password=data.get("obs_password", ""),
            update_notify=bool(data.get("update_notify", True)),
            update_auto=bool(data.get("update_auto", False)),
            linux_install_prompt=bool(data.get("linux_install_prompt", True)),
        )
