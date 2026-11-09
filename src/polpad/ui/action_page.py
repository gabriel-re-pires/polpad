"""Página do editor de ação (no lugar das colunas, com "Voltar").

Embute o :class:`~polpad.ui.action_editor.ActionEditorDialog` como widget;
os passos de macro continuam abrindo o editor em janela.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..actions.executor import ActionRunner
from ..core.models import Action
from . import glyphs, style
from .action_editor import ActionEditorDialog
from .inspector import FitScrollArea


class ActionEditorPage(QWidget):
    """``done`` leva o editor preenchido; ``closed``, voltar sem salvar."""

    done = Signal(object)
    closed = Signal()

    def __init__(
        self,
        key: int,
        action: Action | None,
        profile_name: str,
        runner: ActionRunner | None,
    ) -> None:
        super().__init__()
        self.key = key
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(28, 20, 28, 12)
        header.setSpacing(12)
        back = QPushButton("Voltar")
        back.setObjectName("ghost")
        back.setIcon(glyphs.icon("back", style.TEXT))
        back.setToolTip("Voltar sem salvar (Esc)")
        back.clicked.connect(self.closed.emit)
        header.addWidget(back)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel(f"Tecla {key + 1}")
        title.setObjectName("headline")
        sub = QLabel(f"Perfil “{profile_name}”")
        sub.setObjectName("caption")
        titles.addWidget(title)
        titles.addWidget(sub)
        header.addLayout(titles)
        header.addStretch(1)
        save = QPushButton("Salvar")
        save.setObjectName("primary")
        save.setIcon(glyphs.icon("check", style.ACCENT_TEXT))
        header.addWidget(save)
        root.addLayout(header)

        self.editor = ActionEditorDialog(None, key, action, runner=runner)
        # Embutido: sem moldura de janela, e Salvar/Voltar ficam no cabeçalho.
        self.editor.setWindowFlags(Qt.Widget)
        # Sem o fundo próprio de janela: o formulário assume o do cartão.
        self.editor.setObjectName("embeddedEditor")
        for button in self.editor.dialog_buttons:
            button.hide()
        self.editor.accepted.connect(lambda: self.done.emit(self.editor))
        self.editor.rejected.connect(self.closed.emit)
        save.clicked.connect(self.editor._accept)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.addWidget(self.editor)
        # Largura fixa: a altura das páginas não prevê quebra de linha, e numa
        # largura menor a ajuda quebraria e cortaria os campos.
        card.setFixedWidth(760)

        scroll = FitScrollArea()
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(28, 4, 28, 28)
        # O cartão fica do tamanho do formulário; a sobra vai para baixo.
        column.addWidget(card, 0, Qt.AlignHCenter)
        column.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

    def focus_form(self) -> None:
        self.editor.setFocus(Qt.OtherFocusReason)
