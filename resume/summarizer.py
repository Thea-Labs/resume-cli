"""LLM-backed briefing generator with an offline template fallback.

Thea's voice: energetic, encouraging, natural spoken language, a touch motivational.
All briefings are <=120 words so they fit comfortably inside 60 seconds of speech.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from .utils import clamp_words

_PATH_TOKEN_RE = re.compile(
    r"(?<![\w/:])(?:[A-Za-z0-9_.\-\[\]]+/)+([A-Za-z0-9_.\-\[\]]+\.[A-Za-z0-9]{1,6})\b"
)


def spoken_form(text: str) -> str:
    """Rewrite text for TTS: collapse file paths to basenames.

    `app/[userId]/page.tsx` → `page.tsx`. URLs and `and/or`-style tokens are
    left alone — if the containing whitespace-delimited token has `://` in it,
    we treat it as a URL and skip the match.
    """
    if not text:
        return text

    def _replace(match: re.Match) -> str:
        start = match.start()
        # Walk back to the nearest whitespace; if that surrounding token
        # contains "://", this is a URL — leave it alone.
        token_start = start
        while token_start > 0 and not text[token_start - 1].isspace():
            token_start -= 1
        if "://" in text[token_start : match.end()]:
            return match.group(0)
        return match.group(1)

    return _PATH_TOKEN_RE.sub(_replace, text)

DEFAULT_MODEL = "gpt-4o-mini"
MAX_WORDS = 120

THEA_VOICE = (
    "You are Thea, a calm technical colleague giving a standup-style update to an "
    "experienced engineer. Your output is spoken aloud, so use natural conversational "
    "prose — no markdown, no bullets, no emoji, no code fences, no headings. "
    "Tone: direct, precise, matter-of-fact. You are informing, not cheering. "
    "\n\n"
    "WRITE AT THE LEVEL OF INTENT, NOT IMPLEMENTATION. "
    "Describe what the developer was trying to accomplish, what system or feature "
    "changed, and what the impact is. Think 'added session reconstruction', not "
    "'modified session_cluster.py and session_analyzer.py'. "
    "\n\n"
    "Hard rules — DO NOT: "
    "list file paths; "
    "name more than one file, and only if the change is truly single-file and naming "
    "it adds meaning; "
    "enumerate directories, imports, functions, or line numbers; "
    "turn the summary into a diff walkthrough; "
    "use exclamation points; "
    "use motivational phrases ('you've got this', 'let's', 'keep the momentum', "
    "'great work', 'nice job'); "
    "praise the developer or their code; "
    "use filler ('now', 'alright', 'okay'); "
    "editorialize about whether something is good, smooth, or exciting. "
    "\n\n"
    "Keep it tight: 2–4 sentences. Under 90 words. Think 'what were you building?' — "
    "answer that, then stop."
)

MORNING_USER_TEMPLATE = """Given this git activity timeline — INCLUDING actual diff \
content — write a standup-style morning briefing for a developer returning to work.

Read the diffs, staged changes, and unstaged changes to infer INTENT — what feature \
or system was the developer building, fixing, or refactoring? Summarize at that \
level. Do not narrate file paths, imports, or line-by-line changes.

Cover in 2–4 sentences of flowing prose:
  - the feature or system that was being worked on, framed as intent/outcome
  - the impact of that change (what is now possible, better, or fixed)
  - any uncommitted work still in progress, described as "still finishing X", not "edits in <path>"
  - if a "yesterday_note" is present, surface its substance

Start with "Welcome back." End on a technical sentence — no motivational closers. \
If nothing meaningful is in progress, stop early.

TIMELINE (JSON — includes last_commit, last_commit_diff, staged_changes, \
unstaged_changes, git_status):
{timeline_json}
"""

TODAY_USER_TEMPLATE = """Summarize what the developer SHIPPED today at the level of \
features and systems, not files. Think standup update: "added X", "refactored Y", \
"fixed Z". 2–3 sentences, factual prose. Do not list file paths. End with one \
sentence describing the day's shape (e.g. "A day mostly on the CLI output layer.").

TODAY (JSON):
{today_json}
"""

WRAP_USER_TEMPLATE = """Write a short end-of-day wrap for the developer based on today's git \
activity. One short prose sentence naming the overall theme of the day, then a \
bulleted recap with 2–4 bullets. Format exactly:

Here's what I observed today:
• <feature or system-level observation>
• <another observation>

Each bullet names a FEATURE or SYSTEM that changed — e.g. "Added session \
reconstruction", "Improved CLI rendering". No file paths. No directory names. \
No commit subjects verbatim. Under 14 words per bullet. No headings, no emoji \
beyond the bullet character.

