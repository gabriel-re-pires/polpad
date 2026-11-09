"""Tokens de design e folha de estilo (QSS) do configurador.

Widgets não escrevem hexadecimal próprio: importam daqui, então trocar o tema
é mexer só neste arquivo. Roxo (#7A2EF0) é a única cor de ação; o ciano é
reservado ao OLED (cor física dos pixels do SSD1306).
"""

from __future__ import annotations

from string import Template

# Paleta crua
INK_0 = "#0C0D11"   # fundo da janela
INK_1 = "#13151B"   # painéis laterais
INK_2 = "#1A1D25"   # cartões, campos
INK_3 = "#22262F"   # superfícies elevadas, hover
INK_4 = "#2C313C"   # bordas
INK_5 = "#3A404D"   # bordas fortes
FOG_0 = "#EDEFF4"   # texto principal
FOG_1 = "#A3A9B8"   # texto secundário
FOG_2 = "#7E8497"   # texto terciário, dicas (4,5:1 sobre INK_1)
VIOLET_4 = "#9558F5"
VIOLET_5 = "#7A2EF0"
VIOLET_6 = "#6421D1"
MINT_5 = "#3DDC97"
CORAL_5 = "#FF6B7A"
AMBER_5 = "#F5B651"
CYAN_OLED = "#8FE6FF"

# Papéis semânticos (o que os componentes usam)
BG_APP = INK_0
BG_PANEL = INK_1
BG_SURFACE = INK_2
BG_RAISED = INK_3
BORDER = INK_4
BORDER_STRONG = INK_5
TEXT = FOG_0
TEXT_MUTED = FOG_1
TEXT_FAINT = FOG_2
ACCENT = VIOLET_5
ACCENT_HOVER = VIOLET_4
ACCENT_PRESSED = VIOLET_6
ACCENT_SOFT = "rgba(122, 46, 240, 0.18)"
ACCENT_SOFT_RGB = "#2E7A2EF0"  # o mesmo, no formato #AARRGGBB do QColor
ACCENT_TEXT = "#FFFFFF"
SUCCESS = MINT_5
DANGER = CORAL_5
WARNING = AMBER_5
OLED_LIT = CYAN_OLED
OLED_OFF = "#0A1014"

FONT_FAMILY = '"Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif'
FONT_DISPLAY = '"Segoe UI Variable Display", "Segoe UI", sans-serif'
SIZE_SMALL = 12
SIZE_BODY = 13
SIZE_TITLE = 15
SIZE_HEADLINE = 20

RADIUS_CONTROL = 8
RADIUS_CARD = 14

