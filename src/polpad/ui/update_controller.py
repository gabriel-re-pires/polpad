"""Coordena verificação, aviso, download, troca de versão e backups.

A lógica de decisão está em :mod:`polpad.update.policy`; aqui ficam os
efeitos: consultas fora da thread da interface, o aviso no canto da tela,
a página de versão e o encerramento do Polpad para a troca.

Rede, processos, relógio e o modo de rodar as tarefas são injetáveis, para
que os testes exercitem o fluxo inteiro sem tocar no GitHub nem abrir
programas.
"""

from __future__ import annotations

import logging
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import shiboken6
from PySide6.QtCore import QObject, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QWidget

from .. import APP_NAME, __version__
from ..core.store import Store
from ..update import backup, installer, linux_install, policy, releases
from ..update.state import Pending, Switch, UpdateState, state_path, updates_dir
from .update_toast import UpdateToast
from .version_dialog import VersionDialog, VersionView

log = logging.getLogger(__name__)

Runner = Callable[[Callable[[], Any], Callable[[Any], None], Callable[[str], None]], None]
Launcher = Callable[[list[str]], None]

#: Verificação periódica: confere a cada hora se já passaram 24 h.
TICK_MS = 60 * 60 * 1000
INSTALL_LOG = "instalacao.log"


# ---------------------------------------------------------------- troca


def apply_switch(
    data_dir: Path,
    current: str,
    target: str,
    package: Path,
    relaunch: bool,
    *,
    platform: str = sys.platform,
    executable: str = sys.executable,
    launcher: Launcher = installer.launch_detached,
    release_instance: Callable[[], None] | None = None,
    now: Callable[[], datetime] = datetime.now,
    expected_sha256: str | None = None,
) -> None:
    """Backup, marca de troca e a troca em si. Quem chama encerra o Polpad.

    ``expected_sha256`` é a soma conferida no download: o arquivo fica numa
    pasta gravável e pode ter mudado até a hora de instalar, então é
    conferido de novo antes de ser executado.
    """
    if expected_sha256 and installer.sha256_file(package) != expected_sha256:
        raise installer.InstallError(
            "O arquivo da atualização mudou depois do download. Baixe de novo."
        )
    backup.create(data_dir, current, target, now=now())
    path = state_path(data_dir)
    st = UpdateState.load(path)
    st.switch = Switch(current, target, now().isoformat())
    st.pending = None
    st.save(path)
    if platform == "win32":
        log_path = updates_dir(data_dir) / INSTALL_LOG
        launcher(installer.windows_command(package, log_path, relaunch))
        return
    installer.swap_linux(package, Path(executable))
    if relaunch:
        if release_instance is not None:
            release_instance()
        launcher([executable, "--apos-atualizacao"])


@dataclass(frozen=True)
class StartupResult:
    action: Literal["continue", "exit"]
    outcome: Literal["ok", "failed", "none"] = "none"
    version: str = ""


def startup(
    data_dir: Path,
    current: str,
    frozen: bool,
    *,
    platform: str = sys.platform,
    executable: str = sys.executable,
    launcher: Launcher = installer.launch_detached,
    release_instance: Callable[[], None] | None = None,
    now: Callable[[], datetime] = datetime.now,
) -> StartupResult:
    """Antes da janela: confere a troca anterior e instala a pendente."""
    path = state_path(data_dir)
    st = UpdateState.load(path)
    outcome = policy.switch_outcome(st.switch, current)
    version = st.switch.to_version if st.switch else ""
    if st.switch is not None:
        st.switch = None
        st.save(path)
        if outcome == "ok":
            _clean_downloads(data_dir)
            st = UpdateState.load(path)
    if not frozen:
        return StartupResult("continue", outcome, version)

    pending = st.pending
    exists = pending is not None and Path(pending.path).is_file()
    action = policy.pending_action(pending, current, exists)
    if action == "discard" and pending is not None:
        Path(pending.path).unlink(missing_ok=True)
        st.pending = None
        st.save(path)
    elif action == "install" and pending is not None:
        try:
            apply_switch(
                data_dir,
                current,
                pending.version,
                Path(pending.path),
                True,
                platform=platform,
                executable=executable,
                launcher=launcher,
                release_instance=release_instance,
                now=now,
                expected_sha256=pending.sha256,
            )
            return StartupResult("exit", outcome, version)
        except (installer.InstallError, OSError):
            log.exception("falha ao instalar a atualização pendente")
            _discard_pending(data_dir)
    return StartupResult("continue", outcome, version)


