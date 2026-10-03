"""Small parsing helpers: slugs, dates, tags, front matter, summaries."""

from __future__ import annotations

import datetime as dt

import pytest

import build


@pytest.mark.parametrize("text, expected", [
    ("My Idea", "my-idea"),
    ("Réseaux de neurones: une étude", "reseaux-de-neurones-une-etude"),
    ("  spaces   and___underscores ", "spaces-and-underscores"),
    ("?!", "post"),                      # nothing left: a fallback, never an empty URL
])
def test_slugify(text, expected):
    assert build.slugify(text) == expected


@pytest.mark.parametrize("stem, expected", [
    ("2026-09-09-my-idea", (dt.date(2026, 9, 9), "my-idea")),
    ("2026-09-09_my_idea", (dt.date(2026, 9, 9), "my_idea")),
    ("my-idea", (None, "my-idea")),
    ("2026-13-40-bad-date", (None, "2026-13-40-bad-date")),   # invalid date: untouched
])
def test_split_date_prefix(stem, expected):
    assert build.split_date_prefix(stem) == expected


@pytest.mark.parametrize("value, expected", [
    ("2026-09-09", dt.date(2026, 9, 9)),
    ("2026-09-09T10:00:00Z", dt.date(2026, 9, 9)),
    (dt.datetime(2026, 9, 9, 10), dt.date(2026, 9, 9)),
    (dt.date(2026, 9, 9), dt.date(2026, 9, 9)),
    ("not a date", None),
    ("", None),
    (None, None),
])
def test_coerce_date(value, expected):
    assert build.coerce_date(value) == expected


@pytest.mark.parametrize("value, expected", [
    (["ml", " graphs ", ""], ["ml", "graphs"]),
    ("ml, graphs; stats", ["ml", "graphs", "stats"]),
    (None, []),
    (42, []),
])
def test_coerce_tags(value, expected):
    assert build.coerce_tags(value) == expected


def test_split_front_matter():
    meta, body = build.split_front_matter("---\ntitle: Hi\ntags: [a]\n---\n# Body\n")
    assert meta == {"title": "Hi", "tags": ["a"]}
    assert body == "# Body\n"


@pytest.mark.parametrize("text", [
    "# No front matter\n",
    "---\n: not: valid: yaml\n---\nbody",   # broken YAML is ignored, not fatal
    "---\n- a list\n---\nbody",              # front matter must be a mapping
])
def test_split_front_matter_falls_back_to_the_whole_text(text):
    meta, body = build.split_front_matter(text)
    assert meta == {}
    assert body == text


def test_strip_tags_drops_markup_scripts_and_permalinks():
    html = ('<h2>Intro<a class="heading-anchor" href="#intro">#</a></h2>'
            "<script>alert(1)</script><p>A &amp; B</p>")
    assert build.strip_tags(html) == "Intro A & B"


def test_first_paragraph_skips_too_short_paragraphs():
    html = "<p>Short.</p><p>This paragraph is long enough to be a blurb.</p>"
    assert build.first_paragraph(html) == "This paragraph is long enough to be a blurb."


def test_summarise_truncates_on_words():
    assert build.summarise("one two three", words=5) == "one two three"
    assert build.summarise("one two three, four", words=3) == "one two three…"
