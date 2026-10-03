"""The AI review helpers in .github/scripts: flattening posts, reading the model's JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import ai_review_input  # noqa: E402
import ai_review_report  # noqa: E402

REVIEW = {
    "verdict": "major",
    "summary": "One seed only.",
    "must_fix": [{"location": "cell 7", "problem": "Single run.", "fix": "Use 5 seeds."}],
    "should_fix": [],
    "nitpicks": ["a", "b", "c", "d", "e", "f"],
    "could_not_check": ["References"],
}


def test_parse_accepts_bare_fenced_and_wrapped_json():
    bare = json.dumps(REVIEW)
    assert ai_review_report.parse(bare) == REVIEW
    assert ai_review_report.parse(f"```json\n{bare}\n```") == REVIEW
    assert ai_review_report.parse(f"Here you go:\n{bare}\nCheers") == REVIEW


def test_parse_rejects_non_json():
    assert ai_review_report.parse("Looks great to me!") is None
    assert ai_review_report.parse("[1, 2]") is None


def test_render_counts_must_fix_and_caps_nitpicks():
    body, must_fix = ai_review_report.render(REVIEW)
    assert must_fix == 1
    assert "Major issues" in body and "**cell 7**: Single run." in body
    assert "- e" in body and "- f" not in body          # at most five nitpicks


def test_main_fails_closed_on_unreadable_response(tmp_path, monkeypatch):
    response, comment, out = tmp_path / "r.txt", tmp_path / "c.md", tmp_path / "out"
    response.write_text("no json here", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    ai_review_report.main(str(response), str(comment), "gpt-4.1")
    assert "must_fix=-1" in out.read_text() and "parsed=false" in out.read_text()
    assert "no json here" in comment.read_text(encoding="utf-8")


def test_notebook_flattening_keeps_what_a_review_needs(tmp_path):
    nb = {
        "metadata": {"blog": {"tags": ["ml"]}},
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": ["# Title"]},
            {"cell_type": "code", "metadata": {"tags": ["hide_input"]}, "execution_count": 1,
             "source": ["print('x')"],
             "outputs": [{"output_type": "stream", "text": [f"{i}\n" for i in range(40)]},
                         {"output_type": "display_data", "data": {"image/png": "..."}}]},
            {"cell_type": "code", "metadata": {}, "execution_count": None,
             "source": ["1/0"], "outputs": []},
        ],
    }
    path = tmp_path / "post.ipynb"
    path.write_text(json.dumps(nb), encoding="utf-8")
    text = ai_review_input.notebook_to_markdown(path)
    assert '{"tags": ["ml"]}' in text
    assert "cell 2 code tags=['hide_input']" in text
    assert "(25 more lines)" in text and "[figure]" in text
    assert "[not executed]" in text


def test_input_is_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_review_input, "MAX_CHARS", 100)
    post, out = tmp_path / "p.md", tmp_path / "in.md"
    post.write_text("x" * 1000, encoding="utf-8")
    ai_review_input.main(str(out), [str(post)])
    text = out.read_text(encoding="utf-8")
    assert text.endswith("[TRUNCATED: input capped at 100 characters]")
