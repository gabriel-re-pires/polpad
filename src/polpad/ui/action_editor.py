"""Diálogo de configuração da ação de uma tecla.

Apresenta um formulário específico para cada tipo de ação registrado.
O botão "Testar" executa a ação após 3 segundos, dando tempo de levar
o foco à janela alvo (ex.: o terminal do VS Code).
"""

from __future__ import annotations

import json
import sys
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..actions import keys
from ..actions.base import all_types
from ..actions.executor import ActionRunner
from ..core.models import Action
from .hotkey_capture import HotkeyCapture

if sys.platform == "win32":
    _COMMAND_EXAMPLE = "code C:\\meu\\projeto"
    _LAUNCH_EXAMPLE = "C:\\...\\app.exe, uma pasta ou https://..."
else:
    _COMMAND_EXAMPLE = "code ~/meu/projeto"
    _LAUNCH_EXAMPLE = "firefox, /caminho/do/app, uma pasta ou https://..."

# Tipos ocultos em contexto de macro (passos não podem conter macros/loops).
_MACRO_EXCLUDED = {"macro", "mode_switch"}


class ActionEditorDialog(QDialog):
    # Espera do botão "Testar", para o usuário levar o foco à janela alvo.
    _TEST_DELAY_MS = 3000

    def __init__(
        self,
        parent: QWidget | None,
        key_index: int,
        action: Action | None,
        runner: ActionRunner | None = None,
        allow_macro: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            f"Tecla {key_index + 1} — configurar ação"
            if key_index >= 0
            else "Passo da macro"
        )
        self.setMinimumWidth(520)
        self._runner = runner
        self.result_action: Action | None = None
        self.remove_requested = False

        self._types = [
            t
            for t in all_types()
            if allow_macro or t.name not in _MACRO_EXCLUDED
        ]

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._type_combo = QComboBox()
        for t in self._types:
            self._type_combo.addItem(t.title, t.name)
        form.addRow("Tipo de ação:", self._type_combo)
        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("Nome curto exibido na tecla (opcional)")
        form.addRow("Rótulo:", self._label_edit)
        # A abreviação ia para o mapa de teclas do display, que saiu do
        # aparelho. Ela não é mais editável, mas é preservada ao salvar.
        self._kept_short = action.short if action is not None else ""
        layout.addLayout(form)

        self._description = QLabel()
        self._description.setWordWrap(True)
        self._description.setObjectName("hint")
        layout.addWidget(self._description)

        self._stack = QStackedWidget()
        self._pages: dict[str, QWidget] = {}
        for t in self._types:
            page = self._build_page(t.name)
            self._pages[t.name] = page
            self._stack.addWidget(page)
        layout.addWidget(self._stack)

        self._status = QLabel("")
        self._status.setObjectName("hint")
        layout.addWidget(self._status)

        buttons = QDialogButtonBox()
        self._test_button = buttons.addButton(
            "Testar (3 s)", QDialogButtonBox.ActionRole
        )
        self._remove_button = buttons.addButton(
            "Remover ação", QDialogButtonBox.DestructiveRole
        )
        self._remove_button.setObjectName("danger")
        ok = buttons.addButton(QDialogButtonBox.Ok)
        ok.setText("Salvar")
        ok.setObjectName("primary")
        cancel = buttons.addButton(QDialogButtonBox.Cancel)
        # Dentro da página do editor (ActionEditorPage), Salvar e Voltar
        # ficam no cabeçalho da página; estes dois são escondidos lá.
        self.dialog_buttons = (ok, cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        self._test_button.clicked.connect(self._test)
        self._remove_button.clicked.connect(self._remove)
        if runner is None:
            self._test_button.hide()
        if action is None:
            self._remove_button.hide()
        layout.addWidget(buttons)

        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        self._on_type_changed()

        if action is not None:
            self._load(action)

    # ------------------------------------------------------------- páginas

    def _build_page(self, name: str) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        if name == "hotkey":
            page.capture = HotkeyCapture()
            page.capture.changed.connect(self._on_hotkey_captured)
            form.addRow("Combinação:", page.capture)
            hint = QLabel(
                "Clique no campo e aperte a combinação no seu teclado, como "
                "Ctrl+C. Esc cancela. Teclas como F13–F20 ficam em «Mais teclas»."
            )
            hint.setWordWrap(True)
            hint.setObjectName("hint")
            form.addRow(hint)
        elif name == "text":
            page.text_edit = QPlainTextEdit()
            page.text_edit.setPlaceholderText("npm run dev")
            page.text_edit.setFixedHeight(80)
            form.addRow("Texto:", page.text_edit)
            page.enter_check = QCheckBox("Pressionar Enter ao final")
            page.enter_check.setChecked(True)
            form.addRow(page.enter_check)
        elif name == "command":
            page.command_edit = QLineEdit()
            page.command_edit.setPlaceholderText(_COMMAND_EXAMPLE)
            form.addRow("Comando:", page.command_edit)
            cwd_row = QHBoxLayout()
            page.cwd_edit = QLineEdit()
            page.cwd_edit.setPlaceholderText("Pasta de trabalho (opcional)")
            browse = QPushButton("…")
            browse.setFixedWidth(32)
            browse.clicked.connect(lambda: self._pick_dir(page.cwd_edit))
            cwd_row.addWidget(page.cwd_edit)
            cwd_row.addWidget(browse)
            form.addRow("Pasta:", cwd_row)
            page.visible_check = QCheckBox("Abrir em um terminal visível")
            form.addRow(page.visible_check)
        elif name == "launch":
            row = QHBoxLayout()
            page.target_edit = QLineEdit()
            page.target_edit.setPlaceholderText(_LAUNCH_EXAMPLE)
            browse = QPushButton("…")
            browse.setFixedWidth(32)
            browse.clicked.connect(lambda: self._pick_file(page.target_edit))
            row.addWidget(page.target_edit)
            row.addWidget(browse)
            form.addRow("Alvo:", row)
        elif name == "media":
            page.control_combo = QComboBox()
            for value, title in keys.MEDIA_TITLES.items():
                page.control_combo.addItem(title, value)
            form.addRow("Controle:", page.control_combo)
        elif name == "macro":
            page.steps = []  # list[dict[str, Any]] — anexado dinamicamente
            page.steps_list = QListWidget()
            form.addRow("Passos:", page.steps_list)
            buttons_row = QHBoxLayout()
            for text, slot in (
                ("Adicionar", lambda: self._macro_add(page)),
                ("Editar", lambda: self._macro_edit(page)),
                ("Remover", lambda: self._macro_remove(page)),
                ("▲", lambda: self._macro_move(page, -1)),
                ("▼", lambda: self._macro_move(page, +1)),
            ):
                b = QPushButton(text)
                b.clicked.connect(slot)
                buttons_row.addWidget(b)
            form.addRow(buttons_row)
            page.delay_edit = QLineEdit("100")
            form.addRow("Intervalo entre passos (ms):", page.delay_edit)
        elif name == "home_assistant":
            page.domain_edit = QLineEdit()
            page.domain_edit.setPlaceholderText("light")
            form.addRow("Domínio:", page.domain_edit)
            page.service_edit = QLineEdit()
            page.service_edit.setPlaceholderText("turn_off")
            form.addRow("Serviço:", page.service_edit)
            page.entity_edit = QLineEdit()
            page.entity_edit.setPlaceholderText("light.sala")
            form.addRow("Entidade:", page.entity_edit)
            page.data_edit = QLineEdit()
            page.data_edit.setPlaceholderText('{"brightness": 128} (opcional)')
            form.addRow("Dados JSON:", page.data_edit)
        elif name == "obs":
            from ..integrations.obs import OPERATION_TITLES

            page.operation_combo = QComboBox()
            for value, title in OPERATION_TITLES.items():
                page.operation_combo.addItem(title, value)
            form.addRow("Operação:", page.operation_combo)
            page.scene_edit = QLineEdit()
            page.scene_edit.setPlaceholderText("Nome exato da cena no OBS")
            form.addRow("Cena:", page.scene_edit)
            page.input_edit = QLineEdit()
            page.input_edit.setPlaceholderText("Ex.: Mic/Aux")
            form.addRow("Fonte de áudio:", page.input_edit)
            page.request_edit = QLineEdit()
            page.request_edit.setPlaceholderText("Ex.: SetSceneItemEnabled")
            form.addRow("Requisição:", page.request_edit)
            page.request_data_edit = QLineEdit()
            page.request_data_edit.setPlaceholderText('{"sceneName": "..."} (JSON)')
            form.addRow("Dados:", page.request_data_edit)

            def refresh_obs_fields() -> None:
                op = page.operation_combo.currentData()
                page.scene_edit.setEnabled(op == "scene")
                page.input_edit.setEnabled(op == "toggle_mute")
                page.request_edit.setEnabled(op == "raw")
                page.request_data_edit.setEnabled(op == "raw")

            page.operation_combo.currentIndexChanged.connect(refresh_obs_fields)
            refresh_obs_fields()
        elif name == "webhook":
            page.url_edit = QLineEdit()
            page.url_edit.setPlaceholderText("https://exemplo.com/webhook/abc123")
            form.addRow("URL:", page.url_edit)
            page.method_combo = QComboBox()
            page.method_combo.addItems(["POST", "GET"])
            form.addRow("Método:", page.method_combo)
            page.body_edit = QLineEdit()
            page.body_edit.setPlaceholderText('{"evento": "tecla"} (JSON, opcional)')
            form.addRow("Corpo JSON:", page.body_edit)
        elif name == "mode_switch":
            info = QLabel("Ao pressionar a tecla, o macropad muda para o próximo perfil.")
            info.setWordWrap(True)
            form.addRow(info)
        return page

    def _on_hotkey_captured(self, names: list[str]) -> None:
        """Sugere a combinação como rótulo, se o usuário não escreveu um."""
        self._label_edit.setPlaceholderText(
            keys.pretty(names) or "Nome curto exibido na tecla (opcional)"
        )

    # --------------------------------------------------------------- macro

    def _macro_add(self, page: QWidget) -> None:
        dialog = ActionEditorDialog(self, -1, None, runner=None, allow_macro=False)
        if dialog.exec() == QDialog.Accepted and dialog.result_action:
            page.steps.append(dialog.result_action.to_dict())
            self._macro_refresh(page)

    def _macro_edit(self, page: QWidget) -> None:
        row = page.steps_list.currentRow()
        if row < 0:
            return
        action = Action.from_dict(page.steps[row])
        dialog = ActionEditorDialog(self, -1, action, runner=None, allow_macro=False)
        if dialog.exec() == QDialog.Accepted and dialog.result_action:
            page.steps[row] = dialog.result_action.to_dict()
            self._macro_refresh(page)

    def _macro_remove(self, page: QWidget) -> None:
        row = page.steps_list.currentRow()
        if row >= 0:
            page.steps.pop(row)
            self._macro_refresh(page)

    def _macro_move(self, page: QWidget, delta: int) -> None:
        row = page.steps_list.currentRow()
        new = row + delta
        if row < 0 or not (0 <= new < len(page.steps)):
            return
        page.steps[row], page.steps[new] = page.steps[new], page.steps[row]
        self._macro_refresh(page)
        page.steps_list.setCurrentRow(new)

    def _macro_refresh(self, page: QWidget) -> None:
        page.steps_list.clear()
        for step in page.steps:
            action = Action.from_dict(step)
            title = action.label or _auto_label(action)
            QListWidgetItem(f"{action.type}: {title}", page.steps_list)

    # ------------------------------------------------------------ diálogos

    def _pick_file(self, edit: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Escolher arquivo ou programa")
        if path:
            edit.setText(path)

    def _pick_dir(self, edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Escolher pasta de trabalho")
        if path:
            edit.setText(path)

    # ------------------------------------------------------------- eventos

    def _on_type_changed(self) -> None:
        name = self._type_combo.currentData()
        # O QStackedWidget reserva a altura da maior página; com as outras
        # ignoradas no layout, o formulário fica do tamanho do tipo escolhido.
        for page_name, page in self._pages.items():
            policy = (
                QSizePolicy.Preferred if page_name == name else QSizePolicy.Ignored
            )
            page.setSizePolicy(QSizePolicy.Preferred, policy)
        self._stack.setCurrentWidget(self._pages[name])
        self._stack.adjustSize()
        for t in self._types:
            if t.name == name:
                self._description.setText(t.description)
                break

    def _load(self, action: Action) -> None:
        index = self._type_combo.findData(action.type)
        if index < 0:
            return
        self._type_combo.setCurrentIndex(index)
        self._label_edit.setText(action.label)
        page = self._pages[action.type]
        p = action.params
        if action.type == "hotkey":
            page.capture.set_keys(list(p.get("keys", [])))
            self._on_hotkey_captured(page.capture.keys())
        elif action.type == "text":
            page.text_edit.setPlainText(p.get("text", ""))
            page.enter_check.setChecked(bool(p.get("enter", False)))
        elif action.type == "command":
            page.command_edit.setText(p.get("command", ""))
            page.cwd_edit.setText(p.get("cwd") or "")
            page.visible_check.setChecked(bool(p.get("visible", False)))
        elif action.type == "launch":
            page.target_edit.setText(p.get("target", ""))
        elif action.type == "media":
            index = page.control_combo.findData(p.get("control", ""))
            if index >= 0:
                page.control_combo.setCurrentIndex(index)
        elif action.type == "macro":
            page.steps = [dict(s) for s in p.get("steps", [])]
            page.delay_edit.setText(str(p.get("delay_ms", 100)))
            self._macro_refresh(page)
        elif action.type == "home_assistant":
            page.domain_edit.setText(p.get("domain", ""))
            page.service_edit.setText(p.get("service", ""))
            page.entity_edit.setText(p.get("entity_id", ""))
            data = p.get("data") or {}
            page.data_edit.setText(json.dumps(data, ensure_ascii=False) if data else "")
        elif action.type == "obs":
            index = page.operation_combo.findData(p.get("operation", "scene"))
            if index >= 0:
                page.operation_combo.setCurrentIndex(index)
            page.scene_edit.setText(p.get("scene", ""))
            page.input_edit.setText(p.get("input", ""))
            page.request_edit.setText(p.get("request", ""))
            data = p.get("data") or {}
            page.request_data_edit.setText(
                json.dumps(data, ensure_ascii=False) if data else ""
            )
        elif action.type == "webhook":
            page.url_edit.setText(p.get("url", ""))
            index = page.method_combo.findText(p.get("method", "POST").upper())
            if index >= 0:
                page.method_combo.setCurrentIndex(index)
            body = p.get("body") or {}
            page.body_edit.setText(json.dumps(body, ensure_ascii=False) if body else "")

    def _collect(self) -> Action | None:
        """Monta a Action a partir do formulário atual; None se inválida."""
        name = self._type_combo.currentData()
        page = self._pages[name]
        params: dict[str, Any] = {}
        error = None
        if name == "hotkey":
            names = page.capture.keys()
            invalid = [k for k in names if not keys.is_valid(k)]
            if not names:
                error = "Informe ao menos uma tecla."
            elif invalid:
                error = f"Tecla(s) desconhecida(s): {', '.join(invalid)}"
            params = {"keys": [n.lower() for n in names]}
        elif name == "text":
            text = page.text_edit.toPlainText()
            if not text:
                error = "Informe o texto a digitar."
            params = {"text": text, "enter": page.enter_check.isChecked()}
        elif name == "command":
            command = page.command_edit.text().strip()
            if not command:
                error = "Informe o comando."
            params = {
                "command": command,
                "cwd": page.cwd_edit.text().strip() or None,
                "visible": page.visible_check.isChecked(),
            }
        elif name == "launch":
            target = page.target_edit.text().strip()
            if not target:
                error = "Informe o alvo."
            params = {"target": target}
        elif name == "media":
            params = {"control": page.control_combo.currentData()}
        elif name == "macro":
            if not page.steps:
                error = "Adicione ao menos um passo."
            try:
                delay = max(0, int(page.delay_edit.text() or "100"))
            except ValueError:
                delay = None
                error = "Intervalo inválido."
            params = {"steps": list(page.steps), "delay_ms": delay}
        elif name == "home_assistant":
            domain = page.domain_edit.text().strip()
            service = page.service_edit.text().strip()
            if not domain or not service:
                error = "Informe domínio e serviço (ex.: light / turn_off)."
            data_text = page.data_edit.text().strip()
            data: dict[str, Any] = {}
            if data_text:
                try:
                    data = json.loads(data_text)
                except json.JSONDecodeError:
                    error = "Dados JSON inválidos."
            params = {
                "domain": domain,
                "service": service,
                "entity_id": page.entity_edit.text().strip(),
                "data": data,
            }
        elif name == "obs":
            operation = page.operation_combo.currentData()
            params = {"operation": operation}
            if operation == "scene":
                params["scene"] = page.scene_edit.text().strip()
                if not params["scene"]:
                    error = "Informe o nome da cena."
            elif operation == "toggle_mute":
                params["input"] = page.input_edit.text().strip()
                if not params["input"]:
                    error = "Informe a fonte de áudio (ex.: Mic/Aux)."
            elif operation == "raw":
                params["request"] = page.request_edit.text().strip()
                if not params["request"]:
                    error = "Informe o tipo da requisição."
                data_text = page.request_data_edit.text().strip()
                params["data"] = {}
                if data_text:
                    try:
                        params["data"] = json.loads(data_text)
                    except json.JSONDecodeError:
                        error = "Dados JSON inválidos."
        elif name == "webhook":
            url = page.url_edit.text().strip()
            if not url.startswith(("http://", "https://")):
                error = "Informe uma URL http(s) válida."
            body_text = page.body_edit.text().strip()
            body = None
            if body_text:
                try:
                    body = json.loads(body_text)
                except json.JSONDecodeError:
                    error = "Corpo JSON inválido."
            params = {
                "url": url,
                "method": page.method_combo.currentText(),
                "body": body,
            }
        if error:
            QMessageBox.warning(self, "Configuração incompleta", error)
            return None
        action = Action(
            type=name,
            params=params,
            label=self._label_edit.text().strip(),
            short=self._kept_short,
        )
        if not action.label:
            action.label = _auto_label(action)
        return action

    def _accept(self) -> None:
        action = self._collect()
        if action is not None:
            self.result_action = action
            self.accept()

    def _remove(self) -> None:
        self.remove_requested = True
        self.accept()

    def _test(self) -> None:
        action = self._collect()
        runner = self._runner
        if action is None or runner is None:
            return
        self._status.setText(
            "Executando em 3 segundos — leve o foco à janela alvo…"
        )
        self._test_button.setEnabled(False)

        # Captura o runner agora: o disparo acontece 3 s depois, fora deste
        # escopo.
        def fire() -> None:
            runner.submit(action)
            self._status.setText("Ação enviada.")
            self._test_button.setEnabled(True)

        # Timer filho do editor: se o usuário sair antes do disparo, ele é
        # apagado junto e a ação não roda.
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(fire)
        timer.timeout.connect(timer.deleteLater)
        timer.start(self._TEST_DELAY_MS)


def _auto_label(action: Action) -> str:
    """Gera um rótulo curto a partir dos parâmetros da ação."""
    p = action.params
    if action.type == "hotkey":
        return keys.pretty(list(p.get("keys", [])))[:24]
    if action.type == "text":
        return (p.get("text", "").splitlines() or [""])[0][:14]
    if action.type == "command":
        return p.get("command", "").split()[0][:14] if p.get("command") else "cmd"
    if action.type == "launch":
        target = p.get("target", "")
        name = target.rstrip("/\\").split("\\")[-1].split("/")[-1]
        return (name or target)[:14]
    if action.type == "media":
        return keys.MEDIA_TITLES.get(p.get("control", ""), "Mídia")[:18]
    if action.type == "macro":
        return f"Macro ({len(p.get('steps', []))})"
    if action.type == "home_assistant":
        return p.get("entity_id") or f"{p.get('domain')}.{p.get('service')}"
    if action.type == "obs":
        op = p.get("operation", "")
        if op == "scene":
            return f"OBS: {p.get('scene', '')}"[:18]
        from ..integrations.obs import OPERATION_TITLES

        return f"OBS: {OPERATION_TITLES.get(op, op)}"[:18]
    if action.type == "webhook":
        url = p.get("url", "")
        host = url.split("//")[-1].split("/")[0]
        return f"→ {host}"[:18]
    if action.type == "mode_switch":
        return "Perfil →"
    return action.type
