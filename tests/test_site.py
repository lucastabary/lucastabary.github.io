"""End to end: build a small site from fixture posts and check the output."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import build
from test_posts import unexecuted_notebook, write


@pytest.fixture
def site(tmp_path, monkeypatch):
    """Point the build at fixture posts and empty caches, offline."""
    posts = tmp_path / "posts"
    write(posts / "2026-09-09-first.md",
          "---\ntags: [Jupyter, fresh-tag]\nsummary: First post.\n---\n# First\n\nHello.\n")
    write(posts / "2026-09-10-second" / "index.md", "---\ntags: [notebooks]\n---\n# Second\n")
    write(posts / "2026-09-10-second" / "extra.md", "# Extra\n")
    monkeypatch.setattr(build, "POSTS_DIR", posts)
    monkeypatch.setattr(build, "CACHE_DIR", tmp_path / "cache" / "sources")
    monkeypatch.setattr(build, "ACTIVITY_CACHE_DIR", tmp_path / "cache" / "activity")
    monkeypatch.setattr(build, "PUBLICATIONS_FILE", tmp_path / "publications.bib")

    def run(strict: bool = False) -> Path:
        out = tmp_path / "out"
        build.build(out, offline=True, strict=strict, use_cache=False)
        return out
    run.posts = posts
    run.bib = tmp_path / "publications.bib"
    return run


def test_build_writes_every_page(site):
    out = site()
    for page in ["index.html", "about/index.html", "projects/index.html", "blog/index.html",
                 "blog/first/index.html", "blog/second/index.html",
                 "blog/second/extra/index.html", "404.html", "feed.xml"]:
        assert (out / page).is_file(), page
    assert (out / "blog" / "first" / "2026-09-09-first.md").is_file()   # downloadable source


def test_tags_are_normalised_linked_and_counted(site):
    out = site()
    blog = (out / "blog" / "index.html").read_text(encoding="utf-8")
    # "Jupyter" is an alias of "notebooks" in tags.yml: both posts share one chip.
    assert 'data-tag="notebooks"' in blog and 'data-tag="jupyter"' not in blog
    chip = blog.split('data-tag="notebooks"', 1)[1].split("</button>", 1)[0]
    assert "data-tag-count>2<" in chip
    post = (out / "blog" / "first" / "index.html").read_text(encoding="utf-8")
    assert 'href="/blog/?tag=fresh-tag"' in post


def test_strict_build_fails_on_an_unexecuted_notebook(site):
    unexecuted_notebook(site.posts / "2026-09-11-nb.ipynb")
    site()                                          # a normal build only warns
    with pytest.raises(SystemExit):
        site(strict=True)


def test_search_engine_files_and_tags(site):
    out = site()
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    for url in ("/", "/about/", "/blog/", "/blog/first/", "/blog/second/extra/", "/projects/"):
        assert f"<loc>https://lucastabary.github.io{url}</loc>" in sitemap
    assert "404" not in sitemap
    assert (out / "robots.txt").read_text(encoding="utf-8").startswith("User-agent: *")

    page = (out / "blog" / "first" / "index.html").read_text(encoding="utf-8")
    assert '<link rel="canonical" href="https://lucastabary.github.io/blog/first/">' in page
    assert '<meta name="citation_title" content="First">' in page
    ld = json.loads(re.search(r'application/ld\+json">(.*?)</script>', page, re.S).group(1))
    assert ld["@type"] == "BlogPosting" and ld["headline"] == "First"
    assert "@misc{tabary2026first," in page                     # Cite this post
    home = (out / "index.html").read_text(encoding="utf-8")
    assert '"@type": "Person"' in home


def test_publications_page_only_with_entries(site):
    out = site()
    assert not (out / "publications").exists()
    assert 'href="/publications/"' not in (out / "index.html").read_text(encoding="utf-8")

    site.bib.write_text("@article{x2025, author={Tabary, Lucas}, title={A Paper}, "
                        "journal={J}, year={2025}}", encoding="utf-8")
    out = site()
    page = (out / "publications" / "index.html").read_text(encoding="utf-8")
    assert "<strong>Lucas Tabary</strong>" in page and "A Paper" in page
    assert 'href="/publications/"' in (out / "index.html").read_text(encoding="utf-8")
    assert "/publications/" in (out / "sitemap.xml").read_text(encoding="utf-8")
