"""Key catalog, action description and Tk key-event translation.

Canonical key names follow pynput's ``Key`` attribute names for special keys
(``enter``, ``page_up``, ``media_volume_up`` ...) and plain lowercase
characters for printable keys (``a``, ``1``, ``-`` ...).
"""

MODIFIERS = ["ctrl", "shift", "alt", "cmd"]

MODIFIER_LABELS = {
    "ctrl": "Ctrl",
    "shift": "Shift",
    "alt": "Alt/Option",
    "cmd": "Cmd/Win",
}

# (group, canonical, label)
_SPECIAL = [
    ("Basic", "enter", "Enter"),
    ("Basic", "space", "Space"),
    ("Basic", "tab", "Tab"),
    ("Basic", "esc", "Esc"),
    ("Basic", "backspace", "BackSpace"),
    ("Basic", "delete", "Delete"),
    ("Basic", "insert", "Insert"),
    ("Basic", "caps_lock", "CapsLock"),
    ("Navigation", "up", "↑"),
    ("Navigation", "down", "↓"),
    ("Navigation", "left", "←"),
    ("Navigation", "right", "→"),
    ("Navigation", "home", "Home"),
    ("Navigation", "end", "End"),
    ("Navigation", "page_up", "PageUp"),
    ("Navigation", "page_down", "PageDown"),
    ("Media", "media_play_pause", "Play/Pause"),
    ("Media", "media_next", "Next Track"),
    ("Media", "media_previous", "Prev Track"),
    ("Media", "media_volume_up", "Volume Up"),
    ("Media", "media_volume_down", "Volume Down"),
    ("Media", "media_volume_mute", "Mute"),
    ("Other", "print_screen", "PrintScreen"),
    ("Other", "menu", "Menu"),
    ("Other", "pause", "Pause"),
    ("Other", "num_lock", "NumLock"),
    ("Other", "scroll_lock", "ScrollLock"),
]

_FUNCTION = [("Function", f"f{i}", f"F{i}") for i in range(1, 21)]
_LETTERS = [("Letter", chr(c), chr(c).upper()) for c in range(ord("a"), ord("z") + 1)]
_DIGITS = [("Digit", str(d), str(d)) for d in range(10)]
_SYMBOLS = [("Symbol", ch, ch) for ch in "-=[]\\;',./`"]

KEY_CATALOG = _LETTERS + _DIGITS + _SPECIAL + _FUNCTION + _SYMBOLS
KEY_LABELS = {k: lbl for _, k, lbl in KEY_CATALOG}
KEY_LABELS.update(MODIFIER_LABELS)
SPECIAL_KEY_NAMES = {k for _, k, _ in _SPECIAL + _FUNCTION} | set(MODIFIERS)


def catalog_display_values():
    """Values for the key combobox: '[group] label'."""
    return ["(none)"] + [f"[{g}] {lbl}" for g, _, lbl in KEY_CATALOG]


def catalog_value_to_key(value):
    if not value or value == "(none)":
        return None
    for g, k, lbl in KEY_CATALOG:
        if value == f"[{g}] {lbl}":
            return k
    return None


def key_to_catalog_value(key):
    for g, k, lbl in KEY_CATALOG:
        if k == key:
            return f"[{g}] {lbl}"
    return "(none)"


def key_label(key):
    return KEY_LABELS.get(key, key.upper() if len(key) == 1 else key)


def normalize_combo(keys):
    """Modifiers first in a fixed order, then the remaining keys (deduped)."""
    mods = [m for m in MODIFIERS if m in keys]
    rest = []
    for k in keys:
        if k not in MODIFIERS and k not in rest:
            rest.append(k)
    return mods + rest


# ----------------------------------------------------------------- actions
MOUSE_ACTIONS = [
    ("left", "Left Click"),
    ("right", "Right Click"),
    ("middle", "Middle Click"),
    ("scroll_up", "Scroll Up"),
    ("scroll_down", "Scroll Down"),
    ("scroll_left", "Scroll Left"),
    ("scroll_right", "Scroll Right"),
    ("move_up", "Move Cursor ↑"),
    ("move_down", "Move Cursor ↓"),
    ("move_left", "Move Cursor ←"),
    ("move_right", "Move Cursor →"),
]
MOUSE_LABELS = dict(MOUSE_ACTIONS)

ACTION_TYPES = [
    ("key", "Key"),
    ("mouse", "Mouse"),
    ("text", "Text"),
    ("none", "Off"),
]


