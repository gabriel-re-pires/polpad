"""Formato de arquivo para compartilhar perfis entre máquinas.

Um perfil exportado é um JSON legível com um marcador de formato, o
perfil em si e — quando houver — o ícone embutido em base64. O ícone
precisa viajar junto: ``Profile.icon_path`` aponta para um arquivo na
pasta de dados de quem exportou, que não existe na máquina de destino.

O ``id`` não é exportado: quem importa recebe um perfil novo, para que
importar duas vezes não sobrescreva nada nem gere ids repetidos.

Segurança: um perfil pode conter ações que executam comandos de shell ou
abrem programas. Quem importa precisa saber disso antes de aceitar — ver
:func:`sensitive_actions` e a confirmação na interface.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import Profile

FORMAT = "macropad-profile"
VERSION = 1

# Tipos de ação que executam algo escolhido por quem criou o perfil.
SENSITIVE_TYPES = ("command", "launch")

# Limite defensivo para o ícone embutido (o display tem 128x64).
MAX_ICON_BYTES = 2 * 1024 * 1024


class ProfileFileError(Exception):
    """Arquivo de perfil inválido, com mensagem apresentável ao usuário."""


@dataclass
class ImportedProfile:
    """Resultado da leitura de um arquivo de perfil."""

    profile: Profile
    icon_bytes: bytes | None = None
    icon_suffix: str = ".png"
    sensitive: list[tuple[int, str]] = field(default_factory=list)


def sensitive_actions(profile: Profile) -> list[tuple[int, str]]:
    """Lista ``(tecla, descrição)`` das ações que executam algo na máquina."""
    encontradas = []
    for key in sorted(profile.bindings):
        action = profile.bindings[key]
        if action.type not in SENSITIVE_TYPES:
            continue
        alvo = action.params.get("command") or action.params.get("target") or ""
        encontradas.append((key, str(alvo)))
    return encontradas


def to_json(profile: Profile, icon_path: str | None = None) -> str:
    """Serializa o perfil no formato de troca."""
    dados = profile.to_dict()
    dados.pop("id", None)
    dados.pop("icon_path", None)

    documento: dict[str, Any] = {
        "format": FORMAT,
        "version": VERSION,
        "profile": dados,
    }

    if icon_path:
        origem = Path(icon_path)
        try:
            bruto = origem.read_bytes()
        except OSError:
            # Ícone ausente não impede a exportação do resto do perfil.
            bruto = b""
        if bruto and len(bruto) <= MAX_ICON_BYTES:
            documento["icon"] = {
                "suffix": origem.suffix.lower() or ".png",
                "data": base64.b64encode(bruto).decode("ascii"),
            }

    return json.dumps(documento, ensure_ascii=False, indent=2)


def from_json(texto: str) -> ImportedProfile:
    """Lê e valida um arquivo de perfil. Lança :class:`ProfileFileError`."""
    try:
        documento = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise ProfileFileError(f"não é um JSON válido: {exc}") from exc
    if not isinstance(documento, dict):
        raise ProfileFileError("o conteúdo não é um objeto JSON")
    if documento.get("format") != FORMAT:
        raise ProfileFileError("não é um arquivo de perfil do macropad")
    versao = documento.get("version")
    if not isinstance(versao, int) or versao > VERSION:
        raise ProfileFileError(
            f"formato versão {versao} é mais novo que o suportado ({VERSION})"
        )

    bruto = documento.get("profile")
    if not isinstance(bruto, dict):
        raise ProfileFileError("o arquivo não contém um perfil")
    # Id novo: importar duas vezes gera dois perfis, sem sobrescrever nada.
    bruto = {**bruto, "id": ""}
    try:
        profile = Profile.from_dict(bruto)
    except (KeyError, TypeError, ValueError) as exc:
        raise ProfileFileError(f"perfil inválido: {exc}") from exc

    icon_bytes, icon_suffix = _icon_from_document(documento)
    return ImportedProfile(
        profile=profile,
        icon_bytes=icon_bytes,
        icon_suffix=icon_suffix,
        sensitive=sensitive_actions(profile),
    )


def _icon_from_document(documento: dict[str, Any]) -> tuple[bytes | None, str]:
    icone = documento.get("icon")
    if not isinstance(icone, dict):
        return None, ".png"
    try:
        bruto = base64.b64decode(icone.get("data", ""), validate=True)
    except (ValueError, TypeError):
        # Ícone corrompido não invalida o perfil: entra sem ícone.
        return None, ".png"
    if not bruto or len(bruto) > MAX_ICON_BYTES:
        return None, ".png"
    suffix = str(icone.get("suffix") or ".png")
    if not suffix.startswith(".") or len(suffix) > 6:
        suffix = ".png"
    return bruto, suffix
