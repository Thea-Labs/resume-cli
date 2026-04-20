"""Run git commands and capture raw diff context for the briefing.

Every call is:
  - isolated in its own subprocess invocation
  - timeout-capped (git should never block the CLI)
  - error-swallowing (missing HEAD, shallow clones, permission errors all
    collapse to empty strings so the caller can reason about presence vs
    absence without try/except noise)

Diff output is length-capped to keep LLM prompts predictable.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

DEFAULT_MAX_CHARS = 5000
_SHORT_TIMEOUT = 3.0
_LONG_TIMEOUT = 8.0  # diff can be slow on very large repos


def _run(args: list[str], cwd: Path, timeout: float = _SHORT_TIMEOUT) -> str:
    """Run `git <args>` in `cwd`, returning stdout or "" on any failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


def _truncate(text: str, max_chars: int) -> str:
    if not text or max_chars <= 0 or len(text) <= max_chars:
        return text
    elided = len(text) - max_chars
    return f"{text[:max_chars]}\n…[truncated, {elided} chars elided]"


def last_commit_meta(repo_root: Path) -> dict:
    """Return {hash, author, date, message} for HEAD, or {} if no commits."""
    out = _run(
        ["log", "-1", "--pretty=format:%H%n%an%n%ad%n%s"],
        repo_root,
    )
    if not out:
        return {}
    parts = out.split("\n", 3)
    if len(parts) < 4:
        return {}
    return {
        "hash": parts[0],
        "author": parts[1],
        "date": parts[2],
        "message": parts[3],
    }


def files_changed_last_commit(repo_root: Path) -> list[str]:
    """Return the list of files touched by HEAD."""
    out = _run(
        ["diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
        repo_root,
    )
    return [line for line in out.splitlines() if line.strip()]


def last_commit_diff(repo_root: Path, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Return the diff introduced by HEAD.

    Uses HEAD~1..HEAD when there's a parent; falls back to `git show HEAD`
    on the initial commit so repositories with a single commit still
    produce diff text.
    """
    has_parent = bool(_run(["rev-parse", "--verify", "HEAD~1"], repo_root).strip())
    if has_parent:
        raw = _run(["diff", "HEAD~1", "HEAD"], repo_root, timeout=_LONG_TIMEOUT)
    else:
        raw = _run(["show", "--no-color", "HEAD"], repo_root, timeout=_LONG_TIMEOUT)
    return _truncate(raw, max_chars)


def staged_diff(repo_root: Path, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Return the index-vs-HEAD diff (what's staged but not committed)."""
    return _truncate(
        _run(["diff", "--cached"], repo_root, timeout=_LONG_TIMEOUT),
        max_chars,
    )


def unstaged_diff(repo_root: Path, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Return the working-tree-vs-index diff (unstaged edits)."""
    return _truncate(
        _run(["diff"], repo_root, timeout=_LONG_TIMEOUT),
        max_chars,
    )


def short_status(repo_root: Path) -> str:
    """Return `git status --short` — a compact view of WIP files."""
    return _run(["status", "--short"], repo_root)
