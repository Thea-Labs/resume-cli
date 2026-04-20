"""Detect last-edited / suggested files and launch them in VS Code."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional


_PATH_RE = re.compile(
    r"(?<![\w/:])((?:[A-Za-z0-9_\-\[\]]+/)*[A-Za-z0-9_\-\[\]]+\.(?:ts|tsx|py|js|jsx|md|json|toml|yaml|yml|css|scss|html|sql|go|rs|rb|java))\b"
)


def last_edited_file(timeline: dict, repo_root: Path) -> Optional[Path]:
    """Pick the most relevant file from the user's last commit that still exists on disk."""
    last = timeline.get("last_user_commit") or {}
    files = last.get("files") or []
    for rel in files:
        candidate = (repo_root / rel).resolve()
        if candidate.exists():
            return candidate
    return None


def extract_file_path(text: str, repo_root: Optional[Path] = None) -> Optional[Path]:
    """Find the first file-path-like token in `text` and resolve it against repo_root.

    Returns an absolute Path if a match resolves to an existing file on disk,
    otherwise returns the first raw match as a Path (caller decides how to
    handle missing files). Returns None if nothing matches.
    """
    if not text:
        return None

    matches = _PATH_RE.findall(text)
    if not matches:
        return None

    if repo_root is not None:
        for rel in matches:
            candidate = (repo_root / rel).resolve()
            if candidate.exists():
                return candidate

    return Path(matches[0])


def open_in_editor(path: Path, repo_root: Optional[Path] = None) -> bool:
    """Open `path` in VS Code if the `code` command is on PATH. Returns True on success."""
    code_bin = shutil.which("code")
    if not code_bin:
        return False
    try:
        if repo_root is not None:
            subprocess.run([code_bin, str(repo_root), "-g", str(path)], check=False)
        else:
            subprocess.run([code_bin, "-g", str(path)], check=False)
        return True
    except Exception:
        return False


# Alias matching the naming used in newer call sites.
open_in_vscode = open_in_editor
