"""Shared fixtures: import the build modules from the repo root, and keep tests
out of the real build cache."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build  # noqa: E402


@pytest.fixture(autouse=True)
def no_build_cache():
    """Render for real and write nothing to .cache/: tests must not depend on,
    or pollute, the cache of the working copy."""
    build.cache.enabled = False
    yield
    build.cache.enabled = True


@pytest.fixture
def make_post():
    """A Post with sensible defaults, for tests that only care about a few fields."""
    def make(slug: str = "post", **fields) -> build.Post:
        fields.setdefault("title", slug.title())
        fields.setdefault("kind", "markdown")
        fields.setdefault("source", Path(f"{slug}.md"))
        return build.Post(slug=slug, **fields)
    return make
