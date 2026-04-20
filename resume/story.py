"""`resume story` — cluster recent commits into work threads and render bars.

Two clustering paths:
  - LLM: delegate to summarizer.summarize_story (returns theme groupings).
  - Heuristic: group by the top-level directory of the majority of files touched.
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from .summarizer import summarize_story
from .utils import console

BAR_FULL = "█"
BAR_EMPTY = "░"


def cluster_commits(commits: list[dict], client=None) -> list[dict]:
    """Return [{'theme': str, 'commits': [...]}] ordered by commit count desc."""
    if not commits:
        return []

    if client is not None:
        grouped = summarize_story(commits, client=client)
        rendered = _materialize_llm_groups(grouped, commits)
        if rendered:
            return rendered

    return _heuristic_cluster(commits)


def _materialize_llm_groups(groups: list[dict], commits: list[dict]) -> list[dict]:
    """Turn LLM index-groups into concrete commit-lists; ensure all commits land somewhere."""
    if not groups:
        return []
    used: set[int] = set()
    threads: list[dict] = []
    for g in groups:
        indices = [i for i in g.get("commit_indices", []) if i not in used]
        if not indices:
            continue
        used.update(indices)
        threads.append(
            {
                "theme": g["theme"],
                "commits": [commits[i] for i in indices],
            }
        )

    leftovers = [c for i, c in enumerate(commits) if i not in used]
    if leftovers:
        threads.append({"theme": "Other", "commits": leftovers})

    threads.sort(key=lambda t: len(t["commits"]), reverse=True)
    return threads


def _heuristic_cluster(commits: list[dict]) -> list[dict]:
    """Group commits by the majority top-level directory of their touched files."""
    buckets: dict[str, list[dict]] = {}
    for commit in commits:
        label = _top_level_label(commit.get("files") or [])
        buckets.setdefault(label, []).append(commit)

    threads = [{"theme": theme, "commits": cs} for theme, cs in buckets.items()]
    threads.sort(key=lambda t: len(t["commits"]), reverse=True)
    return threads


def _top_level_label(files: list[str]) -> str:
    if not files:
        return "other"
    tops = []
    for path in files:
        head = path.split("/", 1)[0] if "/" in path else "root"
        tops.append(head)
    most_common, _ = Counter(tops).most_common(1)[0]
    return most_common


def render_threads(
    threads: list[dict],
    *,
    total_commits: Optional[int] = None,
    width: int = 22,
) -> None:
    """Print threads as labelled progress bars."""
    if not threads:
        console.print("[dim]No commits found — nothing to map.[/dim]")
        return

    n = total_commits if total_commits is not None else sum(len(t["commits"]) for t in threads)
    console.print(f"[bold magenta]Work threads[/bold magenta] [dim]· last {n} commits[/dim]\n")

    max_count = max(len(t["commits"]) for t in threads) or 1
    label_width = min(max(len(t["theme"]) for t in threads), 28)

    for thread in threads:
        count = len(thread["commits"])
        filled = max(1, round((count / max_count) * width))
        empty = width - filled
        bar = f"[magenta]{BAR_FULL * filled}[/magenta][dim]{BAR_EMPTY * empty}[/dim]"
        theme = thread["theme"][:label_width].ljust(label_width)
        console.print(f"  [bold]{theme}[/bold]  {bar}  [dim]{count:>3}[/dim]")
