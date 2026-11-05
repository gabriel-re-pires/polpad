"""Inspetor: o painel à direita do aparelho.

Três cartões, de cima para baixo na ordem em que se usa:

``KeyCard``      a tecla selecionada no aparelho — o que ela faz e os
                 botões para editar, testar e limpar;
``IconCard``     o ícone do perfil, com a prévia EXATA de como ele sai no
                 OLED (1 bit, ocupando a altura do display);
``DisplayCard``  o que o display mostra: o ícone do perfil ou uma tela
                 personalizada (hora, data, perfil, texto).

A prévia do ícone resolve a principal dúvida de quem escolhe uma imagem:
"como isso vai ficar no aparelho?". Antes, só se descobria olhando o
hardware — e se o ícone saía apagado, parecia que não tinha funcionado.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..actions import keys
from ..actions.base import get as action_type
from ..core import display, icons, oled_render
from ..core.models import KEY_COUNT, Action, Profile
from ..core.store import Store
from . import glyphs, style
from .oled_preview import OledPreview

# Parâmetros mais informativos de cada tipo, na ordem de preferência.
_DETAIL_KEYS = (
    "keys", "text", "command", "target", "url", "scene", "entity_id",
    "control", "operation", "steps",
)


def describe(action: Action) -> str:
    """Resumo legível dos parâmetros de uma ação (uma linha)."""
    p: dict[str, Any] = action.params
    for key in _DETAIL_KEYS:
        value = p.get(key)
        if not value:
            continue
        if key == "keys" and isinstance(value, list):
            return keys.pretty([str(k) for k in value])
        if key == "steps" and isinstance(value, list):
            return f"{len(value)} passos"
        return str(value).splitlines()[0] if str(value) else ""
    return ""


def _card(title: str) -> tuple[QFrame, QVBoxLayout, QLabel]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 16)
    layout.setSpacing(10)
    label = QLabel(title)
    label.setObjectName("sectionTitle")
    return frame, layout, label


def _wrap(card: QFrame, owner: QFrame) -> None:
    outer = QVBoxLayout(owner)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(card)


class _Field(QWidget):
    """Par rótulo/valor em duas linhas (o valor quebra se for longo)."""

    def __init__(self, caption: str) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        cap = QLabel(caption)
        cap.setObjectName("caption")
        self.value = QLabel()
        self.value.setObjectName("value")
        self.value.setWordWrap(True)
        self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(cap)
        lay.addWidget(self.value)

    def set(self, text: str) -> None:
        self.value.setText(text)
        self.setVisible(bool(text))


class KeyCard(QFrame):
    edit_requested = Signal(int)
    test_requested = Signal(int)
    clear_requested = Signal(int)
    settings_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._key: int | None = None
        frame, layout, self._title = _card("Tecla")
        _wrap(frame, self)
        layout.addWidget(self._title)

        self._message = QLabel()
        self._message.setObjectName("hint")
        self._message.setWordWrap(True)
        layout.addWidget(self._message)

        self._type = _Field("Tipo")
        self._label = _Field("Rótulo")
        self._detail = _Field("Faz")
        for f in (self._type, self._label, self._detail):
            layout.addWidget(f)

        self._edit = QPushButton("Configurar ação")
        self._edit.setObjectName("primary")
        self._edit.setIcon(glyphs.icon("edit", style.ACCENT_TEXT))
        self._edit.clicked.connect(lambda: self._emit(self.edit_requested))
        layout.addWidget(self._edit)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(0, 0, 0, 0)
        self._test = QPushButton("Testar")
        self._test.setIcon(glyphs.icon("play"))
        self._test.setToolTip("Executa a ação após 3 s — leve o foco à janela alvo")
        self._test.clicked.connect(lambda: self._emit(self.test_requested))
        self._clear = QPushButton("Limpar")
        self._clear.setObjectName("danger")
        self._clear.setIcon(glyphs.icon("trash", style.DANGER))
        self._clear.clicked.connect(lambda: self._emit(self.clear_requested))
        row.addWidget(self._test, 1)
        row.addWidget(self._clear, 1)
        self._secondary = QWidget()
        self._secondary.setLayout(row)
        layout.addWidget(self._secondary)

        self._settings = QPushButton("Abrir configurações")
        self._settings.clicked.connect(self.settings_requested.emit)
        layout.addWidget(self._settings)

        self.show_key(None, None, False)

    def _emit(self, signal) -> None:
        if self._key is not None:
            signal.emit(self._key)

    def show_key(self, key: int | None, action: Action | None, is_mode: bool) -> None:
        self._key = key
        for w in (self._type, self._label, self._detail):
            w.set("")
        self._secondary.hide()
        self._settings.hide()
        self._edit.hide()

        if key is None:
            self._title.setText("Tecla")
            self._message.setText(
                "Selecione uma tecla no aparelho para ver o que ela faz. "
                "Clique duplo abre o editor direto."
            )
            self._message.show()
            return

        self._title.setText(f"Tecla {key + 1}")
        if is_mode:
            self._message.setText(
                "Esta é a tecla de modo: cada toque passa para o próximo "
                "perfil da lista. Para usá-la como atalho, escolha outra "
                "tecla de modo nas configurações."
            )
            self._message.show()
            self._settings.show()
            return

        self._edit.show()
        if action is None:
            self._message.setText("Nenhuma ação. Configure o que esta tecla faz.")
            self._message.show()
            self._edit.setText("Configurar ação")
            return

        self._message.hide()
        kind = action_type(action.type)
        self._type.set(kind.title if kind else action.type)
        self._label.set(action.label)
        self._detail.set(describe(action))
        self._edit.setText("Editar ação")
        self._secondary.show()


class IconCard(QFrame):
    """Ícone do perfil, com a prévia exata no OLED."""

    icon_changed = Signal()

    def __init__(self, store: Store) -> None:
        super().__init__()
        self._store = store
        self._profile: Profile | None = None

        frame, layout, title = _card("Ícone do perfil")
        _wrap(frame, self)
        layout.addWidget(title)

        self._preview = OledPreview(pixel=2.0, padding=8)
        self._preview.setToolTip("Exatamente como o ícone aparece no display")
        # Passo de 2 px por ponto: grande o bastante para ler o desenho, sem
        # empurrar o resto do painel para fora da tela.
        self._preview.setFixedHeight(64 * 2 + 16)
        layout.addWidget(self._preview)

        self._warning = QLabel()
        self._warning.setWordWrap(True)
        self._warning.setStyleSheet(f"color:{style.WARNING}; font-size:12px;")
        self._warning.hide()
        layout.addWidget(self._warning)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self._choose = QPushButton("Escolher imagem")
        self._choose.setIcon(glyphs.icon("image", style.TEXT))
        self._choose.clicked.connect(self._set_icon)
        self._remove = QPushButton("Remover")
        self._remove.setObjectName("ghost")
        self._remove.clicked.connect(self._clear_icon)
        buttons.addWidget(self._choose, 1)
        buttons.addWidget(self._remove)
        layout.addLayout(buttons)

        guide = QLabel(
            "Use PNG quadrado com fundo transparente e desenho chapado, sem "
            "texto miúdo. Ele ocupa a altura do display (60 pontos), só "
            "aceso ou apagado. Sem ícone, o display mostra o nome do perfil."
        )
        guide.setObjectName("caption")
        guide.setWordWrap(True)
        layout.addWidget(guide)

    def show_profile(self, profile: Profile | None) -> None:
        self._profile = profile
        self._choose.setEnabled(profile is not None)
        self._remove.setVisible(bool(profile and profile.icon_path))
        self._warning.hide()
        if profile is None:
            self._preview.show_frame(oled_render.new_frame())
            return
        self._preview.show_frame(display.icon_frame(profile))
        if profile.icon_path:
            self._check_quality(profile.icon_path)

    def _check_quality(self, path: str) -> None:
        try:
            lit = icons.lit_fraction(icons.icon_bitmap(path, *display.ICON_AREA))
        except Exception:  # Pillow levanta tipos variados
            self._warning.setText(
                "A imagem não pôde ser lida; o display mostra o nome do perfil."
            )
            self._warning.show()
            return
        if lit < 0.02:
            self._warning.setText(
                "Quase nada acende com esta imagem. Use um desenho mais "
                "grosso ou com mais contraste."
            )
        elif lit > 0.45:
            self._warning.setText(
                "A imagem acende quase todos os pontos e vira um bloco. "
                "Prefira um desenho com fundo transparente."
            )
        else:
            return
        self._warning.show()

    def _set_icon(self) -> None:
        profile = self._profile
        if profile is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Escolher ícone do perfil",
            "",
            "Imagens (*.png *.jpg *.jpeg *.bmp *.gif *.webp)",
        )
        if not path:
            return
        try:
            self._store.import_icon(path, profile)
        except (OSError, ValueError) as exc:
            # Sem isto a exceção subia para fora do slot Qt, onde o PySide6
            # pode encerrar o processo.
            QMessageBox.warning(
                self,
                "Não foi possível usar esta imagem",
                f"{exc}\n\nEscolha outro arquivo — de preferência um PNG com "
                "fundo transparente e desenho simples.",
            )
            return
        self.show_profile(profile)
        self.icon_changed.emit()

    def _clear_icon(self) -> None:
        profile = self._profile
        if profile is None:
            return
        profile.icon_path = None
        self._store.save()
        self.show_profile(profile)
        self.icon_changed.emit()


class DisplayCard(QFrame):
    """O que o display mostra neste perfil, numa lista única de opções.

    "Ícone" e os itens da tela montada (hora, data, nome) se excluem:
    marcar o ícone desmarca os outros; marcar qualquer outro desmarca o
    ícone. Desmarcar o ícone traz a tela montada com hora, data e nome;
    desmarcar o último item (sem texto livre) volta ao ícone — o display
    nunca fica sem nada escolhido.

    A configuração é do perfil selecionado na lista (cada perfil tem a sua).
    """

    display_settings_changed = Signal()

    _ITEMS = (
        ("show_time", "Hora"),
        ("show_date", "Data"),
        ("show_profile", "Nome do perfil"),
    )

    def __init__(self, store: Store) -> None:
        super().__init__()
        self._store = store
        self._profile: Profile | None = None
        self._loading = False

        frame, layout, title = _card("Tela do display")
        _wrap(frame, self)
        layout.addWidget(title)

        self._icon = QCheckBox("Ícone do perfil")
        self._icon.setToolTip("Só o ícone, ocupando a tela. Sem ícone, o nome.")
        self._icon.toggled.connect(self._on_icon)
        layout.addWidget(self._icon)

        self._boxes: dict[str, QCheckBox] = {}
        for attr, text in self._ITEMS:
            box = QCheckBox(text)
            box.toggled.connect(lambda on, a=attr: self._on_item(a, on))
            layout.addWidget(box)
            self._boxes[attr] = box

        self._text = QLineEdit()
        self._text.setPlaceholderText("Texto livre (opcional)")
        self._text.setMaxLength(oled_render.TEXT_COLS)
        self._text.setToolTip(
            "Até 21 caracteres, sem acentos (a fonte do display só tem ASCII)."
        )
        self._text.textEdited.connect(self._on_text)
        layout.addWidget(self._text)

        self._splash = QCheckBox("Ícone por 1,5 s ao entrar no perfil")
        self._splash.toggled.connect(lambda on: self._save("icon_splash", on))
        layout.addWidget(self._splash)

        self.show_profile(None)

    # ---------------------------------------------------------------- API

    def show_profile(self, profile: Profile | None) -> None:
        """Mostra (e passa a editar) a configuração de ``profile``."""
        self._profile = profile
        self.setEnabled(profile is not None)
        self._sync()

    # ------------------------------------------------------------- estado

    def _sync(self) -> None:
        """Reflete a configuração do perfil nas caixas, sem disparar sinais."""
        cfg = self._profile.display if self._profile is not None else None
        icon_mode = cfg is None or cfg.mode == "icone"
        self._loading = True
        try:
            self._icon.setChecked(cfg is not None and icon_mode)
            for attr, box in self._boxes.items():
                box.setChecked(cfg is not None and not icon_mode and getattr(cfg, attr))
            self._text.setText(cfg.text if cfg is not None else "")
            self._splash.setChecked(cfg is not None and cfg.icon_splash)
        finally:
            self._loading = False
        # Texto e ícone na troca só valem para a tela montada.
        self._text.setEnabled(not icon_mode)
        self._splash.setEnabled(not icon_mode)

    def _on_icon(self, on: bool) -> None:
        if self._loading or self._profile is None:
            return
        cfg = self._profile.display
        if on:
            cfg.mode = "icone"
            for attr, _ in self._ITEMS:
                setattr(cfg, attr, False)
        else:
            # Sair do ícone: a tela montada começa com hora, data e nome.
            cfg.mode = "personalizado"
            for attr, _ in self._ITEMS:
                setattr(cfg, attr, True)
        self._commit()

    def _on_item(self, attr: str, on: bool) -> None:
        if self._loading or self._profile is None:
            return
        cfg = self._profile.display
        if on and cfg.mode == "icone":
            # Vindo do ícone: só o item marcado fica ligado.
            for other, _ in self._ITEMS:
                setattr(cfg, other, False)
        setattr(cfg, attr, on)
        cfg.mode = "personalizado"
        if not any(getattr(cfg, a) for a, _ in self._ITEMS) and not cfg.text.strip():
            cfg.mode = "icone"  # nada sobrou na tela montada: volta ao ícone
        self._commit()

    def _on_text(self, text: str) -> None:
        if self._loading or self._profile is None:
            return
        self._profile.display.text = text
        self._commit(resync=False)  # não mexe no campo enquanto se digita

    def _save(self, attr: str, value: Any) -> None:
        if self._loading or self._profile is None:
            return
        setattr(self._profile.display, attr, value)
        self._commit(resync=False)

    def _commit(self, resync: bool = True) -> None:
        self._store.save()
        if resync:
            self._sync()
        self.display_settings_changed.emit()


class FitScrollArea(QScrollArea):
    """Rolagem vertical que dá ao conteúdo a altura que ele pede.

    Com ``widgetResizable``, o QScrollArea ajusta o conteúdo à altura da
    janela sem considerar textos com quebra de linha (altura que depende
    da largura): quando os cartões não cabem, eles eram espremidos e se
    sobrepunham em vez de rolar. Aqui a altura mínima do conteúdo é
    recalculada para a largura atual sempre que o layout muda.

    Quando só a altura-por-largura muda (um texto que quebra em mais
    linhas, opções que aparecem), o Qt não avisa a área de rolagem; por
    isso quem muda o conteúdo chama :meth:`refit`.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)

    def setWidget(self, widget: QWidget) -> None:  # noqa: N802 — API Qt
        super().setWidget(widget)
        widget.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 — API Qt
        if obj is self.widget() and event.type() == QEvent.LayoutRequest:
            self._fit()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:  # noqa: N802 — API Qt
        super().resizeEvent(event)
        self._fit()

    def refit(self) -> None:
        """Recalcula a altura depois que o laço de eventos aplicar o layout."""
        QTimer.singleShot(0, self._fit)

    def _fit(self) -> None:
        widget = self.widget()
        layout = widget.layout() if widget is not None else None
        if widget is None or layout is None:
            return
        width = self.viewport().width()
        if layout.hasHeightForWidth():
            height = layout.totalHeightForWidth(width)
        else:
            height = layout.totalSizeHint().height()
        widget.setMinimumHeight(height)


