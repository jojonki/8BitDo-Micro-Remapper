"""macOS key output via Quartz, shaped like a real keyboard.

pynput's synthetic F-keys are not seen by Carbon ``RegisterEventHotKey``
hot keys (e.g. apps using the ``global-hotkey`` crate), while events posted
the way below are. We also mimic hardware details apps may check:
  * function / navigation keys carry the ``SecondaryFn`` flag,
  * modifiers are sent as ``FlagsChanged`` events and their state is
    reflected in the flags of every following event,
  * held-key repeats are marked with the autorepeat field.
"""

# kVK_* virtual key codes (HIToolbox/Events.h)
KEYCODES = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04, "g": 0x05, "z": 0x06,
    "x": 0x07, "c": 0x08, "v": 0x09, "b": 0x0B, "q": 0x0C, "w": 0x0D, "e": 0x0E,
    "r": 0x0F, "y": 0x10, "t": 0x11, "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15,
    "6": 0x16, "5": 0x17, "=": 0x18, "9": 0x19, "7": 0x1A, "-": 0x1B, "8": 0x1C,
    "0": 0x1D, "]": 0x1E, "o": 0x1F, "u": 0x20, "[": 0x21, "i": 0x22, "p": 0x23,
    "l": 0x25, "j": 0x26, "'": 0x27, "k": 0x28, ";": 0x29, "\\": 0x2A, ",": 0x2B,
    "/": 0x2C, "n": 0x2D, "m": 0x2E, ".": 0x2F, "`": 0x32,
    "enter": 0x24, "tab": 0x30, "space": 0x31, "backspace": 0x33, "esc": 0x35,
    "cmd": 0x37, "shift": 0x38, "caps_lock": 0x39, "alt": 0x3A, "ctrl": 0x3B,
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76, "f5": 0x60, "f6": 0x61,
    "f7": 0x62, "f8": 0x64, "f9": 0x65, "f10": 0x6D, "f11": 0x67, "f12": 0x6F,
    "f13": 0x69, "f14": 0x6B, "f15": 0x71, "f16": 0x6A, "f17": 0x40, "f18": 0x4F,
    "f19": 0x50, "f20": 0x5A,
    "insert": 0x72, "home": 0x73, "page_up": 0x74, "delete": 0x75, "end": 0x77,
    "page_down": 0x79, "left": 0x7B, "right": 0x7C, "down": 0x7D, "up": 0x7E,
}

# keys a real Apple keyboard reports with the fn (SecondaryFn) flag
FN_KEYS = {f"f{i}" for i in range(1, 21)} | {
    "insert", "home", "end", "page_up", "page_down", "delete",
    "left", "right", "down", "up"}
ARROWS = {"left", "right", "down", "up"}


class MacKeys:
    def __init__(self):
        import Quartz as Q
        self.Q = Q
        self.mod_masks = {
            "shift": Q.kCGEventFlagMaskShift,
            "ctrl": Q.kCGEventFlagMaskControl,
            "alt": Q.kCGEventFlagMaskAlternate,
            "cmd": Q.kCGEventFlagMaskCommand,
        }
        self.held_mods = {}   # name -> count (two buttons may hold the same modifier)

    @staticmethod
    def supports(name):
        return name in KEYCODES

    def _mod_flags(self):
        f = 0
        for m, n in self.held_mods.items():
            if n > 0:
                f |= self.mod_masks[m]
        return f

    def flags_for(self, name):
        Q = self.Q
        f = self._mod_flags()
        if name in FN_KEYS:
            f |= Q.kCGEventFlagMaskSecondaryFn
        if name in ARROWS:
            f |= Q.kCGEventFlagMaskNumericPad
        return f

    def _post(self, name, down, repeat=False):
        Q = self.Q
        ev = Q.CGEventCreateKeyboardEvent(None, KEYCODES[name], down)
        if name in self.mod_masks:
            Q.CGEventSetType(ev, Q.kCGEventFlagsChanged)
        Q.CGEventSetFlags(ev, self.flags_for(name))
        if repeat:
            Q.CGEventSetIntegerValueField(ev, Q.kCGKeyboardEventAutorepeat, 1)
        Q.CGEventPost(Q.kCGHIDEventTap, ev)

    def press(self, name, repeat=False):
        if name in self.mod_masks and not repeat:
            self.held_mods[name] = self.held_mods.get(name, 0) + 1
        self._post(name, True, repeat)

    def release(self, name):
        if name in self.mod_masks:
            self.held_mods[name] = max(0, self.held_mods.get(name, 0) - 1)
        self._post(name, False)
