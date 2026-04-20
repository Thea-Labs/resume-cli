"""Persist wrap-up notes to .resume/wrap.json at the repo root.

Each entry looks like:
  {
    "date": "2026-04-19",
    "branch": "main",
    "confirmed_summary": "…",
    "tomorrow_note": "ship the retry backoff fix",
    "commits": [{"sha": "...", "message": "..."}, ...]
  }

Newest entries are appended to the end of the list.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

WRAP_DIR = ".resume"
WRAP_FILE = "wrap.json"


def wrap_path(repo_root: Path) -> Path:
    return repo_root / WRAP_DIR / WRAP_FILE


def _load(repo_root: Path) -> list[dict]:
    path = wrap_path(repo_root)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "entries" in data:
        return list(data.get("entries") or [])
    return []


def _save(repo_root: Path, entries: list[dict]) -> None:
    path = wrap_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, default=str))


def save_wrap(
    repo_root: Path,
    *,
    confirmed_summary: str,
    tomorrow_note: str,
    today: dict,
) -> Path:
    """Append (or replace) today's wrap entry and return the file path."""
    today_iso = today.get("date") or date.today().isoformat()
    entries = [e for e in _load(repo_root) if e.get("date") != today_iso]
    entries.append(
        {
            "date": today_iso,
            "branch": today.get("branch", ""),
            "confirmed_summary": confirmed_summary,
            "tomorrow_note": tomorrow_note,
            "commits": [
                {"sha": c.get("sha"), "message": c.get("message")} for c in (today.get("commits") or [])
            ],
        }
    )
    _save(repo_root, entries)
    return wrap_path(repo_root)


def latest_wrap(repo_root: Path) -> Optional[dict]:
    """Return the most recent wrap entry, or None."""
    entries = _load(repo_root)
    return entries[-1] if entries else None