class _KeyRow(QAbstractButton):
    """Linha do resumo de teclas: número, rótulo e o que a tecla faz."""

    def __init__(self, key: int, title: str, detail: str, is_mode: bool) -> None:
        super().__init__()
        self.key = key
        self._title = title
        self._detail = detail
        self._mode = is_mode
        self._hover = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(34)
        self.setToolTip(f"Tecla {key + 1}: {title}" + (f" — {detail}" if detail else ""))
        self.setAccessibleName(self.toolTip())

    def enterEvent(self, event) -> None:  # noqa: N802 — API Qt
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 — API Qt
        self._hover = False
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 — API Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        if self._hover or self.hasFocus():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(style.BG_RAISED))
            p.drawRoundedRect(r, 7, 7)
        badge = QRectF(6, (r.height() - 22) / 2, 22, 22)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(style.ACCENT_SOFT_RGB if self._mode else style.BG_PANEL))
        p.drawRoundedRect(badge, 6, 6)
        small = QFont(self.font())
        small.setPixelSize(11)
        small.setWeight(QFont.DemiBold)
        p.setFont(small)
        p.setPen(QColor(style.ACCENT_HOVER if self._mode else style.TEXT_MUTED))
        p.drawText(badge, Qt.AlignCenter, str(self.key + 1))

        x = badge.right() + 10
        title_font = QFont(self.font())
        title_font.setPixelSize(13)
        detail_font = QFont(self.font())
        detail_font.setPixelSize(12)
        fm_d = QFontMetrics(detail_font)
        fm_t = QFontMetrics(title_font)
        avail = r.width() - x - 8
        detail = fm_d.elidedText(self._detail, Qt.ElideRight, int(avail * 0.5))
        detail_w = fm_d.horizontalAdvance(detail)
        p.setFont(detail_font)
        p.setPen(QColor(style.TEXT_FAINT))
        p.drawText(
            QRectF(r.right() - 8 - detail_w, 0, detail_w, r.height()),
            Qt.AlignVCenter | Qt.AlignRight,
            detail,
        )
        p.setFont(title_font)
        p.setPen(QColor(style.ACCENT_HOVER if self._mode else style.TEXT))
        title_w = avail - detail_w - (12 if detail else 0)
        p.drawText(
            QRectF(x, 0, title_w, r.height()),
            Qt.AlignVCenter | Qt.AlignLeft,
            fm_t.elidedText(self._title, Qt.ElideRight, int(title_w)),
        )
        p.end()


