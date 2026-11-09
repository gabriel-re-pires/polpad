"""Protocolo host <-> macropad: JSON Lines sobre USB CDC a 115200 bps.

Contrato completo em ``docs/PROTOCOLO.md``.

Dispositivo -> Host:
    {"t": "hello", "fw": "1.0.0", "keys": 18, "screen": {"w": 128, "h": 64}}
    {"t": "key", "k": 0..17, "e": "down" | "up"}
    {"t": "pong"}

Host -> Dispositivo:
    {"t": "ping"}
    {"t": "text", "lines": ["Perfil", "VS Code"]}
    {"t": "img", "fmt": "xbm1", "d": "<base64 de 1024 bytes>"}
"""

from __future__ import annotations

import json
import unicodedata
from typing import Any

BAUD_RATE = 115200
ENCODING = "utf-8"

# VID USB da Espressif, para priorizar portas na detecção.
ESPRESSIF_VID = 0x303A


def encode(message: dict[str, Any]) -> bytes:
    """Serializa uma mensagem para o fio (JSON compacto + newline)."""
    return (json.dumps(message, separators=(",", ":")) + "\n").encode(ENCODING)


def decode(line: bytes | str) -> dict[str, Any] | None:
    """Desserializa uma linha; None se inválida (o boot do ESP32 imprime texto)."""
    if isinstance(line, bytes):
        try:
            line = line.decode(ENCODING, errors="replace")
        except Exception:
            return None
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "t" not in data:
        return None
    return data


def msg_ping() -> dict[str, Any]:
    return {"t": "ping"}


def msg_text(lines: list[str]) -> dict[str, Any]:
    """Até 3 linhas no display, em ASCII: a fonte Adafruit GFX não tem acentos."""
    return {"t": "text", "lines": [_ascii(ln) for ln in lines[:3]]}


def _ascii(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return decomposed.encode("ascii", "ignore").decode("ascii")


def msg_image(payload_b64: str) -> dict[str, Any]:
    """Exibe uma imagem 128x64 1 bpp (ver ``core.icons.icon_payload``)."""
    return {"t": "img", "fmt": "xbm1", "d": payload_b64}
