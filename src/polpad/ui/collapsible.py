"""Coluna lateral recolhível.

O botão de recolher é só um ícone (sem fundo nem borda) dentro do
cabeçalho da própria coluna. Recolhida, a coluna não some: vira um trilho
fino com o mesmo ícone, que a expande de novo. Assim o usuário sempre vê
onde ela está e como trazê-la de volta.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QToolButton, QVBoxLayout, QWidget

from . import glyphs, style

RAIL_W = 52  # px — largura do trilho da coluna recolhida


def bare_icon_button(glyph: str, tooltip: str) -> QToolButton:
    """Botão que é só o ícone: clareia ao passar o mouse, sem caixa."""
    button = QToolButton()
    button.setObjectName("bareIcon")
    button.setAutoRaise(True)
    button.setIcon(glyphs.icon(glyph, style.TEXT_MUTED, hover=style.TEXT))
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    button.setCursor(Qt.PointingHandCursor)
    return button


class CollapsibleSide(QFrame):
    """Envolve uma coluna (perfis ou inspetor) e a recolhe para um trilho.

    ``header`` é o layout do cabeçalho da coluna, onde o ícone de recolher
    é posto — na ponta de fora da coluna (direita da coluna da esquerda,
    esquerda da coluna da direita), perto de onde ela encolhe.
    """

    collapsed_changed = Signal(bool)

    def __init__(
        self,
        content: QWidget,
        side: str,
        header: QHBoxLayout,
        name: str,
        rail_extra: QWidget | None = None,
    ) -> None:
        super().__init__()
        self._content = content
        self._side = side
        self._collapsed = False
        self._min_w = content.minimumWidth()
        self._max_w = content.maximumWidth()
        self.expanded_width = max(self._min_w, 280)
        # O fundo e a borda passam para o invólucro, que existe também no
        # estado recolhido; a coluna em si fica transparente.
        self.setObjectName(content.objectName())
        content.setObjectName("")

        glyph = "panel-left" if side == "left" else "panel-right"
        self._collapse_btn = bare_icon_button(glyph, f"Recolher {name}")
        self._collapse_btn.clicked.connect(lambda: self.set_collapsed(True))
        if side == "left":
            header.addWidget(self._collapse_btn)
        else:
            header.insertWidget(0, self._collapse_btn)

        self._rail = QWidget()
        rail = QVBoxLayout(self._rail)
        rail.setContentsMargins(0, 18, 0, 0)
        self._expand_btn = bare_icon_button(glyph, f"Mostrar {name}")
        self._expand_btn.clicked.connect(lambda: self.set_collapsed(False))
        rail.addWidget(self._expand_btn, alignment=Qt.AlignHCenter | Qt.AlignTop)
        if rail_extra is not None:
            # Ex.: os ladrilhos dos perfis, que seguem utilizáveis recolhidos.
            rail.addWidget(rail_extra, alignment=Qt.AlignHCenter | Qt.AlignTop)
        rail.addStretch(1)
        self._rail.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(content)
        layout.addWidget(self._rail)
        self.setMinimumWidth(self._min_w)
        self.setMaximumWidth(self._max_w)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        if collapsed and self.isVisible():
            # Largura a devolver quando a coluna for expandida de novo.
            self.expanded_width = self.width()
        self._content.setVisible(not collapsed)
        self._rail.setVisible(collapsed)
        if collapsed:
            self.setFixedWidth(RAIL_W)
        else:
            self.setMinimumWidth(self._min_w)
            self.setMaximumWidth(self._max_w)
        self.collapsed_changed.emit(collapsed)
