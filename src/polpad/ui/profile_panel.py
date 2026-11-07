"""Barra lateral de perfis ("saves") do usuário.

Lista os perfis na ordem em que a tecla de modo os percorre (arrastar
reordena) e marca com uma bolinha verde o que está ativo no aparelho. O
cabeçalho tem três ícones: ``+`` (novo perfil), a engrenagem (operações
sobre o perfil: ativar, renomear, apps vinculados, exportar, importar,
excluir) e o de recolher, posto pela coluna recolhível.

Recolhida, a coluna mostra só os ladrilhos dos perfis (:meth:`rail`): dá
para trocar o perfil em edição sem expandi-la.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import (
    QModelIndex,
    QPersistentModelIndex,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core import profile_io
from ..core.store import Store
from . import profile_tile, style
from .collapsible import bare_icon_button

ROLE_ID = Qt.UserRole
ROLE_ICON = Qt.UserRole + 1
ROLE_ACTIVE = Qt.UserRole + 3

ROW_H = 54
TILE = 36
RAIL_TILE = 30


def _nome_de_arquivo(nome: str) -> str:
    """Nome de perfil -> nome de arquivo seguro no Windows."""
    limpo = re.sub(r'[<>:"/\\|?*]', "_", nome).strip(" .")
    return limpo or "perfil"


def _draw_active_dot(p: QPainter, cx: float, cy: float, r: float = 4.0) -> None:
    """Bolinha verde de "perfil ativo", com halo — a mesma em todo lugar."""
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(61, 220, 151, 45))
    p.drawEllipse(QRectF(cx - r - 3, cy - r - 3, 2 * r + 6, 2 * r + 6))
    p.setBrush(QColor(style.SUCCESS))
    p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))


class _ProfileDelegate(QStyledItemDelegate):
    """Linha do perfil: ladrilho, nome e a bolinha verde se estiver ativo."""

    def sizeHint(self, _option, _index) -> QSize:  # noqa: N802 — API Qt
        return QSize(200, ROW_H)

    def paint(
        self,
        p: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(option.rect).adjusted(6, 2, -6, -2)
        selected = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)

        if selected:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(style.ACCENT_SOFT_RGB))
            p.drawRoundedRect(r, 10, 10)
            p.setBrush(QColor(style.ACCENT))
            bar = QRectF(r.left(), r.top() + 13, 3, r.height() - 26)
            p.drawRoundedRect(bar, 1.5, 1.5)
        elif hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(style.BG_RAISED))
            p.drawRoundedRect(r, 10, 10)

        name = index.data(Qt.DisplayRole) or ""
        tile = QRectF(r.left() + 12, r.center().y() - TILE / 2, TILE, TILE)
        ratio = p.device().devicePixelRatioF() if p.device() else 1.0
        p.drawPixmap(
            tile.topLeft(),
            profile_tile.tile(index.data(ROLE_ICON) or None, name, TILE, ratio),
        )

        badge_w = 0.0
        if index.data(ROLE_ACTIVE):
            _draw_active_dot(p, r.right() - 18, r.center().y())
            badge_w = 26.0

        text_left = tile.right() + 12
        text_w = r.right() - text_left - 10 - badge_w
        f_name = QFont(option.font)
        f_name.setPixelSize(13)
        f_name.setWeight(QFont.DemiBold)
        fm = QFontMetrics(f_name)
        p.setFont(f_name)
        p.setPen(QColor(style.TEXT))
        p.drawText(
            QRectF(text_left, r.top(), text_w, r.height()),
            Qt.AlignLeft | Qt.AlignVCenter,
            fm.elidedText(name, Qt.ElideRight, int(text_w)),
        )
        p.restore()


class _RailTile(QToolButton):
    """Ladrilho do perfil no trilho da coluna recolhida."""

    def __init__(self, profile_id: str, icon_path: str | None, name: str) -> None:
        super().__init__()
        self.profile_id = profile_id
        self._icon_path = icon_path
        self._name = name
        self.active = False
        self.current = False
        self.setFixedSize(RAIL_TILE + 8, RAIL_TILE + 8)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(name)
        self.setAccessibleName(f"Perfil {name}")
        self.setAutoRaise(True)
        self.setStyleSheet("QToolButton { background: transparent; border: none; }")

    def paintEvent(self, _event) -> None:  # noqa: N802 — API Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        tile = QRectF(4, 4, RAIL_TILE, RAIL_TILE)
        ratio = self.devicePixelRatioF()
        pm = profile_tile.tile(self._icon_path, self._name, RAIL_TILE, ratio)
        p.drawPixmap(tile.topLeft(), pm)
        if self.current or self.hasFocus():
            p.setPen(QColor(style.ACCENT))
            p.setBrush(Qt.NoBrush)
            radius = RAIL_TILE * 0.24 + 2
            p.drawRoundedRect(tile.adjusted(-2, -2, 2, 2), radius, radius)
        if self.active:
            _draw_active_dot(p, tile.right() - 1, tile.top() + 1, 3.5)
        p.end()


class ProfilePanel(QFrame):
    profile_selected = Signal(str)   # perfil escolhido para EDIÇÃO
    activate_requested = Signal(str)  # perfil a ATIVAR no dispositivo
    profiles_changed = Signal()

    def __init__(self, store: Store) -> None:
        super().__init__()
        self.setObjectName("sidebar")
        self._store = store
        self.setMinimumWidth(240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 18, 12, 14)
        layout.setSpacing(10)

        # Exposto para a coluna recolhível pôr o ícone de recolher aqui.
        self.header = header = QHBoxLayout()
        header.setContentsMargins(8, 0, 0, 0)
        header.setSpacing(2)
        title = QLabel("Perfis")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        new_btn = bare_icon_button("plus", "Novo perfil")
        new_btn.clicked.connect(self._new)
        header.addWidget(new_btn)
        # Engrenagem: as configurações do perfil, num menu.
        gear = bare_icon_button("settings", "Configurações do perfil")
        gear.setPopupMode(QToolButton.InstantPopup)
        gear.setMenu(self._build_menu(gear))
        header.addWidget(gear)
        layout.addLayout(header)

        self._list = QListWidget()
        self._list.setObjectName("profileList")
        self._delegate = _ProfileDelegate(self._list)
        self._list.setItemDelegate(self._delegate)
        self._list.setMouseTracking(True)
        self._list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._list.currentItemChanged.connect(self._on_selection)
        self._list.itemDoubleClicked.connect(
            lambda item: self.activate_requested.emit(item.data(ROLE_ID))
        )
        # Arrastar reordena a lista — e a ordem da lista é a ordem em que a
        # tecla de modo percorre os perfis.
        self._list.setDragDropMode(QAbstractItemView.InternalMove)
        self._list.setDefaultDropAction(Qt.MoveAction)
        self._list.model().rowsMoved.connect(self._on_rows_moved)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(
            lambda pos: self._build_menu(self).exec(
                self._list.viewport().mapToGlobal(pos)
            )
        )
        layout.addWidget(self._list, stretch=1)
        self.setFocusProxy(self._list)

        hint = QLabel("A tecla de modo segue esta ordem. Arraste para mudar.")
        hint.setObjectName("caption")
        hint.setWordWrap(True)
        hint.setContentsMargins(8, 0, 8, 0)
        layout.addWidget(hint)

        # Ladrilhos para o trilho da coluna recolhida.
        self._rail = QWidget()
        self._rail_layout = QVBoxLayout(self._rail)
        self._rail_layout.setContentsMargins(0, 6, 0, 0)
        self._rail_layout.setSpacing(4)
        self._rail_tiles: list[_RailTile] = []

        self.refresh()

    # ---------------------------------------------------------------- API

    def rail(self) -> QWidget:
        """Os ladrilhos dos perfis, para o trilho da coluna recolhida."""
        return self._rail

    def refresh(self) -> None:
        current = self.selected_profile_id()
        profile_tile.forget()
        self._list.blockSignals(True)
        self._list.clear()
        for profile in self._store.profiles:
            item = QListWidgetItem(profile.name)
            item.setData(ROLE_ID, profile.id)
            item.setData(ROLE_ICON, profile.icon_path or "")
            item.setData(ROLE_ACTIVE, profile.id == self._store.active_profile_id)
            item.setToolTip(
                "Perfil ativo no macropad"
                if profile.id == self._store.active_profile_id
                else "Clique duplo para ativar no macropad"
            )
            self._list.addItem(item)
            if profile.id == current:
                self._list.setCurrentItem(item)
        self._list.blockSignals(False)
        if self._list.currentRow() < 0 and self._list.count() > 0:
            self._list.setCurrentRow(0)
        self._rebuild_rail()

    def _rebuild_rail(self) -> None:
        for tile in self._rail_tiles:
            self._rail_layout.removeWidget(tile)
            tile.deleteLater()
        self._rail_tiles = []
        current = self.selected_profile_id()
        for profile in self._store.profiles:
            tile = _RailTile(profile.id, profile.icon_path, profile.name)
            tile.active = profile.id == self._store.active_profile_id
            tile.current = profile.id == current
            tile.clicked.connect(lambda _c=False, pid=profile.id: self._select(pid))
            self._rail_layout.addWidget(tile, alignment=Qt.AlignHCenter)
            self._rail_tiles.append(tile)

    def selected_profile_id(self) -> str | None:
        item = self._list.currentItem()
        return item.data(ROLE_ID) if item else None

    def select(self, profile_id: str) -> None:
        self._select(profile_id)

    # ------------------------------------------------------------- eventos

    def _build_menu(self, parent: QWidget) -> QMenu:
        """Configurações do perfil: o menu da engrenagem e do botão direito."""
        menu = QMenu(parent)
        menu.aboutToShow.connect(lambda: self._update_menu(menu))
        for text, slot, needs_profile in (
            ("Ativar no macropad", self._activate, True),
            (None, None, False),
            ("Renomear…", self._rename, True),
            ("Apps vinculados…", self._edit_auto_apps, True),
            (None, None, False),
            ("Exportar…", self._export, True),
            ("Importar…", self._import, False),
            (None, None, False),
            ("Excluir…", self._delete, True),
        ):
            if text is None:
                menu.addSeparator()
                continue
            act = menu.addAction(text)
            act.setData(needs_profile)
            act.triggered.connect(slot)
        return menu

    def _update_menu(self, menu: QMenu) -> None:
        has = self.selected_profile_id() is not None
        for act in menu.actions():
            if act.data():
                act.setEnabled(has)

    def _on_selection(self, current: QListWidgetItem | None, _prev=None) -> None:
        if current is not None:
            pid = current.data(ROLE_ID)
            for tile in self._rail_tiles:
                tile.current = tile.profile_id == pid
                tile.update()
            self.profile_selected.emit(pid)

    def _on_rows_moved(self, *_args) -> None:
        """Persiste a nova ordem depois de um arrastar-e-soltar."""
        ordem = [self._list.item(i).data(ROLE_ID) for i in range(self._list.count())]
        por_id = {p.id: p for p in self._store.profiles}
        reordenados = [por_id[pid] for pid in ordem if pid in por_id]
        # Rede de segurança: nenhum perfil pode sumir por não estar na lista.
        vistos = set(ordem)
        reordenados += [p for p in self._store.profiles if p.id not in vistos]

        self._store.profiles = reordenados
        self._store.save()
        self.profiles_changed.emit()

    def _new(self) -> None:
        name, ok = QInputDialog.getText(self, "Novo perfil", "Nome do perfil:")
        if ok and name.strip():
            profile = self._store.add_profile(name.strip())
            self.refresh()
            self._select(profile.id)
            self.profiles_changed.emit()

    def _rename(self) -> None:
        profile = self._store.profile_by_id(self.selected_profile_id())
        if profile is None:
            return
        name, ok = QInputDialog.getText(
            self, "Renomear perfil", "Novo nome:", text=profile.name
        )
        if ok and name.strip():
            profile.name = name.strip()
            self._store.save()
            self.refresh()
            self.profiles_changed.emit()

    def _delete(self) -> None:
        profile = self._store.profile_by_id(self.selected_profile_id())
        if profile is None:
            return
        answer = QMessageBox.question(
            self,
            "Excluir perfil",
            f"Excluir o perfil “{profile.name}” e todos os seus atalhos?",
        )
        if answer == QMessageBox.Yes:
            self._store.remove_profile(profile.id)
            self.refresh()
            self.profiles_changed.emit()

    # ------------------------------------------------- exportar/importar

    def _export(self) -> None:
        profile = self._store.profile_by_id(self.selected_profile_id())
        if profile is None:
            return
        sugestao = f"{_nome_de_arquivo(profile.name)}.json"
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Exportar perfil", sugestao, "Perfil do macropad (*.json)"
        )
        if not caminho:
            return
        try:
            self._store.export_profile(profile, Path(caminho))
        except OSError as exc:
            QMessageBox.critical(self, "Exportar perfil", f"Falha ao gravar: {exc}")
            return
        QMessageBox.information(
            self, "Exportar perfil", f"Perfil “{profile.name}” exportado."
        )

    def _import(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Importar perfil", "", "Perfil do macropad (*.json)"
        )
        if not caminho:
            return
        try:
            # utf-8-sig: aceita também o arquivo salvo com BOM.
            texto = Path(caminho).read_text(encoding="utf-8-sig")
            importado = profile_io.from_json(texto)
        except OSError as exc:
            QMessageBox.critical(self, "Importar perfil", f"Falha ao ler: {exc}")
            return
        except UnicodeDecodeError:
            # Imagem ou outro binário com extensão .json.
            QMessageBox.critical(
                self, "Importar perfil", "Arquivo inválido: não é um arquivo de texto."
            )
            return
        except (profile_io.ProfileFileError, ValueError) as exc:
            QMessageBox.critical(self, "Importar perfil", f"Arquivo inválido: {exc}")
            return

        if not self._confirmar_acoes_sensiveis(importado):
            return

        profile = self._store.add_imported_profile(importado)
        self.refresh()
        self._select(profile.id)
        self.profiles_changed.emit()

    def _confirmar_acoes_sensiveis(self, importado) -> bool:
        """Mostra o que o perfil executaria antes de aceitá-lo.

        Um perfil vindo de terceiros pode conter ações que rodam comandos
        de shell ou abrem programas com os privilégios de quem importa.
        """
        if not importado.sensitive:
            return True
        linhas = "\n".join(
            f"  • Tecla {tecla + 1}: {alvo or '(sem alvo)'}"
            for tecla, alvo in importado.sensitive[:10]
        )
        restantes = len(importado.sensitive) - 10
        if restantes > 0:
            linhas += f"\n  • … e mais {restantes}"
        answer = QMessageBox.warning(
            self,
            "Importar perfil",
            f"O perfil “{importado.profile.name}” executa comandos ou abre "
            f"programas nesta máquina:\n\n{linhas}\n\n"
            "Importe apenas de fontes confiáveis. Continuar?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return answer == QMessageBox.Yes

    def _edit_auto_apps(self) -> None:
        from .auto_apps_dialog import AutoAppsDialog

        profile = self._store.profile_by_id(self.selected_profile_id())
        if profile is None:
            return
        dialog = AutoAppsDialog(self, profile)
        if dialog.exec() == AutoAppsDialog.Accepted:
            self._store.save()

    def _activate(self) -> None:
        profile_id = self.selected_profile_id()
        if profile_id:
            self.activate_requested.emit(profile_id)

    def _select(self, profile_id: str) -> None:
        for i in range(self._list.count()):
            if self._list.item(i).data(ROLE_ID) == profile_id:
                self._list.setCurrentRow(i)
                return

