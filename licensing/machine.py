"""A stable, non-identifying fingerprint for this computer.

Seat enforcement needs to recognise the same machine across restarts and app
upgrades. It does not need to know anything *about* the machine, so this hashes
its inputs and keeps only 128 bits of the digest: the server stores an opaque
id it cannot reverse into a serial number, a MAC address or a username.

Stability is the hard part. Anything that changes when a customer docks a
laptop, joins a VPN or updates Windows would silently burn a seat, so the
inputs are limited to things that do not move:

* a random id this app writes once into its own config directory,
* the machine's own hardware/installation id where the OS exposes one,
* the hostname and CPU architecture, as a weak tiebreaker.

The random id alone would make "delete a file, get another trial" trivial;
hardware ids alone break for customers who reimage. Together, a matching id in
*either* half is treated as the same machine.
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import secrets
import subprocess
import uuid
from pathlib import Path
from typing import Optional

#: Test hook: when set, this is the fingerprint, full stop.
MACHINE_ID_ENV = "LLSP_MACHINE_ID"

_INSTALL_FILE = "install-id"
_cached: Optional[str] = None


def _config_dir() -> Path:
    """Where the install id lives — the app's own settings directory."""
    from gui import settings_store  # imported lazily: the TUI has no Qt

    return settings_store.config_dir()


def install_id(directory: Optional[Path] = None) -> str:
    """A random id written once per installation, created on first read."""
    folder = Path(directory) if directory is not None else _config_dir()
    path = folder / _INSTALL_FILE
    try:
        existing = path.read_text(encoding="utf-8").strip()
        if len(existing) >= 16:
            return existing
    except OSError:
        pass
    fresh = secrets.token_hex(16)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(fresh, encoding="utf-8")
    except OSError:
        # A read-only config directory should not stop the app from running;
        # the fingerprint just leans entirely on the hardware half this run.
        return hardware_id() or fresh
    return fresh


def hardware_id() -> str:
    """The OS's own installation id, where there is one to read.

    Every branch is best-effort: none of these commands exist everywhere, and a
    missing one costs stability, not correctness.
    """
    system = platform.system()
    try:
        if system == "Windows":
            import winreg  # noqa: PLC0415 - Windows-only import

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Cryptography", 0,
                                winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as handle:
                value, _ = winreg.QueryValueEx(handle, "MachineGuid")
                return str(value).strip()
        if system == "Darwin":
            out = subprocess.run(
                ["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True, text=True, timeout=5, check=False,
            ).stdout
            found = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out)
            if found:
                return found.group(1)
        if system == "Linux":
            for candidate in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                try:
                    value = Path(candidate).read_text(encoding="utf-8").strip()
                    if value:
                        return value
                except OSError:
                    continue
    except Exception:  # noqa: BLE001 - a fingerprint is never worth an exception
        return ""
    return ""


def _weak_traits() -> str:
    """Low-entropy extras. Used only as a tiebreaker inside the hash."""
    try:
        node = platform.node() or ""
    except Exception:  # noqa: BLE001
        node = ""
    return "|".join((node, platform.machine() or "", platform.system() or ""))


def _digest(*parts: str) -> str:
    raw = "␟".join(parts).encode("utf-8", "replace")
    return hashlib.sha256(raw).hexdigest()[:32]


def fingerprint(directory: Optional[Path] = None) -> str:
    """The id sent to the licence server. 32 hex characters, cached per run."""
    global _cached
    override = os.environ.get(MACHINE_ID_ENV)
    if override:
        return override.strip()
    if _cached is not None:
        return _cached
    _cached = _digest(install_id(directory), hardware_id(), _weak_traits())
    return _cached


def reset_cache() -> None:
    """Forget the cached fingerprint. For tests, and after a config move."""
    global _cached
    _cached = None


def describe() -> str:
    """A short human label for the seat list — "Jordan-PC (Windows)"."""
    try:
        node = platform.node() or "this computer"
    except Exception:  # noqa: BLE001
        node = "this computer"
    system = platform.system() or "unknown"
    release = platform.release() or ""
    return f"{node} ({system} {release})".strip()


def anonymous_id() -> str:
    """A throwaway id for machines that cannot persist anything.

    Used only when the config directory is unwritable *and* the OS exposes no
    hardware id — a rare enough combination that burning a seat per run is
    better than refusing to start.
    """
    return _digest(uuid.uuid4().hex)
