"""`resume` command entry point.

Subcommands:
  resume          → morning briefing (default)
  resume wrap     → end-of-day review + note for tomorrow
  resume story    → cluster recent commits into work threads
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.prompt import Prompt

from . import __version__
from .git_analysis import (
    NotAGitRepo,
    build_diff_context,
    build_timeline,
    build_today,
    get_current_user,
    get_repo,
    recent_user_commits,
)
from .storage import latest_wrap, save_wrap
from .story import cluster_commits, render_threads
from .summarizer import (
    spoken_form,
    suggest_next_step,
    summarize,
    summarize_wrap,
)
from .tts import TTSUnavailable, play_async, synthesize
from .ui import (
    render_menu,
    render_paragraph,
    render_section,
)
from .utils import (
    console,
    get_openai_client,
    pick_analysis_label,
    pick_briefing_label,
    pick_context_title,
    pick_git_label,
    pick_greeting,
    print_header,
    run_startup,
)
from .workspace import (
    extract_file_path,
    last_edited_file,
    open_in_vscode,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="resume",
        description="Thea | Resume — a 60-second briefing on what you were working on.",
    )
    parser.add_argument("--version", action="version", version=f"resume {__version__}")
    parser.add_argument(
        "--text", action="store_true", help="Print the briefing instead of speaking it."
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print the raw git activity timeline and exit.",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Print the briefing all at once (no narration effect).",
    )

    sub = parser.add_subparsers(dest="command")
    sub.add_parser(
        "wrap",
        help="End-of-day wrap: review today's work and leave a note for tomorrow.",
    )
    story_parser = sub.add_parser(
        "story", help="Group recent commits into work threads with progress bars."
    )
    story_parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="How many recent commits to consider (default: 30).",
    )
    story_parser.add_argument(
        "--all-authors",
        action="store_true",
        help="Include commits from all authors, not just you.",
    )
    return parser


def _section(title: str) -> None:
    render_section(title)


def _repo_or_exit():
    try:
        repo = get_repo(Path.cwd())
    except NotAGitRepo as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)
    return repo


def _render_briefing(text: str, *, stream: bool) -> None:
    """Render a paragraph of narration, wrapped to the content column."""
    render_paragraph(text or "", stream=stream)


def _attach_prior_wrap(timeline: dict, repo_root: Path) -> dict:
    prior = latest_wrap(repo_root)
    if prior and prior.get("tomorrow_note"):
        timeline["yesterday_note"] = prior["tomorrow_note"]
    return timeline


def _prompt_choice(prompt_text: str, valid: set[str]) -> str:
    """Read a single-token input() answer, constrained to `valid`. Returns '' on abort."""
    try:
        raw = input(prompt_text).strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return ""
    return raw if raw in valid else ""


def _action_menu(
    *,
    next_step: str,
    timeline: dict,
    repo_root: Path,
    text_only: bool,
) -> int:
    """Render the post-briefing action menu and dispatch on the choice."""
    _section("What would you like to do?")
    render_menu([
        "Continue where you left off",
        "Follow suggested step",
        "Skip",
    ])

    choice = _prompt_choice("> ", {"1", "2", "3"})

    if choice == "1":
        return _action_continue(timeline, repo_root)
    if choice == "2":
        return _action_follow_step(next_step, repo_root)

    console.print("\nContext loaded.")
    return 0


def _action_continue(timeline: dict, repo_root: Path) -> int:
    target = last_edited_file(timeline, repo_root)
    if target is None:
        console.print("\n[dim]No last-edited file detected on disk to reopen.[/dim]")
        return 0

    console.print(
        f"\nThea located your most recently edited file: "
        f"[bold]{target.relative_to(repo_root)}[/bold]"
    )
    answer = _prompt_choice("Open in VS Code? (y/n): ", {"y", "n", "yes", "no"})
    if answer not in {"y", "yes"}:
        return 0

    if open_in_vscode(target, repo_root=repo_root):
        console.print(f"[green]Opened {target.name} in VS Code.[/green]")
    else:
        console.print(
            "[yellow]VS Code `code` command not found on PATH.[/yellow] "
            f"File to open: [bold]{target}[/bold]"
        )
    return 0


def _action_follow_step(next_step: str, repo_root: Path) -> int:
    console.print("\n🧠 Thea is preparing that context...")

    candidate = extract_file_path(next_step, repo_root=repo_root)
    if candidate is None:
        console.print("[dim]No specific file referenced in the suggested step.[/dim]")
        return 0

    absolute = candidate if candidate.is_absolute() else (repo_root / candidate).resolve()

    if not absolute.exists():
        console.print(
            f"[yellow]Referenced file not found on disk:[/yellow] "
            f"[bold]{candidate}[/bold]"
        )
        return 0

    try:
        rel = absolute.relative_to(repo_root)
    except ValueError:
        rel = absolute

    console.print(f"\nOpening [bold]{rel}[/bold]")
    if not open_in_vscode(absolute, repo_root=repo_root):
        console.print(
            "[yellow]VS Code `code` command not found on PATH.[/yellow] "
            f"File to open: [bold]{absolute}[/bold]"
        )
    return 0


def cmd_briefing(args: argparse.Namespace) -> int:
    print_header()
    console.print(f"[italic]{pick_greeting()}[/italic]\n")

    repo = _repo_or_exit()
    repo_root = Path(repo.working_tree_dir or Path.cwd())
    client = get_openai_client()
    want_audio = not args.text

    state: dict = {}

    def _scan() -> dict:
        state["timeline"] = build_timeline(repo)
        return state["timeline"]

    def _context() -> dict:
        state["timeline"] = _attach_prior_wrap(state["timeline"], repo_root)
        state["timeline"].update(build_diff_context(repo_root))
        return state["timeline"]

    def _prepare() -> dict:
        timeline = state["timeline"]
        briefing = summarize(timeline, client=client)
        next_step = suggest_next_step(timeline, client=client)
        audio_path = None
        audio_error = None
        if want_audio:
            try:
                audio_path = synthesize(spoken_form(briefing))
            except TTSUnavailable as exc:
                audio_error = str(exc)
        state["briefing"] = briefing
        state["next_step"] = next_step
        state["audio_path"] = audio_path
        state["audio_error"] = audio_error
        return state

    try:
        run_startup(
            pick_context_title(),
            [
                (pick_git_label(), _scan),
                (pick_analysis_label(), _context),
                (pick_briefing_label(), _prepare),
            ],
        )
    except Exception as exc:
        console.print(f"[red]Startup failed:[/red] {exc}")
        return 1

    timeline = state["timeline"]

    if args.debug:
        _section("Git activity timeline")
        console.print_json(json.dumps(timeline, default=str))
        return 0

    last = timeline.get("last_user_commit")
    if last is None:
        email = timeline.get("user", {}).get("email") or "<unset>"
        console.print(
            f"[yellow]No commits by the current git user ({email}) were found.[/yellow]\n"
            f"Make a commit first, then run [bold]resume[/bold] again."
        )
        return 0

    audio_thread = None
    if want_audio:
        if state.get("audio_path"):
            audio_thread = play_async(state["audio_path"])
        elif state.get("audio_error"):
            console.print(f"[yellow]Audio unavailable:[/yellow] {state['audio_error']}")

    _section("Morning briefing")
    _render_briefing(state["briefing"], stream=not args.no_stream)

    _section("Suggested next step")
    _render_briefing(state["next_step"], stream=not args.no_stream)

    if audio_thread is not None:
        audio_thread.join()

    return _action_menu(
        next_step=state["next_step"],
        timeline=timeline,
        repo_root=repo_root,
        text_only=args.text,
    )


def cmd_wrap(args: argparse.Namespace) -> int:
    print_header("Thea is wrapping up your day...")

    repo = _repo_or_exit()
    repo_root = Path(repo.working_tree_dir or Path.cwd())
    today = build_today(repo)

    _section("Today's work")

    if not (today.get("commits") or []):
        console.print("[yellow]No commits today — nothing to wrap.[/yellow]")
        return 0

    client = get_openai_client()
    with console.status("[bold magenta]Drafting the wrap...", spinner="dots"):
        draft = summarize_wrap(today, client=client)
    render_paragraph(draft)

    _section("Note for tomorrow")
    try:
        tomorrow_note = Prompt.ask(
            "[magenta]Thea[/magenta] › What should tomorrow-you know?",
            default="",
        )
    except (EOFError, KeyboardInterrupt):
        console.print()
        return 0

    saved_to = save_wrap(
        repo_root,
        confirmed_summary=draft,
        tomorrow_note=tomorrow_note.strip(),
        today=today,
    )
    console.print(
        f"\n[green]Saved to[/green] [dim]{saved_to.relative_to(repo_root)}[/dim]"
    )
    if tomorrow_note.strip():
        console.print("[dim]Tomorrow's briefing will reference this note.[/dim]")
    return 0


def cmd_story(args: argparse.Namespace) -> int:
    print_header("Thea is mapping your work threads...")

    repo = _repo_or_exit()
    name, email = get_current_user(repo)

    if getattr(args, "all_authors", False):
        commits = []
        for commit in repo.iter_commits(max_count=args.limit):
            from .git_analysis import _commit_dict

            commits.append(_commit_dict(commit))
    else:
        commits = recent_user_commits(repo, email, limit=args.limit)

    if not commits:
        console.print(
            f"[yellow]No commits found for {email or 'the current user'}.[/yellow] "
            f"Try [bold]resume story --all-authors[/bold]."
        )
        return 0

    client = get_openai_client()
    with console.status(
        "[bold magenta]Clustering commits into threads...", spinner="dots"
    ):
        threads = cluster_commits(commits, client=client)

    _section("Work threads")
    render_threads(threads, total_commits=len(commits))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)

    if argv and argv[0] == "today":
        console.print(
            "This command has been merged into [bold]resume wrap[/bold].\n"
            "Run [bold]resume wrap[/bold] to review today's work."
        )
        return 0
    if argv and argv[0] == "session":
        console.print(
            "[bold]resume[/bold] now automatically reconstructs your last session.\n"
            "Just run [bold]resume[/bold]."
        )
        return 0

    parser = _build_parser()
    args = parser.parse_args(argv)

    command = getattr(args, "command", None)
    if command == "wrap":
        return cmd_wrap(args)
    if command == "story":
        return cmd_story(args)
    return cmd_briefing(args)


if __name__ == "__main__":
    sys.exit(main())
