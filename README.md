# Resume

> Thea — your 60-second developer briefing.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python: 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

Resume is a small CLI that reconstructs your last working session from git
history and reads it back to you in under a minute. Run it in the morning,
get a spoken briefing about what you were building, what changed since, and
where to pick up.

It's a ritual, not a dashboard.

```text
$ resume

🧠 Thea is reconstructing your last session

   ✓  scanning git history
   ✓  rebuilding context
   ✓  preparing your briefing

Status report.

──── Morning briefing ──────────────────────────────────────
  Last time you shipped "retry backoff for the Stripe
  webhook", touching billing_service.py.

  Since then three new commits landed, including edits to
  payment_handler.py — worth a quick scan before diving
  back in.

──── Suggested next step ───────────────────────────────────
  Wire the new retry schedule into the webhook dispatcher.
```

The briefing streams char-by-char and, with an `ELEVENLABS_API_KEY` (or
`OPENAI_API_KEY`), plays through your speakers in parallel.

---

## Install

```bash
pip install resume-cli
```

Or from source:

```bash
git clone https://github.com/Thea-Labs/resume-cli
cd resume-cli
pip install -e .
```

Set your keys (both optional — Resume falls back to text templates without
them):

```bash
export OPENAI_API_KEY=sk-...        # LLM summaries + fallback audio
export ELEVENLABS_API_KEY=sk_...    # preferred TTS
```

Then, in any git repository:

```bash
resume
```

The first run walks you through a one-time onboarding (your name, speech
speed, audio preference) and saves to `~/.thea/config.json`.

---

## The three rituals

| Command | When to run it |
| --- | --- |
| `resume` | Morning. Reconstructs your last session and reads it back. |
| `resume wrap` | End of day. Reviews today's commits, asks what tomorrow-you should know, saves it. |
| `resume plan` | Before sending a big prompt to Claude Code. Walks you through five questions and assembles a structured prompt. |

Flags on `resume`:

| Flag | Effect |
| --- | --- |
| `--text` | Print the briefing instead of speaking it. |
| `--instant` | Skip the streaming narration effect. |
| `--debug` | Print the raw git activity timeline as JSON. |
| `--version` | Print the version. |

---

## Advanced (hidden) commands

These are intentionally hidden from `resume --help` to keep the surface
minimal, but they're fully supported:

```bash
resume watch --setup        # pick teammates to follow
resume watch list           # show the watch list
resume watch add EMAIL
resume watch remove EMAIL

resume story                # cluster recent commits into work threads
resume story --all-authors
```

When a watch list is configured, the morning briefing gains a **Team
activity** section summarizing what teammates shipped while you were away.

Run `resume watch --help` or `resume story --help` for full documentation.

---

## How it works

1. **Analyze git** — finds your most recent commit, files it touched, and
   every commit landed since.
2. **Summarize** — sends the timeline to OpenAI with Thea's voice (status-
   report tone, ≤120 words). No key? Deterministic templates take over.
3. **Stream** — types the briefing char-by-char in a narrow column.
4. **Speak** — synthesizes via ElevenLabs (preferred) or OpenAI TTS and plays
   it locally while the text streams.
5. **Remember** — `resume wrap` persists tomorrow notes to `.resume/` at the
   repo root; the next morning's briefing threads them in.

---

## Environment variables

| Var | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | LLM summaries + fallback audio. |
| `ELEVENLABS_API_KEY` | Preferred TTS backend. |
| `ELEVENLABS_VOICE_ID` | Override the default "Rachel" voice. |
| `ELEVENLABS_MODEL` | Override the default `eleven_turbo_v2_5` model. |

---

## Requirements

- Python 3.9+
- A git repository with at least one commit by the current `user.email`
- Optional: ElevenLabs and/or OpenAI API keys
- Optional: VS Code `code` command on `$PATH` (enables the reopen step)

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). PRs welcome — keep the surface small.

## License

[MIT](LICENSE) © 2026 Antonio Krsoski
