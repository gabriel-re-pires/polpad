"""Campo que grava um atalho pressionando a combinação no teclado.

Enquanto grava, captura todas as teclas (inclusive Tab e Esc). A gravação
fecha na primeira tecla não modificadora; soltar só modificadores grava apenas
eles; Esc sozinho cancela. Cada gravação SOMA ao que já estava no campo: dá
para montar Win + V em duas vezes (Win pelo menu ou pelo teclado virtual, V
depois), já que o Windows engole o Win + V antes de ele chegar aqui. Só o
botão Limpar apaga. Letras e números vêm do código físico, então Shift+1 vira
``Shift + 1`` em qualquer layout. A tradução tecla -> nome fica em
:mod:`polpad.actions.keys`.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QMenu, QToolButton, QWidget

from ..actions import keys
from . import style

_MOD_ORDER = ("ctrl", "alt", "shift", "win")

# Teclas oferecidas no menu: as que não dá para apertar num teclado comum.
EXTRA_KEYS = [f"f{i}" for i in range(13, 21)] + ["printscreen", "pause", "menu", "win"]

_ALIASES = {"control": "ctrl", "windows": "win", "cmd": "win", "super": "win"}


def merge_keys(old: list[str], new: list[str]) -> list[str]:
    """Soma ``new`` à combinação ``old``, sem repetir; modificadores na frente."""
    out: list[str] = []
    for name in [*old, *new]:
        name = _ALIASES.get(name, name)
        if name not in out:
            out.append(name)
    mods = sorted((n for n in out if n in _MOD_ORDER), key=_MOD_ORDER.index)
    return mods + [n for n in out if n not in _MOD_ORDER]


class _CaptureField(QWidget):
    changed = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self._keys: list[str] = []
        self._listening = False
        self._held: list[str] = []      # modificadores pressionados agora
        self._peak: list[str] = []      # maior conjunto pressionado na gravação
        self._warning = ""              # tecla não reconhecida na gravação
        self._hover = False
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(46)
        self.setAccessibleName("Atalho")

    def keys(self) -> list[str]:
        return list(self._keys)

    def warning(self) -> str:
        """Aviso da última tecla não reconhecida ("" se não houver)."""
        return self._warning

    def set_keys(self, names: list[str]) -> None:
        self._keys = [n.strip().lower() for n in names if n.strip()]
        self.setAccessibleDescription(keys.pretty(self._keys) or "vazio")
        self.update()

    def start(self) -> None:
        self._listening = True
        self._held = []
        self._peak = []
        self._warning = ""
        self.setFocus(Qt.MouseFocusReason)
        self.update()

    def stop(self) -> None:
        self._listening = False
        self._held = []
        self._peak = []
        self._warning = ""
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 — API Qt
        return QSize(280, 46)

    def mousePressEvent(self, event) -> None:  # noqa: N802 — API Qt
        if event.button() == Qt.LeftButton:
            self.start()

    def clear(self) -> None:
        self.stop()
        self.set_keys([])

    def focusOutEvent(self, event) -> None:  # noqa: N802 — API Qt
        # Win + V (e outros atalhos do Windows) abrem um painel que tira o
        # foco antes de o Win ser solto: grava o que já estava apertado.
        if self._listening and self._peak:
            self._commit(list(self._peak))
        else:
            self.stop()
        super().focusOutEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802 — API Qt
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 — API Qt
        self._hover = False
        self.update()

    def event(self, e) -> bool:
        if self._listening and e.type() == QEvent.KeyPress:
            self._on_press(e)
            return True
        if self._listening and e.type() == QEvent.KeyRelease:
            self._on_release(e)
            return True
        if (
            not self._listening
            and e.type() == QEvent.KeyPress
            and e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space)
        ):
            self.start()
            return True
        return super().event(e)

    def _on_press(self, e) -> None:
        if e.isAutoRepeat():
            return
        key = int(e.key())
        mods = int(e.modifiers().value)
        if key in keys.QT_MODIFIER_KEYS:
            name = keys.QT_MODIFIER_KEYS[key]
            if name not in self._held:
                self._held.append(name)
            if len(self._held) > len(self._peak):
                self._peak = sorted(self._held, key=_MOD_ORDER.index)
            self.update()
            return
        if key == Qt.Key_Escape and not mods:
            self.stop()
            return
        names = keys.names_from_event(
            key, mods, int(e.nativeVirtualKey()), int(e.nativeScanCode())
        )
        if names:
            self._commit(names)
            return
        self._warning = "Tecla não reconhecida. Tente outra ou use Mais teclas."
        self.update()

    def _on_release(self, e) -> None:
        if e.isAutoRepeat():
            return
        name = keys.QT_MODIFIER_KEYS.get(int(e.key()))
        if name is None:
            return
        if name in self._held:
            self._held.remove(name)
        # Soltou todos os modificadores sem tecla principal: grava só eles.
        if not self._held and self._peak:
            self._commit(list(self._peak))
        else:
            self.update()

    def _commit(self, names: list[str]) -> None:
        self.stop()
        self.set_keys(merge_keys(self._keys, names))
        self.changed.emit(self.keys())

    def paintEvent(self, _event) -> None:  # noqa: N802 — API Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self._listening:
            p.setPen(QPen(QColor(style.ACCENT), 1.5))
            p.setBrush(QColor(122, 46, 240, 26))
        else:
            hovered = self._hover or self.hasFocus()
            p.setPen(QPen(QColor(style.BORDER_STRONG if hovered else style.BORDER), 1))
            p.setBrush(QColor(style.BG_PANEL))
        p.drawRoundedRect(r, style.RADIUS_CONTROL, style.RADIUS_CONTROL)

        font = QFont(self.font())
        font.setPixelSize(13)
        p.setFont(font)
        x = 12.0
        if self._listening:
            combo = merge_keys(self._keys, self._held)
            if self._warning:
                p.setPen(QColor(style.WARNING))
                p.drawText(
                    r.adjusted(12, 0, -12, 0),
                    Qt.AlignVCenter | Qt.AlignLeft,
                    self._warning,
                )
            elif combo:
                x = self._draw_combo(p, combo, x, trailing=True)
            else:
                p.setPen(QColor(style.ACCENT_HOVER))
                p.drawText(
                    r.adjusted(12, 0, -12, 0),
                    Qt.AlignVCenter | Qt.AlignLeft,
                    "Pressione a combinação…   (Esc cancela)",
                )
        elif self._keys:
            self._draw_combo(p, self._keys, x)
            p.setPen(QColor(style.TEXT_FAINT))
            small = QFont(font)
            small.setPixelSize(11)
            p.setFont(small)
            p.drawText(
                r.adjusted(0, 0, -12, 0),
                Qt.AlignVCenter | Qt.AlignRight,
                "clique para adicionar",
            )
        else:
            p.setPen(QColor(style.TEXT_FAINT))
            p.drawText(
                r.adjusted(12, 0, -12, 0),
                Qt.AlignVCenter | Qt.AlignLeft,
                "Clique aqui e pressione a combinação",
            )
        p.end()

    def _draw_combo(
        self, p: QPainter, names: list[str], x: float, trailing: bool = False
    ) -> float:
        cap_font = QFont(self.font())
        cap_font.setPixelSize(12)
        cap_font.setWeight(QFont.DemiBold)
        fm = QFontMetrics(cap_font)
        plus_font = QFont(self.font())
        plus_font.setPixelSize(13)
        h = 26.0
        y = (self.height() - h) / 2
        for i, name in enumerate(names):
            if i:
                p.setFont(plus_font)
                p.setPen(QColor(style.TEXT_FAINT))
                p.drawText(QRectF(x, y, 16, h), Qt.AlignCenter, "+")
                x += 16
            label = keys.pretty_name(name)
            w = max(fm.horizontalAdvance(label) + 18, h)
            cap = QRectF(x, y, w, h)
            # Tecla desenhada: base escura (curso) e face por cima.
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#07080B"))
            p.drawRoundedRect(cap.adjusted(0, 2, 0, 2), 6, 6)
            p.setPen(QPen(QColor(style.BORDER_STRONG), 1))
            p.setBrush(QColor(style.BG_RAISED))
            p.drawRoundedRect(cap, 6, 6)
            p.setFont(cap_font)
            p.setPen(QColor(style.TEXT))
            p.drawText(cap, Qt.AlignCenter, label)
            x += w
        if trailing:
            p.setFont(plus_font)
            p.setPen(QColor(style.ACCENT_HOVER))
            p.drawText(QRectF(x, y, 40, h), Qt.AlignCenter, "+ …")
        return x


class HotkeyCapture(QWidget):
    """Campo de gravação + menu com teclas que não dá para apertar."""

    changed = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.field = _CaptureField()
        self.field.changed.connect(self.changed.emit)
        layout.addWidget(self.field, stretch=1)

        more = QToolButton()
        more.setText("Mais teclas")
        more.setToolTip("Teclas que não existem em teclados comuns, como F13–F20")
        more.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(more)
        for name in EXTRA_KEYS:
            act = menu.addAction(keys.pretty_name(name))
            act.triggered.connect(lambda _c=False, n=name: self._pick(n))
        more.setMenu(menu)
        more.setMinimumHeight(46)
        layout.addWidget(more)

        self.clear_button = QToolButton()
        self.clear_button.setText("Limpar")
        self.clear_button.setToolTip("Apaga a combinação para gravar outra")
        self.clear_button.setMinimumHeight(46)
        self.clear_button.clicked.connect(self._clear)
        layout.addWidget(self.clear_button)

        self.field.changed.connect(self._sync)
        self._sync()

    def _pick(self, name: str) -> None:
        self.field.set_keys(merge_keys(self.field.keys(), [name]))
        self._sync()
        self.changed.emit(self.field.keys())

    def _clear(self) -> None:
        self.field.clear()
        self._sync()
        self.changed.emit(self.field.keys())

    def _sync(self, *_args) -> None:
        self.clear_button.setEnabled(bool(self.field.keys()))

    def keys(self) -> list[str]:
        return self.field.keys()

    def set_keys(self, names: list[str]) -> None:
        self.field.set_keys(names)
        self._sync()
