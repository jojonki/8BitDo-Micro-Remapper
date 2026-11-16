"""Exclusive (seized) HID access to the 8BitDo Micro in D mode — macOS only.

When the gamepad is opened exclusively, macOS' GameController stack stops
receiving it, so the Home button no longer launches the Games app (and games
no longer see the pad while this is active).

Input report layout (from the device's HID report descriptor, report ID 3):
    [0] report id (3)
    [1] low nibble: hat switch 0..7 (N, NE, E, SE, S, SW, W, NW), other = centred
    [2..5] X, Y, Z, Rz          (unused by the Micro)
    [6], [7] brake / accelerator (analog L2 / R2 on some firmwares)
    [8], [9] 16 button bits
    [10] battery
Sources emitted: ``x:hat:up`` …, ``x:bN`` (bit N of the button field),
``x:brake`` / ``x:accel``.
"""

import sys

VID = 0x2DC8
REPORT_ID = 3
TRIGGER_THRESHOLD = 128

_HAT_DIRS = {
    0: ("up",), 1: ("up", "right"), 2: ("right",), 3: ("down", "right"),
    4: ("down",), 5: ("down", "left"), 6: ("left",), 7: ("up", "left"),
}


def supported():
    if sys.platform != "darwin":
        return False
    try:
        import hid  # noqa: F401
        return True
    except Exception:
        return False


def parse_report(data):
    """Return the set of active source ids for one input report (or None)."""
    if not data:
        return None
    data = list(data)
    if data[0] != REPORT_ID:
        # some hidapi backends strip the report id
        data = [REPORT_ID] + data
    if len(data) < 10:
        return None
    active = set()
    hat = data[1] & 0x0F
    for d in _HAT_DIRS.get(hat, ()):
        active.add(f"x:hat:{d}")
    if data[6] >= TRIGGER_THRESHOLD:
        active.add("x:brake")
    if data[7] >= TRIGGER_THRESHOLD:
        active.add("x:accel")
    bits = data[8] | (data[9] << 8)
    for i in range(16):
        if bits & (1 << i):
            active.add(f"x:b{i}")
    return active


class ExclusiveMicro:
    def __init__(self):
        self.dev = None
        self.name = None
        self.active = set()
        self.error = None

    @property
    def is_open(self):
        return self.dev is not None

    def try_open(self):
        """Seize the first 8BitDo gamepad interface. True on success."""
        import ctypes
        import hid
        try:
            ctypes.CDLL(hid.__file__).hid_darwin_set_open_exclusive(1)
        except Exception:
            pass  # older hidapi builds open exclusively by default on macOS
        for d in hid.enumerate(VID, 0):
            if d.get("usage_page") == 1 and d.get("usage") in (4, 5):
                dev = hid.device()
                try:
                    dev.open_path(d["path"])
                except Exception as e:
                    self.error = str(e)
                    continue
                dev.set_nonblocking(1)
                self.dev = dev
                self.name = (d.get("product_string") or "8BitDo gamepad").strip()
                self.active = set()
                return True
        return False

    def poll(self):
        """Read pending reports; return list of ("down"|"up", source).
        Raises OSError when the device is gone."""
        events = []
        for _ in range(64):
            data = self.dev.read(64)
            if not data:
                break
            now = parse_report(data)
            if now is None:
                continue
            for s in sorted(now - self.active):
                events.append(("down", s))
            for s in sorted(self.active - now):
                events.append(("up", s))
            self.active = now
        return events

    def close(self):
        events = [("up", s) for s in sorted(self.active)]
        self.active = set()
        if self.dev is not None:
            try:
                self.dev.close()
            except Exception:
                pass
        self.dev = None
        return events
