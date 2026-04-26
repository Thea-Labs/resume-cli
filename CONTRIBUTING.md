# Contributing to Resume

Thanks for considering a contribution. Resume is small and opinionated, so the
bar for "good change" is: does it make the morning briefing feel sharper, more
useful, or less in the way?

## Setup

```bash
git clone https://github.com/Thea-Labs/resume-cli
cd resume-cli
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env  # fill in keys you have
```

You should now be able to run `resume`, `resume wrap`, and `resume plan` from
inside any git repository on your machine.

## Pull requests

- One focused change per PR. Refactors and feature work should not be mixed.
- Keep dependencies minimal — Resume is meant to feel light.
- Match the existing CLI tone: calm, terse, no exclamation points, no praise.
- If you change user-facing behavior, update `README.md` in the same PR.

## Filing issues

- Bugs: include the command you ran, what you expected, and what happened. A
  redacted snippet of the briefing output usually helps.
- Feature ideas: describe the daily ritual it improves, not just the
  mechanism. Resume's design center is the morning/evening rhythm.

## Code style

- Python 3.9+. Type hints where they aid readability.
- Default to no comments. Add one only when the *why* is non-obvious.
- Keep functions short; reach for the existing helpers in `resume/ui/` and
  `resume/utils.py` before adding new ones.
