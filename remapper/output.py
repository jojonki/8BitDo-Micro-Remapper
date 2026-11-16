"""Synthesizes keyboard / mouse output with pynput."""

import sys
import time

from .keys import MODIFIERS

REPEAT_DELAY = 0.40   # seconds before key auto-repeat starts
REPEAT_RATE = 0.035   # seconds between repeats
MOVE_STEP = 6         # pixels per tick for cursor movement
MOVE_ACCEL_MAX = 4.0


class OutputError(RuntimeError):
    pass


class Executor:
    """Executes action dicts. ``press``/``release`` are keyed by the logical
    controller button so that a release always matches what was pressed,
    even if the mapping was edited while the button was held."""

    def __init__(self, log=print):
        self.log = log
        self.kb = None
        self.mouse = None
        self.Key = None
        self.KeyCode = None
        self.Button = None
        self.error = None
        self.repeat_enabled = True
        self.active = {}   # button_id -> state dict
        try:
            from pynput import keyboard, mouse
            self.kb = keyboard.Controller()
            self.mouse = mouse.Controller()
            self.Key = keyboard.Key
            self.KeyCode = keyboard.KeyCode
            self.Button = mouse.Button
        except Exception as e:  # pragma: no cover - platform dependent
            self.error = f"Could not initialise pynput: {e}"
        # macOS: post keys through Quartz like a real keyboard (pynput's
        # synthetic F-keys are invisible to Carbon global hot keys)
        self.mac = None
        if sys.platform == "darwin":
            try:
                from .mac_keys import MacKeys
                self.mac = MacKeys()
            except Exception as e:  # pragma: no cover
                self.log(f"Quartz unavailable, using pynput: {e}")

    @property
    def available(self):
        return self.kb is not None

    # ---------------------------------------------------------- helpers
    def _key(self, name):
        if len(name) == 1:
            return self.KeyCode.from_char(name)
        k = getattr(self.Key, name, None)
        if k is None:
            raise OutputError(f"Key '{name}' is not available on this OS")
        return k

    def _resolve(self, name):
        """-> ("mac", name) for Quartz output, or ("pynput", key object)."""
        if self.mac is not None and self.mac.supports(name):
            return ("mac", name)
        return ("pynput", self._key(name))

    def _down(self, k, repeat=False):
        kind, obj = k
        if kind == "mac":
            self.mac.press(obj, repeat=repeat)
        else:
            self.kb.press(obj)

    def _press_keys(self, keys):
        resolved = [self._resolve(n) for n in keys]   # fail before pressing anything
        done = []
        for k in resolved:
            self._down(k)
            done.append(k)
        return done

    def _release_keys(self, objs):
        for kind, obj in reversed(objs):
            try:
                if kind == "mac":
                    self.mac.release(obj)
                else:
                    self.kb.release(obj)
            except Exception:
                pass

    # ------------------------------------------------------------ API
    def press(self, button_id, action):
        if not self.available or not action:
            return
        self.release(button_id)
        t = action.get("type")
        try:
            if t == "key":
                keys = action.get("keys") or []
                objs = self._press_keys(keys)
                main = [k for k in keys if k not in MODIFIERS]
                self.active[button_id] = {
                    "type": "key", "objs": objs,
                    "repeat": main and len(main) == 1 and keys[-1] not in MODIFIERS,
                    "next": time.monotonic() + REPEAT_DELAY,
                }
            elif t == "mouse":
                b = action.get("button")
                st = {"type": "mouse", "button": b, "start": time.monotonic()}
                if b in ("left", "right", "middle"):
                    self.mouse.press(getattr(self.Button, b))
                elif b.startswith("scroll_"):
                    self._scroll(b)
                    st["next"] = time.monotonic() + REPEAT_DELAY
                elif b.startswith("move_"):
                    self._move(b, 1.0)
                self.active[button_id] = st
            elif t == "text":
                self.kb.type(action.get("text", ""))
        except OutputError as e:
            self.log(str(e))
        except Exception as e:
            self.log(f"Output error: {e}")

    def release(self, button_id):
        st = self.active.pop(button_id, None)
        if not st:
            return
        try:
            if st["type"] == "key":
                self._release_keys(st["objs"])
            elif st["type"] == "mouse" and st["button"] in ("left", "right", "middle"):
                self.mouse.release(getattr(self.Button, st["button"]))
        except Exception as e:
            self.log(f"Output error: {e}")

    def release_all(self):
        for bid in list(self.active):
            self.release(bid)

    def tick(self):
        """Called periodically from the GUI loop: auto-repeat & cursor moves."""
        if not self.active:
            return
        now = time.monotonic()
        for st in list(self.active.values()):
            try:
                if st["type"] == "key" and st["repeat"] and self.repeat_enabled:
                    if now >= st["next"]:
                        # OS sees repeated key-down events (flagged as autorepeat)
                        self._down(st["objs"][-1], repeat=True)
                        st["next"] = now + REPEAT_RATE
                elif st["type"] == "mouse":
                    b = st["button"]
                    if b.startswith("move_"):
                        held = now - st["start"]
                        accel = min(MOVE_ACCEL_MAX, 1.0 + held * 2.0)
                        self._move(b, accel)
                    elif b.startswith("scroll_") and now >= st.get("next", now + 1):
                        self._scroll(b)
                        st["next"] = now + 0.08
            except Exception as e:
                self.log(f"Output error: {e}")

    def _scroll(self, b):
        dx, dy = {"scroll_up": (0, 1), "scroll_down": (0, -1),
                  "scroll_left": (-1, 0), "scroll_right": (1, 0)}[b]
        self.mouse.scroll(dx, dy)

    def _move(self, b, accel):
        step = int(MOVE_STEP * accel)
        dx, dy = {"move_up": (0, -step), "move_down": (0, step),
                  "move_left": (-step, 0), "move_right": (step, 0)}[b]
        self.mouse.move(dx, dy)
