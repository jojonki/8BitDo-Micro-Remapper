"""Drives the real Tk GUI (window is created then destroyed)."""
import os
import tempfile
import unittest

os.environ["MICRO_REMAPPER_HOME"] = tempfile.mkdtemp(prefix="micro-remap-gui-")

try:
    import tkinter as tk
    _ROOT = tk.Tk()          # one root per process (a 2nd Tk() crashes Tk 9 on macOS)
    _ROOT.withdraw()
    HAVE_TK = True
except Exception:
    HAVE_TK = False


class FakeExecutor:
    available = True
    error = None
    repeat_enabled = True

    def __init__(self):
        self.calls = []

    def press(self, bid, action):
        self.calls.append(("press", bid, action))

    def release(self, bid):
        self.calls.append(("release", bid))

    def release_all(self):
        pass

    def tick(self):
        pass


class E:
    def __init__(self, keysym, char=""):
        self.keysym, self.char = keysym, char


@unittest.skipUnless(HAVE_TK, "no display")
class GuiTest(unittest.TestCase):
    def setUp(self):
        from remapper import gui, storage
        storage.save_profile("default", storage.DEFAULT_MAPPINGS)
        self.gui = gui
        self.root = tk.Toplevel(_ROOT)
        self.app = gui.RemapperApp(self.root)
        self.app.executor = FakeExecutor()
        self.root.update()

    def tearDown(self):
        self.app.on_close()

    def test_canvas_has_all_buttons(self):
        from remapper.layout import BUTTON_IDS
        self.assertEqual(set(self.app.items), set(BUTTON_IDS))
        txt = self.app.canvas.itemcget(self.app.items["up"]["map"], "text")
        self.assertEqual(txt, "↑")

    def test_click_selects(self):
        self.app.select_button("x")
        self.assertEqual(self.app.selected, "x")
        self.assertEqual(self.app.sel_title.get(), "X")
        self.assertEqual(self.app.canvas.itemcget(self.app.items["x"]["chip"], "outline"),
                         self.gui.C_ACCENT)

    def test_capture_combo(self):
        self.app.select_button("a")
        self.app.start_capture()
        self.app._on_key_press(E("Control_L"))
        self.app._on_key_press(E("c", "c"))
        self.assertFalse(self.app.capturing)
        self.assertEqual(self.app.mappings["a"], {"type": "key", "keys": ["ctrl", "c"]})
        self.assertIn("Ctrl", self.app.canvas.itemcget(self.app.items["a"]["map"], "text"))

    def test_capture_modifier_only(self):
        self.app.select_button("l2")
        self.app.start_capture()
        self.app._on_key_press(E("Shift_L"))
        self.app._on_key_release(E("Shift_L"))
        self.assertEqual(self.app.mappings["l2"], {"type": "key", "keys": ["shift"]})

    def test_select_from_list(self):
        from remapper.keys import key_to_catalog_value
        self.app.select_button("b")
        self.app.mod_vars["shift"].set(True)
        self.app.key_var.set(key_to_catalog_value("f5"))
        self.app._apply_key_form()
        self.assertEqual(self.app.mappings["b"], {"type": "key", "keys": ["shift", "f5"]})

    def test_mouse_and_text(self):
        self.app.select_button("y")
        self.app.type_var.set("mouse")
        self.app.mouse_var.set("Right Click")
        self.app._on_type_change()
        self.assertEqual(self.app.mappings["y"], {"type": "mouse", "button": "right"})
        self.app.type_var.set("text")
        self.app.text_var.set("hello")
        self.app._on_type_change()
        self.assertEqual(self.app.mappings["y"], {"type": "text", "text": "hello"})

    def test_input_triggers_output_and_highlight(self):
        # verified on hardware: physical A -> SDL "a", X -> "x"
        self.app.on_source_down("c:a")
        self.assertTrue(self.app.pressed["a"])
        fill = self.app.canvas.itemcget(self.app.items["a"]["shape"], "fill")
        self.assertEqual(fill, self.gui.C_PRESSED)
        self.assertEqual(self.app.executor.calls[-1][0:2], ("press", "a"))
        self.app.on_source_up("c:a")
        self.assertEqual(self.app.executor.calls[-1], ("release", "a"))
        self.assertEqual(self.app.resolve("c:x"), "x")
        self.assertEqual(self.app.resolve("c:b"), "b")

    def test_disabled_does_not_output(self):
        self.app.enabled_var.set(False)
        self.app.on_source_down("h0:up")
        self.assertEqual(self.app.executor.calls, [])
        self.assertTrue(self.app.pressed["up"])
        self.app.enabled_var.set(True)

    def test_learning_wizard(self):
        self.app.start_wizard()
        self.assertEqual(self.app.learn_target, "up")
        self.app.on_source_down("b:7")
        self.assertEqual(self.app.settings["source_map"]["b:7"], "up")
        self.assertEqual(self.app.learn_target, "down")
        self.app.stop_learning()
        self.app.on_source_down("b:7")
        self.assertTrue(self.app.pressed["up"])
        self.app.settings["source_map"] = {}

    def test_disabled_buttons(self):
        self.app.select_button("home")
        self.assertNotEqual(self.app.selected, "home")
        self.app.on_source_down("c:guide")
        self.app.on_source_down("x:b12")
        self.assertFalse(self.app.pressed.get("home"))
        self.assertEqual(self.app.executor.calls, [])
        self.assertEqual(self.app.canvas.itemcget(self.app.items["star"]["map"], "text"), "Disabled")

    def test_home_menu_setting(self):
        import sys
        if sys.platform != "darwin":
            self.skipTest("macOS only")
        txt = lambda: self.app.canvas.itemcget(self.app.items["home"]["map"], "text")
        self.app.exclusive_var.set(True)
        self.app.settings["exclusive"] = True
        self.app._update_home_chip()
        self.assertEqual(txt(), "Games app blocked")
        self.app.exclusive_var.set(False)
        self.app.on_toggle_exclusive()
        self.assertFalse(self.app.settings["exclusive"])
        self.assertEqual(txt(), "Opens Games app")
        self.app.exclusive_var.set(True)
        self.app.on_toggle_exclusive()
        self.assertTrue(self.app.settings["exclusive"])

    def test_profile_persistence(self):
        from remapper import storage
        self.app.select_button("minus")
        self.app.type_var.set("none")
        self.app._on_type_change()
        self.assertEqual(storage.load_profile("default")["minus"], {"type": "none"})


if __name__ == "__main__":
    unittest.main()
