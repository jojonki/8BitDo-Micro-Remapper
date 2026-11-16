import os
import sys
import tempfile
import unittest

os.environ["MICRO_REMAPPER_HOME"] = tempfile.mkdtemp(prefix="micro-remap-test-")

from remapper import keys, layout, storage  # noqa: E402


class KeysTest(unittest.TestCase):
    def test_tk_translation(self):
        self.assertEqual(keys.tk_event_to_key("a"), "a")
        self.assertEqual(keys.tk_event_to_key("A"), "a")
        self.assertEqual(keys.tk_event_to_key("Return"), "enter")
        self.assertEqual(keys.tk_event_to_key("Prior"), "page_up")
        self.assertEqual(keys.tk_event_to_key("F12"), "f12")
        self.assertEqual(keys.tk_event_to_key("exclam"), "1")
        self.assertEqual(keys.tk_event_to_key("minus"), "-")
        self.assertEqual(keys.tk_event_to_key("KP_5"), "5")
        self.assertEqual(keys.tk_event_to_key("Meta_L"), "cmd")
        self.assertEqual(keys.tk_event_to_key("Win_L"), "cmd")
        self.assertIsNone(keys.tk_event_to_key("XF86Unknown"))

    def test_normalize_combo(self):
        self.assertEqual(keys.normalize_combo(["c", "shift", "ctrl"]), ["ctrl", "shift", "c"])
        self.assertEqual(keys.normalize_combo(["a", "a"]), ["a"])

    def test_catalog_roundtrip(self):
        for _, k, _ in keys.KEY_CATALOG:
            self.assertEqual(keys.catalog_value_to_key(keys.key_to_catalog_value(k)), k)

    def test_describe(self):
        self.assertEqual(keys.describe_action({"type": "key", "keys": ["ctrl", "c"]}), "Ctrl + C")
        self.assertEqual(keys.describe_action({"type": "mouse", "button": "left"}), "Left Click")
        self.assertEqual(keys.describe_action(None), "—")

    def test_validate(self):
        self.assertIsNone(keys.validate_action({"type": "key", "keys": []}))
        self.assertIsNone(keys.validate_action({"type": "mouse", "button": "bogus"}))
        self.assertEqual(keys.validate_action({"type": "none"}), {"type": "none"})


class LayoutTest(unittest.TestCase):
    def test_all_buttons_present(self):
        self.assertEqual(set(layout.WIZARD_ORDER), set(layout.ASSIGNABLE_IDS))
        self.assertEqual(layout.DISABLED_IDS, {"star", "home"})
        self.assertEqual(len(layout.BUTTON_IDS), 16)
        for target in layout.DEFAULT_SOURCE_MAP.values():
            self.assertIn(target, layout.BUTTON_IDS)

    def test_chips_do_not_overlap(self):
        boxes = [layout.chip_box(b) for b in layout.BUTTONS]
        for i, a in enumerate(boxes):
            self.assertTrue(0 <= a[0] and a[2] <= layout.CANVAS_W and 0 <= a[1] and a[3] <= layout.CANVAS_H)
            for b in boxes[i + 1:]:
                overlap = a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
                self.assertFalse(overlap, (a, b))
            # chips stay clear of the controller body
            bx1, by1, bx2, by2 = layout.BODY
            self.assertTrue(a[2] < bx1 or a[0] > bx2)

    def test_leader_lines_avoid_other_buttons(self):
        def hits(box, p, q, shape):
            # sample the segment; circles use radius test, others the box
            x1, y1, x2, y2 = box
            cx, cy, r = (x1 + x2) / 2, (y1 + y2) / 2, (x2 - x1) / 2
            for i in range(101):
                t = i / 100
                x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
                if shape == "circle":
                    if (x - cx) ** 2 + (y - cy) ** 2 < (r - 1) ** 2:
                        return True
                elif x1 + 1 < x < x2 - 1 and y1 + 1 < y < y2 - 1:
                    return True
            return False
        for b in layout.BUTTONS:
            pts = layout.leader_points(b)
            for other in layout.BUTTONS:
                if other is b:
                    continue
                for p, q in zip(pts, pts[1:]):
                    self.assertFalse(hits(other["box"], p, q, other["shape"]),
                                     f"line of {b['id']} crosses {other['id']}")

    def test_inside_canvas(self):
        for b in layout.BUTTONS:
            x1, y1, x2, y2 = b["box"]
            self.assertTrue(0 <= x1 < x2 <= layout.CANVAS_W, b["id"])
            self.assertTrue(0 <= y1 < y2 <= layout.CANVAS_H, b["id"])


