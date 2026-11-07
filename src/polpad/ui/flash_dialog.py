"""Página de gravação do firmware no macropad.

Reúne em uma página só o que antes exigia a Arduino IDE: escolher a porta,
obter o binário (do release publicado ou de um arquivo local) e gravar,
acompanhando o progresso e o log.

O trabalho pesado roda em :class:`_FlashJob`, uma ``QThread`` — a interface
não pode congelar durante os ~20 s de gravação. Durante a gravação o
enlace serial do aplicativo fica pausado (o esptool precisa da porta com
acesso exclusivo) e a página não pode ser deixada: ver :meth:`FlashPage.leave`.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QWidget,
)

from ..app import MacropadApp
from ..device import firmware_release, flasher
from ..device.firmware_release import FirmwareRelease, ReleaseError
from ..device.flasher import FirmwareImage, FlashError
from ..device.link import available_ports
from . import glyphs, style
from .page import Page

log = logging.getLogger(__name__)


class _ReleaseQuery(QThread):
    """Consulta o release mais recente sem travar a interface."""

    ok = Signal(object)
    failed = Signal(str)

    def run(self) -> None:  # pragma: no cover - exercitada pela UI
        try:
            self.ok.emit(firmware_release.latest_release())
        except ReleaseError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            log.exception("falha inesperada ao consultar o release")
            self.failed.emit(f"Erro inesperado ao consultar o GitHub: {exc}")


class _FlashJob(QThread):
    """Baixa (se preciso) e grava o firmware."""

    log_line = Signal(str)
    progress = Signal(int)
    stage = Signal(str)
    ok = Signal()
    failed = Signal(str)

    def __init__(
        self,
        port: str,
        release: FirmwareRelease | None,
        local_path: Path | None,
        cancel: threading.Event,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._port = port
        self._release = release
        self._local_path = local_path
        self._cancel = cancel

    def run(self) -> None:  # pragma: no cover - exercitada pela UI
        try:
            image = self._resolve_image()
            if self._cancel.is_set():
                self.failed.emit("Gravação cancelada.")
                return
            self.stage.emit(
                f"Gravando em {self._port} (endereço 0x{image.offset:X})…"
            )
            self.progress.emit(0)
            flasher.flash(
                self._port,
                image,
                on_log=self.log_line.emit,
                on_progress=self.progress.emit,
                cancel=self._cancel,
            )
            self.ok.emit()
        except (FlashError, ReleaseError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            log.exception("falha inesperada ao gravar o firmware")
            self.failed.emit(f"Erro inesperado: {exc}")

    def _resolve_image(self) -> FirmwareImage:
        if self._release is not None:
            self.stage.emit(f"Baixando {self._release.asset_name}…")
            path = firmware_release.download(self._release, self.progress.emit)
            return FirmwareImage.from_path(path, self._release.version)
        if self._local_path is None:
            raise FlashError("Nenhum arquivo de firmware foi selecionado.")
        return FirmwareImage.from_path(self._local_path)


class FlashPage(Page):
    """Página "Gravar firmware".

    ``running_changed`` avisa a janela quando a gravação começa e termina,
    para ela travar a troca de porta enquanto o esptool usa a COM.
    """

    running_changed = Signal(bool)

    def __init__(
        self,
        core: MacropadApp,
        current_port: str | None = None,
        device_version: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Gravar firmware", parent)
        self._core = core
        self._device_version = device_version or ""
        self._release: FirmwareRelease | None = None
        self._job: _FlashJob | None = None
        self._query: _ReleaseQuery | None = None
        self._cancel = threading.Event()
        self._link_paused = False

        self._build_buttons()
        self.body.addWidget(self._build_device_box())
        self.body.addWidget(self._build_source_box())
        self.body.addWidget(self._build_progress())

        self._reload_ports(current_port)
        self._refresh_enabled()
        # Consultar já na abertura poupa um clique no caminho mais comum.
        self._check_release()

    # ------------------------------------------------------------- montagem

    def _build_device_box(self) -> QWidget:
        box, column = self.card(
            "Dispositivo",
            "Grava o firmware diretamente no ESP32-C3, sem precisar da "
            "Arduino IDE. Mantenha o macropad conectado pelo cabo USB do "
            "início ao fim — interromper no meio deixa o dispositivo sem "
            "firmware até uma nova gravação.",
        )
        row = QHBoxLayout()
        row.addWidget(QLabel("Porta:"))
        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(220)
        row.addWidget(self._port_combo, stretch=1)
        refresh = QPushButton("Atualizar")
        refresh.clicked.connect(lambda: self._reload_ports(None))
        row.addWidget(refresh)
        column.addLayout(row)
        installed = self._device_version or "não identificada"
        self._installed_label = QLabel(f"Versão no dispositivo: {installed}")
        self._installed_label.setObjectName("hint")
        column.addWidget(self._installed_label)
        return box

    def _build_source_box(self) -> QWidget:
        box, column = self.card("Firmware a gravar")

        self._source_group = QButtonGroup(self)
        self._release_radio = QRadioButton("Último release publicado no GitHub")
        self._release_radio.setChecked(True)
        self._file_radio = QRadioButton("Arquivo .bin no computador")
        self._source_group.addButton(self._release_radio)
        self._source_group.addButton(self._file_radio)
        self._release_radio.toggled.connect(self._refresh_enabled)

        release_row = QHBoxLayout()
        release_row.addWidget(self._release_radio)
        self._recheck = QPushButton("Verificar")
        self._recheck.clicked.connect(self._check_release)
        release_row.addWidget(self._recheck)
        release_row.addStretch(1)
        column.addLayout(release_row)

        self._release_label = QLabel("Consultando o GitHub…")
        self._release_label.setObjectName("hint")
        self._release_label.setWordWrap(True)
        self._release_label.setIndent(22)
        column.addWidget(self._release_label)

        file_row = QHBoxLayout()
        file_row.addWidget(self._file_radio)
        self._file_edit = QLineEdit()
        self._file_edit.setReadOnly(True)
        self._file_edit.setPlaceholderText(
            "Ex.: macropad_firmware.ino.bin exportado pela Arduino IDE"
        )
        file_row.addWidget(self._file_edit, stretch=1)
        browse = QPushButton("Procurar…")
        browse.clicked.connect(self._browse)
        file_row.addWidget(browse)
        column.addLayout(file_row)

        self._offset_label = QLabel("")
        self._offset_label.setObjectName("hint")
        self._offset_label.setIndent(22)
        self._offset_label.setWordWrap(True)
        column.addWidget(self._offset_label)
        return box

    def _build_progress(self) -> QWidget:
        box, column = self.card("Gravação")
        self._stage_label = QLabel("Pronto para gravar.")
        column.addWidget(self._stage_label)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        column.addWidget(self._progress)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        self._log.setMinimumHeight(150)
        mono = QFont("Consolas", 9)
        # Sem a Consolas (fora do Windows), cai na monoespaçada do sistema.
        mono.setStyleHint(QFont.Monospace)
        self._log.setFont(mono)
        column.addWidget(self._log)
        return box

    def _build_buttons(self) -> None:
        """Botões no cabeçalho, à direita, como o "Salvar" das Configurações."""
        self._cancel_button = QPushButton("Cancelar gravação")
        self._cancel_button.clicked.connect(self._request_cancel)
        self._cancel_button.setVisible(False)
        self.header.addWidget(self._cancel_button)
        self._flash_button = QPushButton("Gravar firmware")
        self._flash_button.setObjectName("primary")
        self._flash_button.setIcon(glyphs.icon("chip", style.ACCENT_TEXT))
        self._flash_button.clicked.connect(self._start)
        self.header.addWidget(self._flash_button)

    # ---------------------------------------------------------------- portas

    def _reload_ports(self, preselect: str | None) -> None:
        current = preselect or self._port_combo.currentData()
        self._port_combo.clear()
        for device, description in available_ports():
            self._port_combo.addItem(f"{device} — {description}", device)
        if self._port_combo.count() == 0:
            self._port_combo.addItem("Nenhuma porta encontrada", None)
        index = self._port_combo.findData(current)
        if index >= 0:
            self._port_combo.setCurrentIndex(index)
        self._refresh_enabled()

    # --------------------------------------------------------------- release

    def _check_release(self) -> None:
        if self._query is not None and self._query.isRunning():
            return
        self._release = None
        self._recheck.setEnabled(False)
        self._release_label.setText("Consultando o GitHub…")
        self._refresh_enabled()
        query = _ReleaseQuery(self)
        query.ok.connect(self._on_release_found)
        query.failed.connect(self._on_release_failed)
        query.finished.connect(lambda: self._recheck.setEnabled(True))
        self._query = query
        query.start()

    def _on_release_found(self, release: object) -> None:
        # O sinal trafega como ``object`` (QThread não tipa dataclasses).
        if not isinstance(release, FirmwareRelease):  # pragma: no cover - defensivo
            return
        self._release = release
        size = f"{release.size / 1024:.0f} KB" if release.size else "tamanho desconhecido"
        text = f"{release.tag} — {release.asset_name} ({size})"
        if self._device_version:
            if firmware_release.is_newer(release.version, self._device_version):
                text += (
                    f"  •  mais recente que a versão no dispositivo "
                    f"({self._device_version})."
                )
            elif release.version == self._device_version:
                text += "  •  já é a versão gravada no dispositivo."
            elif firmware_release.is_newer(self._device_version, release.version):
                # Gravar o release voltaria o aparelho a uma versão anterior —
                # foi assim que um firmware 2.0.0, com a pinagem antiga, foi
                # gravado por cima do 2.0.1 e embaralhou as teclas. O arquivo
                # local passa a ser a opção marcada.
                text += (
                    f"  •  MAIS ANTIGO que o firmware do dispositivo "
                    f"({self._device_version}); gravar voltaria a uma versão "
                    "anterior."
                )
                self._file_radio.setChecked(True)
        self._release_label.setText(text)
        self._refresh_enabled()

    def _on_release_failed(self, message: str) -> None:
        self._release = None
        self._release_label.setText(message.splitlines()[0])
        # Sem release utilizável, o arquivo local é o único caminho: mudar a
        # seleção evita que o usuário clique em "Gravar" e leve outro erro.
        self._file_radio.setChecked(True)
        self._refresh_enabled()

    # ----------------------------------------------------------- arquivo local

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar firmware",
            "",
            "Firmware do ESP32 (*.bin);;Todos os arquivos (*)",
        )
        if not path:
            return
        self._file_edit.setText(path)
        self._file_radio.setChecked(True)
        self._refresh_enabled()

    def _local_path(self) -> Path | None:
        text = self._file_edit.text().strip()
        return Path(text) if text else None

    # ---------------------------------------------------------------- estado

    def _refresh_enabled(self) -> None:
        running = self._job is not None and self._job.isRunning()
        using_release = self._release_radio.isChecked()
        port = self._port_combo.currentData()

        source_ready = (
            self._release is not None
            if using_release
            else self._local_path() is not None
        )
        self._flash_button.setEnabled(
            not running and source_ready and bool(port)
        )
        self._port_combo.setEnabled(not running)
        self._release_radio.setEnabled(not running)
        self._file_radio.setEnabled(not running)
        self.back_button.setEnabled(not running)

        path = self._local_path()
        if not using_release and path is not None:
            offset = flasher.guess_offset(path)
            if offset == flasher.APP_OFFSET:
                self._offset_label.setText(
                    "Detectado como exportação da Arduino IDE (só a aplicação): "
                    "será gravado em 0x10000, preservando o bootloader já "
                    "presente no chip."
                )
            else:
                self._offset_label.setText(
                    "Detectado como imagem completa: será gravada em 0x0."
                )
        else:
            self._offset_label.setText("")
        self._offset_label.setVisible(bool(self._offset_label.text()))

    # -------------------------------------------------------------- gravação

    def _start(self) -> None:
        port = self._port_combo.currentData()
        if not port:
            return
        if not self._confirm(port):
            return

        self._cancel.clear()
        self._log.clear()
        self._progress.setValue(0)
        self._link_paused = self._core.pause_link()

        job = _FlashJob(
            port=str(port),
            release=self._release if self._release_radio.isChecked() else None,
            local_path=None if self._release_radio.isChecked() else self._local_path(),
            cancel=self._cancel,
            parent=self,
        )
        job.log_line.connect(self._append_log)
        job.progress.connect(self._progress.setValue)
        job.stage.connect(self._stage_label.setText)
        job.ok.connect(self._on_success)
        job.failed.connect(self._on_failure)
        job.finished.connect(self._on_finished)
        self._job = job

        self._flash_button.setVisible(False)
        self._cancel_button.setVisible(True)
        self._set_running(True)
        job.start()

    def _confirm(self, port: str) -> bool:
        answer = QMessageBox.question(
            self,
            "Gravar firmware",
            f"O firmware atual do macropad em {port} será substituído.\n\n"
            "Não desconecte o cabo USB durante a gravação. Continuar?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        return answer == QMessageBox.Yes

    def _request_cancel(self) -> None:
        answer = QMessageBox.question(
            self,
            "Cancelar gravação",
            "Cancelar agora deixa a memória do macropad pela metade e o "
            "dispositivo não vai funcionar até uma nova gravação (que pode "
            "ser feita normalmente por esta página).\n\nCancelar mesmo assim?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._cancel.set()
        self._cancel_button.setEnabled(False)
        self._stage_label.setText("Cancelando…")

    def _append_log(self, line: str) -> None:
        self._log.appendPlainText(line)

    def _on_success(self) -> None:
        self._progress.setValue(100)
        self._stage_label.setText("Firmware gravado com sucesso.")
        version = self._release.version if self._release else ""
        detail = f" (versão {version})" if version else ""
        QMessageBox.information(
            self,
            "Gravar firmware",
            f"Firmware gravado com sucesso{detail}.\n\n"
            "O macropad reiniciou sozinho e deve reaparecer como conectado "
            "em alguns segundos.",
        )

    def _on_failure(self, message: str) -> None:
        self._stage_label.setText("A gravação falhou.")
        self._append_log(message)
        QMessageBox.critical(self, "Gravar firmware", message)

    def _on_finished(self) -> None:
        self._job = None
        self._flash_button.setVisible(True)
        self._cancel_button.setVisible(False)
        self._cancel_button.setEnabled(True)
        self._resume_link()
        self._set_running(False)

    def _set_running(self, running: bool) -> None:
        self._refresh_enabled()
        self.running_changed.emit(running)

    def _resume_link(self) -> None:
        if self._link_paused:
            self._link_paused = False
            self._core.resume_link()

    # ----------------------------------------------------------------- ciclo

    def leave(self) -> bool:
        """Chamado pela janela antes de sair da página.

        Recusa no meio da gravação — sair agora tijolaria o chip — e, fora
        dela, devolve a porta ao enlace do aplicativo.
        """
        if self._job is not None and self._job.isRunning():
            QMessageBox.warning(
                self,
                "Gravar firmware",
                "A gravação está em andamento. Aguarde o fim ou use "
                "Cancelar gravação.",
            )
            return False
        if self._query is not None and self._query.isRunning():
            self._query.wait(2000)
        self._resume_link()
        return True
