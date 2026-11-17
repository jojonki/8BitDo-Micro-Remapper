"""Tkinter GUI: visual 8BitDo Micro layout + remap editor (dark theme)."""

import multiprocessing as mp
import queue as queue_mod
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, simpledialog, ttk

from . import APP_NAME, __version__, input_worker, keepalive, storage, updater
from .keys import (ACTION_TYPES, MODIFIER_LABELS, MODIFIERS, MOUSE_ACTIONS,
                   catalog_display_values, catalog_value_to_key, describe_action,
                   key_to_catalog_value, normalize_combo, tk_event_to_key,
                   tk_modifier, validate_action)
from .layout import (BODY, BODY_RADIUS, BUTTON_BY_ID, BUTTONS, CANVAS_H,
                     CANVAS_W, DEFAULT_SOURCE_MAP, DISABLED_IDS, DPAD_C,
                     DPAD_HALF, WIZARD_ORDER, chip_box,
                     leader_points)
from .output import Executor

# ------------------------------------------------------------------ palette
C_BG = "#121419"          # window
C_PANEL = "#1a1d23"       # side panel / bars
C_CARD = "#23272f"        # chips, inputs
C_CARD_HOVER = "#2b303a"
C_BORDER = "#323845"
C_TEXT = "#e7e9ee"
C_MUTED = "#8b92a1"
C_DIM = "#5d6472"
C_ACCENT = "#5b8cff"
C_ACCENT_HOVER = "#769fff"
C_GREEN = "#3ccf7a"
C_ORANGE = "#ffb547"
C_RED = "#ff6b6b"
C_PINK = "#ff5fa2"

C_BODY = "#2a2f38"
C_BODY_EDGE = "#3b424f"
C_BODY_SHADOW = "#0b0c0f"
C_BTN = "#454c5a"
C_BTN_EDGE = "#2a2f38"
C_BTN_TEXT = "#f2f4f8"
C_HOVER = "#59627a"
C_PRESSED = C_GREEN
C_SELECT = C_ACCENT
C_LEARN = C_PINK
C_LINE = "#5c6578"      # idle leader line: visible on both bg and body

import os as _os
# set MICRO_REMAPPER_LOG=/path/file.log to record every controller event
DEBUG_LOG = _os.environ.get("MICRO_REMAPPER_LOG")
LEARN_LINK = "Wrong button lights up? Fix…"
HINT_DEFAULT = ""   # the canvas only shows prompts while capturing / fixing
MOD_KEY = "Command" if sys.platform == "darwin" else "Ctrl"


def pick_font_family(root):
    prefs = {
        # UI text is English: Latin UI fonts have even vertical metrics, so
        # text lines up with switches / inputs (CJK fonts sit noticeably off)
        "darwin": ["Helvetica Neue", "Helvetica"],
        "win32": ["Segoe UI", "Tahoma"],
    }.get(sys.platform, ["DejaVu Sans", "Liberation Sans"])
    try:
        fams = set(tkfont.families(root))
    except Exception:
        fams = set()
    for f in prefs:
        if f in fams:
            return f
    return "TkDefaultFont"


def mac_accessibility_trusted():
    """True/False on macOS (can we post key events?), None elsewhere/unknown."""
    if sys.platform != "darwin":
        return None
    try:
        import ctypes
        hs = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        hs.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(hs.AXIsProcessTrusted())
    except Exception:
        return None


def rounded_points(x1, y1, x2, y2, r):
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


# ===================================================================== widgets
class FlatButton(tk.Label):
    """A colourable button (tk.Button ignores colours on macOS)."""

    STYLES = {
        "primary": (C_ACCENT, C_ACCENT_HOVER, "#ffffff"),
        "secondary": (C_CARD, C_CARD_HOVER, C_TEXT),
        "ghost": (C_PANEL, C_CARD, C_MUTED),
        "danger": (C_CARD, "#3a2328", C_RED),
        "learn": (C_PINK, "#ff7fb5", "#ffffff"),
    }

    def __init__(self, master, text, command=None, kind="secondary", font=None,
                 padx=14, pady=7, **kw):
        bg, hover, fg = self.STYLES[kind]
        super().__init__(master, text=text, bg=bg, fg=fg, font=font, padx=padx,
                         pady=pady, cursor="hand2", **kw)
        self._bg, self._hover, self._fg = bg, hover, fg
        self.command = command
        self.active = False
        self.bind("<Enter>", lambda e: self._paint(hover=True))
        self.bind("<Leave>", lambda e: self._paint(hover=False))
        self.bind("<Button-1>", self._click)

    def set_kind(self, kind):
        self._bg, self._hover, self._fg = self.STYLES[kind]
        self._paint(False)

    def set_active(self, active):
        self.active = active
        self._paint(False)

    def _paint(self, hover):
        if self.active:
            self.configure(bg=C_ACCENT, fg="#ffffff")
        else:
            self.configure(bg=self._hover if hover else self._bg, fg=self._fg)

    def _click(self, _e):
        if self.command:
            self.command()


class Toggle(tk.Frame):
    """iOS-like switch bound to a BooleanVar."""

    def __init__(self, master, text, variable, command=None, font=None, bg=C_BG, tooltip=None):
        super().__init__(master, bg=bg)
        self.var = variable
        self.command = command
        self.cv = tk.Canvas(self, width=38, height=22, bg=bg, highlightthickness=0, cursor="hand2")
        self.cv.pack(side="left", pady=(2, 0))   # optical centre of the label text
        lbl = tk.Label(self, text=text, bg=bg, fg=C_TEXT, font=font, cursor="hand2")
        lbl.pack(side="left", padx=(6, 0))
        for w in (self.cv, lbl):
            w.bind("<Button-1>", self._toggle)
            if tooltip:
                Tooltip(w, tooltip)
        self.var.trace_add("write", lambda *a: self._draw())
        self._draw()

    def _draw(self):
        on = bool(self.var.get())
        c = self.cv
        c.delete("all")
        c.create_polygon(rounded_points(1, 1, 37, 21, 10), smooth=True,
                         fill=C_ACCENT if on else C_BORDER, outline="")
        x = 26 if on else 12
        c.create_oval(x - 8, 3, x + 8, 19, fill="#ffffff", outline="")

    def _toggle(self, _e):
        self.var.set(not self.var.get())
        if self.command:
            self.command()


