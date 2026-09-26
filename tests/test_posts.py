"""Turning files in posts/ into Post objects: discovery, metadata, folders."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import nbformat
import pytest

import build


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def unexecuted_notebook(path: Path) -> Path:
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_markdown_cell("# A notebook"),
                nbformat.v4.new_code_cell("1 + 1")]          # never run: no outputs
    path.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(nb, str(path))
    return path


def test_discover_skips_parked_and_ignored_entries(tmp_path):
    write(tmp_path / "2026-01-01-note.md", "# Note\n")
    write(tmp_path / "_parked.md", "# Not a post\n")
    write(tmp_path / "README.md", "# Not a post either\n")
    write(tmp_path / "paper.meta.yml", "title: x\n")
    write(tmp_path / "study" / "index.md", "# Study\n")
    write(tmp_path / "study" / "appendix.md", "# Appendix\n")
    write(tmp_path / "study" / "_scratch.md", "# Scratch\n")
    write(tmp_path / "empty" / "data.csv", "a,b\n")

    found = {(src.relative_to(tmp_path).as_posix(), bundle.name if bundle else None)
             for src, bundle in build.discover(tmp_path)}
    assert found == {
        ("2026-01-01-note.md", None),
        ("study/appendix.md", "study"),
        ("study/index.md", "study"),
    }


def test_markdown_post_metadata(tmp_path):
    source = write(tmp_path / "2026-09-09-my-idea.md",
                   "---\ntags: ml, graphs\nsummary: Short.\nfeatured: true\n---\n"
                   "# The real title\n\nBody text here.\n")
    post = build.build_post(source, None)
    assert post.slug == "my-idea"
    assert post.url == "/blog/my-idea/"
    assert post.title == "The real title"          # first heading, not the filename
    assert post.date == dt.date(2026, 9, 9)
    assert post.tags == ["ml", "graphs"]
    assert post.summary == "Short."
    assert post.featured and not post.draft


def test_front_matter_overrides_the_filename(tmp_path):
    source = write(tmp_path / "2026-09-09-my-idea.md",
                   "---\ntitle: Chosen\nslug: other\ndate: 2025-01-02\ndraft: true\n---\nText.\n")
    post = build.build_post(source, None)
    assert (post.title, post.slug, post.date, post.draft) == \
        ("Chosen", "other", dt.date(2025, 1, 2), True)


def test_project_posts_are_namespaced(tmp_path):
    source = write(tmp_path / "2026-09-02-vae.md", "# VAE\n")
    post = build.build_post(source, None, project={"slug": "nirs", "repo": "me/nirs"})
    assert post.url == "/blog/nirs/vae/"
    assert post.ref == "nirs/vae"


def test_folder_posts_nest_under_the_folder_url(tmp_path):
    folder = tmp_path / "2026-09-09-study"
    index = build.build_post(write(folder / "index.md", "# Study\n"), folder)
    appendix = build.build_post(write(folder / "appendix.md", "# Appendix\n"), folder)
    assert index.url == "/blog/study/"
    assert appendix.url == "/blog/study/appendix/"
    assert appendix.date == dt.date(2026, 9, 9)       # inherited from the folder name


def test_scratch_named_file_in_a_folder_is_flagged(tmp_path):
    folder = tmp_path / "2026-09-09-study"
    write(folder / "index.md", "# Study\n")
    draft = build.build_post(write(folder / "draft-v2.md", "# Oops\n"), folder)
    assert any("scratch file" in issue for issue in draft.issues)


def test_unexecuted_notebook_is_flagged(tmp_path):
    post = build.build_post(unexecuted_notebook(tmp_path / "nb.ipynb"), None)
    assert post.kind == "notebook"
    assert any("never executed" in issue for issue in post.issues)


def test_link_folder_pages_builds_a_series(tmp_path):
    folder = tmp_path / "2026-09-09-study"
    posts = [build.build_post(write(folder / name, f"# {name}\n"), folder)
             for name in ("index.md", "02-method.md", "01-intro.md")]
    series, folders = build.link_folder_pages(posts)

    assert series == []                        # the folder has an index: no generated page
    assert [f["key"] for f in folders] == ["study"]
    assert folders[0]["count"] == 3
    order = sorted(posts, key=lambda p: p.sequence["index"])
    assert [p.source.name for p in order] == ["index.md", "01-intro.md", "02-method.md"]
    assert order[0].sequence["prev"] is None and order[-1].sequence["next"] is None


def test_folder_without_index_gets_a_generated_page(tmp_path):
    folder = tmp_path / "2026-09-09-notes"
    write(folder / "meta.yml", "title: Reading notes\n")
    # Write every file first: whether a file owns the folder depends on its siblings.
    sources = [write(folder / name, f"# {name}\n") for name in ("a.md", "b.md")]
    posts = [build.build_post(source, folder) for source in sources]
    series, _ = build.link_folder_pages(posts)
    assert [(s["url"], s["title"]) for s in series] == [("/blog/notes/", "Reading notes")]


def test_report_issues_only_blocks_on_local_posts(make_post):
    local = make_post("a", issues=["broken"])
    remote = make_post("b", issues=["broken"], project={"slug": "p", "repo": "me/p"})
    build.report_issues([remote], strict=True)          # project posts only warn
    with pytest.raises(SystemExit):
        build.report_issues([local, remote], strict=True)
    build.report_issues([local], strict=False)          # without --strict, nothing fails