class KeysCard(QFrame):
    """Resumo das teclas do perfil: quantas estão configuradas e o que fazem."""

    key_chosen = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        frame, layout, title = _card("Teclas")
        _wrap(frame, self)
        head = QHBoxLayout()
        head.addWidget(title)
        head.addStretch(1)
        self._count = QLabel()
        self._count.setObjectName("caption")
        head.addWidget(self._count)
        layout.addLayout(head)
        self._empty = QLabel(
            "Nenhuma tecla configurada. Clique numa tecla do aparelho para começar."
        )
        self._empty.setObjectName("hint")
        self._empty.setWordWrap(True)
        layout.addWidget(self._empty)
        self._rows_box = QVBoxLayout()
        self._rows_box.setSpacing(2)
        layout.addLayout(self._rows_box)
        self._rows: list[_KeyRow] = []

    def show_profile(self, profile: Profile | None, mode_key: int | None) -> None:
        for row in self._rows:
            self._rows_box.removeWidget(row)
            row.deleteLater()
        self._rows = []
        bindings = dict(profile.bindings) if profile is not None else {}
        if mode_key is not None:
            bindings.pop(mode_key, None)
        self._count.setText(f"{len(bindings)} de {KEY_COUNT} configuradas")
        entries: list[tuple[int, str, str, bool]] = []
        if mode_key is not None:
            entries.append((mode_key, "Tecla de modo", "troca o perfil", True))
        for key in sorted(bindings):
            action = bindings[key]
            kind = action_type(action.type)
            title = action.label or (kind.title if kind else action.type)
            entries.append((key, title, describe(action), False))
        entries.sort(key=lambda e: e[0])
        for key, title, detail, is_mode in entries:
            row = _KeyRow(key, title, detail, is_mode)
            row.clicked.connect(lambda _c=False, k=key: self.key_chosen.emit(k))
            self._rows_box.addWidget(row)
            self._rows.append(row)
        self._empty.setVisible(not entries)


