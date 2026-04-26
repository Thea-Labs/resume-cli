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

    Returns 'up', 'down', 'enter', 'space', 'save', 'abort', or ''.
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
    if ch == 32:
        return "space"
    if ch in (ord("x"), ord("X")):
        return "save"
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
    if ch == b" ":
        return "space"
    if ch in (b"x", b"X"):
        return "save"
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


def _render_multi(options: list[str], idx: int, selected: set[int]) -> Text:
    text = Text()
    for i, label in enumerate(options):
        cursor = "❯" if i == idx else " "
        box = "[x]" if i in selected else "[ ]"
        line = f"  {cursor} {box} {label}\n"
        text.append(line, style="bold magenta" if i == idx else "dim")
    text.append(
        "\n  ↑/↓ move · enter toggle · x to save · q to cancel\n",
        style="dim",
    )
    return text


def _render_multi_final(options: list[str], selected: set[int]) -> Text:
    text = Text()
    if not selected:
        text.append("  (no selections)\n", style="dim")
        return text
    for i in sorted(selected):
        text.append(f"  ❯ [x] {options[i]}\n", style="bold magenta")
    return text


def _fallback_multi_numeric(options: list[str]) -> Optional[list[int]]:
    from rich.prompt import Prompt

    for i, label in enumerate(options, start=1):
        console.print(f"  [bold]{i}[/bold]  {label}")
    console.print()
    try:
        raw = Prompt.ask(
            "[magenta]Thea[/magenta] › Enter numbers (e.g. 1,2 3)"
        )
    except (EOFError, KeyboardInterrupt):
        console.print()
        return None
    import re

    picked: set[int] = set()
    for tok in re.split(r"[,\s]+", (raw or "").strip()):
        if tok.isdigit():
            n = int(tok)
            if 1 <= n <= len(options):
                picked.add(n - 1)
    return sorted(picked)


def select_many(
    title: str,
    options: list[str],
    *,
    preselected: Optional[list[int]] = None,
) -> Optional[list[int]]:
    """Multi-select picker. Enter toggles, x saves, q/Esc aborts.

    Returns sorted list of selected 0-based indices (possibly empty), or None
    if the user aborted.
    """
    if not options:
        return []

    if not sys.stdin.isatty():
        return _fallback_multi_numeric(options)

    is_windows = sys.platform == "win32"
    if is_windows:
        return _select_many_windows(options, preselected or [])

    try:
        import termios
        import tty
    except ImportError:
        return _fallback_multi_numeric(options)

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    idx = 0
    selected: set[int] = {i for i in (preselected or []) if 0 <= i < len(options)}

    try:
        tty.setcbreak(fd)
        with Live(
            _render_multi(options, idx, selected),
            console=console,
            refresh_per_second=30,
            transient=True,
        ) as live:
            while True:
                key = _read_key_posix(fd)
                if key == "up":
                    idx = (idx - 1) % len(options)
                elif key == "down":
                    idx = (idx + 1) % len(options)
                elif key in ("enter", "space"):
                    if idx in selected:
                        selected.remove(idx)
                    else:
                        selected.add(idx)
                elif key == "save":
                    break
                elif key == "abort":
                    return None
                else:
                    continue
                live.update(_render_multi(options, idx, selected))
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    console.print(_render_multi_final(options, selected))
    return sorted(selected)


def _select_many_windows(
    options: list[str], preselected: list[int]
) -> Optional[list[int]]:
    idx = 0
    selected: set[int] = {i for i in preselected if 0 <= i < len(options)}
    with Live(
        _render_multi(options, idx, selected),
        console=console,
        refresh_per_second=30,
        transient=True,
    ) as live:
        while True:
            key = _read_key_windows()
            if key == "up":
                idx = (idx - 1) % len(options)
            elif key == "down":
                idx = (idx + 1) % len(options)
            elif key in ("enter", "space"):
                if idx in selected:
                    selected.remove(idx)
                else:
                    selected.add(idx)
            elif key == "save":
                break
            elif key == "abort":
                return None
            else:
                continue
            live.update(_render_multi(options, idx, selected))
    console.print(_render_multi_final(options, selected))
    return sorted(selected)


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