TODAY (JSON):
{today_json}
"""

NEXT_STEP_SYSTEM = (
    "You are Thea. Propose ONE concrete next step for an experienced developer, "
    "in 1–2 crisp sentences (max 30 words). Phrase it at the level of feature or "
    "behavior — what to build, finish, verify, or fix — not which file to edit. "
    "Name at most one file, and only if it's the single obvious target. "
    "No greeting, no filler, no markdown, no bullets, no exclamation points, "
    "no motivational phrases ('let's', 'you've got this', 'keep going', 'great'). "
    "Just the step."
)

NEXT_STEP_USER_TEMPLATE = """Based on this git timeline — including the actual diff \
content, staged/unstaged changes, and git status — what is the single most useful \
next step? Infer intent from the diffs. Prefer steps that finish work visibly in \
progress over starting something new. Frame the step as an outcome ("finish the \
session summary rendering", "verify the new UI wraps correctly") rather than as a \
file edit. If a "yesterday_note" is present, let it steer the suggestion.

TIMELINE (JSON — includes last_commit, last_commit_diff, staged_changes, \
unstaged_changes, git_status):
{timeline_json}
"""

STORY_SYSTEM = (
    "You are Thea. You group a developer's recent commits into 3–6 short work threads. "
    "Respond with STRICT JSON only — an array of objects, no prose, no markdown. Each "
    "object has two keys: `theme` (a short 2–4 word label like \"Billing retry logic\") "
    "and `commit_indices` (a list of integer indices into the input commits array). "
    "Every input commit index must appear in exactly one group."
)

STORY_USER_TEMPLATE = """Group these commits into 3–6 coherent work threads. Use short \
human-readable theme labels.

COMMITS (JSON array, index = position):
{commits_json}

Respond with JSON only.
"""

SESSION_SYSTEM = (
    "You are Thea, a calm technical colleague describing a developer's most recent "
    "continuous working session — a single burst of commits. "
    "Respond with STRICT JSON only — no prose, no markdown, no code fences. Shape: "
    "{\"focus\": str, \"summary\": str, \"next_step\": str}. "
    "\n\n"
    "`focus` = 3–8 word label naming the FEATURE or SYSTEM worked on (e.g. "
    "\"Session reconstruction\", \"CLI rendering\", \"Billing retry logic\"). Never a "
    "commit subject or file path. "
    "`summary` = 2–4 sentences at the level of intent and impact — what the developer "
    "was building or fixing and what that change enables. Standup tone. No file paths, "
    "no directory names, no diff walkthroughs. Flowing prose, no bullets. "
    "`next_step` = one concrete sentence describing what to do next as an outcome, "
    "not as 'open file X'. "
    "\n\n"
    "Hard rules across all three fields: never list file paths; name at most one file, "
    "and only when the change is genuinely single-file; no exclamation points; no "
    "motivational phrases ('you've got this', 'let's', 'keep going', 'great job'); "
    "no praise; no filler; no editorializing. Just the work."
)

SESSION_USER_TEMPLATE = """Summarize this working session at the level of features and \
systems. Read the commit messages and stat snippets to infer what was actually being \
built or fixed — then describe that, not the files that moved. Prefer the most recent \
commits when deciding the suggested next step.

SESSION (JSON):
{session_json}

