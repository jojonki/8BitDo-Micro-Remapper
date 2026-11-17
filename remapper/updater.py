"""Check GitHub Releases for a newer version and install it.

Installing works for the packaged app only (PyInstaller):
  * macOS  - the .app bundle is swapped for the new one and relaunched.
  * Windows - the new files are copied over the app folder and the exe relaunched.
The swap is done by a small helper script that waits for this process to exit,
because a running app cannot replace its own files. When running from source
the caller should just open the release page instead.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

from . import __version__

REPO = "jojonki/8BitDo-Micro-Remapper"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
ASSETS = {
    "darwin": "8BitDo-Micro-Remapper-macOS-arm64.zip",
    "win32": "8BitDo-Micro-Remapper-Windows-x64.zip",
}
APP_DIR_NAME = "8BitDo Micro Remapper"           # .app name / Windows folder name
EXE_NAME = APP_DIR_NAME + ".exe"
USER_AGENT = f"8BitDo-Micro-Remapper/{__version__}"


# ------------------------------------------------------------------ versions
def parse_version(text):
    """'v1.2.3' -> (1, 2, 3); anything unparsable -> (0,)."""
    m = re.match(r"\s*v?(\d+(?:\.\d+)*)", str(text or ""))
    if not m:
        return (0,)
    parts = [int(p) for p in m.group(1).split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def is_newer(latest, current=__version__):
    return parse_version(latest) > parse_version(current)


# ------------------------------------------------------------------ lookup
def _get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


def release_info(data, platform=sys.platform):
    """Pick what we need from a GitHub release JSON object."""
    asset_name = ASSETS.get(platform)
    asset = next((a for a in data.get("assets", []) if a.get("name") == asset_name), None)
    return {
        "version": str(data.get("tag_name", "")).lstrip("v"),
        "page": data.get("html_url") or RELEASES_PAGE,
        "notes": data.get("body") or "",
        "asset_url": asset.get("browser_download_url") if asset else None,
        "asset_size": asset.get("size") if asset else None,
    }


def fetch_latest(timeout=10):
    with _get(LATEST_API, timeout) as r:
        return release_info(json.load(r))


# ------------------------------------------------------------------ install
def install_target():
    """Path that an update replaces, or None when running from source."""
    if not getattr(sys, "frozen", False):
        return None
    exe = os.path.realpath(sys.executable)
    if sys.platform == "darwin":
        app = os.path.dirname(os.path.dirname(os.path.dirname(exe)))   # X.app/Contents/MacOS/X
        return app if app.endswith(".app") else None
    if sys.platform == "win32":
        folder = os.path.dirname(exe)
        return folder if os.path.isfile(os.path.join(folder, EXE_NAME)) else None
    return None


def can_self_update(info=None):
    target = install_target()
    if not target or sys.platform not in ASSETS:
        return False
    if info is not None and not info.get("asset_url"):
        return False
    return os.access(os.path.dirname(target), os.W_OK)


def download(url, dest, progress=None, timeout=30):
    with _get(url, timeout) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)


def _find(root, name, want_dir=True):
    for dirpath, dirnames, filenames in os.walk(root):
        if want_dir and name in dirnames:
            return os.path.join(dirpath, name)
        if not want_dir and name in filenames:
            return os.path.join(dirpath, name)
    return None


def prepare(info, progress=None):
    """Download and unpack the update. Returns the path of the new app/folder."""
    work = tempfile.mkdtemp(prefix="micro-remapper-update-")
    zpath = os.path.join(work, "update.zip")
    download(info["asset_url"], zpath, progress)
    if info.get("asset_size") and os.path.getsize(zpath) != int(info["asset_size"]):
        raise RuntimeError("Download incomplete")
    out = os.path.join(work, "new")
    os.makedirs(out)
    if sys.platform == "darwin":
        # ditto keeps the bundle's symlinks, permissions and signature intact
        subprocess.run(["ditto", "-x", "-k", zpath, out], check=True)
        new = _find(out, APP_DIR_NAME + ".app")
    else:
        with zipfile.ZipFile(zpath) as z:
            z.extractall(out)
        exe = _find(out, EXE_NAME, want_dir=False)
        new = os.path.dirname(exe) if exe else None
    if not new:
        raise RuntimeError("The download does not contain the app")
    return new


_MAC_SCRIPT = r'''#!/bin/sh
PID="$1"; NEW="$2"; TARGET="$3"
while kill -0 "$PID" 2>/dev/null; do sleep 0.3; done
rm -rf "$TARGET.old"
if mv "$TARGET" "$TARGET.old"; then
  if mv "$NEW" "$TARGET"; then rm -rf "$TARGET.old"; else mv "$TARGET.old" "$TARGET"; fi
fi
xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null
open "$TARGET"
'''

_WIN_SCRIPT = r'''@echo off
:wait
tasklist /FI "PID eq %~1" 2>nul | find "%~1" >nul && (timeout /t 1 /nobreak >nul & goto wait)
timeout /t 1 /nobreak >nul
robocopy "%~2" "%~3" /E /R:10 /W:1 /NFL /NDL /NJH /NJS >nul
start "" "%~3\%~4"
'''


def launch_installer(new_path):
    """Start the helper that swaps in new_path once this process exits.

    The caller must quit the app right after this returns."""
    target = install_target()
    if not target:
        raise RuntimeError("Not running as an installed app")
    work = os.path.dirname(os.path.dirname(new_path))   # the temp dir made by prepare()
    pid = str(os.getpid())
    if sys.platform == "darwin":
        script = os.path.join(work, "install.sh")
        with open(script, "w") as f:
            f.write(_MAC_SCRIPT)
        os.chmod(script, 0o755)
        subprocess.Popen(["/bin/sh", script, pid, new_path, target],
                         start_new_session=True, close_fds=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif sys.platform == "win32":
        script = os.path.join(work, "install.bat")
        with open(script, "w") as f:
            f.write(_WIN_SCRIPT)
        flags = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED | NEW_GROUP | NO_WINDOW
        subprocess.Popen(["cmd", "/c", script, pid, new_path, target, EXE_NAME],
                         creationflags=flags, close_fds=True)
    else:
        raise RuntimeError("Unsupported platform")


def cleanup_old():
    """Remove leftovers of a previous update (best effort)."""
    target = install_target()
    if target and os.path.isdir(target + ".old"):
        shutil.rmtree(target + ".old", ignore_errors=True)
