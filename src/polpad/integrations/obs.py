"""OBS Studio via obs-websocket v5 (embutido no OBS 28+, porta 4455).

A conexão é criada no primeiro uso, reutilizada e refeita se cair.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from ..actions.base import ActionError

log = logging.getLogger(__name__)

OPERATION_TITLES = {
    "scene": "Trocar cena",
    "toggle_mute": "Alternar mudo (microfone/fonte)",
    "toggle_record": "Iniciar/Parar gravação",
    "toggle_stream": "Iniciar/Parar transmissão",
    "raw": "Requisição avançada",
}

_lock = threading.Lock()
_client: Any = None
_client_key: tuple[str, int, str] | None = None


def _connect(host: str, port: int, password: str) -> Any:
    try:
        import obsws_python
    except ImportError as exc:  # pragma: no cover — dependência declarada
        raise ActionError("biblioteca obsws-python não instalada") from exc
    try:
        return obsws_python.ReqClient(
            host=host or "localhost", port=port or 4455, password=password, timeout=3
        )
    except Exception as exc:
        raise ActionError(
            f"não foi possível conectar ao OBS ({host}:{port}): {exc}"
        ) from exc


def _get_client(host: str, port: int, password: str) -> Any:
    global _client, _client_key
    key = (host, port, password)
    with _lock:
        if _client is None or _client_key != key:
            _client = _connect(host, port, password)
            _client_key = key
        return _client


def _reset_client() -> None:
    global _client
    with _lock:
        try:
            if _client is not None:
                _client.disconnect()
        except Exception:  # desconectar é best-effort
            log.debug("falha ao desconectar do OBS", exc_info=True)
        _client = None


def send(
    host: str,
    port: int,
    password: str,
    operation: str,
    params: dict[str, Any],
) -> None:
    request, data = _build_request(operation, params)
    client = _get_client(host, port, password)
    try:
        client.send(request, data or None)
    except Exception as exc:
        if not _connection_lost(exc):
            # Timeout ou recusa: reenviar executaria duas vezes (a gravação
            # liga e desliga).
            raise ActionError(f"OBS recusou {request}: {exc}") from exc
        # Conexão caiu (OBS reiniciado): tenta uma única vez de novo.
        _reset_client()
        client = _get_client(host, port, password)
        try:
            client.send(request, data or None)
        except Exception as exc:
            raise ActionError(f"OBS recusou {request}: {exc}") from exc


def _connection_lost(exc: Exception) -> bool:
    """O pedido falhou porque a conexão já tinha caído (dá para reenviar)?"""
    import json

    from websocket import WebSocketConnectionClosedException

    if isinstance(exc, TimeoutError):  # é OSError, mas o pedido pode ter saído
        return False
    # JSONDecodeError: ao sair, o OBS fecha e o recv devolve texto vazio.
    return isinstance(
        exc, (OSError, WebSocketConnectionClosedException, json.JSONDecodeError)
    )


def _build_request(operation: str, params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if operation == "scene":
        scene = params.get("scene", "").strip()
        if not scene:
            raise ActionError("informe o nome da cena")
        return "SetCurrentProgramScene", {"sceneName": scene}
    if operation == "toggle_mute":
        source = params.get("input", "").strip()
        if not source:
            raise ActionError("informe o nome da fonte de áudio (ex.: Mic/Aux)")
        return "ToggleInputMute", {"inputName": source}
    if operation == "toggle_record":
        return "ToggleRecord", {}
    if operation == "toggle_stream":
        return "ToggleStream", {}
    if operation == "raw":
        request = params.get("request", "").strip()
        if not request:
            raise ActionError("informe o tipo da requisição obs-websocket")
        return request, dict(params.get("data") or {})
    raise ActionError(f"operação OBS desconhecida: {operation!r}")


def check_connection(host: str, port: int, password: str) -> str:
    """Valida a conexão (botão Testar); retorna a versão do OBS."""
    _reset_client()
    client = _get_client(host, port, password)
    try:
        version = client.get_version()
        return f"OBS {version.obs_version} (WebSocket {version.obs_web_socket_version})"
    except Exception as exc:
        raise ActionError(f"conectou, mas falhou ao consultar a versão: {exc}") from exc
