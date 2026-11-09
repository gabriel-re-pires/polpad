"""O aparelho na tela: corpo do macropad, display OLED e as 18 teclas.

A disposição segue :data:`~polpad.core.models.KEY_LAYOUT` (grade 4x5 do PCB,
com o OLED no canto superior esquerdo, como no aparelho real).
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QAbstractButton, QSizePolicy, QWidget

from ..actions.base import get as action_type
from ..core.models import GRID_COLS, GRID_ROWS, KEY_LAYOUT, Profile, key_at
from . import style
from .oled_preview import OledPreview

KEY_MIN = 74          # px — tecla mínima (janela pequena)
KEY_MAX = 124         # px — tecla máxima (janela grande)
KEY_GAP_RATIO = 0.14  # vão entre teclas, proporcional à tecla
BODY_PAD_RATIO = 0.30  # margem do corpo do aparelho, proporcional à tecla
KEY_RADIUS = 12
KEY_TRAVEL = 3        # px de "curso" da tecla (sombra inferior)


@dataclass
class KeyContent:
    """O que uma tecla mostra (independente de como é desenhada)."""

    kind: str = "empty"        # "empty" | "bound" | "mode"
    title: str = ""            # rótulo da ação
    subtitle: str = ""         # tipo da ação


class KeyCap(QAbstractButton):
    """Uma tecla desenhada como tecla: face, borda, curso e estados."""

    activated = Signal()        # Enter / clique duplo
    menu_requested = Signal()

    def __init__(self, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.index = index
        self.content = KeyContent()
        self.selected = False
        self.lit = False
        self._hover = False
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda _p: self.menu_requested.emit())
        self.setAccessibleName(f"Tecla {index + 1}")

    def set_content(self, content: KeyContent) -> None:
        self.content = content
        if content.kind == "bound":
            desc = f"{content.title} ({content.subtitle})"
        elif content.kind == "mode":
            desc = "tecla de modo"
        else:
            desc = "sem ação"
        self.setAccessibleDescription(desc)
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802 — API Qt
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 — API Qt
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 — API Qt
        if event.button() == Qt.LeftButton:
            self.activated.emit()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 — API Qt
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.activated.emit()
            return
        if event.key() == Qt.Key_Menu:
            self.menu_requested.emit()
            return
        if event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            # Sobe para o DeviceView, que navega pela grade física (o
            # QAbstractButton trocaria o foco na ordem de criação).
            event.ignore()
            return
        super().keyPressEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802 — API Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = self.content
        pressed = self.lit or self.isDown()
        travel = 0 if pressed else KEY_TRAVEL
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        face = r.adjusted(0, 0 if travel else KEY_TRAVEL, 0, -travel)

        # "Saia" escura sob a face: o curso de tecla física.
        if travel:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#07080B"))
            p.drawRoundedRect(r.adjusted(0, travel, 0, 0), KEY_RADIUS, KEY_RADIUS)

        if self.lit:
            top, bottom = QColor(style.ACCENT_HOVER), QColor(style.ACCENT)
        elif c.kind == "empty":
            top = bottom = QColor(style.BG_PANEL)
        else:
            top, bottom = QColor("#272B35"), QColor(style.BG_SURFACE)
            if self._hover:
                top, bottom = top.lighter(112), bottom.lighter(110)
        grad = QLinearGradient(face.topLeft(), face.bottomLeft())
        grad.setColorAt(0, top)
        grad.setColorAt(1, bottom)

        if self.selected:
            border = QPen(QColor(style.ACCENT), 2)
        elif self.hasFocus():
            border = QPen(QColor(style.ACCENT_HOVER), 1.4)
        elif c.kind == "mode":
            border = QPen(QColor(style.ACCENT_PRESSED), 1)
        elif c.kind == "empty":
            border = QPen(QColor(style.BORDER_STRONG if self._hover else style.BORDER), 1)
            border.setStyle(Qt.DashLine)
            border.setDashPattern([3, 3])
        else:
            border = QPen(QColor(style.BORDER_STRONG if self._hover else "#323744"), 1)
        p.setPen(border)
        p.setBrush(grad)
        inset = border.widthF() / 2
        p.drawRoundedRect(
            face.adjusted(inset, inset, -inset, -inset), KEY_RADIUS, KEY_RADIUS
        )

        # Brilho de borda superior: a luz vem de cima.
        if c.kind != "empty" and not self.lit:
            p.setPen(QPen(QColor(255, 255, 255, 18), 1))
            p.drawLine(
                QPointF(face.left() + KEY_RADIUS, face.top() + 1.5),
                QPointF(face.right() - KEY_RADIUS, face.top() + 1.5),
            )

        self._paint_content(p, face)
        p.end()

    def _paint_content(self, p: QPainter, face: QRectF) -> None:
        c = self.content
        pad = max(8.0, face.width() * 0.1)
        inner = face.adjusted(pad, pad - 1, -pad, -pad + 1)
        on_accent = self.lit
        base = self.font()

        num_font = QFont(base)
        num_font.setPixelSize(11)
        num_font.setWeight(QFont.DemiBold)
        p.setFont(num_font)
        p.setPen(QColor(style.ACCENT_TEXT if on_accent else style.TEXT_FAINT))
        p.drawText(inner, Qt.AlignLeft | Qt.AlignTop, str(self.index + 1))

        if c.kind == "empty":
            p.setPen(QPen(QColor(style.TEXT_FAINT), 1.6, Qt.SolidLine, Qt.RoundCap))
            cx, cy = face.center().x(), face.center().y() + 4
            p.drawLine(QPointF(cx - 6, cy), QPointF(cx + 6, cy))
            p.drawLine(QPointF(cx, cy - 6), QPointF(cx, cy + 6))
            return

        # Rótulo (até duas linhas) e tipo, ancorados embaixo.
        title_font = QFont(base)
        title_font.setPixelSize(13 if face.width() >= 96 else 12)
        title_font.setWeight(QFont.DemiBold)
        sub_font = QFont(base)
        sub_font.setPixelSize(11)
        fm_t = QFontMetrics(title_font)
        fm_s = QFontMetrics(sub_font)

        # O tipo só aparece se couber inteiro; cortado é ruído (o inspetor mostra).
        show_sub = (
            bool(c.subtitle)
            and face.height() >= 84
            and fm_s.horizontalAdvance(c.subtitle) <= inner.width()
        )
        y_bottom = inner.bottom()
        if show_sub:
            p.setFont(sub_font)
            p.setPen(
                QColor(style.ACCENT_TEXT if on_accent else style.TEXT_FAINT)
            )
            sub = fm_s.elidedText(c.subtitle, Qt.ElideRight, int(inner.width()))
            p.drawText(
                QRectF(
                    inner.left(), y_bottom - fm_s.height(), inner.width(), fm_s.height()
                ),
                Qt.AlignLeft | Qt.AlignVCenter,
                sub,
            )
            y_bottom -= fm_s.height() + 1

        lines = _wrap(c.title, fm_t, int(inner.width()), 2)
        p.setFont(title_font)
        if on_accent:
            p.setPen(QColor(style.ACCENT_TEXT))
        elif c.kind == "mode":
            p.setPen(QColor(style.ACCENT_HOVER))
        else:
            p.setPen(QColor(style.TEXT))
        line_h = fm_t.height()
        y = y_bottom - line_h * len(lines)
        for line in lines:
            p.drawText(
                QRectF(inner.left(), y, inner.width(), line_h),
                Qt.AlignLeft | Qt.AlignVCenter,
                line,
            )
            y += line_h


def _wrap(text: str, fm: QFontMetrics, width: int, max_lines: int) -> list[str]:
    """Quebra por palavras em até ``max_lines``, com reticências no fim."""
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    for i, word in enumerate(words):
        candidate = f"{current} {word}".strip()
        if fm.horizontalAdvance(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) == max_lines - 1:
            rest = " ".join(words[i:])
            lines.append(fm.elidedText(rest, Qt.ElideRight, width))
            return lines
    lines.append(fm.elidedText(current, Qt.ElideRight, width))
    return lines[:max_lines]


class DeviceView(QWidget):
    """Corpo do macropad com o display e as teclas, centralizado e escalável."""

    key_clicked = Signal(int)         # seleção
    key_activated = Signal(int)       # editar
    key_menu_requested = Signal(int)

    # Tempo que a tecla fica acesa após ser pressionada no dispositivo.
    FLASH_MS = 280

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.selected: int | None = None
        self.oled = OledPreview(pixel=2.0, padding=6)
        self.oled.setParent(self)
        self._caps: list[KeyCap] = []
        self._flash_timers: dict[int, QTimer] = {}
        self._body = QRectF()
        for i in range(len(KEY_LAYOUT)):
            cap = KeyCap(i, self)
            cap.clicked.connect(lambda _c=False, k=i: self._on_click(k))
            cap.activated.connect(lambda k=i: self.key_activated.emit(k))
            cap.menu_requested.connect(lambda k=i: self.key_menu_requested.emit(k))
            self._caps.append(cap)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def _metrics(self, w: float, h: float) -> tuple[float, float, float]:
        """(tecla, vão, margem) que cabem em ``w`` x ``h``."""
        for unit in range(KEY_MAX, KEY_MIN - 1, -2):
            gap = round(unit * KEY_GAP_RATIO)
            pad = round(unit * BODY_PAD_RATIO)
            need_w = GRID_COLS * unit + (GRID_COLS - 1) * gap + 2 * pad
            need_h = GRID_ROWS * unit + (GRID_ROWS - 1) * gap + 2 * pad
            if need_w <= w and need_h <= h:
                return unit, gap, pad
        unit = KEY_MIN
        return unit, round(unit * KEY_GAP_RATIO), round(unit * BODY_PAD_RATIO)

    def sizeHint(self) -> QSize:  # noqa: N802 — API Qt
        unit = 100
        gap, pad = round(unit * KEY_GAP_RATIO), round(unit * BODY_PAD_RATIO)
        return QSize(
            GRID_COLS * unit + (GRID_COLS - 1) * gap + 2 * pad + 32,
            GRID_ROWS * unit + (GRID_ROWS - 1) * gap + 2 * pad + 32,
        )

    def minimumSizeHint(self) -> QSize:  # noqa: N802 — API Qt
        unit = KEY_MIN
        gap, pad = round(unit * KEY_GAP_RATIO), round(unit * BODY_PAD_RATIO)
        return QSize(
            GRID_COLS * unit + (GRID_COLS - 1) * gap + 2 * pad,
            GRID_ROWS * unit + (GRID_ROWS - 1) * gap + 2 * pad,
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 — API Qt
        self._layout()
        super().resizeEvent(event)

    def _layout(self) -> None:
        unit, gap, pad = self._metrics(self.width(), self.height())
        body_w = GRID_COLS * unit + (GRID_COLS - 1) * gap + 2 * pad
        body_h = GRID_ROWS * unit + (GRID_ROWS - 1) * gap + 2 * pad
        x0 = (self.width() - body_w) / 2
        y0 = (self.height() - body_h) / 2
        self._body = QRectF(x0, y0, body_w, body_h)

        def cell(row: int, col: int) -> QRectF:
            return QRectF(
                x0 + pad + col * (unit + gap),
                y0 + pad + row * (unit + gap),
                unit,
                unit,
            )

        for cap, (row, col) in zip(self._caps, KEY_LAYOUT, strict=True):
            cap.setGeometry(cell(row, col).toRect())

        # O display ocupa as posições vazias da primeira linha.
        empty = [c for c in range(GRID_COLS) if key_at(0, c) is None]
        if empty:
            first, last = cell(0, empty[0]), cell(0, empty[-1])
            self.oled.setGeometry(first.united(last).toRect())
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 — API Qt
        if self._body.isEmpty():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        body = self._body
        radius = 26

        # Sombra projetada, em camadas, sob o aparelho.
        for i, alpha in enumerate((40, 26, 14)):
            spread = 6 + i * 8
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, alpha))
            p.drawRoundedRect(
                body.adjusted(-spread / 3, spread / 2, spread / 3, spread),
                radius + spread / 2,
                radius + spread / 2,
            )

        grad = QLinearGradient(body.topLeft(), body.bottomLeft())
        grad.setColorAt(0, QColor("#1F222A"))
        grad.setColorAt(1, QColor("#14161B"))
        p.setBrush(grad)
        p.setPen(QPen(QColor("#2A2E38"), 1))
        p.drawRoundedRect(body.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        # Filete de luz na borda superior do corpo.
        hl = QPainterPath()
        hl.moveTo(body.left() + radius, body.top() + 1.5)
        hl.lineTo(body.right() - radius, body.top() + 1.5)
        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.drawPath(hl)
        p.end()

    def _on_click(self, key: int) -> None:
        self.set_selected(key)
        self.key_clicked.emit(key)

    def set_selected(self, key: int | None) -> None:
        self.selected = key
        for cap in self._caps:
            cap.selected = cap.index == key
            cap.update()

    def focus_key(self, key: int) -> None:
        if 0 <= key < len(self._caps):
            self._caps[key].setFocus(Qt.OtherFocusReason)

    def keyPressEvent(self, event) -> None:  # noqa: N802 — API Qt
        """Setas movem a seleção pela grade física."""
        moves = {
            Qt.Key_Left: (0, -1),
            Qt.Key_Right: (0, 1),
            Qt.Key_Up: (-1, 0),
            Qt.Key_Down: (1, 0),
        }
        focused = self.focusWidget()
        if event.key() in moves and isinstance(focused, KeyCap):
            dr, dc = moves[event.key()]
            row, col = KEY_LAYOUT[focused.index]
            while True:
                row, col = row + dr, col + dc
                if not (0 <= row < GRID_ROWS and 0 <= col < GRID_COLS):
                    return
                target = key_at(row, col)
                if target is not None:
                    self.focus_key(target)
                    self._on_click(target)
                    return
        super().keyPressEvent(event)

    def flash(self, key: int) -> None:
        """Acende a tecla recém-pressionada no macropad (ou no simulador)."""
        if not 0 <= key < len(self._caps):
            return
        self._set_lit(key, True)
        timer = self._flash_timers.get(key)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda k=key: self._set_lit(k, False))
            self._flash_timers[key] = timer
        # start() reinicia a contagem: teclas repetidas seguem acesas.
        timer.start(self.FLASH_MS)

    def _set_lit(self, key: int, lit: bool) -> None:
        cap = self._caps[key]
        cap.lit = lit
        cap.update()

    def refresh(self, profile: Profile | None, mode_key: int | None) -> None:
        for i, cap in enumerate(self._caps):
            action = profile.action_for(i) if profile else None
            if i == mode_key:
                cap.set_content(
                    KeyContent("mode", "Modo", "troca o perfil")
                )
                cap.setToolTip("Tecla de modo: alterna o perfil ativo")
            elif action is not None:
                kind = action_type(action.type)
                type_title = kind.title if kind else action.type
                cap.set_content(
                    KeyContent(
                        "bound",
                        action.label or type_title,
                        type_title,
                    )
                )
                cap.setToolTip(
                    f"{action.label or type_title}\nClique duplo para editar"
                )
            else:
                cap.set_content(KeyContent("empty"))
                cap.setToolTip("Sem ação — clique duplo para configurar")
