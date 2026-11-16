"""Visual layout of the 8BitDo Micro (top view) and logical button definitions.

The controller is drawn in the middle of the canvas; every button has a
"chip" (its mapping label) in the left or right column, joined by a leader
line, so labels never overlap the controller or each other.
"""

CANVAS_W = 920
CANVAS_H = 470

# Controller body (rounded rectangle)
BODY = (280, 132, 640, 352)
BODY_RADIUS = 70

DPAD_C = (370, 247)
DPAD_HALF = 17
DPAD_ARM = 52

FACE_C = (550, 247)
FACE_OFF = 44
FACE_R = 20

# chip columns
CHIP_W = 196
CHIP_H = 34
CHIP_LEFT_X = 20                      # left column x1
CHIP_RIGHT_X = CANVAS_W - 20 - CHIP_W  # right column x1
CHIP_SLOTS = [62, 112, 172, 222, 272, 322, 372, 422]  # chip centre y


def _dpad(direction):
    cx, cy = DPAD_C
    h, a = DPAD_HALF, DPAD_ARM
    return {
        "up": (cx - h, cy - a, cx + h, cy - h),
        "down": (cx - h, cy + h, cx + h, cy + a),
        "left": (cx - a, cy - h, cx - h, cy + h),
        "right": (cx + h, cy - h, cx + a, cy + h),
    }[direction]


def _circle(cx, cy, r):
    return (cx - r, cy - r, cx + r, cy + r)


# Each button:
#   id    : logical id used in profiles
#   label : text printed on the button (and on its chip badge)
#   name  : human readable (Japanese) name
#   shape : rect | circle | pill | tab
#   box   : bounding box on the canvas
#   chip  : (side, slot index) of its mapping chip
BUTTONS = [
    {"id": "l2", "label": "L2", "name": "L2", "shape": "tab",
     "box": (305, 84, 425, 106), "chip": ("left", 0)},
    {"id": "l", "label": "L", "name": "L", "shape": "tab",
     "box": (305, 109, 425, 131), "chip": ("left", 1)},
    {"id": "minus", "label": "−", "name": "Select (−)", "shape": "pill",
     "box": (415, 175, 455, 197), "chip": ("left", 2)},
    {"id": "up", "label": "▲", "name": "D-pad Up", "shape": "rect",
     "box": _dpad("up"), "chip": ("left", 3)},
    {"id": "left", "label": "◀", "name": "D-pad Left", "shape": "rect",
     "box": _dpad("left"), "chip": ("left", 4)},
    {"id": "right", "label": "▶", "name": "D-pad Right", "shape": "rect",
     "box": _dpad("right"), "chip": ("left", 5),
     "via": [(410, 322)]},          # route below/right of the down arm
    {"id": "down", "label": "▼", "name": "D-pad Down", "shape": "rect",
     "box": _dpad("down"), "chip": ("left", 6)},

    {"id": "r2", "label": "R2", "name": "R2", "shape": "tab",
     "box": (495, 84, 615, 106), "chip": ("right", 0)},
    {"id": "r", "label": "R", "name": "R", "shape": "tab",
     "box": (495, 109, 615, 131), "chip": ("right", 1)},
    {"id": "plus", "label": "+", "name": "Start (+)", "shape": "pill",
     "box": (465, 175, 505, 197), "chip": ("right", 2)},
    {"id": "x", "label": "X", "name": "X", "shape": "circle",
     "box": _circle(FACE_C[0], FACE_C[1] - FACE_OFF, FACE_R), "chip": ("right", 3)},
    {"id": "y", "label": "Y", "name": "Y", "shape": "circle",
     "box": _circle(FACE_C[0] - FACE_OFF, FACE_C[1], FACE_R), "chip": ("right", 4),
     "via": [(572, 272)]},          # pass between A and B
    {"id": "a", "label": "A", "name": "A", "shape": "circle",
     "box": _circle(FACE_C[0] + FACE_OFF, FACE_C[1], FACE_R), "chip": ("right", 5)},
    {"id": "b", "label": "B", "name": "B", "shape": "circle",
     "box": _circle(FACE_C[0], FACE_C[1] + FACE_OFF, FACE_R), "chip": ("right", 6)},
    # The two small centre buttons are handled by the controller / OS
    # (star: never reported over USB, home: power + OS shortcut), so they are
    # shown but cannot be assigned.
    {"id": "star", "label": "", "name": "Centre left (disabled)", "shape": "circle",
     "box": _circle(440, 300, 12), "chip": ("left", 7), "disabled": True},
    {"id": "home", "label": "", "name": "Centre right / Home (disabled)", "shape": "circle",
     "box": _circle(480, 300, 12), "chip": ("right", 7), "disabled": True},
]

