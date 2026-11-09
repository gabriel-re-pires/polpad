"""Arquivo para compartilhar perfis entre máquinas.

JSON com marcador de formato, o perfil e o ícone em base64 (o ``icon_path``
não existe no destino). O ``id`` não vai: importar duas vezes não sobrescreve.
Ações que executam algo são listadas por :func:`sensitive_actions` para a
confirmação na interface.
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

# Executam algo escolhido por quem criou o perfil (o webhook, um endereço).
SENSITIVE_TYPES = ("command", "launch", "webhook")

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
    encontradas: list[tuple[int, str]] = []
    for key in sorted(profile.bindings):
        action = profile.bindings[key]
        for alvo in _sensitive_targets(action.type, action.params):
            encontradas.append((key, alvo))
    return encontradas


def _sensitive_targets(tipo: Any, params: Any, profundidade: int = 0) -> list[str]:
    """Alvos sensíveis de uma ação, descendo pelos passos das macros.

    O arquivo vem de terceiros: qualquer campo pode ter o tipo errado.
    """
    if not isinstance(params, dict):
        return []
    if tipo in SENSITIVE_TYPES:
        alvo = (
            params.get("command") or params.get("target") or params.get("url") or ""
        )
        return [str(alvo)]
    if tipo != "macro" or profundidade > 5:
        return []
    passos = params.get("steps")
    if not isinstance(passos, list):
        return []
    alvos = []
    for i, passo in enumerate(passos, start=1):
        if not isinstance(passo, dict):
            continue
        for alvo in _sensitive_targets(
            passo.get("type"), passo.get("params", {}), profundidade + 1
        ):
            alvos.append(f"macro, passo {i}: {alvo}")
    return alvos


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


def from_json(texto: str | bytes) -> ImportedProfile:
    """Lê e valida um arquivo de perfil. Lança :class:`ProfileFileError`.

    Aceita texto ou bytes; um BOM no início (Bloco de Notas) é ignorado.
    """
    if isinstance(texto, bytes):
        try:
            texto = texto.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ProfileFileError("o arquivo não é um texto UTF-8") from exc
    texto = texto.removeprefix(chr(0xFEFF))
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
    nome = bruto.get("name")
    if not isinstance(nome, str) or not nome.strip():
        raise ProfileFileError("o perfil não tem um nome válido")
    # Id novo: importar duas vezes gera dois perfis.
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
    # Importação tardia: store importa este módulo.
    from .store import Store

    suffix = str(icone.get("suffix") or ".png").lower()
    if suffix not in Store.ICON_SUFFIXES:
        # Um ".exe" não pode ir parar na pasta de dados.
        return None, ".png"
    return bruto, suffix