Respond with JSON only.
"""


def suggest_next_step(timeline: dict, client=None, model: str = DEFAULT_MODEL) -> str:
    """Generate a single concrete next-step suggestion (≤35 words)."""
    if client is None:
        return _next_step_template(timeline)

    prompt = NEXT_STEP_USER_TEMPLATE.format(timeline_json=json.dumps(_shrink(timeline), indent=2))
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": NEXT_STEP_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
        )
        text = (response.choices[0].message.content or "").strip()
    except Exception:
        text = ""
    if not text:
        text = _next_step_template(timeline)
    return clamp_words(text, max_words=40)


def summarize_story(commits: list[dict], client=None, model: str = DEFAULT_MODEL) -> list[dict]:
    """Ask the LLM to group commits into themes. Returns list of {theme, commit_indices}.

    Returns [] on any failure — caller should fall back to the heuristic path.
    """
    if client is None or not commits:
        return []

    trimmed = [
        {
            "index": i,
            "message": (c.get("message") or "")[:120],
            "files": (c.get("files") or [])[:6],
        }
        for i, c in enumerate(commits)
    ]
    prompt = STORY_USER_TEMPLATE.format(commits_json=json.dumps(trimmed, indent=2))

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": STORY_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        raw = (response.choices[0].message.content or "").strip()
    except Exception:
        return []

    return _parse_story_response(raw, len(commits))


def _parse_story_response(raw: str, commit_count: int) -> list[dict]:
    """Defensively parse a JSON array of {theme, commit_indices}."""
    if not raw:
        return []
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        parsed = json.loads(raw[start : end + 1])
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    clean: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        theme = str(item.get("theme") or "").strip()
        raw_idx = item.get("commit_indices") or []
        if not isinstance(raw_idx, list):
            continue
        indices = [int(i) for i in raw_idx if isinstance(i, (int, float)) and 0 <= int(i) < commit_count]
        if theme and indices:
            clean.append({"theme": theme, "commit_indices": indices})
    return clean


def summarize_session(session: dict, client=None, model: str = DEFAULT_MODEL) -> dict:
    """Return {focus, summary, next_step} for the given session context."""
    if not session or not session.get("commit_count"):
        return _session_template(session)
    if client is None:
        return _session_template(session)

    prompt = SESSION_USER_TEMPLATE.format(
        session_json=json.dumps(_shrink_session(session), indent=2)
    )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SESSION_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        raw = (response.choices[0].message.content or "").strip()
    except Exception:
        raw = ""

    parsed = _parse_session_response(raw)
    return parsed or _session_template(session)


def _parse_session_response(raw: str) -> Optional[dict]:
    if not raw:
        return None
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(raw[start : end + 1])
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    focus = str(parsed.get("focus") or "").strip()
    summary = str(parsed.get("summary") or "").strip()
    next_step = str(parsed.get("next_step") or "").strip()
    if not (focus and summary and next_step):
        return None
    return {"focus": focus, "summary": summary, "next_step": next_step}


def _shrink_session(session: dict, max_snippets: int = 6, max_files: int = 12) -> dict:
    s = dict(session)
    snippets = s.get("diff_snippets") or []
    s["diff_snippets"] = [
        {**snip, "diff": _cap(snip.get("diff", ""))}
        for snip in snippets[:max_snippets]
    ]
    files = s.get("files_touched") or []
    if len(files) > max_files:
        s["files_touched"] = files[:max_files]
    commits = s.get("commits") or []
    s["commits"] = [
        {k: (v[:max_files] if k == "files" and isinstance(v, list) else v)
         for k, v in c.items()}
        for c in commits
    ]
    return s


def _session_template(session: dict) -> dict:
    """Deterministic fallback when no LLM or the call failed."""
    commits = (session or {}).get("commits") or []
    files = (session or {}).get("files_touched") or []

    if not commits:
        return {
            "focus": "No recent session",
            "summary": "No recent commits by the current git user were found to reconstruct.",
            "next_step": "Make a small commit and run resume session again.",
        }

    latest = commits[0]
    latest_msg = latest.get("message") or "your last change"
    focus = latest_msg if len(latest_msg) <= 60 else latest_msg[:57] + "..."

    n = len(commits)
    file_mention = ", ".join(files[:3]) if files else "a few files"
    summary = (
        f"{n} commit{'s' if n != 1 else ''} in this session, touching {file_mention}. "
        f"Latest: \"{latest_msg}\"."
    )

    target = files[0] if files else (latest.get("files") or ["the last touched file"])[0]
    next_step = f"Open {target} and continue from \"{latest_msg}\"."

    return {"focus": focus, "summary": summary, "next_step": next_step}


def _next_step_template(timeline: dict) -> str:
    yesterday = timeline.get("yesterday_note")
    if yesterday:
        return f"Pick up on yesterday's note: {yesterday}."

    last = timeline.get("last_user_commit") or {}
    files = last.get("files") or []
    if files:
        target = files[0]
        return f"Open {target} and keep moving on \"{last.get('message', 'your last change')}\"."

    return "Pick one small change, make one commit, and let momentum build from there."


def summarize(timeline: dict, client=None, model: str = DEFAULT_MODEL) -> str:
    """Produce the morning briefing from a timeline dict."""
    if client is None:
        return _morning_template(timeline)

    prompt = MORNING_USER_TEMPLATE.format(timeline_json=json.dumps(_shrink(timeline), indent=2))
    text = _chat(client, model, prompt) or _morning_template(timeline)
    return clamp_words(text, max_words=MAX_WORDS)


def summarize_today(today: dict, client=None, model: str = DEFAULT_MODEL) -> str:
    """Produce a short upbeat recap of today's commits."""
    if client is None:
        return _today_template(today)

    prompt = TODAY_USER_TEMPLATE.format(today_json=json.dumps(_shrink_today(today), indent=2))
    text = _chat(client, model, prompt) or _today_template(today)
    return clamp_words(text, max_words=MAX_WORDS)


def summarize_wrap(today: dict, client=None, model: str = DEFAULT_MODEL) -> str:
    """Produce the bulleted end-of-day wrap."""
    if client is None:
        return _wrap_template(today)

    prompt = WRAP_USER_TEMPLATE.format(today_json=json.dumps(_shrink_today(today), indent=2))
    text = _chat(client, model, prompt) or _wrap_template(today)
    return text.strip()


def _chat(client, model: str, user_prompt: str) -> Optional[str]:
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": THEA_VOICE},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
        )
        return (response.choices[0].message.content or "").strip() or None
    except Exception:
        return None


