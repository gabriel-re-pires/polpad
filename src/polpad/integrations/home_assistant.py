"""Integração com o Home Assistant via API REST.

O Home Assistant expõe uma API REST local autenticada por token de longa
duração (Perfil do usuário -> Segurança -> Tokens de acesso de longa
duração). Chamar um serviço é um simples POST:

    POST {base_url}/api/services/{domain}/{service}
    Authorization: Bearer <token>
    {"entity_id": "light.sala"}

Isso permite associar teclas do macropad a qualquer automação da casa
(luzes, tomadas, cenas, scripts...).
"""

from __future__ import annotations

from typing import Any

import requests

from ..actions.base import ActionError

TIMEOUT_S = 5.0


def call_service(
    base_url: str,
    token: str,
    domain: str,
    service: str,
    entity_id: str = "",
    data: dict[str, Any] | None = None,
) -> None:
    if not domain or not service:
        raise ActionError("serviço do Home Assistant não configurado")
    payload: dict[str, Any] = dict(data or {})
    if entity_id:
        payload["entity_id"] = entity_id
    url = f"{base_url.rstrip('/')}/api/services/{domain}/{service}"
    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise ActionError(f"Home Assistant inacessível: {exc}") from exc
    if response.status_code == 401:
        raise ActionError("Home Assistant recusou o token (401)")
    if not response.ok:
        raise ActionError(f"Home Assistant retornou {response.status_code}")


def check_connection(base_url: str, token: str) -> str:
    """Valida URL/token; retorna a mensagem da API (usado no botão Testar)."""
    url = f"{base_url.rstrip('/')}/api/"
    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise ActionError(f"não foi possível conectar: {exc}") from exc
    if response.status_code == 401:
        raise ActionError("token inválido (401)")
    if not response.ok:
        raise ActionError(f"resposta inesperada: {response.status_code}")
    return response.json().get("message", "OK")
