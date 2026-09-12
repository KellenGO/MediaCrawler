"""Paths shared by source and PyInstaller runtime modes."""

from __future__ import annotations

import sys
from pathlib import Path


def bundle_root() -> Path:
    """Return the directory containing packaged read-only resources."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def application_root() -> Path:
    """Return the stable application directory for user-writable data."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_path(*parts: str) -> Path:
    """Resolve a bundled/source resource without depending on cwd."""
    return bundle_root().joinpath(*parts)


def writable_path(*parts: str) -> Path:
    """Resolve data that must survive restarts outside PyInstaller resources."""
    return application_root().joinpath(*parts)
