# PyInstaller spec — builds a windowed app on macOS (.app) and Windows (.exe).
#   pyinstaller --noconfirm packaging/remapper.spec
import sys

from PyInstaller.utils.hooks import collect_submodules

APP = "8BitDo Micro Remapper"
ROOT = SPECPATH + "/.."

# pynput picks its backend at runtime, so list it explicitly
hidden = ["remapper.input_worker", "remapper.hid_exclusive", "remapper.mac_keys",
          "remapper.keepalive", "remapper.updater",
          "remapper.tray"]
if sys.platform == "darwin":
    hidden += ["pynput.keyboard._darwin", "pynput.mouse._darwin", "pynput._util.darwin",
               "Quartz", "AppKit", "hid"]
elif sys.platform == "win32":
    hidden += ["pynput.keyboard._win32", "pynput.mouse._win32", "pynput._util.win32", "hid",
               "pystray._win32", "PIL.ImageDraw"]
hidden += collect_submodules("pygame._sdl2")

a = Analysis(
    [ROOT + "/run.py"],
    pathex=[ROOT],
    hiddenimports=hidden,
    excludes=["GameController", "numpy", "matplotlib"] + ([] if sys.platform == "win32" else ["PIL"]),
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name=APP,
    console=False,            # windowed app
    disable_windowed_traceback=False,
    argv_emulation=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name=APP)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=APP + ".app",
        bundle_identifier="io.github.micro-remapper",
        info_plist={
            "CFBundleShortVersionString": __import__("remapper").__version__,
            "CFBundleVersion": __import__("remapper").__version__,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
