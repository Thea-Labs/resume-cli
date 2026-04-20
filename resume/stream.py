"""Chunk-based streaming renderer for narration-style output.

Prints incoming text chunks character-by-character, word-wrapping at a
narrow column so the output reads like a ChatGPT/Claude web response.
Explicit newlines are preserved, which lets the summarizer use blank
lines as paragraph breaks.
"""

from __future__ import annotations

import sys
import time
from typing import Iterable

DEFAULT_WIDTH = 72
DEFAULT_LEFT_PAD = 2
DEFAULT_CHAR_DELAY = 0.012


def stream_chunks(
    chunks: Iterable[str],
    *,
    width: int = DEFAULT_WIDTH,
    left_pad: int = DEFAULT_LEFT_PAD,
    char_delay: float = 0.0,
) -> None:
    """Render an iterable of text chunks with live wrapping.

    Each chunk is consumed one character at a time so callers can pass either
    a single pre-generated string or a real streaming token iterator.
    """
    pad = " " * left_pad
    word_buf = ""
    line_len = 0
    pad_written = False

    def _write(s: str) -> None:
        sys.stdout.write(s)
        sys.stdout.flush()

    def _newline() -> None:
        nonlocal line_len, pad_written
        _write("\n")
        line_len = 0
        pad_written = False

    def _ensure_pad() -> None:
        nonlocal pad_written
        if not pad_written and pad:
            _write(pad)
            pad_written = True

    def _flush_word() -> None:
        nonlocal word_buf, line_len
        if not word_buf:
            return
        if line_len > 0 and line_len + len(word_buf) > width:
            _newline()
        _ensure_pad()
        _write(word_buf)
        line_len += len(word_buf)
        word_buf = ""

    for chunk in chunks:
        if not chunk:
            continue
        for ch in chunk:
            if ch == "\n":
                _flush_word()
                _newline()
            elif ch.isspace():
                _flush_word()
                if line_len == 0:
                    continue
                if line_len + 1 > width:
                    _newline()
                else:
                    _ensure_pad()
                    _write(ch)
                    line_len += 1
            else:
                word_buf += ch
            if char_delay:
                time.sleep(char_delay)

    _flush_word()
    if line_len > 0 or pad_written:
        _newline()


def stream_text(
    text: str,
    *,
    width: int = DEFAULT_WIDTH,
    left_pad: int = DEFAULT_LEFT_PAD,
    char_delay: float = DEFAULT_CHAR_DELAY,
    line_delay: float = 0.0,  # kept for backward compatibility (unused)
    style: str = "white",  # kept for backward compatibility (unused)
) -> None:
    """Render a full pre-generated string with chunk-style wrapping.

    Thin wrapper over `stream_chunks` so existing call sites keep working.
    `line_delay` and `style` are accepted but ignored — spacing now comes
    from explicit newlines in the text itself.
    """
    stream_chunks([text or ""], width=width, left_pad=left_pad, char_delay=char_delay)