def describe_action(action, short=False):
    """Human readable text for an action dict."""
    if not action:
        return "—"
    t = action.get("type")
    if t == "key":
        keys = action.get("keys") or []
        if not keys:
            return "—"
        sep = "+" if short else " + "
        return sep.join(key_label(k) for k in keys)
    if t == "mouse":
        return MOUSE_LABELS.get(action.get("button"), "?")
    if t == "text":
        txt = action.get("text", "")
        if short and len(txt) > 8:
            txt = txt[:7] + "…"
        return f"“{txt}”"
    if t == "none":
        return "Disabled"
    return "—"


def validate_action(action):
    """Return a cleaned action dict or None if invalid."""
    if not isinstance(action, dict):
        return None
    t = action.get("type")
    if t == "key":
        keys = [k for k in action.get("keys", []) if isinstance(k, str) and k]
        return {"type": "key", "keys": normalize_combo(keys)} if keys else None
    if t == "mouse":
        b = action.get("button")
        return {"type": "mouse", "button": b} if b in MOUSE_LABELS else None
    if t == "text":
        txt = action.get("text")
        return {"type": "text", "text": txt} if isinstance(txt, str) and txt else None
    if t == "none":
        return {"type": "none"}
    return None


# ------------------------------------------------------ Tk event translation
_TK_MODIFIERS = {
    "Shift_L": "shift", "Shift_R": "shift",
    "Control_L": "ctrl", "Control_R": "ctrl",
    "Alt_L": "alt", "Alt_R": "alt", "Option_L": "alt", "Option_R": "alt",
    "Meta_L": "cmd", "Meta_R": "cmd", "Super_L": "cmd", "Super_R": "cmd",
    "Win_L": "cmd", "Win_R": "cmd", "Command": "cmd", "Cmd_L": "cmd", "Cmd_R": "cmd",
}

_TK_SPECIAL = {
    "Return": "enter", "KP_Enter": "enter", "space": "space", "Tab": "tab",
    "ISO_Left_Tab": "tab", "Escape": "esc", "BackSpace": "backspace",
    "Delete": "delete", "KP_Delete": "delete", "Insert": "insert",
    "Caps_Lock": "caps_lock",
    "Up": "up", "Down": "down", "Left": "left", "Right": "right",
    "KP_Up": "up", "KP_Down": "down", "KP_Left": "left", "KP_Right": "right",
    "Home": "home", "End": "end", "Prior": "page_up", "Next": "page_down",
    "Page_Up": "page_up", "Page_Down": "page_down",
    "Print": "print_screen", "Menu": "menu", "App": "menu", "Pause": "pause",
    "Num_Lock": "num_lock", "Scroll_Lock": "scroll_lock",
}

_TK_SYMBOLS = {
    "minus": "-", "equal": "=", "bracketleft": "[", "bracketright": "]",
    "backslash": "\\", "semicolon": ";", "apostrophe": "'", "quoteright": "'",
    "comma": ",", "period": ".", "slash": "/", "grave": "`", "quoteleft": "`",
    # shifted symbols -> base key on a US layout
    "exclam": "1", "at": "2", "numbersign": "3", "dollar": "4", "percent": "5",
    "asciicircum": "6", "ampersand": "7", "asterisk": "8", "parenleft": "9",
    "parenright": "0", "underscore": "-", "plus": "=", "braceleft": "[",
    "braceright": "]", "bar": "\\", "colon": ";", "quotedbl": "'", "less": ",",
    "greater": ".", "question": "/", "asciitilde": "`",
}


def tk_modifier(keysym):
    return _TK_MODIFIERS.get(keysym)


def tk_event_to_key(keysym, char=""):
    """Translate a Tk keysym (+ char) to a canonical key name, or None."""
    if not keysym:
        return None
    if keysym in _TK_MODIFIERS:
        return _TK_MODIFIERS[keysym]
    if keysym in _TK_SPECIAL:
        return _TK_SPECIAL[keysym]
    if keysym in _TK_SYMBOLS:
        return _TK_SYMBOLS[keysym]
    if len(keysym) >= 2 and keysym[0] in "Ff" and keysym[1:].isdigit():
        n = int(keysym[1:])
        if 1 <= n <= 20:
            return f"f{n}"
    if keysym.startswith("KP_") and len(keysym) == 4 and keysym[3].isdigit():
        return keysym[3]
    if len(keysym) == 1 and keysym.isprintable():
        return keysym.lower()
    if char and len(char) == 1 and char.isprintable() and not char.isspace():
        return char.lower()
    return None
