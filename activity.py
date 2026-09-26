"""Commit activity of project repositories, for the GitHub-style heatmaps.

The build asks the GitHub REST API for the commits of the past year on each
project's default branch, caches their dates in ``.cache/activity/``, and turns
them into a grid of weeks x weekdays with an intensity level per day.

The API is used rather than the local clones because those are shallow (one
commit deep) on purpose. Anonymous calls are limited to 60 an hour, plenty for a
handful of projects; in CI the workflow passes ``GITHUB_TOKEN`` to lift it.
A failed fetch never fails the build: the project simply shows no heatmap.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

WEEKS = 53                         # a full year, like GitHub's contribution graph
RECENT_DAYS = 30                   # the rolling month that orders the projects
MAX_PAGES = 10                     # 1000 commits a year is more than enough
FRESH_FOR = dt.timedelta(hours=6)  # reuse a cached fetch this recent


def _log(msg: str) -> None:
    print(f"  {msg}")


def _get(url: str) -> list:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "lucastabary.github.io-build",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as resp:
        return json.load(resp)


def _fetch(repo: str, since: dt.date) -> list[str]:
    """ISO author dates of every commit on the default branch since ``since``."""
    stamps: list[str] = []
    for page in range(1, MAX_PAGES + 1):
        batch = _get(f"https://api.github.com/repos/{repo}/commits"
                     f"?since={since.isoformat()}T00:00:00Z&per_page=100&page={page}")
        stamps += [c["commit"]["author"]["date"] for c in batch
                   if c.get("commit", {}).get("author", {}).get("date")]
        if len(batch) < 100:
            break
    return stamps


def commit_dates(repo: str, cache_dir: Path, refresh: bool, offline: bool,
                 today: dt.date) -> list[dt.date] | None:
    """Commit dates of the past year, from the cache when it is recent enough."""
    cache = cache_dir / f"{repo.replace('/', '__')}.json"
    cached = None
    if cache.is_file():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = None

    def dates(data: dict) -> list[dt.date]:
        return [dt.datetime.fromisoformat(s.replace("Z", "+00:00")).date() for s in data["commits"]]

    if cached:
        age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(cached["fetched_at"])
        if offline or (age < FRESH_FOR and not refresh):
            return dates(cached)
    if offline:
        _log(f"! no cached activity for {repo} and --offline is set — no heatmap")
        return None

    try:
        stamps = _fetch(repo, today - dt.timedelta(weeks=WEEKS))
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        reason = getattr(exc, "code", None) or exc.__class__.__name__
        _log(f"! could not fetch the activity of {repo} ({reason})"
             + (" — using the cached one" if cached else " — no heatmap"))
        return dates(cached) if cached else None

    data = {"fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(), "commits": stamps}
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data), encoding="utf-8")
    return dates(data)


def _levels(counts: list[int]) -> list[float]:
    """Thresholds for levels 1-4: quartiles of the non-zero days, like GitHub.

    Quantiles rather than a linear scale, so one burst day does not wash every
    other day out to the palest shade.
    """
    busy = sorted(c for c in counts if c > 0)
    if not busy:
        return [1, 1, 1, 1]
    return [busy[min(len(busy) - 1, int(q * len(busy)))] for q in (0.0, 0.25, 0.5, 0.75)]


def grid(dates: list[dt.date], today: dt.date, weeks: int = WEEKS) -> dict:
    """Weeks (Monday first) x 7 days, each day with its count and level 0-4.

    ``weeks`` is a list of ``{"days": [7 cells], "total": n}``; a cell is None for
    the days of the current week still to come.
    """
    per_day: dict[dt.date, int] = {}
    for day in dates:
        per_day[day] = per_day.get(day, 0) + 1

    start = today - dt.timedelta(days=today.weekday()) - dt.timedelta(weeks=weeks - 1)
    days = [start + dt.timedelta(days=i) for i in range(weeks * 7)]
    in_range = [per_day.get(d, 0) for d in days if d <= today]
    thresholds = _levels(in_range)

    columns = []
    months = []
    for w in range(weeks):
        column = []
        for d in days[w * 7:(w + 1) * 7]:
            if d > today:
                column.append(None)        # the rest of the current week
                continue
            count = per_day.get(d, 0)
            level = 0 if count == 0 else sum(count >= t for t in thresholds)
            column.append({"date": d.isoformat(), "label": d.strftime("%d %b %Y").lstrip("0"),
                           "count": count, "level": level})
        columns.append({"days": column, "total": sum(c["count"] for c in column if c)})
        # Label a column when its week holds the 1st of a month, unless the
        # previous label is too close to leave room for this one.
        month_start = next((d for d in days[w * 7:(w + 1) * 7] if d.day == 1), None)
        if month_start and (not months or w - months[-1]["week"] >= 3):
            months.append({"week": w, "label": month_start.strftime("%b")})

    total = sum(in_range)
    last = max((d for d in dates if d <= today), default=None)
    month_start = today - dt.timedelta(days=RECENT_DAYS - 1)
    return {
        "recent": sum(1 for d in dates if month_start <= d <= today),
        "last_date": last,
        "weeks": columns,
        "months": months,
        "total": total,
        "active_days": sum(1 for c in in_range if c),
        "last": last.strftime("%d %B %Y").lstrip("0") if last else None,
    }
