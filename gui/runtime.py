"""Where the app finds its files, running from source or from a packaged .exe.

Inside a PyInstaller bundle the code lives in a temporary folder that is wiped
on exit, and the working directory is wherever the user happened to double-click
from. So on a frozen build we:

* copy the editable assets (email templates, the pitch script) into a per-user
  folder the first time they are needed, and
* make that folder the working directory, so every relative path the existing
  code uses — ``data/``, ``pricing.json``, ``.env`` — lands somewhere writable.

Run from source, nothing moves: the repo is already the right place.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
import io
import json
import stat
import zipfile
from typing import Iterable, Optional

APP_NAME = "LocalLeadScraperPro"

#: Files and folders the user is meant to be able to edit.
SEEDED_ASSETS = ("email_templates", "email_template.html", "pitch_script.md")


def frozen() -> bool:
    """True when running from a packaged executable."""
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    """Read-only resources: the PyInstaller payload, or the repo root."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


def app_data_dir() -> Path:
    """Writable per-user folder for exports, settings and edited assets."""
    override = os.environ.get("LLSP_DATA_DIR")
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA")
    if local:  # Windows
        return Path(local) / APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / APP_NAME


_RESOLVED_DIR: Optional[Path] = None


def working_dir() -> Path:
    """The directory relative paths resolve against."""
    if frozen():
        return _RESOLVED_DIR or app_data_dir()
    return Path.cwd()


def user_asset(name: str) -> Path:
    """Return the editable copy of ``name``, seeding it from the bundle once.

    Running from source this is just the file in the repo, so editing a
    template edits the one the app uses.
    """
    source = bundle_dir() / name
    if not frozen():
        return source
    target = app_data_dir() / name
    if not target.exists() and source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    return target


def seed_assets(names: Iterable[str] = SEEDED_ASSETS) -> None:
    for name in names:
        try:
            user_asset(name)
        except OSError:  # pragma: no cover - a read-only profile is survivable
            pass


def prepare() -> Path:
    """Get the process ready to run; returns the working directory."""
    if frozen():
        target = _writable_dir(app_data_dir())
        os.chdir(target)
        # data_store anchors data/ to its own module directory, which inside a
        # one-file bundle is the temp folder PyInstaller deletes on exit. Point
        # it at the user's folder before anything writes a CSV.
        os.environ.setdefault("GOOGLE_SCRAPER_DATA_DIR", str(target / "data"))
        globals()["_RESOLVED_DIR"] = target
        use_bundled_driver()
        seed_assets()
    else:
        use_bundled_driver()
        # The pitch script is looked up relative to the tui package, which the
        # bundle flattens; point it at the editable copy instead.
        try:
            from tui import pitch_script

            script = app_data_dir() / "pitch_script.md"
            if script.exists():
                pitch_script.DEFAULT_SCRIPT_PATH = script
        except Exception:  # pragma: no cover - the fallback script still works
            pass
    return working_dir()


def bundled_driver_dir() -> Optional[Path]:
    """The folder holding the chromedriver shipped with the app, if any."""
    for base in (bundle_dir(), Path(__file__).resolve().parent.parent / "packaging"):
        drivers = base / "drivers"
        if drivers.is_dir() and any(drivers.glob("chromedriver*")):
            return drivers
    return None


def _major(version: str) -> str:
    """"141.0.7390.37" -> "141"."""
    return (version or "").strip().split(".")[0]


def bundled_driver_version() -> str:
    """The version of the chromedriver shipped with the app, if known."""
    drivers = bundled_driver_dir()
    if drivers is None:
        return ""
    stamp = drivers / "VERSION"
    try:
        return stamp.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def installed_chrome_version() -> str:
    """The version of Chrome on this machine, or "" if it cannot be told."""
    if os.name == "nt":  # pragma: no cover - Windows only
        try:
            import winreg

            for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(root, r"Software\Google\Chrome\BLBeacon") as key:
                        value, _type = winreg.QueryValueEx(key, "version")
                        if value:
                            return str(value)
                except OSError:
                    continue
        except Exception:  # noqa: BLE001 - detection is best-effort
            pass
        return ""

    import shutil
    import subprocess

    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        binary = shutil.which(name)
        if not binary:
            continue
        try:
            # binary is whatever shutil.which resolved one of the fixed names
            # above to — no part of this comes from a page, a CSV or a
            # setting, and it is a list, so there is no shell to inject into.
            # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
            out = subprocess.run([binary, "--version"], capture_output=True,  # noqa: S603
                                 text=True, timeout=15).stdout
        except Exception:  # noqa: BLE001 - a browser that will not answer
            continue
        for word in out.split():
            if word[:1].isdigit():
                return word
    return ""