class Inspector(QFrame):
    """Coluna direita, com duas visões.

    * **Perfil** (nada selecionado): o ícone do perfil no topo, a tela do
      display (ícone, hora, data, nome, texto) e o resumo das teclas.
    * **Tecla** (uma tecla clicada no aparelho): o que ela faz e os botões
      para editar, testar e limpar; "Voltar ao perfil" retorna à primeira.

    O título é o nome do perfil que está no centro da tela.
    """

    back_requested = Signal()

    def __init__(self, store: Store) -> None:
        super().__init__()
        self.setObjectName("inspector")
        self.setMinimumWidth(300)
        self.setMaximumWidth(400)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        # Cabeçalho fixo (fora da rolagem): nome do perfil e o ícone de recolher.
        self.header = header = QHBoxLayout()
        header.setContentsMargins(10, 14, 14, 4)
        header.setSpacing(6)
        self._title = QLabel("Perfil")
        self._title.setObjectName("sectionTitle")
        header.addWidget(self._title, stretch=1)
        outer.addLayout(header)

        self._scroll = scroll = FitScrollArea()
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 8, 14, 14)
        layout.setSpacing(14)

        self._back = QToolButton()
        self._back.setObjectName("bareIcon")
        self._back.setAutoRaise(True)
        self._back.setIcon(glyphs.icon("back", style.TEXT_MUTED, hover=style.TEXT))
        self._back.setText("Voltar ao perfil")
        self._back.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._back.setCursor(Qt.PointingHandCursor)
        self._back.clicked.connect(self.back_requested.emit)
        layout.addWidget(self._back, alignment=Qt.AlignLeft)

        self.key_card = KeyCard()
        self.icon_card = IconCard(store)
        self.display_card = DisplayCard(store)
        self.keys_card = KeysCard()
        for card in (self.key_card, self.icon_card, self.display_card, self.keys_card):
            layout.addWidget(card)
        layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        # Cartões que mudam de altura sozinhos (opções que aparecem).
        self.display_card.display_settings_changed.connect(self.refit)
        self.show_profile_view()

    def set_title(self, text: str) -> None:
        self._title.setText(text)
        self._title.setToolTip(text)

    def show_profile_view(self) -> None:
        self._back.hide()
        self.key_card.hide()
        for card in (self.icon_card, self.display_card, self.keys_card):
            card.show()
        self.refit()

    def show_key_view(self) -> None:
        for card in (self.icon_card, self.display_card, self.keys_card):
            card.hide()
        self._back.show()
        self.key_card.show()
        self.refit()

    def refit(self) -> None:
        """Chamar depois de mudar o conteúdo dos cartões."""
        self._scroll.refit()


__all__ = ["DisplayCard", "IconCard", "Inspector", "KeyCard", "KeysCard", "describe"]