class Tooltip:
    """Small hover popup."""

    def __init__(self, widget, text):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _e=None):
        if self.tip:
            return
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self.text, bg=C_CARD, fg=C_TEXT, justify="left",
                 wraplength=340, padx=10, pady=8).pack()

    def hide(self, _e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class KeyPicker(tk.Frame):
    """Dropdown field for picking a key. Unlike ttk.Combobox (whose popdown
    can't be controlled reliably on macOS Tk 9), the list opens scrolled to
    and selected on the current value, and typing filters it."""

    def __init__(self, master, variable, values, command=None, font=None):
        super().__init__(master, bg=C_CARD, highlightthickness=1,
                         highlightbackground=C_BORDER, highlightcolor=C_ACCENT, cursor="hand2")
        self.var, self.values, self.command, self.font = variable, list(values), command, font
        self.popup = None
        self.lbl = tk.Label(self, textvariable=variable, bg=C_CARD, fg=C_TEXT, font=font,
                            anchor="w", padx=8, pady=4)
        self.lbl.pack(side="left", fill="x", expand=True)
        arrow = tk.Label(self, text="▾", bg=C_CARD, fg=C_MUTED, font=font, padx=8)
        arrow.pack(side="right")
        for w in (self, self.lbl, arrow):
            w.bind("<Button-1>", lambda e: self.open())

    # -- popup -------------------------------------------------------------
    def open(self):
        if self.popup:
            self.close()
            return
        top = self.popup = tk.Toplevel(self, bg=C_BORDER)
        top.wm_overrideredirect(True)
        w = self.winfo_width()
        x, y = self.winfo_rootx(), self.winfo_rooty() + self.winfo_height() + 2
        top.wm_geometry(f"{w}x320+{x}+{y}")
        inner = tk.Frame(top, bg=C_CARD)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        self.filter_var = tk.StringVar()
        ent = tk.Entry(inner, textvariable=self.filter_var, bg=C_PANEL, fg=C_TEXT,
                       insertbackground=C_TEXT, relief="flat", font=self.font,
                       highlightthickness=0)
        ent.pack(fill="x", padx=6, pady=6, ipady=3)
        ent.insert(0, "")
        frame = tk.Frame(inner, bg=C_CARD)
        frame.pack(fill="both", expand=True)
        sb = tk.Scrollbar(frame, orient="vertical")
        self.lb = tk.Listbox(frame, bg=C_CARD, fg=C_TEXT, selectbackground=C_ACCENT,
                             selectforeground="#ffffff", activestyle="none", relief="flat",
                             highlightthickness=0, font=self.font, yscrollcommand=sb.set,
                             exportselection=False)
        sb.configure(command=self.lb.yview)
        sb.pack(side="right", fill="y")
        self.lb.pack(side="left", fill="both", expand=True)
        self._fill("")
        self.filter_var.trace_add("write", lambda *a: self._fill(self.filter_var.get()))
        for wdg in (ent, self.lb):
            wdg.bind("<Return>", lambda e: self._choose())
            wdg.bind("<Escape>", lambda e: self.close())
            wdg.bind("<Up>", lambda e: self._move(-1))
            wdg.bind("<Down>", lambda e: self._move(1))
        self.lb.bind("<ButtonRelease-1>", lambda e: self._choose())
        top.bind("<FocusOut>", lambda e: self.after(80, self._close_if_unfocused))
        ent.focus_set()

    def _fill(self, query):
        q = query.strip().lower()
        self.shown = [v for v in self.values if q in v.lower()] if q else list(self.values)
        self.lb.delete(0, "end")
        for v in self.shown:
            self.lb.insert("end", v)
        # select + scroll to the current value (or the first match)
        cur = self.var.get()
        idx = self.shown.index(cur) if cur in self.shown else 0
        if self.shown:
            self._select(idx, center=True)

    def _select(self, idx, center=False):
        idx = max(0, min(idx, len(self.shown) - 1))
        self.lb.selection_clear(0, "end")
        self.lb.selection_set(idx)
        self.lb.activate(idx)
        if center:
            # put the current item in the middle of the visible list
            self.lb.update_idletasks()
            first, last = self.lb.nearest(0), self.lb.nearest(self.lb.winfo_height())
            visible = max(1, last - first)
            self.lb.yview(max(0, idx - visible // 2))
        self.lb.see(idx)

    def _move(self, d):
        sel = self.lb.curselection()
        self._select((sel[0] if sel else 0) + d)
        return "break"

    def _choose(self):
        sel = self.lb.curselection()
        if sel:
            self.var.set(self.shown[sel[0]])
            if self.command:
                self.command()
        self.close()

    def _close_if_unfocused(self):
        if self.popup and not str(self.focus_get() or "").startswith(str(self.popup)):
            self.close()

    def close(self):
        if self.popup:
            self.popup.destroy()
            self.popup = None


# ======================================================================= app
class RemapperApp:
    def __init__(self, root):
        self.root = root
        self.settings = storage.load_settings()
        self.profiles = storage.list_profiles()
        if self.settings["profile"] not in self.profiles:
            self.settings["profile"] = "default"
        self.profile_name = self.settings["profile"]
        self.mappings = storage.load_profile(self.profile_name)
        self.dirty = False

        self.executor = Executor(log=self.log)
        self.executor.repeat_enabled = self.settings["repeat"]

        self.selected = None          # logical button id being edited
        self.hover = None
        self.pressed = {}             # logical id -> set(source ids)
        self.capturing = False
        self.capture_mods = []
        self.capture_deadline = 0
        self.learn_target = None
        self.wizard = []              # remaining ids for the learn wizard
        self.device_name = None
        self.unknown_sources = set()
        self._suppress_form = False
        self._learn_pending = None
        self.last_activity = time.monotonic()   # last button press (for auto power-off)
        self._ui_q = queue_mod.Queue()          # callables posted from worker threads
        self._update_info = None
        self._updating = False

        self.ff = pick_font_family(root)
        self.f_body = (self.ff, 12)
        self.f_small = (self.ff, 11)
        self.f_bold = (self.ff, 12, "bold")
        self.f_title = (self.ff, 20, "bold")
        self.f_current = (self.ff, 15, "bold")
        self.f_section = (self.ff, 10, "bold")

        self._build_ui()
        self._start_worker()
        self.select_button("a")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(5, self.poll)
        self.root.after(keepalive.PING_INTERVAL_MS, self._keepalive_tick)
        updater.cleanup_old()
        if self.settings.get("check_updates", True):
            self.root.after(3000, lambda: self.check_for_updates(manual=False))

        if mac_accessibility_trusted() is False:
            self.show_banner(
                "⚠ Accessibility permission is missing, so key presses cannot be sent. Open System Settings → "
                "Privacy & Security → Accessibility, enable the app that launched this one (e.g. Terminal), "
                "then restart the app.")

        if not self.executor.available:
            self.root.after(300, lambda: messagebox.showerror(
                APP_NAME, (self.executor.error or "pynput is not installed") +
                "\n\nRun: pip install -r requirements.txt"))

    # ================================================================ UI
    def _style(self):
        root = self.root
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", background=C_PANEL, foreground=C_TEXT, font=self.f_body)
        style.configure("TCombobox", fieldbackground=C_CARD, background=C_CARD,
                        foreground=C_TEXT, arrowcolor=C_TEXT, bordercolor=C_BORDER,
                        lightcolor=C_CARD, darkcolor=C_CARD, padding=6)
        style.map("TCombobox",
                  fieldbackground=[("readonly", C_CARD)],
                  foreground=[("readonly", C_TEXT)],
                  selectbackground=[("readonly", C_CARD)],
                  selectforeground=[("readonly", C_TEXT)],
                  background=[("active", C_CARD_HOVER)],
                  bordercolor=[("focus", C_ACCENT)])
        style.configure("TEntry", fieldbackground=C_CARD, foreground=C_TEXT,
                        insertcolor=C_TEXT, bordercolor=C_BORDER,
                        lightcolor=C_CARD, darkcolor=C_CARD, padding=6)
        style.map("TEntry", bordercolor=[("focus", C_ACCENT)])
        root.option_add("*TCombobox*Listbox.background", C_CARD)
        root.option_add("*TCombobox*Listbox.foreground", C_TEXT)
        root.option_add("*TCombobox*Listbox.selectBackground", C_ACCENT)
        root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        root.option_add("*TCombobox*Listbox.font", self.f_body)

    def _build_ui(self):
        root = self.root
        root.title(f"{APP_NAME} v{__version__}")
        root.configure(bg=C_BG)
        root.minsize(1280, 600)
        self._style()

        # ---- toolbar -------------------------------------------------
        bar = tk.Frame(root, bg=C_BG, padx=20, pady=14)
        bar.pack(side="top", fill="x")
        # baselines in this bar are aligned to the input text (measured);
        # the larger title is lifted a few px so it sits on the same line
        tk.Label(bar, text="8BitDo Micro", bg=C_BG, fg=C_TEXT,
                 font=(self.ff, 17, "bold")).pack(side="left", pady=(0, 6))
        tk.Label(bar, text=" Remapper", bg=C_BG, fg=C_ACCENT,
                 font=(self.ff, 17, "bold")).pack(side="left", pady=(0, 6))

        pf = tk.Frame(bar, bg=C_BG)
        pf.pack(side="left", padx=(36, 0))
        tk.Label(pf, text="Profile", bg=C_BG, fg=C_MUTED, font=self.f_body).pack(
            side="left", padx=(0, 8), pady=(1, 0))
        self.profile_var = tk.StringVar(value=self.profile_name)
        self.profile_cb = ttk.Combobox(pf, textvariable=self.profile_var, values=self.profiles,
                                       state="readonly", width=18, font=self.f_body)
        self.profile_cb.pack(side="left")
        self.profile_cb.bind("<<ComboboxSelected>>",
                             lambda e: self.switch_profile(self.profile_var.get()))
        FlatButton(pf, "＋ New", self.new_profile, font=self.f_body).pack(side="left", padx=(8, 0))
        self.menu_btn = FlatButton(pf, "⋯", self._open_profile_menu, font=self.f_body, padx=12)
        self.menu_btn.pack(side="left", padx=(6, 0))
        self.profile_menu = tk.Menu(root, tearoff=0)
        self.profile_menu.add_command(label="Duplicate…", command=self.duplicate_profile)
        self.profile_menu.add_command(label="Import…", command=self.import_profile)
        self.profile_menu.add_command(label="Export…", command=self.export_profile)
        self.profile_menu.add_separator()
        self.profile_menu.add_command(label="Delete", command=self.delete_profile)
        self.profile_menu.add_separator()
        self.profile_menu.add_command(label="Check for updates…",
                                      command=lambda: self.check_for_updates(manual=True))
        self.check_updates_var = tk.BooleanVar(value=self.settings.get("check_updates", True))
        self.profile_menu.add_checkbutton(label="Check for updates at launch",
                                          variable=self.check_updates_var,
                                          command=self.on_toggle_check_updates)

        self.enabled_var = tk.BooleanVar(value=self.settings["enabled"])
        self.repeat_var = tk.BooleanVar(value=self.settings["repeat"])
        Toggle(bar, "Remap", self.enabled_var, self.on_toggle_enabled,
               font=self.f_body).pack(side="right")
        Toggle(bar, "Key repeat", self.repeat_var, self.on_toggle_repeat,
               font=self.f_body).pack(side="right", padx=(0, 22))
        # auto power-off: the pad sleeps after 15 idle minutes by itself;
        # the app can keep it awake longer (see keepalive.py)
        self.power_var = tk.StringVar(value=self._power_key(self.settings["power_off"]))
        self.power_btn = FlatButton(bar, "", self._open_power_menu, font=self.f_body, padx=12)
        self.power_btn.pack(side="right", padx=(0, 22))
        Tooltip(self.power_btn, "How long the controller may sit idle before it powers off.\n"
                                "The Micro turns itself off after 15 min; longer times keep it\n"
                                "awake from this app (uses more battery).")
        self.power_menu = tk.Menu(root, tearoff=0)
        self.power_menu.add_command(label="Power off after idle", state="disabled")
        self.power_menu.add_separator()
        for minutes, label in keepalive.POWER_OFF_CHOICES:
            self.power_menu.add_radiobutton(label=label, value=self._power_key(minutes),
                                            variable=self.power_var,
                                            command=self.on_power_off_change)
        self._update_power_btn()
        self.exclusive_var = tk.BooleanVar(value=self.settings["exclusive"])
        # Home-button menu (opened by clicking the Home button / its label).
        # macOS itself can stop Home from opening the Games app (System
        # Settings > Game Controllers > Home Button > "Enable Home Button
        # Actions"); that keeps the D-pad working. Exclusive mode is only a
        # fallback: it also blocks Home but the pad then sends no D-pad data.
        self.home_menu = tk.Menu(root, tearoff=0)
        self.home_menu.add_command(label="Home button", state="disabled")
        self.home_menu.add_separator()
        self.home_menu.add_command(
            label="Open Game Controller settings…  (turn off “Enable Home Button Actions”)",
            command=self.open_gc_settings)
        self.home_menu.add_separator()
        self.home_menu.add_checkbutton(
            label="Exclusive mode — block Home in this app (D-pad won't work)",
            variable=self.exclusive_var, command=self.on_toggle_exclusive)

        # ---- status bar ----------------------------------------------
        status = tk.Frame(root, bg=C_PANEL, padx=20, pady=8)
        status.pack(side="bottom", fill="x")
        self.dot = tk.Canvas(status, width=10, height=10, bg=C_PANEL, highlightthickness=0)
        self.dot.pack(side="left")
        self._dot = self.dot.create_oval(1, 1, 9, 9, fill=C_ORANGE, outline="")
        self.device_var = tk.StringVar(value="Searching for controller…")
        tk.Label(status, textvariable=self.device_var, bg=C_PANEL, fg=C_TEXT,
                 font=self.f_small).pack(side="left", padx=(8, 0))
        self.log_var = tk.StringVar(value="")
        tk.Label(status, textvariable=self.log_var, bg=C_PANEL, fg=C_MUTED,
                 font=self.f_small).pack(side="right")

        # ---- warning banner (hidden unless needed) ---------------------
        self.banner = tk.Label(root, text="", bg="#3a2f14", fg="#ffd88a", anchor="w",
                               justify="left", padx=14, pady=10, wraplength=1250,
                               font=self.f_small)

        # ---- update bar (hidden unless an update is available) ---------
        self.update_bar = tk.Frame(root, bg="#16294a", padx=14, pady=8)
        self.update_var = tk.StringVar(value="")
        tk.Label(self.update_bar, textvariable=self.update_var, bg="#16294a", fg="#cfe0ff",
                 font=self.f_small, anchor="w", justify="left").pack(side="left")
        FlatButton(self.update_bar, "Later", self.hide_update_bar, kind="ghost",
                   font=self.f_small, pady=4).pack(side="right")
        FlatButton(self.update_bar, "What's new", self.open_release_page,
                   font=self.f_small, pady=4).pack(side="right", padx=(0, 8))
        self.update_btn = FlatButton(self.update_bar, "Update now", self.install_update,
                                     kind="primary", font=self.f_small, pady=4)
        self.update_btn.pack(side="right", padx=(0, 8))

        # ---- main area -----------------------------------------------
        main = tk.Frame(root, bg=C_BG)
        main.pack(side="top", fill="both", expand=True)
        self.main_frame = main

        right = tk.Frame(main, bg=C_PANEL, width=340, padx=14, pady=12)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        self._build_editor(right)

        left = tk.Frame(main, bg=C_BG, padx=10)
        left.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(left, width=CANVAS_W, height=CANVAS_H, bg=C_BG,
                                highlightthickness=0, takefocus=1)
        self.canvas.pack(side="top", pady=(6, 0))
        self.hint_var = tk.StringVar(value=HINT_DEFAULT)
        self.hint_lbl = tk.Label(left, textvariable=self.hint_var, bg=C_BG, fg=C_MUTED,
                                 font=self.f_body)
        self.hint_lbl.pack(side="top", pady=(4, 10))

        self._draw_controller()
        self.refresh_all()

        # keyboard capture (only acts while capturing)
        root.bind_all("<KeyPress>", self._on_key_press, add="+")
        root.bind_all("<KeyRelease>", self._on_key_release, add="+")

    def _section(self, parent, text, pady=(12, 4)):
        tk.Label(parent, text=text, bg=C_PANEL, fg=C_DIM, font=self.f_section,
                 anchor="w").pack(fill="x", pady=pady)

    def _build_editor(self, parent):
        self.sel_title = tk.StringVar(value="")
        self.sel_current = tk.StringVar(value="")
        # one compact header row:  <button>   → <current mapping>
        head = tk.Frame(parent, bg=C_PANEL)
        head.pack(fill="x")
        tk.Label(head, textvariable=self.sel_title, bg=C_PANEL, fg=C_TEXT,
                 font=self.f_current, anchor="w").pack(side="left")
        tk.Label(head, text="→", bg=C_PANEL, fg=C_DIM, font=self.f_body).pack(side="left", padx=6)
        tk.Label(head, textvariable=self.sel_current, bg=C_PANEL, fg=C_ACCENT,
                 font=self.f_bold, anchor="w").pack(side="left", fill="x", expand=True)

        # segmented control for the action type
        seg = tk.Frame(parent, bg=C_CARD, padx=2, pady=2)
        seg.pack(fill="x", pady=(10, 0))
        self.type_var = tk.StringVar(value="key")
        self.seg_buttons = {}
        for val, lbl in ACTION_TYPES:
            b = FlatButton(seg, lbl, lambda v=val: self._select_type(v), kind="secondary",
                           font=self.f_small, padx=2, pady=3)
            b.pack(side="left", fill="x", expand=True, padx=1)
            self.seg_buttons[val] = b

        self.forms = tk.Frame(parent, bg=C_PANEL)
        self.forms.pack(fill="x", pady=(10, 0))

        # --- key form ---------------------------------------------------
        kf = tk.Frame(self.forms, bg=C_PANEL)
        self.capture_btn = FlatButton(kf, "Press a key to assign", self.toggle_capture,
                                      kind="primary", font=self.f_small, pady=5)
        self.capture_btn.pack(fill="x")
        self._section(kf, "OR PICK", pady=(8, 3))
        modrow = tk.Frame(kf, bg=C_PANEL)
        modrow.pack(fill="x")
        self.mod_vars = {}
        self.mod_buttons = {}
        for m in MODIFIERS:
            v = tk.BooleanVar(value=False)
            self.mod_vars[m] = v
            b = FlatButton(modrow, MODIFIER_LABELS[m], lambda m=m: self._toggle_mod(m),
                           font=self.f_small, padx=2, pady=2)
            b.pack(side="left", fill="x", expand=True, padx=(0, 3))
            self.mod_buttons[m] = b
            v.trace_add("write", lambda *a, m=m: self.mod_buttons[m].set_active(self.mod_vars[m].get()))
        self.key_var = tk.StringVar(value="(none)")
        self.key_cb = KeyPicker(kf, self.key_var, catalog_display_values(),
                                command=self._apply_key_form, font=self.f_small)
        self.key_cb.pack(fill="x", pady=(4, 0))
        self.forms_key = kf

        # --- mouse form ------------------------------------------------
        mfm = tk.Frame(self.forms, bg=C_PANEL)
        self.mouse_var = tk.StringVar()
        self.mouse_cb = ttk.Combobox(mfm, textvariable=self.mouse_var, state="readonly",
                                     values=[lbl for _, lbl in MOUSE_ACTIONS], font=self.f_small)
        self.mouse_cb.pack(fill="x")
        self.mouse_cb.bind("<<ComboboxSelected>>", lambda e: self._apply_mouse_form())
        tk.Label(mfm, text="Hold to accelerate / keep scrolling.", bg=C_PANEL, fg=C_MUTED,
                 font=self.f_small, anchor="w").pack(fill="x", pady=(4, 0))
        self.forms_mouse = mfm

        # --- text form -------------------------------------------------
        txf = tk.Frame(self.forms, bg=C_PANEL)
        self.text_var = tk.StringVar()
        trow = tk.Frame(txf, bg=C_PANEL)
        trow.pack(fill="x")
        ent = ttk.Entry(trow, textvariable=self.text_var, font=self.f_small)
        ent.pack(side="left", fill="x", expand=True)
        ent.bind("<Return>", lambda e: self._apply_text_form())
        FlatButton(trow, "Apply", self._apply_text_form, kind="primary",
                   font=self.f_small, padx=10, pady=3).pack(side="left", padx=(4, 0))
        self.forms_text = txf

        # --- none form -------------------------------------------------
        nf = tk.Frame(self.forms, bg=C_PANEL)
        tk.Label(nf, text="This button does nothing.", bg=C_PANEL, fg=C_MUTED,
                 font=self.f_small, anchor="w").pack(fill="x")
        self.forms_none = nf

        act = tk.Frame(parent, bg=C_PANEL)
        act.pack(fill="x", pady=(8, 0))
        FlatButton(act, "Reset to default", self.reset_selected, kind="ghost",
                   font=self.f_small, padx=0, pady=2).pack(side="left")
        FlatButton(act, "Clear", self.clear_selected, kind="ghost",
                   font=self.f_small, padx=0, pady=2).pack(side="left", padx=(14, 0))

        # --- button fixing (bottom, deliberately low-key) --------------------
        lf = tk.Frame(parent, bg=C_PANEL)
        lf.pack(side="bottom", fill="x")
        self.learn_btn = FlatButton(lf, LEARN_LINK, self.open_fix_dialog, kind="ghost",
                                    font=self.f_small, padx=0, pady=2)
        self.learn_btn.pack(anchor="w")

    def _open_profile_menu(self):
        x = self.menu_btn.winfo_rootx()
        y = self.menu_btn.winfo_rooty() + self.menu_btn.winfo_height()
        try:
            self.profile_menu.tk_popup(x, y)
        finally:
            self.profile_menu.grab_release()

    # ---------------------------------------------------------- drawing
    def _draw_controller(self):
        c = self.canvas
        c.delete("all")
        self.items = {}

        # body
        x1, y1, x2, y2 = BODY
        c.create_polygon(rounded_points(x1 + 3, y1 + 10, x2 + 3, y2 + 10, BODY_RADIUS),
                         smooth=True, fill=C_BODY_SHADOW, outline="")
        c.create_polygon(rounded_points(*BODY, BODY_RADIUS), smooth=True,
                         fill=C_BODY, outline=C_BODY_EDGE, width=2)
        c.create_polygon(rounded_points(x1 + 14, y1 + 12, x2 - 14, y2 - 12, BODY_RADIUS - 14),
                         smooth=True, fill="", outline="#323844", width=1)
        c.create_text((x1 + x2) / 2, y2 - 24, text="8BitDo", fill="#59606e",
                      font=(self.ff, 12, "bold"))
        # USB-C port + LED
        c.create_polygon(rounded_points((x1 + x2) / 2 - 16, y1 - 3, (x1 + x2) / 2 + 16, y1 + 5, 4),
                         smooth=True, fill="#4a5160", outline="")
        c.create_oval((x1 + x2) / 2 - 3, y1 + 18, (x1 + x2) / 2 + 3, y1 + 24,
                      fill=C_GREEN if self.device_name else "#4a5160", outline="", tags=("led",))

        # leader lines: drawn on top of the body (so they stay visible on the
        # controller) but below the buttons, which hide where they end
        for b in BUTTONS:
            pts = [v for p in leader_points(b) for v in p]
            self.items[b["id"]] = {"line": c.create_line(*pts, fill=C_LINE, width=1.5,
                                                         capstyle="round", joinstyle="round")}

        # D-pad centre
        cx, cy = DPAD_C
        h = DPAD_HALF
        c.create_rectangle(cx - h, cy - h, cx + h, cy + h, fill=C_BTN, outline=C_BTN)
        c.create_oval(cx - 6, cy - 6, cx + 6, cy + 6, fill="#373d49", outline="")

        for b in BUTTONS:
            bid = b["id"]
            tag = f"btn_{bid}"
            bx1, by1, bx2, by2 = b["box"]
            if b.get("disabled"):
                self._draw_disabled(b)
                continue
            common = dict(fill=C_BTN, outline=C_BTN_EDGE, width=2, tags=(tag,))
            if b["shape"] == "circle":
                shape = c.create_oval(*b["box"], **common)
            elif b["shape"] == "rect":
                shape = c.create_rectangle(*b["box"], **common)
            else:  # pill / tab
                shape = c.create_polygon(rounded_points(*b["box"], 8), smooth=True, **common)
            size = 13 if b["shape"] in ("circle", "tab") else 12
            dy = 0
            if bid in ("home", "star"):
                size = 11
            if b["shape"] == "pill":
                dy = -2   # − / + glyphs sit below the visual centre
            c.create_text((bx1 + bx2) / 2, (by1 + by2) / 2 + dy, text=b["label"],
                          fill=C_BTN_TEXT, font=(self.ff, size, "bold"), tags=(tag,))

            # mapping chip
            ctag = f"chip_{bid}"
            x1, y1, x2, y2 = chip_box(b)
            chip = c.create_polygon(rounded_points(x1, y1, x2, y2, 9), smooth=True,
                                    fill=C_CARD, outline=C_BORDER, width=1, tags=(ctag,))
            badge = c.create_polygon(rounded_points(x1 + 6, y1 + 5, x1 + 40, y2 - 5, 6),
                                     smooth=True, fill=C_BTN, outline="", tags=(ctag,))
            c.create_text(x1 + 23, (y1 + y2) / 2 + dy, text=b["label"], fill=C_BTN_TEXT,
                          font=(self.ff, 10, "bold"), tags=(ctag,))
            maptxt = c.create_text(x1 + 50, (y1 + y2) / 2, text="", anchor="w",
                                   fill=C_TEXT, font=(self.ff, 12), tags=(ctag,))
            self.items[bid].update({"shape": shape, "chip": chip, "badge": badge, "map": maptxt})

            for t in (tag, ctag):
                c.tag_bind(t, "<Button-1>", lambda e, i=bid: self.select_button(i))
                c.tag_bind(t, "<Enter>", lambda e, i=bid: self._set_hover(i))
                c.tag_bind(t, "<Leave>", lambda e, i=bid: self._set_hover(None))

    def _draw_disabled(self, b):
        """Centre buttons the app can't use: plain dashed outline, no glyph."""
        c = self.canvas
        bid = b["id"]
        shape = c.create_oval(*b["box"], fill="#30353f", outline=C_DIM, width=1, dash=(2, 2))
        if b.get("no_chip"):
            c.delete(self.items[bid]["line"])
            self.items[bid] = {"shape": shape}
            return
        x1, y1, x2, y2 = chip_box(b)
        cy = (y1 + y2) / 2
        if bid == "home" and sys.platform == "darwin":
            # Home can't be remapped, but it has a setting: a solid, clickable
            # chip showing the Games-app state; click opens the Home menu.
            chip = c.create_polygon(rounded_points(x1, y1, x2, y2, 9), smooth=True,
                                    fill=C_CARD, outline=C_BORDER, width=1)
            maptxt = c.create_text(x1 + 12, cy, text="", anchor="w", font=(self.ff, 11))
            gear = c.create_text(x2 - 13, cy, text="⚙", fill=C_MUTED, font=(self.ff, 13))
            self.items[bid].update({"shape": shape, "chip": chip, "map": maptxt})
            c.itemconfigure(self.items[bid]["line"], dash=(2, 3))
            for item in (shape, chip, maptxt, gear):
                c.tag_bind(item, "<Button-1>", self._open_home_menu)
                c.tag_bind(item, "<Enter>", lambda e: (self.canvas.configure(cursor="hand2"),
                                                        self.canvas.itemconfigure(chip, fill=C_CARD_HOVER)))
                c.tag_bind(item, "<Leave>", lambda e: (self.canvas.configure(cursor=""),
                                                        self.canvas.itemconfigure(chip, fill=C_CARD)))
            self._update_home_chip()
            return
        chip = c.create_polygon(rounded_points(x1, y1, x2, y2, 9), smooth=True,
                                fill=C_BG, outline=C_BORDER, width=1, dash=(3, 3))
        maptxt = c.create_text(x1 + 12, cy, text="Disabled", anchor="w",
                               fill=C_DIM, font=(self.ff, 11))
        self.items[bid].update({"shape": shape, "chip": chip, "map": maptxt})
        c.itemconfigure(self.items[bid]["line"], dash=(2, 3))

    def _update_home_chip(self):
        it = self.items.get("home")
        if not it or sys.platform != "darwin":
            return
        if self.exclusive_var.get():
            self.canvas.itemconfigure(it["map"], text="Exclusive mode", fill=C_ORANGE)
        else:
            self.canvas.itemconfigure(it["map"], text="Home: macOS setting", fill=C_MUTED)

    def _open_home_menu(self, e):
        try:
            self.home_menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.home_menu.grab_release()

    # ------------------------------------------------------- auto power-off
    @staticmethod
    def _power_key(minutes):
        return "never" if minutes is None else str(minutes)

    def _update_power_btn(self):
        self.power_btn.configure(
            text=f"⏻ Power-off: {keepalive.short_label(self.settings['power_off'])} ▾")

    def _open_power_menu(self):
        b = self.power_btn
        try:
            self.power_menu.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())
        finally:
            self.power_menu.grab_release()

    def on_power_off_change(self):
        v = self.power_var.get()
        self.settings["power_off"] = None if v == "never" else int(v)
        storage.save_settings(self.settings)
        self._update_power_btn()
        self.last_activity = time.monotonic()
        self.log("Auto power-off: " + keepalive.short_label(self.settings["power_off"]))
        if keepalive.should_ping(self.settings["power_off"], 0):
            self._keepalive_ping()

    def _keepalive_tick(self):
        try:
            idle = time.monotonic() - self.last_activity
            if (self.device_name and not self.settings.get("exclusive")
                    and keepalive.should_ping(self.settings["power_off"], idle)):
                self._keepalive_ping()
        finally:
            self.root.after(keepalive.PING_INTERVAL_MS, self._keepalive_tick)

    def _keepalive_ping(self):
        if keepalive.supported():
            keepalive.ping_async()

    def _set_hover(self, bid):
        self.hover = bid
        self.canvas.configure(cursor="hand2" if bid else "")
        self.refresh_visuals()

    def refresh_visuals(self):
        c = self.canvas
        for bid, it in self.items.items():
            if bid in DISABLED_IDS:
                continue
            pressed = bool(self.pressed.get(bid))
            learning = bid == self.learn_target
            selected = bid == self.selected
            hover = bid == self.hover

            fill = C_PRESSED if pressed else (C_HOVER if hover else C_BTN)
            outline, width = C_BTN_EDGE, 2
            if learning:
                outline, width = C_LEARN, 4
            elif selected:
                outline, width = C_SELECT, 3
            c.itemconfigure(it["shape"], fill=fill, outline=outline, width=width)

            c.itemconfigure(it["chip"], fill=C_CARD_HOVER if hover else C_CARD,
                            outline=C_LEARN if learning else (C_ACCENT if selected else C_BORDER),
                            width=2 if (selected or learning) else 1)
            c.itemconfigure(it["badge"], fill=C_PRESSED if pressed else
                            (C_ACCENT if selected else C_BTN))
            line = C_PRESSED if pressed else (C_LEARN if learning else
                                              (C_ACCENT if selected else C_LINE))
            c.itemconfigure(it["line"], fill=line,
                            width=2.5 if (pressed or learning or selected) else 1.5)
        c.itemconfigure("led", fill=C_GREEN if self.device_name else "#4a5160")

    def refresh_all(self):
        for b in BUTTONS:
            bid = b["id"]
            if bid in DISABLED_IDS:
                continue
            a = self.mappings.get(bid)
            if not a:
                txt, color = "Unassigned", C_DIM
            elif a.get("type") == "none":
                txt, color = "Disabled", C_RED
            else:
                txt, color = describe_action(a, short=True), C_TEXT
                if len(txt) > 16:
                    txt = txt[:15] + "…"
            self.canvas.itemconfigure(self.items[bid]["map"], text=txt, fill=color)
        self.refresh_visuals()
        self._update_title()

    def _update_title(self):
        mark = " *" if self.dirty else ""
        self.root.title(f"{APP_NAME} v{__version__} — {self.profile_name}{mark}")

    # ----------------------------------------------------------- selection
    def select_button(self, bid):
        if bid in DISABLED_IDS:
            return
        if self.capturing:
            self.stop_capture()
        self.selected = bid
        self.sel_title.set(BUTTON_BY_ID[bid]["name"])
        self._load_form()
        self.refresh_visuals()

    def _current_text(self, a):
        if not a:
            return "Unassigned"
        return describe_action(a)

    def _load_form(self):
        a = self.mappings.get(self.selected)
        self.sel_current.set(self._current_text(a))
        self._suppress_form = True
        t = a.get("type") if a else "key"
        self.type_var.set(t)
        for m in MODIFIERS:
            self.mod_vars[m].set(False)
        self.key_var.set("(none)")
        self.mouse_var.set("")
        self.text_var.set("")
        if t == "key" and a:
            keys = a.get("keys", [])
            for m in MODIFIERS:
                self.mod_vars[m].set(m in keys)
            main = [k for k in keys if k not in MODIFIERS]
            if main:
                self.key_var.set(key_to_catalog_value(main[-1]))
        elif t == "mouse":
            for val, lbl in MOUSE_ACTIONS:
                if val == a.get("button"):
                    self.mouse_var.set(lbl)
        elif t == "text":
            self.text_var.set(a.get("text", ""))
        self._suppress_form = False
        self._show_form(t)

    def _show_form(self, t):
        for f in (self.forms_key, self.forms_mouse, self.forms_text, self.forms_none):
            f.pack_forget()
        {"key": self.forms_key, "mouse": self.forms_mouse,
         "text": self.forms_text, "none": self.forms_none}[t].pack(fill="x")
        for val, b in self.seg_buttons.items():
            b.set_active(val == t)

    def _select_type(self, t):
        self.type_var.set(t)
        self._on_type_change()

    def _on_type_change(self):
        t = self.type_var.get()
        self._show_form(t)
        if t == "none":
            self.set_mapping(self.selected, {"type": "none"})
        elif t == "mouse" and self.mouse_var.get():
            self._apply_mouse_form()
        elif t == "text" and self.text_var.get():
            self._apply_text_form()
        elif t == "key":
            self._apply_key_form()

    # ----------------------------------------------------------- editing
    def set_mapping(self, bid, action):
        action = validate_action(action) if action else None
        old = self.mappings.get(bid)
        if action:
            self.mappings[bid] = action
        else:
            self.mappings.pop(bid, None)
        if old != action:
            self.dirty = True
            self.save_current(quiet=True)  # auto-save: changes apply instantly
        self.refresh_all()
        if bid == self.selected:
            self.sel_current.set(self._current_text(self.mappings.get(bid)))

    def _toggle_mod(self, m):
        self.mod_vars[m].set(not self.mod_vars[m].get())
        self._apply_key_form()

    def _apply_key_form(self):
        if self._suppress_form or not self.selected:
            return
        keys = [m for m in MODIFIERS if self.mod_vars[m].get()]
        k = catalog_value_to_key(self.key_var.get())
        if k:
            keys.append(k)
        if keys:
            self.set_mapping(self.selected, {"type": "key", "keys": keys})

    def _apply_mouse_form(self):
        if self._suppress_form or not self.selected:
            return
        lbl = self.mouse_var.get()
        for val, l in MOUSE_ACTIONS:
            if l == lbl:
                self.set_mapping(self.selected, {"type": "mouse", "button": val})

    def _apply_text_form(self):
        if self._suppress_form or not self.selected:
            return
        if self.text_var.get():
            self.set_mapping(self.selected, {"type": "text", "text": self.text_var.get()})

    def reset_selected(self):
        if self.selected:
            self.set_mapping(self.selected, storage.DEFAULT_MAPPINGS.get(self.selected))
            self._load_form()

    def clear_selected(self):
        if self.selected:
            self.set_mapping(self.selected, None)
            self._load_form()

    # ------------------------------------------------------- key capture
    def toggle_capture(self):
        if self.capturing:
            self.stop_capture()
        else:
            self.start_capture()

    def start_capture(self):
        if not self.selected:
            return
        self.stop_learning()
        self.capturing = True
        self.capture_mods = []
        self.capture_deadline = time.monotonic() + 15
        self.type_var.set("key")
        self._show_form("key")
        self.capture_btn.configure(text="…Press a key  (click to cancel)")
        self.capture_btn.set_kind("learn")
        self.hint_var.set(f"Press the key to assign to {BUTTON_BY_ID[self.selected]['name']}")
        self.hint_lbl.configure(fg=C_PINK)
        self.canvas.focus_set()

    def stop_capture(self):
        self.capturing = False
        self.capture_mods = []
        self.capture_btn.configure(text="Press a key to assign")
        self.capture_btn.set_kind("primary")
        self.hint_var.set(HINT_DEFAULT)
        self.hint_lbl.configure(fg=C_MUTED)

    def _finish_capture(self, keys):
        bid = self.selected
        self.stop_capture()
        self.set_mapping(bid, {"type": "key", "keys": normalize_combo(keys)})
        self._load_form()
        self.log(f"{BUTTON_BY_ID[bid]['name']} → {describe_action(self.mappings.get(bid))}")

    def _on_key_press(self, e):
        if not self.capturing:
            return None
        mod = tk_modifier(e.keysym)
        if mod:
            if mod not in self.capture_mods:
                self.capture_mods.append(mod)
            return "break"
        k = tk_event_to_key(e.keysym, e.char)
        if k:
            self._finish_capture(self.capture_mods + [k])
        else:
            self.log(f"This key cannot be assigned: {e.keysym}")
        return "break"

    def _on_key_release(self, e):
        if not self.capturing:
            return None
        mod = tk_modifier(e.keysym)
        if mod and self.capture_mods:
            # modifier(s) pressed and released alone -> register modifiers
            self._finish_capture(list(self.capture_mods))
        return "break"

    # ----------------------------------------------------------- learning
    def open_fix_dialog(self):
        """Explain how fixing works, then let the user start it."""
        d = tk.Toplevel(self.root, bg=C_PANEL, padx=22, pady=18)
        d.title("Fix button detection")
        d.transient(self.root)
        d.resizable(False, False)
        tk.Label(d, text="Fix button detection", bg=C_PANEL, fg=C_TEXT,
                 font=self.f_current, anchor="w").pack(fill="x")
        steps = (
            "Use this only if pressing a button on the Micro lights up a different "
            "button on screen (or none).\n\n"
            "1.  Click “Start”.\n"
            "2.  The button to press is outlined in pink, and named under the controller.\n"
            "3.  Press that button on the Micro. The next one is highlighted automatically.\n"
            "4.  Repeat until all buttons are done (or click “■ Stop fixing”).\n\n"
            "This re-learns which physical button is which. "
            "Your key assignments are kept.")
        tk.Label(d, text=steps, bg=C_PANEL, fg=C_MUTED, font=self.f_small, justify="left",
                 wraplength=420, anchor="w").pack(fill="x", pady=(8, 14))
        row = tk.Frame(d, bg=C_PANEL)
        row.pack(fill="x")

        def go(fn):
            d.destroy()
            fn()
        FlatButton(row, "Start (all buttons)", lambda: go(self.start_wizard), kind="primary",
                   font=self.f_small).pack(side="left")
        if self.selected:
            FlatButton(row, f"Only {BUTTON_BY_ID[self.selected]['name']}",
                       lambda: go(self.learn_selected), font=self.f_small).pack(side="left", padx=(6, 0))
        FlatButton(row, "Cancel", d.destroy, kind="ghost", font=self.f_small).pack(side="right")
        FlatButton(d, "Undo all fixes (back to defaults)", lambda: go(self.reset_learning),
                   kind="ghost", font=self.f_small, padx=0).pack(anchor="w", pady=(10, 0))
        d.bind("<Escape>", lambda e: d.destroy())
        d.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - d.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - d.winfo_height()) // 3
        d.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        d.grab_set()

    def learn_selected(self):
        if not self.selected:
            return
        self.wizard = []
        self._begin_learn(self.selected)

    def start_wizard(self):
        self.wizard = list(WIZARD_ORDER)
        self._begin_learn(self.wizard.pop(0))

    def _begin_learn(self, bid):
        if self.capturing:
            self.stop_capture()
        self.executor.release_all()
        self.learn_target = bid
        self.selected = bid
        self.sel_title.set(BUTTON_BY_ID[bid]["name"])
        self._load_form()
        rest = f"({len(self.wizard)} more)" if self.wizard else ""
        self.hint_var.set(f"Press {BUTTON_BY_ID[bid]['name']} on the controller {rest}")
        self.hint_lbl.configure(fg=C_PINK)
        self.learn_btn.configure(text="■ Stop fixing")
        self.learn_btn.command = self.stop_learning
        self.learn_btn.set_kind("learn")
        self.learn_btn.configure(padx=8)
        self.refresh_visuals()

    def stop_learning(self):
        if self.learn_target is None:
            return
        self.learn_target = None
        self.wizard = []
        self.learn_btn.configure(text=LEARN_LINK, padx=0)
        self.learn_btn.command = self.open_fix_dialog
        self.learn_btn.set_kind("ghost")
        self.hint_var.set(HINT_DEFAULT)
        self.hint_lbl.configure(fg=C_MUTED)
        self.refresh_visuals()

    def _finish_learn(self):
        sources, self._learn_pending = self._learn_pending, None
        if sources and self.learn_target is not None:
            self._learned(sources)

    def _learned(self, sources):
        if isinstance(sources, str):
            sources = [sources]
        target = self.learn_target
        smap = self.settings["source_map"]
        for s in [s for s, t in smap.items() if t == target]:
            del smap[s]
        for src in sources:
            smap[src] = target
            self.unknown_sources.discard(src)
        storage.save_settings(self.settings)
        self.log(f"Learned: {' + '.join(sources)} → {BUTTON_BY_ID[target]['name']}")
        if self.wizard:
            self._begin_learn(self.wizard.pop(0))
        else:
            self.stop_learning()
            self.log("Learning complete")

    def reset_learning(self):
        if messagebox.askyesno(APP_NAME, "Delete all learned button bindings?"):
            self.settings["source_map"] = {}
            storage.save_settings(self.settings)
            self.log("Learned buttons reset")

    def resolve(self, source):
        smap = self.settings["source_map"]
        if source in smap:
            return smap[source]
        return DEFAULT_SOURCE_MAP.get(source)

    # ------------------------------------------------------- input events
    def on_source_down(self, source):
        self.last_activity = time.monotonic()
        if self.learn_target is not None:
            # one physical press can emit several inputs at once (e.g. a
            # trigger sends an analog value *and* a button bit): collect them
            # for a moment and bind them all to the target button
            if self._learn_pending is None:
                self._learn_pending = [source]
                self.root.after(150, self._finish_learn)
            elif source not in self._learn_pending:
                self._learn_pending.append(source)
            return
        bid = self.resolve(source)
        self.log(f"Input {source} → {BUTTON_BY_ID[bid]['name'] if bid else '?'}")
        if bid is None:
            if source not in self.unknown_sources:
                self.unknown_sources.add(source)
                self.log(f"Unknown input {source} — use “{LEARN_LINK}” to bind it")
            return
        if bid in DISABLED_IDS:
            return  # e.g. Home: shown but never remapped
        srcs = self.pressed.setdefault(bid, set())
        first = not srcs
        srcs.add(source)
        if first:
            if self.enabled_var.get() and not self.capturing:
                self.executor.press(bid, self.mappings.get(bid))
            self.refresh_visuals()

    def on_source_up(self, source):
        bid = self.resolve(source)
        if bid is None:
            return
        srcs = self.pressed.get(bid)
        if not srcs:
            return
        srcs.discard(source)
        if not srcs:
            self.executor.release(bid)
            self.refresh_visuals()

    # ------------------------------------------------------- worker
    def _start_worker(self):
        ctx = mp.get_context("spawn")
        self.q = ctx.Queue()
        self.stop_evt = ctx.Event()
        self.proc = ctx.Process(target=input_worker.run,
                                args=(self.q, self.stop_evt, self.settings["force_raw"],
                                      bool(self.settings.get("exclusive"))),
                                daemon=True)
        self.proc.start()

    def poll(self):
        try:
            while True:
                self._ui_q.get_nowait()()
        except queue_mod.Empty:
            pass
        try:
            for _ in range(200):
                msg = self.q.get_nowait()
                self._handle_msg(msg)
        except queue_mod.Empty:
            pass
        except Exception as e:  # pragma: no cover
            self.log(f"Queue error: {e}")
        if self.capturing and time.monotonic() > self.capture_deadline:
            self.stop_capture()
            self.log("Timed out waiting for a key")
        self.executor.tick()
        if not self.proc.is_alive() and not getattr(self, "_dead_reported", False):
            self._dead_reported = True
            self.set_device("Input process stopped (check pygame-ce)", C_RED)
        self.root.after(4, self.poll)

    def set_device(self, text, color):
        self.device_var.set(text)
        self.dot.itemconfigure(self._dot, fill=color)

    def _handle_msg(self, msg):
        if DEBUG_LOG:
            try:
                with open(DEBUG_LOG, "a", encoding="utf-8") as f:
                    f.write(f"{time.time():.3f} {msg!r} learn={self.learn_target}\n")
            except OSError:
                pass
        kind = msg[0]
        if kind == "down":
            self.on_source_down(msg[1])
        elif kind == "up":
            self.on_source_up(msg[1])
        elif kind == "connected":
            _, name, guid, mode = msg
            self.device_name = name
            self.last_activity = time.monotonic()
            m = {"controller": "GameController", "exclusive": "Exclusive · Home blocked"}.get(mode, "Raw")
            self.set_device(f"Connected: {name}  ·  {m}", C_GREEN)
            self.hide_banner("kmode")
            self.refresh_visuals()
            self.log(f"Connected: {name}")
        elif kind == "disconnected":
            self.executor.release_all()
            self.pressed.clear()
            self.device_name = None
            self.refresh_visuals()
            self.set_device("Disconnected — reconnect the 8BitDo Micro (USB or Bluetooth)", C_RED)
            self.log(f"Disconnected: {msg[1]}")
        elif kind == "kmode":
            if not self.device_name:
                self.set_device(f"{msg[1]} is in K (keyboard) mode", C_ORANGE)
                self.show_banner(
                    "⚠ The 8BitDo Micro is in K (keyboard) mode. In K mode the Micro sends keys itself, so they "
                    "cannot be remapped. Set the switch on the back to D — it will be detected automatically.",
                    kind="kmode")
        elif kind == "status":
            if not self.device_name:
                self.set_device(msg[1], C_ORANGE)
        elif kind == "error":
            self.log(msg[1])

    # ------------------------------------------------------- profiles
    def save_current(self, quiet=False):
        storage.save_profile(self.profile_name, self.mappings)
        self.settings["profile"] = self.profile_name
        storage.save_settings(self.settings)
        self.dirty = False
        self._update_title()
        if not quiet:
            self.log(f"Saved: {self.profile_name}")

    def switch_profile(self, name):
        if name == self.profile_name:
            return
        self.executor.release_all()
        self.profile_name = name
        self.mappings = storage.load_profile(name)
        self.settings["profile"] = name
        storage.save_settings(self.settings)
        self.dirty = False
        self.refresh_all()
        self._load_form()
        self.log(f"Profile: {name}")

    def _reload_profiles(self, select):
        self.profiles = storage.list_profiles()
        self.profile_cb.configure(values=self.profiles)
        self.profile_var.set(select)

    def _ask_name(self, title, initial=""):
        name = simpledialog.askstring(APP_NAME, title, initialvalue=initial, parent=self.root)
        if not name or not name.strip():
            return None
        name = storage._safe_name(name)
        if name in self.profiles and not messagebox.askyesno(APP_NAME, f"Overwrite \"{name}\"?"):
            return None
        return name

    def new_profile(self):
        name = self._ask_name("New profile name:")
        if name:
            storage.save_profile(name, storage.DEFAULT_MAPPINGS)
            self._reload_profiles(name)
            self.profile_name = None
            self.switch_profile(name)

    def duplicate_profile(self):
        name = self._ask_name("Name for the copy:", self.profile_name + "_copy")
        if name:
            storage.save_profile(name, self.mappings)
            self._reload_profiles(name)
            self.profile_name = None
            self.switch_profile(name)

    def delete_profile(self):
        if self.profile_name == "default":
            messagebox.showinfo(APP_NAME, "The default profile cannot be deleted.")
            return
        if messagebox.askyesno(APP_NAME, f"Delete profile \"{self.profile_name}\"?"):
            storage.delete_profile(self.profile_name)
            self._reload_profiles("default")
            self.profile_name = None
            self.switch_profile("default")

    def import_profile(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")], parent=self.root)
        if not path:
            return
        try:
            name, mappings = storage.import_profile(path)
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))
            return
        storage.save_profile(name, mappings)
        self._reload_profiles(name)
        self.profile_name = None
        self.switch_profile(name)

    def export_profile(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            initialfile=f"{self.profile_name}.json",
                                            filetypes=[("JSON", "*.json")], parent=self.root)
        if path:
            storage.export_profile(path, self.profile_name, self.mappings)
            self.log(f"Exported: {path}")

    # ------------------------------------------------------- misc
    def on_toggle_enabled(self):
        self.settings["enabled"] = self.enabled_var.get()
        if not self.settings["enabled"]:
            self.executor.release_all()
        storage.save_settings(self.settings)
        self.log("Remap " + ("on" if self.settings["enabled"] else "off"))

    def open_gc_settings(self):
        import subprocess
        subprocess.Popen(["open", "x-apple.systempreferences:com.apple.Game-Controller-Settings.extension"])

    def on_toggle_exclusive(self):
        self._update_home_chip()
        if bool(self.settings.get("exclusive")) == self.exclusive_var.get():
            return
        self.settings["exclusive"] = self.exclusive_var.get()
        storage.save_settings(self.settings)
        self.restart_worker()
        self.log("Exclusive mode " + ("on — Home blocked, but the D-pad won't work"
                                      if self.settings["exclusive"] else "off"))

    def restart_worker(self):
        self.executor.release_all()
        self.pressed.clear()
        self.device_name = None
        self.stop_evt.set()
        self.proc.join(timeout=1.5)
        if self.proc.is_alive():
            self.proc.terminate()
        self._dead_reported = False
        self.set_device("Reconnecting…", C_ORANGE)
        self.refresh_visuals()
        self._start_worker()

    # ------------------------------------------------------- updates
    def _post(self, fn):
        """Run fn on the Tk thread (safe to call from any thread)."""
        self._ui_q.put(fn)

    def on_toggle_check_updates(self):
        self.settings["check_updates"] = self.check_updates_var.get()
        storage.save_settings(self.settings)

    def check_for_updates(self, manual=True):
        if manual:
            self.log("Checking for updates…")

        def work():
            try:
                info = updater.fetch_latest()
                err = None
            except Exception as e:
                info, err = None, e
            self._post(lambda: self._update_checked(info, err, manual))
        threading.Thread(target=work, daemon=True).start()

    def _update_checked(self, info, err, manual):
        if err is not None:
            if manual:
                self.log("Update check failed")
                messagebox.showerror(APP_NAME, f"Could not check for updates:\n{err}", parent=self.root)
            return
        if not updater.is_newer(info["version"]):
            if manual:
                self.log(f"Up to date (v{__version__})")
                messagebox.showinfo(APP_NAME, f"You have the latest version (v{__version__}).",
                                    parent=self.root)
            return
        self._update_info = info
        self.log(f"Update available: v{info['version']}")
        self.show_update_bar()

    def show_update_bar(self, text=None):
        info = self._update_info
        if text is None:
            text = f"Version {info['version']} is available (you have {__version__})."
            if updater.can_self_update(info):
                self.update_btn.configure(text="Update now")
                if sys.platform == "darwin":
                    text += "  After updating, you may need to re-enable the app under Accessibility."
            else:
                self.update_btn.configure(text="Download…")
        self.update_var.set(text)
        if not self.update_bar.winfo_manager():
            self.update_bar.pack(side="top", fill="x", padx=20, pady=(0, 6), before=self.main_frame)

    def hide_update_bar(self):
        if not self._updating and self.update_bar.winfo_manager():
            self.update_bar.pack_forget()

    def open_release_page(self):
        import webbrowser
        webbrowser.open((self._update_info or {}).get("page") or updater.RELEASES_PAGE)

    def install_update(self):
        info = self._update_info
        if not info or self._updating:
            return
        if not updater.can_self_update(info):
            self.open_release_page()
            return
        self._updating = True
        self.show_update_bar(f"Downloading version {info['version']}…")

        def progress(frac):
            self._post(lambda: self.update_var.set(
                f"Downloading version {info['version']}… {int(frac * 100)}%"))

        def work():
            try:
                new = updater.prepare(info, progress)
                self._post(lambda: self._finish_update(new))
            except Exception as e:
                self._post(lambda: self._update_failed(e))
        threading.Thread(target=work, daemon=True).start()

    def _finish_update(self, new_path):
        try:
            updater.launch_installer(new_path)
        except Exception as e:
            self._update_failed(e)
            return
        self.update_var.set("Restarting…")
        self.root.after(200, self.on_close)

    def _update_failed(self, err):
        self._updating = False
        self.show_update_bar()
        messagebox.showerror(APP_NAME, f"The update failed:\n{err}\n\n"
                             "You can download it from the release page instead.", parent=self.root)

    def on_toggle_repeat(self):
        self.settings["repeat"] = self.repeat_var.get()
        self.executor.repeat_enabled = self.settings["repeat"]
        storage.save_settings(self.settings)

    def log(self, text):
        self.log_var.set(text)

    def show_banner(self, text, kind="info"):
        self._banner_kind = kind
        self.banner.configure(text=text)
        if not self.banner.winfo_manager():
            self.banner.pack(side="top", fill="x", padx=20, pady=(0, 6), before=self.main_frame)

    def hide_banner(self, kind=None):
        if kind and getattr(self, "_banner_kind", None) != kind:
            return
        if self.banner.winfo_manager():
            self.banner.pack_forget()

    def on_close(self):
        try:
            self.executor.release_all()
            if self.dirty:
                self.save_current(quiet=True)
            self.stop_evt.set()
            self.proc.join(timeout=1.0)
            if self.proc.is_alive():
                self.proc.terminate()
        finally:
            self.root.destroy()


def main():
    mp.freeze_support()
    root = tk.Tk()
    RemapperApp(root)
    root.mainloop()