_DIFF_MAX_CHARS = 4500  # secondary cap; upstream diff.py already truncates


def _cap(text: object, max_chars: int = _DIFF_MAX_CHARS) -> str:
    if not isinstance(text, str) or not text:
        return "" if text is None else str(text or "")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n…[truncated, {len(text) - max_chars} chars elided]"


def _shrink(timeline: dict, max_commits: int = 10, max_files: int = 8) -> dict:
    t = dict(timeline)
    commits_since = t.get("commits_since") or []
    t["commits_since"] = [
        {k: v for k, v in c.items() if k != "sha"} for c in commits_since[:max_commits]
    ]
    files_changed = t.get("files_changed_since") or {}
    if len(files_changed) > max_files:
        t["files_changed_since"] = dict(list(files_changed.items())[:max_files])
    if t.get("last_user_commit"):
        lc = dict(t["last_user_commit"])
        lc.pop("sha", None)
        lc["files"] = (lc.get("files") or [])[:max_files]
        t["last_user_commit"] = lc

    # Diff fields added by git_analysis.build_diff_context — cap defensively
    # so a single oversized prompt can't blow out the token budget.
    for key in ("last_commit_diff", "staged_changes", "unstaged_changes", "git_status"):
        if key in t:
            t[key] = _cap(t[key])
    if t.get("last_commit"):
        lc = dict(t["last_commit"])
        lc.pop("hash", None)
        lc["files_changed"] = (lc.get("files_changed") or [])[:max_files]
        t["last_commit"] = lc

    return t


def _shrink_today(today: dict, max_commits: int = 12, max_files: int = 10) -> dict:
    t = dict(today)
    commits = t.get("commits") or []
    t["commits"] = [
        {k: v for k, v in c.items() if k != "sha"} for c in commits[:max_commits]
    ]
    files = t.get("files_changed") or {}
    if len(files) > max_files:
        t["files_changed"] = dict(list(files.items())[:max_files])
    return t


def _morning_template(timeline: dict) -> str:
    last: Optional[dict] = timeline.get("last_user_commit")
    since = timeline.get("commits_since") or []
    changed: dict = timeline.get("files_changed_since") or {}
    yesterday = timeline.get("yesterday_note")

    if last is None:
        return (
            "Welcome back.\n\n"
            "I don't see any recent commits by you in this repository yet, so there's "
            "nothing to reconstruct — but that also means a clean runway.\n\n"
            "Pick a small first commit to get momentum going."
        )

    files = last.get("files") or []
    file_mention = files[0] if files else "a few files"
    subject = last.get("message") or "your last change"

    # Paragraph 1: welcome + what you shipped
    p1 = [
        "Welcome back.",
        f"Last time you shipped \"{subject}\", touching {file_mention}.",
    ]
    if len(files) > 1:
        p1.append(f"That commit moved {len(files)} files.")

    # Paragraph 2: what's changed since
    if since:
        n = len(since)
        top = list(changed.keys())[:2]
        if top:
            joined = " and ".join(top)
            p2 = (
                f"Since then {n} new commit{'s' if n != 1 else ''} landed, including "
                f"edits to {joined}. Worth a quick scan before diving back in."
            )
        else:
            p2 = (
                f"Since then {n} new commit{'s' if n != 1 else ''} landed. "
                f"Worth a quick scan before diving back in."
            )
    else:
        p2 = "Nothing new has landed since, so the field is yours."

    paragraphs = [" ".join(p1), p2]

    # Paragraph 3: yesterday's note (optional)
    if yesterday:
        paragraphs.append(f"Your note from yesterday: {yesterday}.")

    return clamp_words("\n\n".join(paragraphs), max_words=MAX_WORDS)


def _today_template(today: dict) -> str:
    commits = today.get("commits") or []
    files = today.get("files_changed") or {}
    if not commits:
        return "No commits yet today — a blank canvas. Pick one small thing and start the streak."

    n = len(commits)
    top = list(files.keys())[:3]
    joined = ", ".join(top) if top else "a handful of files"
    return clamp_words(
        f"{n} commit{'s' if n != 1 else ''} today, across {joined}. "
        f"Latest: \"{commits[0].get('message', '')}\".",
        max_words=MAX_WORDS,
    )


def _wrap_template(today: dict) -> str:
    commits = today.get("commits") or []
    files = today.get("files_changed") or {}
    if not commits:
        return "Here's what I observed today:\n• No commits yet — tomorrow's a fresh start."

    bullets = []
    for path in list(files.keys())[:3]:
        bullets.append(f"• You made changes in {path}")
    if commits:
        bullets.append(f"• Latest commit: \"{commits[0].get('message', '')}\"")

    return "Here's what I observed today:\n" + "\n".join(bullets)
