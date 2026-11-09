"""Nomes de tecla (``["ctrl", "shift", "p"]``, como ficam no arquivo) <-> ``pynput``."""

from __future__ import annotations

import sys

from pynput.keyboard import Key, KeyCode

# Aliases aceitos na configuração -> atributo de pynput.keyboard.Key.
_SPECIAL: dict[str, Key] = {
    "ctrl": Key.ctrl,
    "control": Key.ctrl,
    "alt": Key.alt,
    "altgr": Key.alt_gr,
    "shift": Key.shift,
    "win": Key.cmd,
    "windows": Key.cmd,
    "cmd": Key.cmd,
    "super": Key.cmd,
    "enter": Key.enter,
    "return": Key.enter,
    "tab": Key.tab,
    "esc": Key.esc,
    "escape": Key.esc,
    "space": Key.space,
    "backspace": Key.backspace,
    "delete": Key.delete,
    "del": Key.delete,
    "insert": Key.insert,
    "home": Key.home,
    "end": Key.end,
    "pageup": Key.page_up,
    "pagedown": Key.page_down,
    "up": Key.up,
    "down": Key.down,
    "left": Key.left,
    "right": Key.right,
    "capslock": Key.caps_lock,
    "printscreen": Key.print_screen,
    "pause": Key.pause,
    "menu": Key.menu,
}
_SPECIAL.update({f"f{i}": getattr(Key, f"f{i}") for i in range(1, 21)})

MODIFIERS = {"ctrl", "control", "alt", "altgr", "shift", "win", "windows", "cmd", "super"}

# Teclas de mídia do Windows (códigos de tecla virtual).
MEDIA_VK = {
    "play_pause": 0xB3,
    "next_track": 0xB0,
    "prev_track": 0xB1,
    "stop": 0xB2,
    "volume_up": 0xAF,
    "volume_down": 0xAE,
    "volume_mute": 0xAD,
}

# As mesmas teclas no X11/Wayland: keysyms XF86Audio*, que o pynput aceita
# como "vk" no backend xorg (é assim que ele define Key.media_*).
MEDIA_KEYSYM = {
    "play_pause": 0x1008FF14,   # XF86AudioPlay
    "next_track": 0x1008FF17,   # XF86AudioNext
    "prev_track": 0x1008FF16,   # XF86AudioPrev
    "stop": 0x1008FF15,         # XF86AudioStop
    "volume_up": 0x1008FF13,    # XF86AudioRaiseVolume
    "volume_down": 0x1008FF11,  # XF86AudioLowerVolume
    "volume_mute": 0x1008FF12,  # XF86AudioMute
}

MEDIA_TITLES = {
    "play_pause": "Tocar/Pausar",
    "next_track": "Próxima faixa",
    "prev_track": "Faixa anterior",
    "stop": "Parar",
    "volume_up": "Aumentar volume",
    "volume_down": "Diminuir volume",
    "volume_mute": "Mudo",
}


def resolve(name: str) -> Key | KeyCode:
    """Converte um nome de tecla no objeto pynput correspondente."""
    name = name.strip().lower()
    if name in _SPECIAL:
        return _SPECIAL[name]
    if len(name) == 1:
        # No Windows vai pelo código virtual: como caractere, com Shift o
        # pynput manda um pacote Unicode sem código de tecla e Ctrl+Shift+P
        # não chega como atalho.
        if sys.platform == "win32":
            vk = _char_vk(name)
            if vk is not None:
                return KeyCode.from_vk(vk)
        return KeyCode.from_char(name)
    raise ValueError(f"tecla desconhecida: {name!r}")


def _vk_key_scan(char: str) -> int:
    """``VkKeyScanW``: byte baixo = código virtual, alto = modificadores."""
    if sys.platform != "win32":
        return -1
    import ctypes

    return int(ctypes.windll.user32.VkKeyScanW(ctypes.c_wchar(char)))


