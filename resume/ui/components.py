"""Reusable UI components — header, section, paragraph, menu, status step.

All components render flush-left inside a width-capped content column so
the right side of the terminal stays free for future visualization.
"""

from __future__ import annotations

from typing import Optional

from ..stream import stream_chunks
from ..utils import console
from .renderer import content_width, format_paragraphs, wrap_text


def render_header(title: str = "Thea | Resume", subtitle: Optional[str] = None) -> None:
    """Brand header: 🧠 {title}, optional dim subtitle, trailing blank line."""
    console.print(f"[bold magenta]🧠 {title}[/bold magenta]")
    if subtitle:
        console.print(f"[dim italic]{subtitle}[/dim italic]")
    console.print()


def render_divider() -> None:
    """A plain horizontal divider at the content column width."""
    console.print("[magenta]" + "─" * content_width() + "[/magenta]")


def render_section(title: str) -> None:
    """── Section heading ── spanning exactly the content width."""
    width = content_width()
    label = f" {title} "
    left = 4
    right = max(4, width - left - len(label))
    console.print()
    console.print(f"[magenta]{'─' * left}{label}{'─' * right}[/magenta]")
    console.print()


def render_paragraph(
    text: str,
    *,
    stream: bool = False,
    char_delay: float = 0.03,
) -> None:
    """Wrap `text` to the content width and print (optionally char-streamed)."""
    wrapped = wrap_text(format_paragraphs(text or ""))
    if not wrapped:
        return
    if stream:
        stream_chunks(
            [wrapped],
            width=content_width(),
            left_pad=0,
            char_delay=char_delay,
        )
    else:
        console.print(wrapped)


_STATUS_MARKERS = {
    "done": "[green]✓[/green]",
    "running": "[magenta]…[/magenta]",
    "pending": "[dim]·[/dim]",
    "error": "[red]✗[/red]",
}


def render_status_step(message: str, status: str = "done") -> None:
    """Print a single status step: `✓ analyzing commits`."""
    marker = _STATUS_MARKERS.get(status, _STATUS_MARKERS["done"])
    console.print(f"  {marker}  {message}")