def _discard_pending(data_dir: Path) -> None:
    path = state_path(data_dir)
    st = UpdateState.load(path)
    if st.pending is not None:
        Path(st.pending.path).unlink(missing_ok=True)
        st.pending = None
        st.save(path)


def _clean_downloads(data_dir: Path) -> None:
    folder = updates_dir(data_dir)
    if not folder.is_dir():
        return
    for item in folder.iterdir():
        if item.name == state_path(data_dir).name:
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)


# ---------------------------------------------------------------- tarefas


class _Job(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], Any], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:  # pragma: no cover - exercitada pela interface
        try:
            self.done.emit(self._fn())
        except Exception as exc:
            if not isinstance(exc, installer.InstallError | releases.github.GitHubError):
                log.exception("falha inesperada no atualizador")
            self.failed.emit(str(exc))


class _Progress(QObject):
    """Leva o progresso do download da thread de trabalho para a interface."""

    changed = Signal(int)


# ---------------------------------------------------------------- controlador


class UpdateController(QObject):
    def __init__(
        self,
        store: Store,
        parent: QWidget,
        session: Any | None = None,
        now: Callable[[], datetime] = datetime.now,
        *,
        current: str = __version__,
        platform: str = sys.platform,
        executable: str = sys.executable,
        launcher: Launcher = installer.launch_detached,
        quit_app: Callable[[], None] | None = None,
        runner: Runner | None = None,
        release_instance: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.data_dir = store.data_dir
        self.current = current
        self.update: releases.AppRelease | None = None
        self.releases: list[releases.AppRelease] = []
        self.error = ""
        self.busy = ""
        self._parent = parent
        self._session = session
        self._now = now
        self._platform = platform
        self._executable = executable
        self._launcher = launcher
        self._quit = quit_app or QApplication.quit
        self._runner = runner or self._thread_runner
        self._release_instance = release_instance
        self._dismissed = False
        self._retry: releases.AppRelease | None = None
        self._jobs: set[_Job] = set()
        self._dialog: VersionDialog | None = None
        self._progress = _Progress()
        self._progress.changed.connect(self._on_progress)

        self.toast = UpdateToast()
        self.toast.update_clicked.connect(self._on_toast_update)
        self.toast.install_now_clicked.connect(self._install_pending_now)
        self.toast.details_clicked.connect(self.open_dialog)
        self.toast.retry_clicked.connect(self._on_retry)
        self.toast.dismissed.connect(self._on_dismissed)
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self.tick)

    # ------------------------------------------------------------ ciclo

    def start(self) -> None:
        QTimer.singleShot(policy.FIRST_CHECK_DELAY_MS, self.scheduled_check)
        self._timer.start()

    def tick(self) -> None:
        if policy.should_check(self._last_check(), self._now()):
            self.scheduled_check()

    def scheduled_check(self) -> None:
        """Verificação agendada: o X só esconde o aviso até aqui."""
        self._dismissed = False
        self.check_now(user=False)

    def show_startup_result(self, result: StartupResult) -> None:
        if result.outcome == "ok":
            self.toast.show_updated(result.version)
        elif result.outcome == "failed":
            self._retry = None
            self.toast.show_failed(
                result.version, updates_dir(self.data_dir) / INSTALL_LOG
            )

    def shutdown(self) -> None:
        """Apaga o aviso e a página antes do ``QApplication``.

        O aviso é uma janela sem dono: deixado para o encerramento do
        Python, ele seria destruído depois do ``QApplication`` e o processo
        cairia ao sair (access violation).
        """
        self._timer.stop()
        for widget in (self.toast, self._dialog):
            if widget is not None and shiboken6.isValid(widget):
                widget.close()
                shiboken6.delete(widget)
        self._dialog = None

    def before_quit(self) -> None:
        """Ao sair pela bandeja: instala a pendente sem reabrir."""
        st = UpdateState.load(state_path(self.data_dir))
        pending = st.pending
        exists = pending is not None and Path(pending.path).is_file()
        if (
            pending is None
            or policy.pending_action(pending, self.current, exists) != "install"
        ):
            return
        try:
            self._apply(
                pending.version, Path(pending.path), relaunch=False, sha256=pending.sha256
            )
        except (installer.InstallError, OSError):
            log.exception("falha ao instalar a atualização ao sair")
            _discard_pending(self.data_dir)

    # ------------------------------------------------------------ verificação

    def check_now(self, user: bool) -> None:
        if self.busy:
            return
        self.busy = "Verificando…" if user else ""
        self._refresh_dialog()

        def done(found: list[releases.AppRelease]) -> None:
            self.busy = ""
            self.error = ""
            self.releases = found
            self._save_last_check()
            self.update = policy.available_update(found, self.current)
            update = self.update
            if update is not None and self.store.settings.update_auto:
                self._download_pending(update)
            elif update is not None and policy.should_notify(
                update, self.store.settings.update_notify, self._dismissed
            ):
                self.toast.show_available(update.version, self.current)
            self._refresh_dialog()

        def failed(message: str) -> None:
            self.busy = ""
            log.info("verificação de atualização falhou: %s", message)
            if user:
                self.error = message
            self._refresh_dialog()

        self._runner(lambda: releases.list_releases(self._session), done, failed)

    # ------------------------------------------------------------ instalação

    def begin_update(self, release: releases.AppRelease) -> None:
        if self.busy:
            return
        self.busy = f"Baixando a versão {release.version}…"
        self._retry = release
        self.toast.show_available(release.version, self.current)
        self.toast.show_progress("Baixando… 0%")
        self._refresh_dialog()

        def done(result: tuple[Path, str]) -> None:
            self.toast.show_progress("Instalando…")
            try:
                self._apply(release.version, result[0], relaunch=True, sha256=result[1])
            except (installer.InstallError, OSError) as exc:
                failed(str(exc))
                return
            self._quit()

        def failed(message: str) -> None:
            self.busy = ""
            self.error = message
            self.toast.show_error(message)
            self._refresh_dialog()

        self._runner(
            lambda: installer.prepare(
                release, self.data_dir, self._progress.changed.emit, self._session
            ),
            done,
            failed,
        )

    def _download_pending(self, release: releases.AppRelease) -> None:
        def done(result: tuple[Path, str]) -> None:
            path = state_path(self.data_dir)
            st = UpdateState.load(path)
            st.pending = Pending(release.version, str(result[0]), result[1])
            st.save(path)
            if self.store.settings.update_notify:
                self.toast.show_pending(release.version)
            self._refresh_dialog()

        def failed(message: str) -> None:
            log.info("download automático falhou: %s", message)

        self._runner(
            lambda: installer.prepare(release, self.data_dir, None, self._session),
            done,
            failed,
        )

    def _install_pending_now(self) -> None:
        st = UpdateState.load(state_path(self.data_dir))
        pending = st.pending
        if pending is None:
            return
        try:
            self._apply(
                pending.version, Path(pending.path), relaunch=True, sha256=pending.sha256
            )
        except (installer.InstallError, OSError) as exc:
            _discard_pending(self.data_dir)
            self.toast.show_error(str(exc))
            return
        self._quit()

    def _apply(
        self, target: str, package: Path, relaunch: bool, sha256: str | None
    ) -> None:
        apply_switch(
            self.data_dir,
            self.current,
            target,
            package,
            relaunch,
            platform=self._platform,
            executable=self._executable,
            launcher=self._launcher,
            release_instance=self._release_instance,
            now=self._now,
            expected_sha256=sha256,
        )

    # ------------------------------------------------------------ opções

    def set_notify(self, enabled: bool) -> None:
        self.store.settings.update_notify = enabled
        self.store.save()
        if not enabled:
            self.toast.hide()

    def set_auto(self, enabled: bool) -> None:
        self.store.settings.update_auto = enabled
        self.store.save()
        if enabled and self.update is not None:
            self._download_pending(self.update)

    # ------------------------------------------------------------ página

    def open_dialog(self) -> None:
        if self._dialog is None:
            dialog = VersionDialog(self._parent)
            dialog.check_requested.connect(lambda: self.check_now(user=True))
            dialog.update_requested.connect(self.begin_update)
            dialog.install_requested.connect(self.begin_update)
            dialog.restore_requested.connect(self._restore)
            dialog.open_backups_requested.connect(self._open_backups)
            dialog.notify_changed.connect(self.set_notify)
            dialog.auto_changed.connect(self.set_auto)
            dialog.linux_install_requested.connect(self._linux_install)
            dialog.linux_uninstall_requested.connect(self._linux_uninstall)
            self._dialog = dialog
        self._refresh_dialog()
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()
        if not self.releases and not self.busy:
            self.check_now(user=True)

    def view(self) -> VersionView:
        last = self._last_check()
        return VersionView(
            current=self.current,
            kind=installer.install_kind(),
            last_check=last,
            update=self.update,
            releases=self.releases,
            backups=backup.list_backups(self.data_dir),
            notify=self.store.settings.update_notify,
            auto=self.store.settings.update_auto,
            error=self.error,
            busy=self.busy,
        )

    def _refresh_dialog(self) -> None:
        if self._dialog is not None:
            self._dialog.set_view(self.view())

    def _restore(self, item: backup.Backup) -> None:
        backup.restore(self.data_dir, item, self.current, now=self._now())
        self._restart([])

    def _open_backups(self) -> None:
        folder = backup.backups_dir(self.data_dir)
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _linux_install(self) -> None:
        linux_install.install(Path(self._executable))
        self.store.settings.linux_install_prompt = False
        self.store.save()
        self._restart([], executable=str(linux_install.binary_path()))

    def _linux_uninstall(self) -> None:
        linux_install.uninstall()
        QMessageBox.information(
            self._parent,
            APP_NAME,
            "O Polpad saiu do menu de aplicativos. Este executável continua "
            "funcionando de onde está.",
        )
        self._refresh_dialog()

    def _restart(self, args: list[str], executable: str | None = None) -> None:
        program = executable or self._executable
        argv = [program, *args]
        if not getattr(sys, "frozen", False) and executable is None:
            argv = [program, "-m", "polpad", *args]
        if self._release_instance is not None:
            self._release_instance()
        self._launcher([*argv, "--apos-atualizacao"])
        self._quit()

    # ------------------------------------------------------------ Linux

    def maybe_offer_linux_install(self) -> None:
        """Pergunta uma vez se o executável avulso deve ir para o menu."""
        if not (
            self._platform.startswith("linux")
            and getattr(sys, "frozen", False)
            and self.store.settings.linux_install_prompt
            and not linux_install.running_from_menu()
        ):
            return
        box = QMessageBox(self._parent)
        box.setWindowTitle(APP_NAME)
        box.setText("Instalar o Polpad no menu de aplicativos?")
        install: QPushButton = box.addButton("Instalar", QMessageBox.AcceptRole)
        box.addButton("Agora não", QMessageBox.RejectRole)
        never: QPushButton = box.addButton(
            "Não perguntar de novo", QMessageBox.DestructiveRole
        )
        box.exec()
        if box.clickedButton() is install:
            self._linux_install()
        elif box.clickedButton() is never:
            self.store.settings.linux_install_prompt = False
            self.store.save()

    # ------------------------------------------------------------ interno

    def _on_toast_update(self) -> None:
        if self.update is not None:
            self.begin_update(self.update)

    def _on_retry(self) -> None:
        if self._retry is not None:
            self.begin_update(self._retry)
        else:
            self.check_now(user=True)

    def _on_dismissed(self) -> None:
        self._dismissed = True

    def _on_progress(self, percent: int) -> None:
        self.toast.show_progress(f"Baixando… {percent}%")

    def _last_check(self) -> datetime | None:
        raw = UpdateState.load(state_path(self.data_dir)).last_check
        try:
            return datetime.fromisoformat(raw) if raw else None
        except ValueError:
            return None

    def _save_last_check(self) -> None:
        path = state_path(self.data_dir)
        st = UpdateState.load(path)
        st.last_check = self._now().isoformat()
        st.save(path)

    def _thread_runner(
        self,
        fn: Callable[[], Any],
        on_done: Callable[[Any], None],
        on_fail: Callable[[str], None],
    ) -> None:  # pragma: no cover - exercitada pela interface
        job = _Job(fn, self)
        job.done.connect(on_done)
        job.failed.connect(on_fail)
        job.finished.connect(lambda: self._jobs.discard(job))
        self._jobs.add(job)
        job.start()
