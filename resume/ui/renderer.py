"""Width + wrapping primitives for the unified UI.

Resume uses a fixed content column (max 72 chars) so output stays readable
and leaves the right side of the terminal free for future visualizations
(timelines, sparklines, progress clusters).
"""

from __future__ import annotations

import re
import shutil
import textwrap

MAX_CONTENT_WIDTH = 72
SENTENCES_PER_PARAGRAPH = 2


def content_width() -> int:
    """Return the current content column width.

    Caps at MAX_CONTENT_WIDTH, but shrinks if the terminal is narrower.
    Leaves a small gutter so wrapped text never butts against the edge.
    """
    try:
        cols = shutil.get_terminal_size().columns
    except OSError:
        cols = 80
    return max(40, min(MAX_CONTENT_WIDTH, cols - 4))


def format_paragraphs(text: str, sentences_per_paragraph: int = SENTENCES_PER_PARAGRAPH) -> str:
    """Break a long block into short paragraphs of ~N sentences each.

    Existing blank-line breaks are preserved. Within each existing paragraph,
    sentences are regrouped into chunks so no paragraph exceeds
    `sentences_per_paragraph`.
    """
    if not text:
        return ""

    raw_paragraphs = re.split(r"\n{2,}", text.replace("\r\n", "\n"))
    out: list[str] = []
    for para in raw_paragraphs:
        stripped = " ".join(para.split())
        if not stripped:
            continue
        sentences = re.split(r"(?<=[.!?])\s+", stripped)
        sentences = [s for s in sentences if s.strip()]
        if not sentences:
            continue
        for i in range(0, len(sentences), sentences_per_paragraph):
            chunk = " ".join(sentences[i : i + sentences_per_paragraph]).strip()
            if chunk:
                out.append(chunk)
    return "\n\n".join(out)


def wrap_text(text: str, width: int | None = None) -> str:
    """Wrap `text` to the content column, preserving blank-line paragraph breaks.

    Empty/whitespace-only text is returned unchanged. Each paragraph (split on
    blank lines) is wrapped independently via `textwrap.fill`.
    """
    if not text:
        return ""
    w = width or content_width()
    # Normalize CRLF then split on blank lines; wrap each paragraph.
    paragraphs = text.replace("\r\n", "\n").split("\n\n")
    wrapped = []
    for para in paragraphs:
        # Collapse internal single newlines so textwrap can repack cleanly,
        # but preserve leading bullet/indent characters on the first line.
        stripped = para.strip("\n")
        if not stripped.strip():
            wrapped.append("")
            continue
        wrapped.append(
            textwrap.fill(
                stripped,
                width=w,
                break_long_words=False,
                break_on_hyphens=False,
                replace_whitespace=True,
            )
        )
    return "\n\n".join(wrapped)
