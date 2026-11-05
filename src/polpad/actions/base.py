"""Registro de tipos de ação (padrão Registry).

Cada tipo de ação é uma função ``(params, context) -> None`` registrada
pelo decorador :func:`register`. Adicionar um novo tipo de ação ao
sistema significa apenas registrar uma nova função — nenhuma outra
camada precisa mudar.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Assinatura de um executor: recebe os parâmetros da ação e o contexto.
Handler = Callable[[dict[str, Any], "ActionContext"], None]

_registry: dict[str, ActionType] = {}


@dataclass
class ActionType:
    """Metadados de um tipo de ação, usados também pela interface."""

    name: str            # identificador persistido (ex.: "hotkey")
    title: str           # nome exibido ao usuário
    description: str     # ajuda curta exibida no editor
    handler: Handler = field(repr=False, default=None)  # type: ignore[assignment]
    # Ações "remotas" fazem E/S de rede e podem levar segundos. Executam em
    # uma via própria para não atrasar as teclas seguintes; as demais
    # dependem do foco do teclado e precisam manter a ordem entre si.
    remote: bool = False


@dataclass
class ActionContext:
    """Dependências disponíveis aos executores."""

    settings: Any = None          # core.models.Settings (URL/token do HA, etc.)
    request_mode_switch: Callable[[], None] | None = None


def register(
    name: str, title: str, description: str, *, remote: bool = False
) -> Callable[[Handler], Handler]:
    def decorator(handler: Handler) -> Handler:
        _registry[name] = ActionType(name, title, description, handler, remote=remote)
        return handler

    return decorator


def get(name: str) -> ActionType | None:
    return _registry.get(name)


def all_types() -> list[ActionType]:
    return list(_registry.values())


class ActionError(Exception):
    """Erro de execução de uma ação, com mensagem apresentável ao usuário."""
