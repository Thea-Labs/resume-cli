"""`resume plan` — interactive prompt designer for Claude Code.

Walks the user through five short questions, generates a structured
prompt, then offers copy / edit / cancel.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from rich.prompt import Prompt

from .ui import render_paragraph, render_section, select_option
from .utils import clear_terminal, console

_SCOPE_OPTIONS = [
    "CLI interface",
    "summarizer logic",
    "git analysis",
    "entire system",
    "other",
]

_CHANGE_OPTIONS = [
    "bug fix",
    "improvement",
    "refactor",
    "new feature",
]

_OUTPUT_OPTIONS = [
    "minimal patch",
    "explanation + patch",
    "full refactor",
]

_PROJECT_CONTEXT = (
    "The tool reconstructs development sessions from git history and "
    "prints briefings."
)


def _ask_free_text(prompt: str, *, allow_empty: bool = False) -> str | None:
    try:
        raw = Prompt.ask(f"[magenta]Thea[/magenta] › {prompt}").strip()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return None
    if not raw and not allow_empty:
        return None
    return raw


def _ask_scope_other() -> str:
    text = _ask_free_text("Describe the scope", allow_empty=False)
    return text or "unspecified"


def _build_prompt(
    *,
    goal: str,
    scope: str,
    change_type: str,
    constraints: str,
    output_style: str,
) -> str:
    constraints_line = constraints.strip() or "None specified."
    return (
        "You are modifying a Python CLI project.\n\n"
        f"Goal:\n{goal}\n\n"
        f"Context:\n{_PROJECT_CONTEXT}\n\n"
        f"Scope:\n{scope}\n\n"
        f"Change type:\n{change_type}\n\n"
        f"Constraints:\n{constraints_line}\n\n"
        f"Requested output:\nProduce a {output_style}."
    )


def _copy_to_clipboard(text: str) -> bool:
    """Best-effort copy to the system clipboard. Returns True on success."""
    try:
        import pyperclip  # type: ignore

        pyperclip.copy(text)
        return True
    except Exception:
        pass

    if sys.platform == "darwin" and shutil.which("pbcopy"):
        try:
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
            return True
        except Exception:
            return False

    if sys.platform.startswith("linux"):
        for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"]):
            if shutil.which(cmd[0]):
                try:
                    subprocess.run(cmd, input=text.encode("utf-8"), check=True)
                    return True
                except Exception:
                    continue

    if sys.platform == "win32" and shutil.which("clip"):
        try:
            subprocess.run(["clip"], input=text.encode("utf-16"), check=True)
            return True
        except Exception:
            return False

    return False


def _edit_in_editor(text: str) -> str:
    editor = os.environ.get("EDITOR") or ("notepad" if sys.platform == "win32" else "nano")
    if not shutil.which(editor.split()[0]):
        console.print(
            f"[yellow]Editor `{editor}` not found on PATH. Keeping prompt unchanged.[/yellow]"
        )
        return text

    tmp = tempfile.NamedTemporaryFile(
        prefix="resume-plan-", suffix=".md", delete=False, mode="w", encoding="utf-8"
    )
    try:
        tmp.write(text)
        tmp.close()
        subprocess.run([*editor.split(), tmp.name], check=False)
        return Path(tmp.name).read_text(encoding="utf-8").strip() or text
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _render_prompt(prompt: str) -> None:
    render_section("Claude prompt")
    render_paragraph(prompt)


def cmd_plan(args: argparse.Namespace) -> int:
    clear_terminal()
    console.print("[bold magenta]🧠 Thea | Planning[/bold magenta]")
    console.print("[dim italic]Let's design the prompt before we ask Claude.[/dim italic]")
    console.print()

    # Q1 — goal
    render_section("What are you trying to accomplish?")
    goal = _ask_free_text("Goal")
    if goal is None:
        console.print("[yellow]Cancelled.[/yellow]")
        return 0

    # Q2 — scope
    render_section("Where should the change happen?")
    scope_idx = select_option("scope", _SCOPE_OPTIONS)
    if scope_idx is None:
        console.print("[yellow]Cancelled.[/yellow]")
        return 0
    scope = _SCOPE_OPTIONS[scope_idx]
    if scope == "other":
        scope = _ask_scope_other()

    # Q3 — change type
    render_section("What kind of change is this?")
    change_idx = select_option("change_type", _CHANGE_OPTIONS)
    if change_idx is None:
        console.print("[yellow]Cancelled.[/yellow]")
        return 0
    change_type = _CHANGE_OPTIONS[change_idx]

    # Q4 — constraints (free text, skippable)
    render_section("Any constraints?")
    console.print(
        "[dim]Examples: minimal code changes · performance sensitive · "
        "experimental · quick fix. Press Enter to skip.[/dim]\n"
    )
    constraints = _ask_free_text("Constraints", allow_empty=True) or ""

    # Q5 — output style
    render_section("What should Claude produce?")
    output_idx = select_option("output_style", _OUTPUT_OPTIONS)
    if output_idx is None:
        console.print("[yellow]Cancelled.[/yellow]")
        return 0
    output_style = _OUTPUT_OPTIONS[output_idx]

    prompt = _build_prompt(
        goal=goal,
        scope=scope,
        change_type=change_type,
        constraints=constraints,
        output_style=output_style,
    )

    _render_prompt(prompt)

    while True:
        render_section("Now what?")
        choice = select_option(
            "plan_action",
            ["Copy prompt", "Edit prompt", "Cancel"],
        )
        if choice is None or choice == 2:
            console.print("[dim]Prompt discarded.[/dim]")
            return 0
        if choice == 0:
            if _copy_to_clipboard(prompt):
                console.print("[green]Copied to clipboard.[/green] Paste it into Claude Code.")
            else:
                console.print(
                    "[yellow]Clipboard unavailable.[/yellow] Select the prompt above "
                    "and copy manually."
                )
            return 0
        if choice == 1:
            prompt = _edit_in_editor(prompt)
            _render_prompt(prompt)
            continue
