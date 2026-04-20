"""Build the structured context for `resume session`.

Reuses:
  - `git_analysis.recent_user_commits` for newest-first commit dicts
  - `diff._run` + `diff._truncate` for per-commit `git show --stat` snippets
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from .. import diff
from ..git_analysis import (
    NotAGitRepo,
    get_current_user,
    get_repo,
    recent_user_commits,
)
from .session_cluster import most_recent_session


def _parse_iso(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _files_touched(commits: list[dict]) -> list[str]:
    counts: dict[str, int] = {}
    order: dict[str, int] = {}
    for i, c in enumerate(commits):
        for path in c.get("files") or []:
            counts[path] = counts.get(path, 0) + 1
            order.setdefault(path, i)
    return [p for p, _ in sorted(counts.items(), key=lambda kv: (-kv[1], order[kv[0]]))]


def _show_stat(repo_root: Path, sha: str, max_chars: int) -> str:
    raw = diff._run(
        ["show", "--stat", "--no-color", sha],
        repo_root,
        timeout=diff._LONG_TIMEOUT,
    )
    return diff._truncate(raw, max_chars)


def _empty_context(repo_root: Path) -> dict:
    try:
        repo = get_repo(repo_root)
        name, email = get_current_user(repo)
    except NotAGitRepo:
        name, email = "", ""
    return {
        "user": {"name": name, "email": email},
        "branch": "",
        "session_start": None,
        "session_end": None,
        "duration_minutes": 0,
        "commit_count": 0,
        "commits": [],
        "files_touched": [],
        "diff_snippets": [],
    }


def build_session_context(
    repo_root: Path,
    max_commits: int = 20,
    gap_minutes: int = 90,
    diff_max_chars: int = 4000,
) -> dict:
    """Return the most-recent-session payload consumed by `summarize_session`."""
    try:
        repo = get_repo(repo_root)
    except NotAGitRepo:
        return _empty_context(repo_root)

    name, email = get_current_user(repo)

    try:
        branch = repo.active_branch.name
    except TypeError:
        branch = "(detached HEAD)"
    except Exception:
        branch = ""

    commits = recent_user_commits(repo, email, limit=max_commits) if email else []
    session = most_recent_session(commits, gap_minutes=gap_minutes)

    if not session:
        ctx = _empty_context(repo_root)
        ctx["user"] = {"name": name, "email": email}
        ctx["branch"] = branch
        return ctx

    # session is newest-first; start = oldest commit, end = newest commit
    start_dt = _parse_iso(session[-1].get("date"))
    end_dt = _parse_iso(session[0].get("date"))
    duration_minutes = 0
    if start_dt and end_dt:
        duration_minutes = max(0, int((end_dt - start_dt).total_seconds() // 60))

    trimmed_commits = [
        {
            "short_sha": c.get("short_sha") or (c.get("sha") or "")[:7],
            "message": c.get("message", ""),
            "date": c.get("date", ""),
            "files": c.get("files") or [],
        }
        for c in session
    ]

    diff_snippets = []
    for c in session:
        sha = c.get("sha") or c.get("short_sha") or ""
        if not sha:
            continue
        snippet = _show_stat(repo_root, sha, diff_max_chars)
        diff_snippets.append(
            {
                "short_sha": c.get("short_sha") or sha[:7],
                "message": c.get("message", ""),
                "diff": snippet,
            }
        )

    return {
        "user": {"name": name, "email": email},
        "branch": branch,
        "session_start": start_dt.isoformat() if start_dt else None,
        "session_end": end_dt.isoformat() if end_dt else None,
        "duration_minutes": duration_minutes,
        "commit_count": len(session),
        "commits": trimmed_commits,
        "files_touched": _files_touched(session),
        "diff_snippets": diff_snippets,
    }
