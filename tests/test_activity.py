"""Commit activity: the yearly heatmap grid, the lifetime series, the cache."""

from __future__ import annotations

import datetime as dt
import json

import activity

TODAY = dt.date(2026, 9, 24)            # a Thursday


def days_ago(*offsets: int) -> list[dt.date]:
    return [TODAY - dt.timedelta(days=o) for o in offsets]


def test_grid_shape_and_future_days():
    g = activity.grid([], TODAY)
    assert len(g["weeks"]) == activity.WEEKS
    last_week = g["weeks"][-1]["days"]
    # Monday..Thursday are real days, Friday..Sunday have not happened yet.
    assert [d is None for d in last_week] == [False] * 4 + [True] * 3
    assert g["total"] == 0 and g["last"] is None


def test_grid_counts_recent_and_levels():
    dates = days_ago(0, 0, 0, 1, 40, 400)       # 400 days ago is outside the year
    g = activity.grid(dates, TODAY)
    assert g["total"] == 5
    assert g["recent"] == 4                      # the 30-day window
    assert g["last_date"] == TODAY
    cells = {c["date"]: c for w in g["weeks"] for c in w["days"] if c}
    assert cells[TODAY.isoformat()]["count"] == 3
    # The busiest day gets the top level; any busy day at least level 1.
    assert cells[TODAY.isoformat()]["level"] == 4
    assert all(c["level"] >= 1 for c in cells.values() if c["count"])


def test_levels_are_quartiles_of_busy_days():
    assert activity._levels([0, 0]) == [1, 1, 1, 1]
    assert activity._levels([0, 1, 2, 3, 4]) == [1, 2, 3, 4]


def test_lifetime_spans_first_commit_to_today():
    first = dt.date(2026, 3, 9)                  # a Monday
    life = activity.lifetime([first, first, TODAY, TODAY + dt.timedelta(days=3)], TODAY)
    assert life["weeks"][0]["total"] == 2
    assert life["weeks"][-1]["total"] == 1       # the future commit is ignored
    assert life["span_weeks"] == len(life["weeks"]) == (TODAY - first).days // 7 + 1
    assert life["total"] == 3 and life["peak"] == 2
    assert life["first"] == "9 March 2026"


def test_lifetime_ticks_months_then_years():
    young = activity.lifetime([dt.date(2025, 11, 20)], TODAY)
    old = activity.lifetime([dt.date(2023, 5, 1)], TODAY)
    labels = [t["label"] for t in young["ticks"]]
    # Every label that starts a new year names it, even if January was skipped.
    assert labels[0] == "Dec 2025"
    assert sum(label.endswith("2026") for label in labels) == 1
    assert all(len(label) == 3 for label in labels if not label[-4:].isdigit())
    assert [t["label"] for t in old["ticks"]] == ["2024", "2025", "2026"]


def test_lifetime_ticks_never_crowd():
    for start in (dt.date(2026, 8, 1), dt.date(2025, 7, 28), dt.date(2024, 1, 1)):
        ticks = activity.lifetime([start], TODAY)["ticks"]
        positions = [t["pos"] for t in ticks]
        assert positions == sorted(positions)
        for prev, cur in zip(ticks, ticks[1:]):
            assert cur["pos"] - prev["pos"] >= 0.03 + 0.018 * len(prev["label"])


def test_lifetime_without_commits():
    assert activity.lifetime([], TODAY) is None


def test_commit_dates_reads_the_cache_offline(tmp_path):
    cache = tmp_path / "me__repo.json"
    cache.write_text(json.dumps({"fetched_at": "2020-01-01T00:00:00+00:00",
                                 "commits": ["2026-09-01T10:00:00Z"]}), encoding="utf-8")
    dates = activity.commit_dates("me/repo", tmp_path, refresh=False, offline=True, today=TODAY)
    assert dates == [dt.date(2026, 9, 1)]


def test_commit_dates_offline_without_cache(tmp_path):
    assert activity.commit_dates("me/repo", tmp_path, False, True, TODAY) is None
