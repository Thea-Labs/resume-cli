"""Git-based activity analysis.

Builds a structured timeline describing:
  - the current user's most recent commit,
  - files changed in that commit,
  - any commits that have landed since then,
  - files changed across those commits.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from git import InvalidGitRepositoryError, NoSuchPathError, Repo
from git.objects import Commit


class NotAGitRepo(Exception):
    """Raised when the target path is not inside a git repository."""


class NoUserCommits(Exception):
    """Raised when the repository has no commits by the current user."""


def get_repo(path: str | Path) -> Repo:
    """Open a git repository at `path`, searching parent directories."""
    try:
        return Repo(str(path), search_parent_directories=True)
    except (InvalidGitRepositoryError, NoSuchPathError) as exc:
        raise NotAGitRepo(f"{path} is not inside a git repository.") from exc


def get_current_user(repo: Repo) -> tuple[str, str]:
    """Return (name, email) from git config, with empty-string fallbacks."""
    reader = repo.config_reader()
    try:
        name = reader.get_value("user", "name", default="")
    except Exception:
        name = ""
    try:
        email = reader.get_value("user", "email", default="")
    except Exception:
        email = ""
    return str(name), str(email)


def find_last_user_commit(repo: Repo, email: str) -> Optional[Commit]:
    """Return the most recent commit authored by `email`, or None."""
    if not email:
        return None
    for commit in repo.iter_commits():
        if commit.author.email and commit.author.email.lower() == email.lower():
            return commit
    return None


def files_changed_in(commit: Commit) -> list[str]:
    """Return the list of files touched by `commit`."""
    try:
        return sorted(commit.stats.files.keys())
    except Exception:
        return []


def commits_since(repo: Repo, commit: Commit) -> list[Commit]:
    """Return commits on the current branch strictly newer than `commit`."""
    try:
        head = repo.head.commit
    except Exception:
        return []
    if head.hexsha == commit.hexsha:
        return []
    rev_range = f"{commit.hexsha}..{head.hexsha}"
    try:
        return list(repo.iter_commits(rev_range))
    except Exception:
        return []


def files_changed_since(commits: list[Commit]) -> dict[str, int]:
    """Aggregate touched files across `commits` with a change-count."""
    counts: dict[str, int] = {}
    for c in commits:
        try:
            for path in c.stats.files.keys():
                counts[path] = counts.get(path, 0) + 1
        except Exception:
            continue
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _commit_dict(commit: Commit) -> dict:
    authored = datetime.fromtimestamp(commit.authored_date, tz=timezone.utc)
    return {
        "sha": commit.hexsha,
        "short_sha": commit.hexsha[:7],
        "author": commit.author.name or "",
        "email": commit.author.email or "",
        "message": commit.message.strip().splitlines()[0] if commit.message else "",
        "date": authored.isoformat(),
        "files": files_changed_in(commit),
    }


def _count_user_commits_up_to(repo: Repo, email: str, anchor: Commit) -> int:
    """How many commits has the current user made up to and including `anchor`?"""
    count = 0
    for c in repo.iter_commits(anchor.hexsha):
        if c.author.email and c.author.email.lower() == email.lower():
            count += 1
    return count


def commits_today(repo: Repo, email: str, today: Optional[date] = None) -> list[Commit]:
    """Return commits authored today (local date) by `email`, newest first."""
    if not email:
        return []
    target = today or datetime.now().astimezone().date()
    results: list[Commit] = []
    for commit in repo.iter_commits(max_count=500):
        authored = datetime.fromtimestamp(commit.authored_date).astimezone()
        if authored.date() < target:
            break
        if authored.date() == target and commit.author.email and commit.author.email.lower() == email.lower():
            results.append(commit)
    return results


def build_today(repo: Repo, today: Optional[date] = None) -> dict:
    """Return a structured summary of the current user's commits today."""
    name, email = get_current_user(repo)
    target = today or datetime.now().astimezone().date()

    try:
        branch = repo.active_branch.name
    except TypeError:
        branch = "(detached HEAD)"
    except Exception:
        branch = ""

    commits = commits_today(repo, email, target) if email else []
    files = files_changed_since(commits)

    return {
        "user": {"name": name, "email": email},
        "branch": branch,
        "date": target.isoformat(),
        "commits": [_commit_dict(c) for c in commits],
        "files_changed": files,
    }


def recent_user_commits(repo: Repo, email: str, limit: int = 30) -> list[dict]:
    """Return up to `limit` most recent commits authored by `email`, newest first."""
    if not email:
        return []
    results: list[dict] = []
    for commit in repo.iter_commits(max_count=max(limit * 4, limit)):
        if commit.author.email and commit.author.email.lower() == email.lower():
            results.append(_commit_dict(commit))
            if len(results) >= limit:
                break
    return results


def build_timeline(repo: Repo) -> dict:
    """Top-level orchestrator: returns the full activity timeline dict."""
    name, email = get_current_user(repo)

    try:
        branch = repo.active_branch.name
    except TypeError:
        branch = "(detached HEAD)"
    except Exception:
        branch = ""

    last = find_last_user_commit(repo, email) if email else None
    if last is None:
        return {
            "user": {"name": name, "email": email},
            "branch": branch,
            "last_user_commit": None,
            "commits_since": [],
            "files_changed_since": {},
        }

    since = commits_since(repo, last)
    return {
        "user": {"name": name, "email": email},
        "branch": branch,
        "last_user_commit": {
            **_commit_dict(last),
            "user_commits_up_to": _count_user_commits_up_to(repo, email, last),
        },
        "commits_since": [_commit_dict(c) for c in since],
        "files_changed_since": files_changed_since(since),
    }