_QSS = Template(
    """
QWidget {
    background-color: transparent;
    color: $TEXT;
    font-family: $FONT_FAMILY;
    font-size: ${SIZE_BODY}px;
    selection-background-color: $ACCENT;
    selection-color: $ACCENT_TEXT;
}
QMainWindow, QDialog, QMessageBox, QInputDialog { background-color: $BG_APP; }
QWidget#appRoot { background-color: $BG_APP; }
QDialog#embeddedEditor { background-color: transparent; }

QFrame#sidebar {
    background-color: $BG_PANEL;
    border-right: 1px solid $BORDER;
}
QFrame#topBar {
    background-color: $BG_APP;
    border-bottom: 1px solid $BORDER;
}
QFrame#inspector {
    background-color: $BG_PANEL;
    border-left: 1px solid $BORDER;
}
QFrame#card {
    background-color: $BG_SURFACE;
    border: 1px solid $BORDER;
    border-radius: ${RADIUS_CARD}px;
}
QFrame#dangerCard {
    background-color: $BG_SURFACE;
    border: 1px solid $DANGER;
    border-radius: ${RADIUS_CARD}px;
}
QLabel#dangerTitle {
    color: $DANGER;
    font-size: ${SIZE_TITLE}px;
    font-weight: 600;
    padding: 2px 0;
}
QFrame#divider { background-color: $BORDER; max-height: 1px; min-height: 1px; }

QLabel#appTitle {
    font-family: $FONT_DISPLAY;
    font-size: 17px;
    font-weight: 600;
}
QLabel#appSubtitle, QLabel#hint, QLabel#caption {
    color: $TEXT_FAINT;
    font-size: ${SIZE_SMALL}px;
}
QLabel#hint { color: $TEXT_MUTED; }
QLabel#panelTitle, QLabel#sectionTitle {
    font-size: ${SIZE_TITLE}px;
    font-weight: 600;
    padding: 2px 0;
}
QLabel#headline {
    font-family: $FONT_DISPLAY;
    font-size: ${SIZE_HEADLINE}px;
    font-weight: 600;
}
QLabel#value { color: $TEXT; font-size: ${SIZE_BODY}px; }
QLabel#mono {
    font-family: "Cascadia Mono", "Consolas", monospace;
    color: $TEXT;
}

QLabel#pill {
    background-color: $BG_SURFACE;
    border: 1px solid $BORDER;
    border-radius: 13px;
    padding: 4px 12px;
    color: $TEXT_MUTED;
    font-size: ${SIZE_SMALL}px;
}
QLabel#pill[tone="ok"] { color: $SUCCESS; border-color: rgba(61, 220, 151, 0.35); }
QLabel#pill[tone="off"] { color: $DANGER; border-color: rgba(255, 107, 122, 0.35); }
QLabel#pill[tone="accent"] {
    color: $ACCENT_HOVER;
    background-color: $ACCENT_SOFT;
    border-color: rgba(122, 46, 240, 0.45);
}

QPushButton, QToolButton {
    background-color: $BG_SURFACE;
    border: 1px solid $BORDER;
    border-radius: ${RADIUS_CONTROL}px;
    padding: 7px 14px;
    color: $TEXT;
}
QPushButton:hover, QToolButton:hover {
    background-color: $BG_RAISED;
    border-color: $BORDER_STRONG;
}
QPushButton:pressed, QToolButton:pressed { background-color: $BG_PANEL; }
QPushButton:focus, QToolButton:focus { border-color: $ACCENT; }
QPushButton:disabled, QToolButton:disabled {
    color: $TEXT_FAINT;
    background-color: $BG_PANEL;
    border-color: $BORDER;
}
QPushButton#primary {
    background-color: $ACCENT;
    border-color: $ACCENT;
    color: $ACCENT_TEXT;
    font-weight: 600;
}
QPushButton#primary:hover {
    background-color: $ACCENT_HOVER;
    border-color: $ACCENT_HOVER;
}
QPushButton#primary:pressed { background-color: $ACCENT_PRESSED; }
QPushButton#primary:focus { border: 1px solid $FOG_0; }
QPushButton#primary:disabled {
    background-color: $BG_RAISED;
    border-color: $BORDER;
    color: $TEXT_FAINT;
}
QPushButton#ghost, QToolButton#ghost {
    background-color: transparent;
    border-color: transparent;
    color: $TEXT_MUTED;
}
QPushButton#ghost:hover, QToolButton#ghost:hover {
    background-color: $BG_RAISED;
    color: $TEXT;
}
QPushButton#danger { color: $DANGER; }
QPushButton#danger:hover { border-color: $DANGER; }
QToolButton#iconButton {
    padding: 6px;
    min-width: 22px;
    min-height: 22px;
}
QToolButton#iconButton:checked {
    background-color: $ACCENT_SOFT;
    border-color: rgba(122, 46, 240, 0.50);
}
/* Só o ícone (recolher colunas): contorno aparece apenas com foco de teclado. */
QToolButton#bareIcon {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px;
}
QToolButton#bareIcon:hover, QToolButton#bareIcon:pressed {
    background-color: transparent;
    border-color: transparent;
}
QToolButton#bareIcon:focus { border-color: $ACCENT; }
QToolButton::menu-indicator { image: none; width: 0; }
QToolButton#toastClose {
    color: $DANGER;
    border: none;
    background: transparent;
    padding: 0 4px;
    font-size: ${SIZE_TITLE}px;
    font-weight: 600;
}
QToolButton#toastClose:hover, QToolButton#toastClose:pressed {
    color: $DANGER;
    background: transparent;
    border: none;
}

QPushButton#segment {
    background-color: $BG_PANEL;
    border-radius: 0;
    padding: 6px 10px;
    color: $TEXT_MUTED;
}
QPushButton#segment[pos="first"] {
    border-top-left-radius: ${RADIUS_CONTROL}px;
    border-bottom-left-radius: ${RADIUS_CONTROL}px;
}
QPushButton#segment[pos="last"] {
    border-top-right-radius: ${RADIUS_CONTROL}px;
    border-bottom-right-radius: ${RADIUS_CONTROL}px;
    border-left: none;
}
QPushButton#segment:checked {
    background-color: $ACCENT_SOFT;
    border-color: $ACCENT;
    color: $TEXT;
    font-weight: 600;
}
QPushButton#segment[pos="last"]:checked { border-left: 1px solid $ACCENT; }

QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QKeySequenceEdit {
    background-color: $BG_PANEL;
    border: 1px solid $BORDER;
    border-radius: ${RADIUS_CONTROL}px;
    padding: 6px 10px;
    color: $TEXT;
}
QLineEdit:hover, QPlainTextEdit:hover, QComboBox:hover, QSpinBox:hover {
    border-color: $BORDER_STRONG;
}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: $ACCENT;
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { color: $TEXT_FAINT; }
QComboBox { padding-right: 28px; }
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 26px;
    border: none;
}
QComboBox::down-arrow {
    image: url("$CHEVRON");
    width: 12px;
    height: 12px;
    margin-right: 10px;
}
/* O popup é janela própria: sem fundo explícito herdaria o "transparent"
   global e mostraria cantos pretos. */
QComboBoxPrivateContainer {
    background-color: $BG_RAISED;
    border: 1px solid $BORDER_STRONG;
    border-radius: ${RADIUS_CONTROL}px;
}
QComboBox QAbstractItemView {
    background-color: $BG_RAISED;
    border: 1px solid $BORDER_STRONG;
    border-radius: ${RADIUS_CONTROL}px;
    padding: 4px;
    outline: 0;
}
QComboBox QAbstractItemView::item {
    padding: 6px 10px;
    border-radius: 6px;
    min-height: 22px;
}
QComboBox QAbstractItemView::item:selected {
    background-color: $ACCENT_SOFT;
    color: $TEXT;
}
QSpinBox::up-button, QSpinBox::down-button { width: 16px; border: none; }

QListWidget {
    background-color: $BG_PANEL;
    border: 1px solid $BORDER;
    border-radius: ${RADIUS_CONTROL}px;
    padding: 4px;
    outline: 0;
}
QListWidget::item { padding: 7px 8px; border-radius: 6px; }
QListWidget::item:hover { background-color: $BG_RAISED; }
QListWidget::item:selected { background-color: $ACCENT_SOFT; color: $TEXT; }
QListView#profileList { background-color: transparent; border: none; padding: 0; }

QCheckBox, QRadioButton { spacing: 9px; background: transparent; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
    background-color: $BG_PANEL;
    border: 1px solid $BORDER_STRONG;
}
QCheckBox::indicator { border-radius: 5px; }
QRadioButton::indicator { border-radius: 9px; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: $ACCENT_HOVER; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: $ACCENT;
    border-color: $ACCENT;
}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {
    background-color: $BG_APP;
    border-color: $BORDER;
}
QCheckBox:disabled, QRadioButton:disabled { color: $TEXT_FAINT; }
QGroupBox {
    border: 1px solid $BORDER;
    border-radius: ${RADIUS_CONTROL}px;
    margin-top: 14px;
    padding: 12px 10px 10px 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: $TEXT_MUTED;
}

QProgressBar {
    background-color: $BG_PANEL;
    border: 1px solid $BORDER;
    border-radius: 6px;
    height: 10px;
    text-align: center;
    color: $TEXT_MUTED;
}
QProgressBar::chunk { background-color: $ACCENT; border-radius: 5px; }

QMenu {
    background-color: $BG_RAISED;
    border: 1px solid $BORDER_STRONG;
    border-radius: 10px;
    padding: 5px;
}
QMenu::item { padding: 7px 26px 7px 14px; border-radius: 6px; }
QMenu::item:selected { background-color: $ACCENT_SOFT; }
QMenu::item:disabled { color: $TEXT_FAINT; }
QMenu::separator { height: 1px; background: $BORDER; margin: 5px 8px; }
QMenu::indicator { width: 14px; height: 14px; margin-left: 6px; }
QToolTip {
    background-color: $BG_RAISED;
    color: $TEXT;
    border: 1px solid $BORDER_STRONG;
    border-radius: 6px;
    padding: 6px 8px;
}

QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { width: 10px; background: transparent; margin: 2px; }
QScrollBar:horizontal { height: 10px; background: transparent; margin: 2px; }
QScrollBar::handle { background: $BORDER_STRONG; border-radius: 3px; min-height: 28px; }
QScrollBar::handle:hover { background: $TEXT_FAINT; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

QSplitter::handle { background-color: $BORDER; }
QStatusBar {
    background-color: $BG_APP;
    color: $TEXT_FAINT;
    border-top: 1px solid $BORDER;
    font-size: ${SIZE_SMALL}px;
}
QStatusBar::item { border: none; }
QLabel#statusVersion { color: $TEXT_FAINT; font-size: ${SIZE_SMALL}px; }
QDialogButtonBox QPushButton { min-width: 84px; }
"""
)


def _chevron_png() -> str:
    """Seta dos combos em PNG no temp (a QSS só aceita imagem por URL).

    Precisa de um ``QGuiApplication`` já criado.
    """
    import tempfile
    from pathlib import Path

    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QPen

    image = QImage(48, 48, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(TEXT_MUTED), 4.5)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.drawPolyline([QPointF(12, 19), QPointF(24, 31), QPointF(36, 19)])
    painter.end()
    folder = Path(tempfile.gettempdir()) / "macropad-ui"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "chevron-down.png"
    image.save(str(path))
    return path.as_posix()


def build_stylesheet() -> str:
    """Folha de estilo completa. Chamar depois de criar o ``QApplication``."""
    tokens = {name: value for name, value in globals().items() if name.isupper()}
    try:
        tokens["CHEVRON"] = _chevron_png()
    except OSError:
        tokens["CHEVRON"] = ""  # sem a seta, o combo continua funcional
    return _QSS.substitute(tokens)
