"""Shared helpers: console, OpenAI client, message pools, startup runner."""

from __future__ import annotations

import os
import random
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from rich.console import Console
from rich.live import Live
from rich.table import Table

ASSISTANT_NAME = "Thea"
TOOL_NAME = "Resume"

console = Console()


# ── Rotating message pools ──────────────────────────────────────────────

CONTEXT_MESSAGES = [
    "Thea is reconstructing your last session...",
    "Thea is rebuilding your work context...",
    "Thea is retracing your last commits...",
    "Thea is stitching together yesterday's work...",
    "Thea is piecing together what you were building...",
]

GIT_MESSAGES = [
    "🔎 Thea is looking through your git history",
    "🔎 Thea is inspecting your last commits",
    "🔎 Thea is checking what changed",
    "🔎 Thea is retracing your code trail",
]

ANALYSIS_MESSAGES = [
    "🧩 Thea is rebuilding the story",
    "🧩 Thea is connecting the dots",
    "🧩 Thea is reconstructing your thought process",
    "🧩 Thea is figuring out where you left off",
]

BRIEFING_MESSAGES = [
    "🎧 Thea is preparing your briefing",
    "🎧 Thea is putting together the morning rundown",
    "🎧 Thea is getting your context ready",
    "🎧 Thea is lining up your next move",
]

FUN_MESSAGES = [
    "Thea is reading your last commit message...",
    "Thea is checking if you left any mysteries in the code...",
    "Thea is making sense of yesterday's commits...",
    "Thea is reviewing your trail of changes...",
]

GREETING_MESSAGES = [
    "Welcome back.",
    "Good to see you again.",
    "Ready to continue where you left off.",
    "Resuming your last working context.",
    "Reconstructing your workspace.",
]

FUN_CHANCE = 0.10


def _pick_with_fun(pool: list[str]) -> str:
    """Return a pool message normally; with FUN_CHANCE probability, a fun one."""
    if random.random() < FUN_CHANCE:
        return random.choice(FUN_MESSAGES)
    return random.choice(pool)


def pick_context_title() -> str:
    return random.choice(CONTEXT_MESSAGES)


def pick_git_label() -> str:
    return _pick_with_fun(GIT_MESSAGES)


def pick_analysis_label() -> str:
    return _pick_with_fun(ANALYSIS_MESSAGES)


def pick_briefing_label() -> str:
    return _pick_with_fun(BRIEFING_MESSAGES)


def pick_greeting() -> str:
    return random.choice(GREETING_MESSAGES)


# ── Header ──────────────────────────────────────────────────────────────


def print_header(subtitle: Optional[str] = None) -> None:
    """Render the brand header: `🧠 Thea | Resume`, optionally with a subtitle."""
    console.print("[bold magenta]🧠 Thea | Resume[/bold magenta]")
    if subtitle:
        console.print(f"[dim italic]{subtitle}[/dim italic]")
    console.print()


def thea_says(message: str) -> None:
    """Print an in-character Thea status line."""
    console.print(f"[magenta]{ASSISTANT_NAME}[/magenta] [dim]›[/dim] {message}")


# ── OpenAI client ───────────────────────────────────────────────────────


def get_openai_client():
    """Return an OpenAI client if OPENAI_API_KEY is set, else None."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None
    return OpenAI(api_key=api_key)


# ── Small utilities ─────────────────────────────────────────────────────


def format_iso(dt: datetime) -> str:
    """Format a datetime as a friendly ISO-ish string in UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def clamp_words(text: str, max_words: int = 150) -> str:
    """Trim text to at most max_words, preserving paragraph breaks and sentence boundaries."""
    word_count = len(text.split())
    if word_count <= max_words:
        return text.strip()
    import re
    tokens = re.findall(r"\S+|\s+", text)
    kept = []
    words_kept = 0
    for tok in tokens:
        if tok.strip():
            if words_kept >= max_words:
                break
            words_kept += 1
        kept.append(tok)
    truncated = "".join(kept).rstrip()
    last_stop = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
    if last_stop > 0:
        return truncated[: last_stop + 1]
    return truncated + "…"


def short_sha(sha: Optional[str]) -> str:
    return (sha or "")[:7]


# ── Startup runner ──────────────────────────────────────────────────────


_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def run_startup(title: str, steps: list[tuple[str, Callable[[], Any]]]) -> dict[str, Any]:
    """Print `title`, then run each step sequentially with a live spinner → ✓."""
    console.print(f"[bold magenta]{title}[/bold magenta]\n")

    statuses = ["pending"] * len(steps)
    results: dict[str, Any] = {}

    def _render(frame_idx: int) -> Table:
        table = Table.grid(padding=(0, 1))
        for (label, _), state in zip(steps, statuses):
            if state == "done":
                marker = "[green]✓[/green]"
            elif state == "running":
                marker = f"[magenta]{_SPINNER_FRAMES[frame_idx % len(_SPINNER_FRAMES)]}[/magenta]"
            elif state == "error":
                marker = "[red]✗[/red]"
            else:
                marker = "[dim]·[/dim]"
            table.add_row(" ", marker, label)
        return table

    import threading
    import time

    with Live(_render(0), console=console, refresh_per_second=12, transient=False) as live:
        for i, (label, fn) in enumerate(steps):
            statuses[i] = "running"
            frame = {"i": 0}
            done = threading.Event()

            def _animate() -> None:
                while not done.is_set():
                    frame["i"] += 1
                    live.update(_render(frame["i"]))
                    time.sleep(0.08)

            spinner_thread = threading.Thread(target=_animate, daemon=True)
            spinner_thread.start()
            try:
                results[label] = fn()
                statuses[i] = "done"
            except Exception:
                statuses[i] = "error"
                done.set()
                spinner_thread.join()
                live.update(_render(frame["i"]))
                raise
            finally:
                done.set()
                spinner_thread.join()
                live.update(_render(frame["i"]))

    console.print()
    return results