BUTTON_IDS = [b["id"] for b in BUTTONS]
ASSIGNABLE_IDS = [b["id"] for b in BUTTONS if not b.get("disabled")]
DISABLED_IDS = {b["id"] for b in BUTTONS if b.get("disabled")}
BUTTON_BY_ID = {b["id"]: b for b in BUTTONS}


def leader_points(button):
    """Polyline from the chip to the button centre (chip edge → elbow → via → centre)."""
    bx1, by1, bx2, by2 = button["box"]
    x1, y1, x2, y2 = chip_box(button)
    cy = (y1 + y2) / 2
    if button["chip"][0] == "left":
        pts = [(x2, cy), (250, cy)]
    else:
        pts = [(x1, cy), (670, cy)]
    pts += list(button.get("via", []))
    pts.append(((bx1 + bx2) / 2, (by1 + by2) / 2))
    return pts


def chip_box(button):
    side, slot = button["chip"]
    x1 = CHIP_LEFT_X if side == "left" else CHIP_RIGHT_X
    cy = CHIP_SLOTS[slot]
    return (x1, cy - CHIP_H // 2, x1 + CHIP_W, cy + CHIP_H // 2)


# Order used by the "learn all buttons" wizard.
WIZARD_ORDER = ["up", "down", "left", "right", "a", "b", "x", "y",
                "l", "r", "l2", "r2", "minus", "plus"]

# Default translation of normalized SDL GameController inputs -> Micro buttons.
# For the 8BitDo Micro, SDL reports face buttons by their printed label
# (verified on hardware: physical A -> "a"), so they map 1:1.
DEFAULT_SOURCE_MAP = {
    "c:a": "a", "c:b": "b", "c:x": "x", "c:y": "y",
    "c:back": "minus", "c:start": "plus", "c:guide": "home", "c:misc1": "star",
    "c:leftshoulder": "l", "c:rightshoulder": "r",
    "c:lefttrigger": "l2", "c:righttrigger": "r2",
    "c:dpup": "up", "c:dpdown": "down", "c:dpleft": "left", "c:dpright": "right",
    # Raw joystick fall-backs (hat / axis based D-pad)
    "h0:up": "up", "h0:down": "down", "h0:left": "left", "h0:right": "right",
    "a0:-": "left", "a0:+": "right", "a1:-": "up", "a1:+": "down",
    # Exclusive HID mode (macOS, see hid_exclusive.py): standard 8BitDo
    # D-input bit order. Use "Learn all" if a button lights up wrong.
    "x:hat:up": "up", "x:hat:down": "down", "x:hat:left": "left", "x:hat:right": "right",
    "x:b0": "a", "x:b1": "b", "x:b3": "x", "x:b4": "y",
    "x:b6": "l", "x:b7": "r", "x:b8": "l2", "x:b9": "r2",
    "x:b10": "minus", "x:b11": "plus", "x:b12": "home",
    "x:brake": "l2", "x:accel": "r2",
    # Left stick of the controller API (some modes report the D-pad as a stick)
    "c:leftx:-": "left", "c:leftx:+": "right", "c:lefty:-": "up", "c:lefty:+": "down",
}
