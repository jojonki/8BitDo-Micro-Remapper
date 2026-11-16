"""Controller reader running in its own process.

SDL (pygame) and Tk both want to own the native event loop on macOS, so the
controller is read in a child process and events are sent to the GUI via a
multiprocessing queue as tuples:

    ("status", text)
    ("connected", name, guid, mode)       mode = "controller" | "joystick"
    ("disconnected", name)
    ("down", source_id) / ("up", source_id)
    ("error", text)

``source_id`` examples: ``c:a`` / ``c:dpup`` / ``c:lefttrigger`` (normalized
SDL GameController), ``b:3`` (raw button), ``h0:up`` (hat), ``a1:-`` (axis).
"""

import os
import time

AXIS_THRESHOLD = 0.5

CONTROLLER_BUTTONS = {
    0: "a", 1: "b", 2: "x", 3: "y", 4: "back", 5: "guide", 6: "start",
    7: "leftstick", 8: "rightstick", 9: "leftshoulder", 10: "rightshoulder",
    11: "dpup", 12: "dpdown", 13: "dpleft", 14: "dpright",
    15: "misc1", 16: "paddle1", 17: "paddle2", 18: "paddle3", 19: "paddle4",
    20: "touchpad",
}
CONTROLLER_AXES = {0: "leftx", 1: "lefty", 2: "rightx", 3: "righty",
                   4: "lefttrigger", 5: "righttrigger"}


def _prepare_env():
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    # keep receiving input while another app has focus (that's the point!)
    os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
    # use positional face buttons for Nintendo-style pads
    os.environ.setdefault("SDL_GAMECONTROLLER_USE_BUTTON_LABELS", "0")