def _char_vk(char: str) -> int | None:
    """Código virtual da tecla que digita ``char`` sem modificadores.

    ``None`` se o layout não a tiver ou ela exigir Shift/AltGr (ex.: "!").
    """
    if "a" <= char <= "z" or "0" <= char <= "9":
        return ord(char.upper())
    scan = _vk_key_scan(char) & 0xFFFF
    if scan == 0xFFFF or scan & 0xFF00:
        return None
    return scan & 0xFF


def is_valid(name: str) -> bool:
    try:
        resolve(name)
        return True
    except ValueError:
        return False


def media_key(control: str) -> KeyCode | None:
    """Tecla de mídia da plataforma atual; ``None`` se o controle não existe."""
    codes = MEDIA_VK if sys.platform == "win32" else MEDIA_KEYSYM
    code = codes.get(control)
    return None if code is None else KeyCode.from_vk(code)


# Teclas especiais do Qt -> nome aceito por ``resolve``.
_QT_SPECIAL: dict[int, str] = {
    0x01000004: "enter",     # Qt.Key_Return
    0x01000005: "enter",     # Qt.Key_Enter
    0x01000001: "tab",       # Qt.Key_Tab
    0x01000000: "esc",       # Qt.Key_Escape
    0x20: "space",           # Qt.Key_Space
    0x01000003: "backspace",
    0x01000007: "delete",
    0x01000006: "insert",
    0x01000010: "home",
    0x01000011: "end",
    0x01000016: "pageup",
    0x01000017: "pagedown",
    0x01000013: "up",
    0x01000015: "down",
    0x01000012: "left",
    0x01000014: "right",
    0x01000024: "capslock",
    0x01000009: "printscreen",
    0x01000008: "pause",
    0x01000055: "menu",
}
_QT_SPECIAL.update({0x01000030 + i: f"f{i + 1}" for i in range(20)})  # Key_F1..F20

# Teclas do ABNT2 que não são letra nem número: o código do Qt não depende
# dos modificadores, e o nome é o caractere que ``resolve`` aceita.
_QT_CHARS: dict[int, str] = {
    0xC7: "ç",          # Qt.Key_Ccedilla
    0x01001251: "´",    # Qt.Key_Dead_Acute
    0x01001253: "~",    # Qt.Key_Dead_Tilde
}

_QT_MODIFIERS = (
    (0x04000000, "ctrl"),   # Qt.ControlModifier
    (0x08000000, "alt"),    # Qt.AltModifier
    (0x02000000, "shift"),  # Qt.ShiftModifier
    (0x10000000, "win"),    # Qt.MetaModifier
)


def names_from_qt(sequence: object) -> list[str]:
    """Converte uma ``QKeySequence`` (tipada ``object``, sem Qt aqui) em nomes.

    Lista vazia se só houver modificadores ou a tecla não for representável.
    """
    try:
        combined = int(sequence[0].toCombined())  # type: ignore[index]
    except (IndexError, AttributeError, TypeError):
        return []
    modifiers = combined & 0xFE000000
    key = combined & 0x01FFFFFF
    names = [name for flag, name in _QT_MODIFIERS if modifiers & flag]
    if key in _QT_SPECIAL:
        names.append(_QT_SPECIAL[key])
    elif 0x20 < key < 0x7F:
        names.append(chr(key).lower())
    else:
        return []
    return names


# Códigos de tecla virtual do Windows que não dependem do layout.
_VK_LETTER = range(0x41, 0x5B)    # A..Z
_VK_DIGIT = range(0x30, 0x3A)     # 0..9
_VK_NUMPAD = range(0x60, 0x6A)    # teclado numérico 0..9

# Teclas que só modificam (pressionadas sozinhas, não fecham a combinação).
QT_MODIFIER_KEYS: dict[int, str] = {
    0x01000021: "ctrl",   # Qt.Key_Control
    0x01000020: "shift",  # Qt.Key_Shift
    0x01000023: "alt",    # Qt.Key_Alt
    0x01001103: "alt",    # Qt.Key_AltGr
    0x01000022: "win",    # Qt.Key_Meta
}


