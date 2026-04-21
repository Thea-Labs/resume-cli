"""Arrow-key interactive selection helper.

`select_option(title, options)` renders a highlighted list, reads raw
keystrokes for ↑/↓/Enter, and returns the chosen index (or None on abort).
Falls back to numeric `Prompt.ask` when stdin is not a TTY.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from rich.live import Live
from rich.text import Text

from ..utils import console


def _render(options: list[str], idx: int) -> Text:
    text = Text()
    for i, label in enumerate(options):
        if i == idx:
            text.append(f"  ❯ {label}\n", style="bold magenta")
        else:
            text.append(f"    {label}\n", style="dim")
    return text


def _render_final(options: list[str], idx: int) -> Text:
    text = Text()
    text.append(f"  ❯ {options[idx]}\n", style="bold magenta")
    return text


def _fallback_numeric(options: list[str], default: int) -> Optional[int]:
    from rich.prompt import Prompt

    for i, label in enumerate(options, start=1):
        console.print(f"  [bold]{i}[/bold]  {label}")
    console.print()
    choices = [str(i) for i in range(1, len(options) + 1)]
    try:
        raw = Prompt.ask(
            "[magenta]Thea[/magenta] › Choose",
            choices=choices,
            default=str(default + 1),
        )
    except (EOFError, KeyboardInterrupt):
        console.print()
        return None
    return int(raw) - 1


def _read_key_posix(fd: int) -> str:
    """Block for one logical keypress on `fd` (already in cbreak mode).

    Returns 'up', 'down', 'enter', 'abort', or ''.
    """
    import select as _select

    try:
        b = os.read(fd, 1)
    except OSError:
        return "abort"
    if not b:
        return "abort"
    ch = b[0]

    if ch == 3:  # Ctrl+C
        return "abort"
    if ch in (10, 13):
        return "enter"
    if ch in (ord("q"), ord("Q")):
        return "abort"
    if ch == 27:  # Esc — possibly start of an escape sequence
        if _select.select([fd], [], [], 0.1)[0]:
            try:
                seq = os.read(fd, 2)
            except OSError:
                return "abort"
            if seq == b"[A":
                return "up"
            if seq == b"[B":
                return "down"
            return ""
        return "abort"
    if ch in (ord("k"), ord("K")):
        return "up"
    if ch in (ord("j"), ord("J")):
        return "down"
    return ""


def _read_key_windows() -> str:
    import msvcrt  # type: ignore

    ch = msvcrt.getch()
    if ch in (b"\r", b"\n"):
        return "enter"
    if ch == b"\x03":
        return "abort"
    if ch == b"\x1b":
        return "abort"
    if ch in (b"\xe0", b"\x00"):
        code = msvcrt.getch()
        if code == b"H":
            return "up"
        if code == b"P":
            return "down"
        return ""
    if ch in (b"q", b"Q"):
        return "abort"
    return ""


def select_option(
    title: str,
    options: list[str],
    *,
    default: int = 0,
) -> Optional[int]:
    """Interactive arrow-key selector. Returns the chosen index, or None on abort."""
    if not options:
        return None

    if not sys.stdin.isatty():
        return _fallback_numeric(options, default)

    is_windows = sys.platform == "win32"

    if is_windows:
        return _select_windows(options, default)

    try:
        import termios
        import tty
    except ImportError:
        return _fallback_numeric(options, default)

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    idx = max(0, min(default, len(options) - 1))

    try:
        tty.setcbreak(fd)
        with Live(
            _render(options, idx),
            console=console,
            refresh_per_second=30,
            transient=True,
        ) as live:
            while True:
                key = _read_key_posix(fd)
                if key == "up":
                    idx = (idx - 1) % len(options)
                    live.update(_render(options, idx))
                elif key == "down":
                    idx = (idx + 1) % len(options)
                    live.update(_render(options, idx))
                elif key == "enter":
                    break
                elif key == "abort":
                    return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    console.print(_render_final(options, idx))
    return idx


def _select_windows(options: list[str], default: int) -> Optional[int]:
    idx = max(0, min(default, len(options) - 1))
    with Live(
        _render(options, idx),
        console=console,
        refresh_per_second=30,
        transient=True,
    ) as live:
        while True:
            key = _read_key_windows()
            if key == "up":
                idx = (idx - 1) % len(options)
                live.update(_render(options, idx))
            elif key == "down":
                idx = (idx + 1) % len(options)
                live.update(_render(options, idx))
            elif key == "enter":
                break
            elif key == "abort":
                return None
    console.print(_render_final(options, idx))
    return idx
