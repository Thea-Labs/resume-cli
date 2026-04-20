"""Pure temporal clustering of commits into working sessions.

A session is a contiguous burst of commits where each consecutive pair is
within `gap_minutes` of the next. A gap larger than that threshold starts
a new session.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional


def _parse_date(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def cluster_by_gap(commits: list[dict], gap_minutes: int = 90) -> list[list[dict]]:
    """Split commits (newest-first) into sessions.

    Two consecutive commits belong to the same session if their authored
    timestamps are within `gap_minutes`. A larger gap — or an unparseable
    date — begins a new session.
    """
    if not commits:
        return []

    gap_seconds = gap_minutes * 60
    clusters: list[list[dict]] = [[commits[0]]]
    prev_dt = _parse_date(commits[0].get("date"))

    for commit in commits[1:]:
        cur_dt = _parse_date(commit.get("date"))
        new_session = (
            prev_dt is None
            or cur_dt is None
            or abs((prev_dt - cur_dt).total_seconds()) > gap_seconds
        )
        if new_session:
            clusters.append([commit])
        else:
            clusters[-1].append(commit)
        prev_dt = cur_dt

    return clusters


def most_recent_session(commits: list[dict], gap_minutes: int = 90) -> list[dict]:
    """Return the first (newest) cluster, or [] if there are no commits."""
    clusters = cluster_by_gap(commits, gap_minutes=gap_minutes)
    return clusters[0] if clusters else []
