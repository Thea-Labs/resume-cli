"""`resume watch` — follow teammates' activity in a repository.

Stores watched author emails in `.resume/config.json` at the repo root and
exposes a fetcher used by the morning briefing to surface team activity
since the user's last commit.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Optional

from .git_analysis import NotAGitRepo, get_repo
from .ui import render_paragraph, render_section, select_many, select_option
from .utils import console

CONFIG_DIR = ".resume"
CONFIG_FILE = "config.json"

_SHORTLOG_RE = re.compile(r"\s*(\d+)\s+(.+?)\s+<([^>]+)>\s*$")


# ── Config ──────────────────────────────────────────────────────────────


def _config_path(repo_root: Path) -> Path:
    return repo_root / CONFIG_DIR / CONFIG_FILE


def load_watch_config(repo_root: Path) -> dict:
    path = _config_path(repo_root)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_watch_config(repo_root: Path, data: dict) -> Path:
    path = _config_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    return path


def watched_authors(repo_root: Path) -> list[str]:
    return list(load_watch_config(repo_root).get("watched_authors") or [])


# ── Author detection ────────────────────────────────────────────────────


_BOT_KEYWORDS = (
    "[bot]",
    "claude",
    "copilot",
    "dependabot",
    "renovate",
    "github-actions",
    "snyk-bot",
    "semantic-release",
)


def _is_bot_or_noreply(name: str, email: str) -> bool:
    """Filter out GitHub noreply addresses and known automation accounts."""
    e = email.lower()
    n = name.lower()
    if e.endswith("@users.noreply.github.com"):
        return True
    if "noreply" in e or "no-reply" in e:
        return True
    local = e.split("@", 1)[0]
    haystack = f"{n} {local}"
    return any(kw in haystack for kw in _BOT_KEYWORDS)


def detect_authors(repo_root: Path) -> list[dict]:
    """Run `git shortlog -sne --all` and parse into a list of authors.

    Filters out GitHub noreply addresses and automation accounts (Claude,
    Copilot, Dependabot, Renovate, github-actions, generic `[bot]` accounts).
    """
    try:
        out = subprocess.run(
            ["git", "shortlog", "-sne", "--all"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    authors: list[dict] = []
    for line in out.splitlines():
        m = _SHORTLOG_RE.match(line)
        if not m:
            continue
        count, name, email = m.group(1), m.group(2).strip(), m.group(3).strip()
        if _is_bot_or_noreply(name, email):
            continue
        authors.append({"name": name, "email": email, "count": int(count)})
    return authors


# ── Selection parsing ──────────────────────────────────────────────────


def _parse_selection(raw: str, max_index: int) -> list[int]:
    """Parse '1,2 3' style input into a sorted, unique list of 1-based indices."""
    tokens = [t for t in re.split(r"[,\s]+", raw.strip()) if t]
    picked: set[int] = set()
    for tok in tokens:
        if tok.isdigit():
            n = int(tok)
            if 1 <= n <= max_index:
                picked.add(n)
    return sorted(picked)


# ── Setup flow ──────────────────────────────────────────────────────────


def _cmd_setup(repo_root: Path) -> int:
    console.print("[bold magenta]🧠 Thea | Watch setup[/bold magenta]\n")
    authors = detect_authors(repo_root)
    if not authors:
        console.print("[yellow]No contributors found in this repository.[/yellow]")
        return 0

    console.print('[italic]"I found these developers in this repository."[/italic]\n')

    labels = [f"{a['name']}  <{a['email']}>" for a in authors]
    existing = load_watch_config(repo_root).get("watched_authors") or []
    preselected = [
        i for i, a in enumerate(authors) if a["email"] in existing
    ]
    indices = select_many("watch", labels, preselected=preselected)
    if indices is None:
        console.print("[yellow]Cancelled. Nothing saved.[/yellow]")
        return 0
    if not indices:
        console.print("[dim]No developers selected. Nothing saved.[/dim]")
        return 0

    emails = [authors[i]["email"] for i in indices]
    cfg = load_watch_config(repo_root)
    cfg["watched_authors"] = emails
    saved = save_watch_config(repo_root, cfg)

    render_section("Watching")
    for i in indices:
        a = authors[i]
        console.print(f"  • {a['name']} [dim]<{a['email']}>[/dim]")
    console.print(f"\n[dim]Saved to {saved.relative_to(repo_root)}[/dim]")
    return 0


# ── List / add / remove ────────────────────────────────────────────────


def _name_for_email(repo_root: Path, email: str) -> Optional[str]:
    for a in detect_authors(repo_root):
        if a["email"].lower() == email.lower():
            return a["name"]
    return None


def _cmd_list(repo_root: Path) -> int:
    console.print("[bold magenta]🧠 Thea | Watched developers[/bold magenta]\n")
    emails = watched_authors(repo_root)
    if not emails:
        console.print("[dim]No developers are being watched yet. Run "
                      "[bold]resume watch --setup[/bold] to pick some.[/dim]")
        return 0
    for email in emails:
        name = _name_for_email(repo_root, email) or email
        console.print(f"  • {name} [dim]<{email}>[/dim]")
    return 0


def _cmd_add(repo_root: Path, email: str) -> int:
    email = email.strip()
    if not email:
        console.print("[red]Email is required.[/red]")
        return 1
    cfg = load_watch_config(repo_root)
    emails = list(cfg.get("watched_authors") or [])
    if email in emails:
        console.print(f"[dim]{email} is already being watched.[/dim]")
        return 0
    emails.append(email)
    cfg["watched_authors"] = emails
    save_watch_config(repo_root, cfg)
    console.print(f"[green]Watching[/green] {email}.")
    return 0


def _cmd_remove(repo_root: Path, email: str) -> int:
    email = email.strip()
    cfg = load_watch_config(repo_root)
    emails = list(cfg.get("watched_authors") or [])
    if email not in emails:
        console.print(f"[yellow]{email} is not in the watch list.[/yellow]")
        return 0
    emails.remove(email)
    cfg["watched_authors"] = emails
    save_watch_config(repo_root, cfg)
    console.print(f"[green]Stopped watching[/green] {email}.")
    return 0


# ── Team activity fetch ────────────────────────────────────────────────


def fetch_team_activity(
    repo_root: Path,
    emails: list[str],
    *,
    since_iso: Optional[str],
    self_email: str = "",
) -> list[dict]:
    """Return a list of {author, email, commits: [{message, files}, ...]}.

    Only includes authors with at least one commit in the window. Each commit
    carries its message and the list of files changed (no SHAs).
    """
    if not emails:
        return []

    out: list[dict] = []
    for email in emails:
        if self_email and email.lower() == self_email.lower():
            continue
        cmd = [
            "git", "log",
            f"--author={email}",
            "--no-merges",
            "--pretty=format:%H%x1f%an%x1f%s",
            "--name-only",
            "-z",
        ]
        if since_iso:
            cmd.append(f"--since={since_iso}")

        try:
            result = subprocess.run(
                cmd,
                cwd=str(repo_root),
                check=True,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
            ).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

        commits = _parse_log(result)
        if commits:
            out.append({
                "author": commits[0]["author"],
                "email": email,
                "commits": [
                    {"message": c["message"], "files": c["files"]} for c in commits
                ],
            })
    return out


def _parse_log(raw: str) -> list[dict]:
    """Parse `git log --pretty=...%x1f... --name-only -z` output."""
    commits: list[dict] = []
    if not raw:
        return commits
    # Records are NUL-separated; the first field of each record holds the
    # pretty-formatted header (sha\x1fauthor\x1fsubject) followed by file
    # names on subsequent lines (newline-separated within the record).
    for record in raw.split("\x00"):
        record = record.strip("\n")
        if not record:
            continue
        head, _, files_block = record.partition("\n")
        parts = head.split("\x1f")
        if len(parts) < 3:
            continue
        _, author, subject = parts[0], parts[1], parts[2]
        files = [f for f in files_block.split("\n") if f.strip()]
        commits.append({"author": author, "message": subject, "files": files})
    return commits


# ── Argparse wiring ────────────────────────────────────────────────────


def add_watch_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "watch",
        help=argparse.SUPPRESS,
        description="Follow teammates and surface their activity in your morning briefing.",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Detect contributors and pick who to watch.",
    )
    nested = parser.add_subparsers(dest="watch_action")
    nested.add_parser("list", help="Show watched developers.")
    add_p = nested.add_parser("add", help="Add a developer by email.")
    add_p.add_argument("email")
    rm_p = nested.add_parser("remove", help="Remove a developer by email.")
    rm_p.add_argument("email")


def cmd_watch(args: argparse.Namespace) -> int:
    try:
        repo = get_repo(Path.cwd())
    except NotAGitRepo as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return 1
    repo_root = Path(repo.working_tree_dir or Path.cwd())

    if getattr(args, "setup", False):
        return _cmd_setup(repo_root)

    action = getattr(args, "watch_action", None)
    if action == "add":
        return _cmd_add(repo_root, args.email)
    if action == "remove":
        return _cmd_remove(repo_root, args.email)
    return _cmd_list(repo_root)
