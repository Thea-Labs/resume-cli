"""First-run onboarding: capture name / speech speed / audio preference.

Config lives at ~/.thea/config.json. If the file is missing, `needs_onboarding`
returns True and `run_onboarding` walks the user through three short prompts.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from rich.prompt import Prompt

from .ui import render_paragraph, render_section, select_option
from .utils import clear_terminal, console, print_header

CONFIG_DIR = Path.home() / ".thea"
CONFIG_PATH = CONFIG_DIR / "config.json"

_SPEED_VALUES = ["natural", "fast", "calm"]


def needs_onboarding() -> bool:
    """True if no config has been written yet."""
    return not CONFIG_PATH.exists()


def _save(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))


def run_onboarding() -> dict:
    """Interactive first-run setup. Returns the saved config dict."""
    clear_terminal()
    print_header()

    render_paragraph(
        "Hello.\n\n"
        "It looks like this is your first time running Resume. "
        "Let's get you set up."
    )

    # ── Q1 — name ───────────────────────────────────────────────────────
    render_section("Your name")
    try:
        name_raw = Prompt.ask("[magenta]Thea[/magenta] › What should I call you?").strip()
    except (EOFError, KeyboardInterrupt):
        console.print()
        name_raw = ""
    name = name_raw.split()[0] if name_raw else ""

    # ── Q2 — speech speed ───────────────────────────────────────────────
    render_section("How would you like Thea to speak?")
    speed_idx = select_option(
        "speech_speed",
        ["Natural (recommended)", "Fast", "Calm"],
    )
    speech_speed = _SPEED_VALUES[speed_idx] if speed_idx is not None else "natural"

    # ── Q3 — audio on/off ───────────────────────────────────────────────
    render_section("Do you want Thea to speak briefings out loud?")
    audio_idx = select_option("audio_enabled", ["Yes", "Text only"])
    audio_enabled = audio_idx != 1  # None → default on; 0 → on; 1 → off

    config = {
        "name": name,
        "speech_speed": speech_speed,
        "audio_enabled": audio_enabled,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _save(config)

    render_section("Setup complete")
    render_paragraph(
        "From now on, just run:\n\n"
        "  resume"
    )
    console.print(f"\n[dim]Saved to {CONFIG_PATH}[/dim]\n")
    return config
