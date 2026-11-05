"""Tipos de ação embutidos.

Cada função registrada aqui é um "executor" (ver ``actions.base``).
Executam na thread de ações do :class:`~polpad.actions.executor.ActionRunner`,
nunca na thread da interface.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

from pynput.keyboard import Controller

from ..integrations import home_assistant
from . import keys
from .base import ActionContext, ActionError, register

_keyboard = Controller()


@register(
    "hotkey",
    "Atalho de teclado",
    "Pressiona uma combinação de teclas (ex.: Ctrl+Shift+P).",
)
def run_hotkey(params: dict[str, Any], ctx: ActionContext) -> None:
    names: list[str] = params.get("keys", [])
    if not names:
        raise ActionError("nenhuma tecla configurada")
    try:
        resolved = [keys.resolve(n) for n in names]
    except ValueError as exc:
        raise ActionError(str(exc)) from exc
    # strict=True: resolved vem de names, então têm o mesmo comprimento.
    pares = list(zip(resolved, names, strict=True))
    modifiers = [k for k, n in pares if n.lower() in keys.MODIFIERS]
    others = [k for k, n in pares if n.lower() not in keys.MODIFIERS]
    for mod in modifiers:
        _keyboard.press(mod)
    try:
        for key in others:
            _keyboard.press(key)
            _keyboard.release(key)
    finally:
        for mod in reversed(modifiers):
            _keyboard.release(mod)


@register(
    "text",
    "Digitar texto",
    "Digita um texto na janela em foco; opcionalmente pressiona Enter ao final. "
    "Ex.: enviar \"npm run dev\" ao terminal do VS Code.",
)
def run_text(params: dict[str, Any], ctx: ActionContext) -> None:
    text = params.get("text", "")
    if not text:
        raise ActionError("nenhum texto configurado")
    _keyboard.type(text)
    if params.get("enter", False):
        from pynput.keyboard import Key

        _keyboard.press(Key.enter)
        _keyboard.release(Key.enter)


@register(
    "command",
    "Executar comando",
    "Executa um comando de shell em segundo plano ou em um novo terminal.",
)
def run_command(params: dict[str, Any], ctx: ActionContext) -> None:
    command = params.get("command", "").strip()
    if not command:
        raise ActionError("nenhum comando configurado")
    cwd = params.get("cwd") or None
    visible = params.get("visible", False)
    creationflags = 0
    if sys.platform == "win32":
        creationflags = (
            subprocess.CREATE_NEW_CONSOLE if visible else subprocess.CREATE_NO_WINDOW
        )
        if visible:
            # /k mantém o terminal aberto para o usuário ver a saída.
            #
            # Não use /s aqui: sem ele o cmd preserva as aspas do invólucro
            # quando o conteúdo é um executável com espaço no caminho, o que
            # faz um comando como C:\Program Files\app.exe (digitado sem
            # aspas) funcionar. Com /s o cmd sempre remove a primeira e a
            # última aspa e esse caso passa a falhar — verificado.
            command = f'cmd /k "{command}"'
    elif visible:
        argv = _terminal_argv(command, cwd)
        if argv is None:
            raise ActionError(
                "nenhum emulador de terminal encontrado; instale um (ex.: xterm) "
                "ou desmarque 'Abrir em um terminal visível'"
            )
        try:
            # Mesmo caso do shell=True abaixo: o comando é do próprio usuário.
            subprocess.Popen(argv, cwd=cwd, start_new_session=True)  # noqa: S603
        except OSError as exc:
            raise ActionError(f"falha ao executar comando: {exc}") from exc
        return
    try:
        # shell=True é intencional: o comando é escrito pelo próprio usuário
        # na sua máquina (equivalente a digitá-lo no terminal) e pode conter
        # pipes/&&; não há entrada de terceiros aqui. Perfis importados de
        # fontes externas devem ser revisados (ver docs/ARQUITETURA.md).
        #
        # start_new_session (ignorado no Windows): o comando não morre junto
        # com o aplicativo nem recebe o Ctrl+C do terminal que o abriu.
        subprocess.Popen(  # noqa: S602 — shell=True intencional, ver acima
            command,
            shell=True,
            cwd=cwd,
            creationflags=creationflags,
            start_new_session=True,
        )
    except OSError as exc:
        raise ActionError(f"falha ao executar comando: {exc}") from exc


# Emuladores de terminal conhecidos e o argumento que precede o programa a
# executar dentro deles. O primeiro encontrado no PATH é usado.
_TERMINALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("x-terminal-emulator", ("-e",)),
    ("xfce4-terminal", ("-x",)),
    ("gnome-terminal", ("--",)),
    ("konsole", ("-e",)),
    ("kitty", ()),
    ("alacritty", ("-e",)),
    ("foot", ()),
    ("xterm", ("-e",)),
)


def _terminal_argv(command: str, cwd: str | None = None) -> list[str] | None:
    """Abre ``command`` num terminal que continua aberto ao final (Linux).

    Equivale ao ``cmd /k`` do Windows: depois do comando o terminal segue
    num shell interativo, para o usuário ver a saída. O ``cd`` explícito
    existe porque alguns terminais (xfce4-terminal, gnome-terminal) reusam
    uma instância já aberta, que não herda a pasta deste processo.
    """
    shell = os.environ.get("SHELL") or "/bin/sh"
    script = f"{command}\nexec {shlex.quote(shell)}"
    if cwd:
        script = f"cd {shlex.quote(cwd)} || exit 1\n{script}"
    for terminal, flags in _TERMINALS:
        path = shutil.which(terminal)
        if path:
            return [path, *flags, shell, "-c", script]
    return None


@register(
    "launch",
    "Abrir aplicativo/arquivo/site",
    "Abre um programa, arquivo, pasta ou URL com o aplicativo padrão.",
)
def run_launch(params: dict[str, Any], ctx: ActionContext) -> None:
    target = params.get("target", "").strip()
    if not target:
        raise ActionError("nenhum alvo configurado")
    if target.startswith(("http://", "https://")):
        webbrowser.open(target)
        return
    if sys.platform == "win32":
        try:
            os.startfile(target)  # noqa: S606 — abertura intencional pelo usuário
            return
        except OSError as exc:
            raise ActionError(f"falha ao abrir {target!r}: {exc}") from exc
    argv = _launch_argv(target)
    try:
        # O alvo foi escolhido pelo usuário (seletor de arquivos ou digitado).
        subprocess.Popen(argv, start_new_session=True)  # noqa: S603
    except OSError as exc:
        raise ActionError(f"falha ao abrir {target!r}: {exc}") from exc


def _launch_argv(target: str) -> list[str]:
    """Como abrir ``target`` fora do Windows, à semelhança do ``os.startfile``.

    Aceita um caminho (programa, atalho ``.desktop``, arquivo ou pasta) ou o
    nome de um programa do PATH com argumentos, como ``code ~/projeto`` —
    o equivalente a apontar para o ``.exe`` no Windows.
    """
    path = Path(target).expanduser()
    if path.exists():
        if path.suffix == ".desktop" and shutil.which("gio"):
            return ["gio", "launch", str(path)]
        if path.is_file() and _is_program(path):
            return [str(path)]
        # "xdg-open" abre com o aplicativo padrão do sistema.
        return ["xdg-open", str(path)]
    try:
        argv = shlex.split(target)
    except ValueError:
        argv = []
    if argv and shutil.which(argv[0]):
        return [argv[0], *(os.path.expanduser(arg) for arg in argv[1:])]
    raise ActionError(f"alvo não encontrado: {target!r}")


def _is_program(path: Path) -> bool:
    """Programa de verdade (ELF ou script com ``#!``), não só um arquivo com +x.

    Partições NTFS e FAT montadas costumam marcar todo arquivo como
    executável; um PDF ali deve abrir no leitor, não ser executado.
    """
    if not os.access(path, os.X_OK):
        return False
    try:
        with path.open("rb") as fh:
            head = fh.read(4)
    except OSError:
        return False
    return head == b"\x7fELF" or head.startswith(b"#!")


@register(
    "media",
    "Controle de mídia",
    "Volume, mudo e controles de reprodução (tocar/pausar, próxima faixa...).",
)
def run_media(params: dict[str, Any], ctx: ActionContext) -> None:
    control = params.get("control", "")
    key = keys.media_key(control)
    if key is None:
        raise ActionError(f"controle de mídia desconhecido: {control!r}")
    _keyboard.press(key)
    _keyboard.release(key)


@register(
    "macro",
    "Macro (sequência)",
    "Executa uma sequência de ações com um intervalo entre elas.",
)
def run_macro(params: dict[str, Any], ctx: ActionContext) -> None:
    from .base import get

    steps: list[dict[str, Any]] = params.get("steps", [])
    delay_ms = int(params.get("delay_ms", 100))
    if not steps:
        raise ActionError("macro vazia")
    for i, step in enumerate(steps):
        action_type = get(step.get("type", ""))
        if action_type is None:
            raise ActionError(f"passo {i + 1}: tipo desconhecido {step.get('type')!r}")
        if step.get("type") == "macro":
            raise ActionError("macros não podem conter outras macros")
        action_type.handler(step.get("params", {}), ctx)
        if i < len(steps) - 1:
            time.sleep(delay_ms / 1000)


@register(
    "home_assistant",
    "Home Assistant",
    "Chama um serviço do Home Assistant (ex.: apagar as luzes da sala). "
    "Configure a URL e o token em Configurações.",
    remote=True,
)
def run_home_assistant(params: dict[str, Any], ctx: ActionContext) -> None:
    settings = ctx.settings
    if settings is None or not settings.ha_url or not settings.ha_token:
        raise ActionError(
            "Home Assistant não configurado (URL e token em Configurações)"
        )
    home_assistant.call_service(
        base_url=settings.ha_url,
        token=settings.ha_token,
        domain=params.get("domain", ""),
        service=params.get("service", ""),
        entity_id=params.get("entity_id", ""),
        data=params.get("data") or {},
    )


@register(
    "obs",
    "OBS Studio",
    "Controla o OBS via WebSocket: trocar cena, mudo, gravação, transmissão. "
    "Configure host/porta/senha em Configurações.",
    remote=True,
)
def run_obs(params: dict[str, Any], ctx: ActionContext) -> None:
    from ..integrations import obs

    settings = ctx.settings
    if settings is None:
        raise ActionError("configurações indisponíveis")
    obs.send(
        host=settings.obs_host,
        port=settings.obs_port,
        password=settings.obs_password,
        operation=params.get("operation", ""),
        params=params,
    )


@register(
    "webhook",
    "Webhook (HTTP)",
    "Chama uma URL (GET ou POST com JSON) — integra com n8n, IFTTT, "
    "Zapier ou qualquer serviço com webhooks.",
    remote=True,
)
def run_webhook(params: dict[str, Any], ctx: ActionContext) -> None:
    import requests

    url = params.get("url", "").strip()
    if not url.startswith(("http://", "https://")):
        raise ActionError("informe uma URL http(s) válida")
    method = params.get("method", "POST").upper()
    body = params.get("body") or None
    try:
        response = requests.request(method, url, json=body, timeout=5)
    except requests.RequestException as exc:
        raise ActionError(f"webhook falhou: {exc}") from exc
    if not response.ok:
        raise ActionError(f"webhook retornou {response.status_code}")


@register(
    "mode_switch",
    "Alternar perfil",
    "Faz desta tecla a tecla de modo: em qualquer perfil ela passa para o "
    "próximo da lista e, depois do último, volta ao primeiro.",
)
def run_mode_switch(params: dict[str, Any], ctx: ActionContext) -> None:
    if ctx.request_mode_switch is None:
        raise ActionError("troca de perfil indisponível neste contexto")
    ctx.request_mode_switch()