class HidReportTest(unittest.TestCase):
    def test_parse(self):
        from remapper.hid_exclusive import parse_report
        idle = [3, 0x0F, 0x80, 0x80, 0x80, 0x80, 0, 0, 0, 0, 100]
        self.assertEqual(parse_report(idle), set())
        r = list(idle); r[1] = 0x01; r[8] = 0b1; r[9] = 0b10000  # NE + b0 + b12
        self.assertEqual(parse_report(r), {"x:hat:up", "x:hat:right", "x:b0", "x:b12"})
        r = list(idle); r[6] = 255
        self.assertEqual(parse_report(r), {"x:brake"})
        self.assertEqual(parse_report(idle[1:]), set())   # report id stripped
        self.assertIsNone(parse_report([]))


class MacKeysTest(unittest.TestCase):
    def test_keycodes_cover_catalog(self):
        from remapper.mac_keys import KEYCODES
        missing = {k for _, k, _ in keys.KEY_CATALOG} - set(KEYCODES)
        # keys macOS keyboards don't have, or media keys (sent via pynput)
        allowed = {"menu", "print_screen", "pause", "num_lock", "scroll_lock"} | {
            k for _, k, _ in keys.KEY_CATALOG if k.startswith("media_")}
        self.assertEqual(missing - allowed, set())
        for m in keys.MODIFIERS:
            self.assertIn(m, KEYCODES)
        self.assertEqual(KEYCODES["f3"], 0x63)

    @unittest.skipUnless(sys.platform == "darwin", "macOS only")
    def test_flags(self):
        import Quartz as Q
        from remapper.mac_keys import MacKeys
        mk = MacKeys()
        self.assertTrue(mk.flags_for("f3") & Q.kCGEventFlagMaskSecondaryFn)
        self.assertFalse(mk.flags_for("a") & Q.kCGEventFlagMaskSecondaryFn)
        mk.held_mods["ctrl"] = 1
        self.assertTrue(mk.flags_for("c") & Q.kCGEventFlagMaskControl)


class StorageTest(unittest.TestCase):
    def test_profile_roundtrip(self):
        m = {"a": {"type": "key", "keys": ["shift", "x"]}, "minus": {"type": "text", "text": "hi"}, "home": {"type": "key", "keys": ["a"]},
             "bogus": {"type": "key", "keys": ["a"]}}
        storage.save_profile("t1", m)
        self.assertIn("t1", storage.list_profiles())
        self.assertIn("default", storage.list_profiles())
        loaded = storage.load_profile("t1")
        self.assertEqual(loaded, {"a": {"type": "key", "keys": ["shift", "x"]},
                                  "minus": {"type": "text", "text": "hi"}})
        storage.delete_profile("t1")
        self.assertNotIn("t1", storage.list_profiles())

    def test_export_import(self):
        path = os.path.join(os.environ["MICRO_REMAPPER_HOME"], "exp.json")
        storage.export_profile(path, "game", storage.DEFAULT_MAPPINGS)
        name, m = storage.import_profile(path)
        self.assertEqual(name, "game")
        self.assertEqual(m, storage.clean_mappings(storage.DEFAULT_MAPPINGS))

    def test_settings(self):
        s = storage.load_settings()
        s["source_map"]["b:3"] = "a"
        storage.save_settings(s)
        self.assertEqual(storage.load_settings()["source_map"]["b:3"], "a")


if __name__ == "__main__":
    unittest.main()
