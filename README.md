# Thea · Resume

```
🧠 Thea · using Resume
```

A CLI that helps you start and end the day well.

- `resume` — a **60-second spoken morning briefing** about what you were working on, what changed since, and what to do next.
- `resume today` — what you've shipped so far today.
- `resume wrap` — an end-of-day wrap that confirms the day and takes a note for tomorrow.
- `resume story` — group your recent commits into work threads, visualized as progress bars.

Thea, the assistant identity, narrates briefings with an energetic, encouraging female voice optimized for spoken delivery (~120 words, under a minute).

---

## Demo

```
$ resume

🧠 Thea is reconstructing your last session

   ✓  🔎 scanning git history
   ✓  🧩 rebuilding context
   ✓  🎧 preparing your briefing

── Morning briefing ──────────────────────────────────────
  Welcome back. Last time you shipped "retry backoff for
  the Stripe webhook", touching billing_service.py.

  Since then three new commits landed, including edits to
  payment_handler.py. Worth a quick scan before diving
  back in.

  Let's get going.

── Suggested next step ───────────────────────────────────
  Open billing_service.py and wire the new retry schedule
  into the webhook dispatcher.

Continue where you left off? (Y/n)
```

The briefing streams ChatGPT-style and — if an `ELEVENLABS_API_KEY` (or `OPENAI_API_KEY`) is set — plays through your speakers in parallel.

---

## Commands

| Command | What it does |
| --- | --- |
| `resume` | Morning briefing (default). Uses your last commit + everything since. Appends a dedicated "Suggested next step" block. |
| `resume today` | Tables of today's commits and files, plus a short recap. |
| `resume wrap` | Summarizes today, asks "is this correct?", then asks what to leave for tomorrow. Saves to `.resume/wrap.json`. |
| `resume story` | Clusters recent commits into 3–6 themes and prints a bar chart. Defaults to the last 30 commits by the current git user. |

Flags on `resume`:

| Flag | Effect |
| --- | --- |
| `--text` | Print the briefing instead of speaking it. |
| `--debug` | Print the raw git activity timeline as JSON. |
| `--no-stream` | Print the briefing all at once instead of char-by-char. |
| `--version` | Print the version. |

Flags on `resume story`:

| Flag | Effect |
| --- | --- |
| `--limit N` | How many recent commits to consider (default: 30). |
| `--all-authors` | Include commits from every author, not just you. |

---

## How it works

1. **Analyze git** — `git_analysis.py` finds your most recent commit, the files it touched, and every commit that has landed since. For `today` / `wrap` it scopes to commits authored today. For `story` it pulls the most recent N commits by the current user.
2. **Summarize** — `summarizer.py` sends the timeline to OpenAI with Thea's voice (energetic, encouraging, spoken, ≤120 words). Without an API key, deterministic templates take over so `--text` still works offline.
3. **Cluster** — `story.py` groups commits into themes via the LLM (when available) or by top-level directory.
4. **Stream** — `stream.py` types the briefing char-by-char, wrapped to a narrow column.
5. **Speak** — `tts.py` synthesizes audio via **ElevenLabs** (preferred) or OpenAI TTS (fallback) and plays it locally.
6. **Reopen** — `workspace.py` offers to open the last-edited file in VS Code.
7. **Remember** — `storage.py` persists wrap entries and their "note for tomorrow" to `.resume/wrap.json`. The next morning's briefing picks that note up and threads it into the summary and next-step suggestion.

---

## Install

From source:

```bash
git clone <this repo>
cd resume
pip install -e .
```

Set your keys:

```bash
# Preferred — ElevenLabs for a warm, expressive spoken voice.
export ELEVENLABS_API_KEY=sk_...
# Optional — override the default voice (Rachel). Try "AZnzlk1XvdvUeBnXmlld" (Domi) for more energy.
export ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM

# Required for text summaries; also the audio fallback if ElevenLabs isn't set.
export OPENAI_API_KEY=sk-...
```

Without any key, the LLM summary and audio are skipped — `--text` still prints a template-based briefing.

---

## Environment variables

| Var | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | Drives LLM summaries and is the audio fallback when ElevenLabs isn't configured. |
| `ELEVENLABS_API_KEY` | Enables ElevenLabs as the primary TTS backend. |
| `ELEVENLABS_VOICE_ID` | Override the default "Rachel" voice. |
| `ELEVENLABS_MODEL` | Override the default `eleven_turbo_v2_5` model. |

---

## Project layout

```
resume/
├── cli.py            # argparse + subcommand dispatch + startup sequence
├── git_analysis.py   # last-commit detection, today, timeline, recent commits
├── summarizer.py     # Thea voice prompts, next-step, story clustering LLM prompts
├── story.py          # cluster commits into threads + bar rendering
├── stream.py         # char-by-char narration-style printer
├── storage.py        # .resume/wrap.json persistence
├── tts.py            # ElevenLabs-first TTS with OpenAI fallback
├── workspace.py      # detect last-edited file + VS Code launch
└── utils.py          # shared console, brand header, startup runner, helpers
```

---

## Requirements

- Python 3.9+
- A git repository with at least one commit authored by the current `user.email`
- Optional: `ELEVENLABS_API_KEY` (preferred audio) or `OPENAI_API_KEY` (fallback audio + LLM summaries)
- Optional: the VS Code `code` command on `$PATH` (enables the reopen step)

---

## License

MIT