def use_bundled_driver() -> Optional[Path]:
    """Put the bundled chromedriver first on PATH, when it fits this Chrome.

    Selenium looks on PATH before it downloads anything, so this is what keeps
    a first run from reaching out to the internet — the app is meant to work
    from the .exe alone.

    The catch is that a driver only drives its own major version of Chrome,
    and Chrome updates itself. If the two do not match, standing aside is
    better than failing: Selenium fetches a matching driver, which needs the
    network but does work. So the bundle covers the normal case offline, and
    the exception still gets someone running.
    """
    drivers = bundled_driver_dir()
    if drivers is None:
        return None

    bundled, chrome = bundled_driver_version(), installed_chrome_version()
    # An unknown version on either side is not evidence of a mismatch; prefer
    # the bundled driver, since working offline is the point.
    if bundled and chrome and _major(bundled) != _major(chrome):
        return None

    entries = os.environ.get("PATH", "").split(os.pathsep)
    if str(drivers) not in entries:
        os.environ["PATH"] = os.pathsep.join([str(drivers)] + entries)
    return drivers


#: Where the scrapers look for the browser to drive. Set once the embedded
#: Chromium is unpacked; empty means "use whatever Chrome is installed".
CHROME_BINARY_ENV = "LLSP_CHROME_BINARY"


def embedded_payload():
    """The browser archive appended to this executable, if there is one.

    The build appends it after PyInstaller's own archive: zip finds its
    central directory from the end of the file, so the executable can read
    its own payload, and the bootloader is unaffected by data sitting after
    what it cares about.
    """
    if not frozen():
        return None
    try:
        archive = zipfile.ZipFile(Path(sys.executable))
    except (OSError, zipfile.BadZipFile):
        return None
    if not any(name.startswith("browser/") for name in archive.namelist()):
        archive.close()
        return None
    return archive


def browser_dir() -> Path:
    """Where the unpacked browser lives, outside the executable."""
    return app_data_dir() / "browser"


def _chrome_binary(root: Path) -> Optional[Path]:
    names = ("chrome.exe", "chrome", "Chromium.app")
    for name in names:
        for found in root.rglob(name):
            return found
    return None


def ensure_embedded_browser(progress=None) -> Optional[Path]:
    """Unpack the browser carried inside the executable, once.

    Returns the Chromium binary to drive, or None when this build carries no
    browser (running from source, say) and the machine's own Chrome should be
    used instead.

    The unpacking happens the first time a scrape runs rather than at startup,
    so opening the app — and demo mode, which needs no browser at all — never
    waits for it.
    """
    def say(message: str) -> None:
        if progress is not None:
            progress(message)

    configured = os.environ.get(CHROME_BINARY_ENV)
    if configured and Path(configured).exists():
        return Path(configured)

    payload = embedded_payload()
    if payload is None:
        return None

    with payload:
        try:
            manifest = json.loads(payload.read("browser/manifest.json"))
        except (KeyError, ValueError):
            return None
        target = browser_dir() / str(manifest.get("revision", "current"))

        if not target.exists():
            say("Unpacking the bundled browser — this happens once, "
                "and takes a minute…")
            staging = target.with_name(target.name + ".partial")
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir(parents=True, exist_ok=True)
            try:
                for name in payload.namelist():
                    if not name.endswith(".zip"):
                        continue
                    with payload.open(name) as inner:
                        # Read into memory: ZipFile needs to seek, and a
                        # member stream cannot.
                        with zipfile.ZipFile(io.BytesIO(inner.read())) as archive:
                            archive.extractall(staging)
                # Only now is it complete — a half-written folder must not
                # look like a finished one on the next run.
                staging.rename(target)
            except (OSError, zipfile.BadZipFile) as exc:
                shutil.rmtree(staging, ignore_errors=True)
                say(f"⚠ could not unpack the bundled browser: {exc}")
                return None
            say("Bundled browser ready.")

    binary = _chrome_binary(target)
    if binary is None:
        return None
    # Everything the app launches from here on drives this browser, and the
    # driver that shipped beside it — same build, so they always match.
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    os.environ[CHROME_BINARY_ENV] = str(binary)
    for driver in target.rglob("chromedriver*"):
        if driver.is_file():
            driver.chmod(driver.stat().st_mode | stat.S_IEXEC)
            entries = os.environ.get("PATH", "").split(os.pathsep)
            if str(driver.parent) not in entries:
                os.environ["PATH"] = os.pathsep.join([str(driver.parent)] + entries)
            break
    return binary


def _writable_dir(preferred: Path) -> Path:
    """``preferred`` if it can be created, else a temp folder that can.

    A locked-down or roaming profile should not stop the app from starting;
    it just means this session's files land somewhere else.
    """
    import tempfile

    for candidate in (preferred, Path(tempfile.gettempdir()) / APP_NAME):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write-test"
            probe.touch()
            probe.unlink()
            return candidate
        except OSError:
            continue
    return Path(tempfile.gettempdir())


def env_files() -> list[Path]:
    """Every place a ``.env`` with EMAIL_PASSWORD might sensibly live."""
    candidates = [Path.cwd() / ".env", app_data_dir() / ".env"]
    if frozen():
        candidates.append(Path(sys.executable).resolve().parent / ".env")
    seen: list[Path] = []
    for path in candidates:
        if path not in seen:
            seen.append(path)
    return seen
