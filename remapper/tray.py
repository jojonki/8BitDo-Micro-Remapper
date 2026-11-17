"""Menu-bar (macOS) / notification-area (Windows) icon.

Lets the app keep running after its window is closed: the icon's menu shows
the window again or quits. Callbacks may arrive on another thread (Windows),
so the app passes `post`, which runs a function on the Tk thread.

macOS uses an NSStatusItem through PyObjC (Tk already runs the Cocoa event
loop, so the item works from the main thread). Windows uses pystray.
"""

import sys

_mac_target_cls = None


def _mac_target_class():
    global _mac_target_cls
    if _mac_target_cls is None:
        from Foundation import NSObject

        class MicroRemapperTrayTarget(NSObject):
            def show_(self, _sender):
                self.handlers["show"]()

            def quit_(self, _sender):
                self.handlers["quit"]()

        _mac_target_cls = MicroRemapperTrayTarget
    return _mac_target_cls


class Tray:
    def __init__(self, title, on_show, on_quit, post):
        self.title = title
        self._show = lambda: post(on_show)
        self._quit = lambda: post(on_quit)
        self._item = None        # macOS NSStatusItem
        self._icon = None        # pystray icon
        self._target = None

    # ---------------------------------------------------------------- api
    def start(self):
        """Create the icon. Returns False if this platform/setup can't."""
        try:
            if sys.platform == "darwin":
                return self._start_mac()
            if sys.platform == "win32":
                return self._start_win()
        except Exception:
            return False
        return False

    def stop(self):
        try:
            if self._item is not None:
                from AppKit import NSStatusBar
                NSStatusBar.systemStatusBar().removeStatusItem_(self._item)
                self._item = None
            if self._icon is not None:
                self._icon.stop()
                self._icon = None
        except Exception:
            pass

    @staticmethod
    def set_dock_icon(visible):
        """macOS: show/hide the Dock icon (hidden while only the menu-bar icon is left)."""
        if sys.platform != "darwin":
            return
        try:
            from AppKit import (NSApplication, NSApplicationActivationPolicyAccessory,
                                NSApplicationActivationPolicyRegular)
            app = NSApplication.sharedApplication()
            app.setActivationPolicy_(NSApplicationActivationPolicyRegular if visible
                                     else NSApplicationActivationPolicyAccessory)
            if visible:
                app.activateIgnoringOtherApps_(True)
        except Exception:
            pass

    # ---------------------------------------------------------------- macOS
    def _start_mac(self):
        from AppKit import NSImage, NSMenu, NSMenuItem, NSStatusBar, NSVariableStatusItemLength

        self._target = _mac_target_class().alloc().init()
        self._target.handlers = {"show": self._show, "quit": self._quit}
        item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        button = item.button()
        img = None
        if hasattr(NSImage, "imageWithSystemSymbolName_accessibilityDescription_"):
            img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "gamecontroller", self.title)
        if img is not None:
            img.setTemplate_(True)
            button.setImage_(img)
        else:
            button.setTitle_("8BD")
        button.setToolTip_(self.title)

        menu = NSMenu.alloc().init()
        for label, action in ((f"Show {self.title}", "show:"), (None, None),
                              (f"Quit {self.title}", "quit:")):
            if label is None:
                menu.addItem_(NSMenuItem.separatorItem())
                continue
            mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(label, action, "")
            mi.setTarget_(self._target)
            menu.addItem_(mi)
        item.setMenu_(menu)
        self._item = item
        return True

    # ---------------------------------------------------------------- Windows
    def _start_win(self):
        import pystray
        from PIL import Image, ImageDraw

        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((4, 16, 60, 48), radius=14, fill=(79, 140, 255, 255))
        d.rectangle((14, 29, 26, 35), fill="white")          # d-pad
        d.rectangle((17, 26, 23, 38), fill="white")
        d.ellipse((38, 24, 46, 32), fill="white")             # buttons
        d.ellipse((46, 32, 54, 40), fill="white")

        menu = pystray.Menu(
            pystray.MenuItem(f"Show {self.title}", lambda *_: self._show(), default=True),
            pystray.MenuItem(f"Quit {self.title}", lambda *_: self._quit()),
        )
        self._icon = pystray.Icon("micro-remapper", img, self.title, menu)
        self._icon.run_detached()
        return True
