"""Keep the 8BitDo Micro from powering itself off.

The Micro switches itself off after ~15 minutes without a button press, and
its firmware has no setting for that (the firmware image is encrypted, so it
cannot be patched either). Measured on hardware over Bluetooth: if the host
sends the pad a zero-strength rumble output report (report 0x05, all zero -
a no-op, the Micro has no motor) every 30 s, the idle timer never fires.

The user picks how long the pad may sit idle before it powers off. The app
keeps pinging until (chosen time - 15 min) have passed since the last button
press, then stops; the pad's own 15-minute timer then switches it off.
"""

import sys
import threading

VID = 0x2DC8
PID_MICRO = 0x9020
FIRMWARE_IDLE_MIN = 15          # the pad's built-in idle power-off
PING_INTERVAL_MS = 30_000

# (setting value, menu label); minutes, or None = never power off
POWER_OFF_CHOICES = [
    (15, "15 min (controller default)"),
    (30, "30 min"),
    (60, "1 hour"),
    (120, "2 hours"),
    (240, "4 hours"),
    (360, "6 hours"),
    (480, "8 hours"),
    (None, "Never"),
]
DEFAULT_POWER_OFF = 15

_PINGS = (
    bytes([0x05, 0, 0, 0, 0]),      # rumble, strength 0
)


def normalize_power_off(value):
    valid = [m for m, _ in POWER_OFF_CHOICES]
    return value if value in valid else DEFAULT_POWER_OFF


def short_label(minutes):
    if minutes is None:
        return "Never"
    if minutes < 60:
        return f"{minutes} min"
    h = minutes // 60
    return f"{h} hour" + ("s" if h > 1 else "")


def should_ping(power_off_min, idle_seconds):
    """True while the pad should be kept awake.

    power_off_min: chosen total idle time before power-off (None = never).
    idle_seconds:  time since the last button press.
    """
    if power_off_min is None:
        return True
    if power_off_min <= FIRMWARE_IDLE_MIN:
        return False
    return idle_seconds < (power_off_min - FIRMWARE_IDLE_MIN) * 60


def supported():
    try:
        import hid  # noqa: F401
        return True
    except Exception:
        return False


def ping_once():
    """Send the no-op report to every connected Micro. Returns True if sent."""
    import ctypes
    import hid

    if sys.platform == "darwin":
        try:  # share the device with SDL / macOS GameController
            ctypes.CDLL(hid.__file__).hid_darwin_set_open_exclusive(0)
        except Exception:
            pass
    sent = False
    for info in hid.enumerate(VID, PID_MICRO):
        dev = hid.device()
        try:
            dev.open_path(info["path"])
            for pkt in _PINGS:
                try:
                    if dev.write(pkt) > 0:
                        sent = True
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            try:
                dev.close()
            except Exception:
                pass
    return sent


def ping_async(done=None):
    """Run ping_once() off the UI thread; done(ok) is called from that thread."""
    def run():
        try:
            ok = ping_once()
        except Exception:
            ok = False
        if done:
            done(ok)
    threading.Thread(target=run, daemon=True).start()
