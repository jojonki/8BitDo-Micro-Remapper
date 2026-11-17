"""Profiles and settings persisted as JSON in the per-user config directory."""

import json
import os
import re
import sys

from .keepalive import DEFAULT_POWER_OFF, normalize_power_off
from .keys import validate_action
from .layout import ASSIGNABLE_IDS as BUTTON_IDS

DEFAULT_MAPPINGS = {
    "up": {"type": "key", "keys": ["up"]},
    "down": {"type": "key", "keys": ["down"]},
    "left": {"type": "key", "keys": ["left"]},
    "right": {"type": "key", "keys": ["right"]},
    "a": {"type": "key", "keys": ["enter"]},
    "b": {"type": "key", "keys": ["esc"]},
    "x": {"type": "key", "keys": ["space"]},
    "y": {"type": "key", "keys": ["tab"]},
    "l": {"type": "key", "keys": ["page_up"]},
    "r": {"type": "key", "keys": ["page_down"]},
    "l2": {"type": "key", "keys": ["shift"]},
    "r2": {"type": "key", "keys": ["ctrl"]},
    "minus": {"type": "key", "keys": ["backspace"]},
    "plus": {"type": "key", "keys": ["enter"]},
}


def config_dir():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "8BitDoMicroRemapper")
    elif sys.platform == "darwin":
        d = os.path.expanduser("~/Library/Application Support/8BitDoMicroRemapper")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        d = os.path.join(base, "8bitdo-micro-remapper")
    override = os.environ.get("MICRO_REMAPPER_HOME")
    if override:
        d = override
    os.makedirs(os.path.join(d, "profiles"), exist_ok=True)
    return d


def _atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# ---------------------------------------------------------------- settings
def load_settings():
    s = _read(os.path.join(config_dir(), "settings.json"), {})
    if not isinstance(s, dict):
        s = {}
    s.setdefault("profile", "default")
    s.setdefault("source_map", {})      # learned physical->logical bindings
    s.setdefault("repeat", True)
    s.setdefault("enabled", True)
    s.setdefault("force_raw", False)
    s.setdefault("check_updates", True)     # look for a new release at launch
    # macOS: seize the pad so the Home button can't launch the Games app
    s.setdefault("exclusive", False)  # use macOS Settings > Game Controllers > Home Button instead
    # idle minutes before the pad powers itself off; None = never (see keepalive.py)
    s["power_off"] = normalize_power_off(s.get("power_off", DEFAULT_POWER_OFF))
    if not isinstance(s["source_map"], dict):
        s["source_map"] = {}
    return s


def save_settings(s):
    _atomic_write(os.path.join(config_dir(), "settings.json"), s)


# ---------------------------------------------------------------- profiles
def _safe_name(name):
    name = name.strip()
    return re.sub(r'[\\/:*?"<>|]', "_", name) or "profile"


def profile_path(name):
    return os.path.join(config_dir(), "profiles", _safe_name(name) + ".json")


def list_profiles():
    d = os.path.join(config_dir(), "profiles")
    names = sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json"))
    if "default" not in names:
        save_profile("default", DEFAULT_MAPPINGS)
        names = sorted(names + ["default"])
    return names


def clean_mappings(raw):
    out = {}
    if isinstance(raw, dict):
        for bid in BUTTON_IDS:
            a = validate_action(raw.get(bid))
            if a:
                out[bid] = a
    return out


def load_profile(name):
    data = _read(profile_path(name), None)
    if data is None:
        if name == "default":
            return dict(DEFAULT_MAPPINGS)
        return {}
    return clean_mappings(data.get("mappings") if isinstance(data, dict) else None)


def save_profile(name, mappings):
    _atomic_write(profile_path(name), {
        "name": name, "device": "8BitDo Micro", "mappings": clean_mappings(mappings),
    })


def delete_profile(name):
    try:
        os.remove(profile_path(name))
    except OSError:
        pass


def export_profile(path, name, mappings):
    _atomic_write(path, {"name": name, "device": "8BitDo Micro",
                         "mappings": clean_mappings(mappings)})


def import_profile(path):
    data = _read(path, None)
    if not isinstance(data, dict):
        raise ValueError("Could not read profile JSON")
    name = data.get("name") or os.path.splitext(os.path.basename(path))[0]
    return _safe_name(str(name)), clean_mappings(data.get("mappings"))
