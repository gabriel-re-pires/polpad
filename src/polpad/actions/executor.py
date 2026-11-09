"""Execução assíncrona de ações em duas vias independentes.

``entrada`` (teclado e processos locais) mantém a ordem, pois disputa o foco;
``rede`` (webhook, HA, OBS) pode demorar e não deve atrasar as teclas. Macros
rodam inteiras na via de entrada. Filas limitadas: melhor descartar com aviso
do que disparar um lote acumulado depois.
"""

from __future__ import annotations

import contextlib
import logging
import queue
import threading
from collections.abc import Callable

from ..core.models import Action
from . import builtin  # noqa: F401 — registra os tipos embutidos
from .base import ActionContext, ActionError, get

log = logging.getLogger(__name__)


class ActionRunner:
    # Por via; passar disso significa que alguma ação está travada.
    QUEUE_MAX = 32
    JOIN_TIMEOUT_S = 3.0

    def __init__(
        self,
        context: ActionContext,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._context = context
        self._on_error = on_error or (lambda msg: None)
        self._stopping = threading.Event()
        self._queues: dict[bool, queue.Queue[Action | None]] = {}
        self._threads: list[threading.Thread] = []
        for remote in (False, True):
            work_queue: queue.Queue[Action | None] = queue.Queue(maxsize=self.QUEUE_MAX)
            thread = threading.Thread(
                target=self._run,
                args=(work_queue,),
                daemon=True,
                name="actions-rede" if remote else "actions-entrada",
            )
            self._queues[remote] = work_queue
            self._threads.append(thread)
            thread.start()

    def submit(self, action: Action) -> None:
        action_type = get(action.type)
        if action_type is None:
            self._on_error(f"Tipo de ação desconhecido: {action.type!r}")
            return
        try:
            self._queues[action_type.remote].put_nowait(action)
        except queue.Full:
            log.warning("fila cheia; ação %r descartada", action.type)
            self._on_error(
                f"Muitas ações pendentes — “{action_type.title}” foi descartada"
            )

    def stop(self) -> None:
        """Encerra as vias sem executar o que ficou pendente."""
        self._stopping.set()
        for work_queue in self._queues.values():
            _drain(work_queue)
            # Sentinela para acordar uma thread parada em get().
            with contextlib.suppress(queue.Full):
                work_queue.put_nowait(None)
        for thread in self._threads:
            thread.join(timeout=self.JOIN_TIMEOUT_S)

    def _run(self, work_queue: queue.Queue[Action | None]) -> None:
        while True:
            action = work_queue.get()
            if action is None or self._stopping.is_set():
                return
            self._execute(action)

    def _execute(self, action: Action) -> None:
        action_type = get(action.type)
        if action_type is None:
            self._on_error(f"Tipo de ação desconhecido: {action.type!r}")
            return
        try:
            action_type.handler(action.params, self._context)
        except ActionError as exc:
            self._on_error(f"{action_type.title}: {exc}")
        except Exception:
            log.exception("erro inesperado ao executar %s", action.type)
            self._on_error(f"Erro inesperado ao executar {action_type.title!r}")


def _drain(work_queue: queue.Queue[Action | None]) -> None:
    while True:
        try:
            work_queue.get_nowait()
        except queue.Empty:
            return