class _Reader:
    def __init__(self, queue, force_raw=False, exclusive=False):
        self.q = queue
        self.force_raw = force_raw
        self.exclusive = exclusive
        self.hx = None           # ExclusiveMicro when seized via hidapi
        self._hx_next_try = 0.0
        self.devices = {}      # instance_id -> (obj, name, mode)
        self.pressed = set()   # active source ids (for axes/hats edge detection)

    def send(self, *msg):
        try:
            self.q.put_nowait(msg)
        except Exception:
            pass

    # -------------------------------------------------------------- setup
    def start(self):
        _prepare_env()
        import pygame
        self.pg = pygame
        pygame.display.init()
        pygame.joystick.init()
        self.ctl = None
        if not self.force_raw:
            try:
                from pygame._sdl2 import controller as ctl
                ctl.init()
                self.ctl = ctl
            except Exception as e:  # pragma: no cover - depends on build
                self.send("status", f"GameController API unavailable (raw mode): {e}")
        for i in range(pygame.joystick.get_count()):
            self.open_device(i)
        if not self.devices:
            self.send("status", "No controller — connect the 8BitDo Micro (USB or Bluetooth)")
            self.check_keyboard_mode()

    def open_device(self, index):
        pg = self.pg
        if self.hx is not None and self.hx.is_open:
            try:
                if pg.joystick.Joystick(index).get_name().startswith("8BitDo"):
                    return  # already read exclusively via HID
            except Exception:
                pass
        try:
            if self.ctl is not None and self.ctl.is_controller(index):
                c = self.ctl.Controller(index)
                js = c.as_joystick()
                iid = js.get_instance_id()
                if iid in self.devices:
                    return
                name = c.name or js.get_name()
                self.devices[iid] = (c, name, "controller")
                self.send("connected", name, js.get_guid(), "controller")
                return
            js = pg.joystick.Joystick(index)
            iid = js.get_instance_id()
            if iid in self.devices:
                return
            name = js.get_name()
            self.devices[iid] = (js, name, "joystick")
            self.send("connected", name, js.get_guid(), "joystick")
        except Exception as e:
            self.send("error", f"Cannot open device: {e}")

    def close_device(self, iid):
        dev = self.devices.pop(iid, None)
        if dev:
            prefix = f"{iid}|"
            for sid in [s for s in self.pressed if s.startswith(prefix)]:
                self.pressed.discard(sid)
                self.send("up", sid.split("|", 1)[1])
            self.send("disconnected", dev[1])

    def is_controller(self, iid):
        d = self.devices.get(iid)
        return bool(d and d[2] == "controller")

    # ------------------------------------------------------------- events
    def _set(self, iid, source, down):
        key = f"{iid}|{source}"
        if down and key not in self.pressed:
            self.pressed.add(key)
            self.send("down", source)
        elif not down and key in self.pressed:
            self.pressed.discard(key)
            self.send("up", source)

    def _axis(self, iid, prefix, value):
        """value normalized to -1..1; emits <prefix>:- / <prefix>:+"""
        self._set(iid, prefix + ":-", value < -AXIS_THRESHOLD)
        self._set(iid, prefix + ":+", value > AXIS_THRESHOLD)

    def handle(self, ev):
        pg = self.pg
        t = ev.type
        # --- hot plug -------------------------------------------------
        if t == pg.JOYDEVICEADDED:
            self.open_device(ev.device_index)
            return
        if self.ctl is not None and t == getattr(pg, "CONTROLLERDEVICEADDED", -1):
            self.open_device(ev.device_index)
            return
        if t == pg.JOYDEVICEREMOVED:
            self.close_device(ev.instance_id)
            return
        if self.ctl is not None and t == getattr(pg, "CONTROLLERDEVICEREMOVED", -1):
            self.close_device(ev.instance_id)
            return

        # --- normalized GameController events ---------------------------
        if t in (getattr(pg, "CONTROLLERBUTTONDOWN", -1), getattr(pg, "CONTROLLERBUTTONUP", -1)):
            iid = ev.instance_id
            if not self.is_controller(iid):
                return
            name = CONTROLLER_BUTTONS.get(ev.button, f"btn{ev.button}")
            self._set(iid, f"c:{name}", t == pg.CONTROLLERBUTTONDOWN)
            return
        if t == getattr(pg, "CONTROLLERAXISMOTION", -1):
            iid = ev.instance_id
            if not self.is_controller(iid):
                return
            name = CONTROLLER_AXES.get(ev.axis, f"axis{ev.axis}")
            v = ev.value / 32767.0 if abs(ev.value) > 1.0 else ev.value
            if name.endswith("trigger"):
                self._set(iid, f"c:{name}", v > AXIS_THRESHOLD)
            else:
                self._axis(iid, f"c:{name}", v)
            return

        # --- raw joystick events (only for devices not opened as controller)
        if t in (pg.JOYBUTTONDOWN, pg.JOYBUTTONUP):
            iid = ev.instance_id
            if iid not in self.devices or self.is_controller(iid):
                return
            self._set(iid, f"b:{ev.button}", t == pg.JOYBUTTONDOWN)
        elif t == pg.JOYHATMOTION:
            iid = ev.instance_id
            if iid not in self.devices or self.is_controller(iid):
                return
            x, y = ev.value
            h = f"h{ev.hat}"
            self._set(iid, f"{h}:left", x < 0)
            self._set(iid, f"{h}:right", x > 0)
            self._set(iid, f"{h}:up", y > 0)
            self._set(iid, f"{h}:down", y < 0)
        elif t == pg.JOYAXISMOTION:
            iid = ev.instance_id
            if iid not in self.devices or self.is_controller(iid):
                return
            self._axis(iid, f"a{ev.axis}", ev.value)

    def loop(self, stop_event):
        pg = self.pg
        last_rescan = time.monotonic()
        parent_pid = os.getppid()
        while not stop_event.is_set():
            if os.getppid() != parent_pid:   # GUI died -> don't linger
                self._close_exclusive()
                return
            self._service_exclusive()
            for ev in pg.event.get():
                try:
                    self.handle(ev)
                except Exception as e:
                    self.send("error", f"Input error: {e}")
            now = time.monotonic()
            if not self.devices and now - last_rescan > 2.0:
                # some backends miss hot-plug events without a window
                last_rescan = now
                for i in range(pg.joystick.get_count()):
                    self.open_device(i)
                if not self.devices:
                    self.check_keyboard_mode()
            time.sleep(0.002)

    # ------------------------------------------------- exclusive HID mode
    def _service_exclusive(self):
        if not self.exclusive:
            return
        from . import hid_exclusive as hx_mod
        if self.hx is None:
            if not hx_mod.supported():
                self.exclusive = False
                self.send("status", "Exclusive mode needs macOS + hidapi")
                return
            self.hx = hx_mod.ExclusiveMicro()
        if not self.hx.is_open:
            now = time.monotonic()
            if now < self._hx_next_try:
                return
            self._hx_next_try = now + 2.0
            if self.hx.try_open():
                # stop reading the same pad through SDL
                for iid, (obj, name, mode) in list(self.devices.items()):
                    if name.startswith("8BitDo"):
                        self.devices.pop(iid, None)
                        prefix = f"{iid}|"
                        for sid in [x for x in self.pressed if x.startswith(prefix)]:
                            self.pressed.discard(sid)
                            self.send("up", sid.split("|", 1)[1])
                self.send("connected", self.hx.name, "", "exclusive")
            return
        try:
            events = self.hx.poll()
        except Exception:
            for kind, src in self.hx.close():
                self.send(kind, src)
            self.send("disconnected", self.hx.name or "8BitDo")
            return
        for kind, src in events:
            self.send(kind, src)

    def _close_exclusive(self):
        if self.hx is not None and self.hx.is_open:
            self.hx.close()

    def check_keyboard_mode(self):
        """Detect an 8BitDo pad that is plugged in but switched to K mode
        (it then shows up as a USB keyboard, not as a game controller)."""
        found = find_keyboard_mode_device()
        if found != getattr(self, "_kmode", None):
            self._kmode = found
            if found:
                self.send("kmode", found)


EIGHTBITDO_VID = 0x2DC8


def find_keyboard_mode_device():
    """Return a description if an 8BitDo device exposes a keyboard interface
    (= K mode), else None. Uses hidapi enumeration only (never opens it)."""
    try:
        import hid
    except Exception:
        return None
    try:
        for d in hid.enumerate(EIGHTBITDO_VID, 0):
            if d.get("usage_page") == 1 and d.get("usage") == 6:
                name = (d.get("product_string") or "").strip() or "8BitDo"
                return f"{name} (PID 0x{d.get('product_id', 0):04X})"
    except Exception:
        return None
    return None


def run(queue, stop_event, force_raw=False, exclusive=False):
    """Process entry point."""
    reader = _Reader(queue, force_raw=force_raw, exclusive=exclusive)
    try:
        reader.start()
        reader.loop(stop_event)
    except Exception as e:
        reader.send("error", f"Input process stopped: {e}")
    finally:
        reader._close_exclusive()