# No X11 e no Wayland (xkb) o ``nativeVirtualKey`` do Qt é o keysym, não um
# código virtual do Windows: o "a" minúsculo (0x61) cairia na faixa do
# teclado numérico acima e seria gravado como "1".
_XKB = sys.platform.startswith("linux")
_KEYSYM_LOWER = range(0x61, 0x7B)      # a..z
_KEYSYM_UPPER = range(0x41, 0x5B)      # A..Z (com Shift ou Caps Lock)
_KEYSYM_DIGIT = range(0x30, 0x3A)      # 0..9
_KEYSYM_KP_DIGIT = range(0xFFB0, 0xFFBA)  # KP_0..KP_9
# Com Shift, o keysym da fileira de números já é o símbolo ("exclam"); a
# tecla física vem do código X (evdev + 8), que não depende do layout.
_XKB_DIGIT_ROW = {10 + i: d for i, d in enumerate("1234567890")}


def _main_key_xkb(keysym: int, scan_code: int) -> str | None:
    if keysym in _KEYSYM_LOWER or keysym in _KEYSYM_DIGIT:
        return chr(keysym)
    if keysym in _KEYSYM_UPPER:
        return chr(keysym).lower()
    if keysym in _KEYSYM_KP_DIGIT:
        return str(keysym - 0xFFB0)
    return _XKB_DIGIT_ROW.get(scan_code)


def _main_key_windows(native_vk: int) -> str | None:
    if native_vk in _VK_LETTER or native_vk in _VK_DIGIT:
        return chr(native_vk).lower()
    if native_vk in _VK_NUMPAD:
        return str(native_vk - 0x60)
    return None


def names_from_event(
    key: int,
    modifiers: int,
    native_vk: int = 0,
    native_scan: int = 0,
    *,
    xkb: bool = _XKB,
) -> list[str]:
    """Converte uma tecla pressionada (inteiros de ``QKeyEvent``) em nomes.

    Letras e números vêm do código nativo, para ``Shift+1`` não virar ``!``.
    ``xkb``: keysym e código X (Linux) ou código virtual (Windows). Lista
    vazia se a tecla não for representável ou for só modificador.
    """
    if key in QT_MODIFIER_KEYS:
        return []
    names = [name for flag, name in _QT_MODIFIERS if modifiers & flag]
    main = (
        _main_key_xkb(native_vk, native_scan) if xkb else _main_key_windows(native_vk)
    )
    if main is not None:
        names.append(main)
    elif key in _QT_SPECIAL:
        names.append(_QT_SPECIAL[key])
    elif key in _QT_CHARS:
        names.append(_QT_CHARS[key])
    elif 0x20 < key < 0x7F:
        names.append(chr(key).lower())
    else:
        return []
    return names


_PRETTY = {
    "ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "altgr": "AltGr",
    "shift": "Shift", "win": "Win", "windows": "Win", "cmd": "Win", "super": "Win",
    "enter": "Enter", "return": "Enter", "tab": "Tab", "esc": "Esc",
    "escape": "Esc", "space": "Espaço", "backspace": "Backspace",
    "delete": "Delete", "del": "Delete", "insert": "Insert", "home": "Home",
    "end": "End", "pageup": "PgUp", "pagedown": "PgDn", "up": "↑",
    "down": "↓", "left": "←", "right": "→", "capslock": "Caps Lock",
    "printscreen": "Print Screen", "pause": "Pause", "menu": "Menu",
}


def pretty_name(name: str) -> str:
    """Nome de exibição de uma tecla: ``ctrl`` -> ``Ctrl``, ``c`` -> ``C``."""
    name = name.strip().lower()
    if name in _PRETTY:
        return _PRETTY[name]
    if name.startswith("f") and name[1:].isdigit():
        return name.upper()
    return name.upper() if len(name) == 1 else name


def pretty(names: list[str]) -> str:
    """Combinação para exibir ao usuário: ``["ctrl", "c"]`` -> ``Ctrl + C``."""
    return " + ".join(pretty_name(n) for n in names)
