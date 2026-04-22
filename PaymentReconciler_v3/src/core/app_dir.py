"""
Resolve the application's base directory reliably in both dev and PyInstaller.

Dev layout:    <repo>/src/ui/main_window.py  → app dir = <repo>/
Packaged exe:  Settings/app.exe              → app dir = Settings/
"""
from __future__ import annotations
import os
import sys


def get_app_dir() -> str:
    """Return the folder that contains the exe (frozen) or the repo root (dev)."""
    if getattr(sys, "frozen", False):
        # PyInstaller sets sys.executable to the .exe path
        return os.path.dirname(os.path.abspath(sys.executable))
    # Dev: this file is at src/core/app_dir.py — go up two levels to repo root
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def resolve_archive_path(raw_path: str) -> str:
    """Return an absolute archive path.

    Expands environment variables first (e.g. %OneDrive%, %USERPROFILE%),
    so a path like '%OneDrive%\\...\\BOA3PTY Archive' works for any user.
    If relative after expansion, resolves relative to the app directory.
    """
    expanded = os.path.expandvars(raw_path)
    if os.path.isabs(expanded):
        return os.path.normpath(expanded)
    return os.path.normpath(os.path.join(get_app_dir(), expanded))
