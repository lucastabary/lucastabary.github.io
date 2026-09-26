"""Tag normalisation against tags.yml, and the posts pinned to the home page."""

from __future__ import annotations

import build

REGISTRY = {
    "ML": {"aliases": ["machine-learning"]},
    "notebooks": {"aliases": ["jupyter"]},
}


def test_registered_tags_take_the_registry_spelling(make_post):
    post = make_post(tags=["ml", "Machine-Learning", "JUPYTER"])
    build.normalise_tags([post], REGISTRY)
    assert post.tags == ["ML", "notebooks"]      # the alias collapsed onto "ML"


def test_unregistered_tags_merge_across_case_first_spelling_wins(make_post):
    newest = make_post("a", tags=["Graph Theory"])
    older = make_post("b", tags=["graph theory", "new"])
    build.normalise_tags([newest, older], REGISTRY)
    assert newest.tags == ["Graph Theory"]
    assert older.tags == ["Graph Theory", "new"]


def test_normalise_tags_without_registry_keeps_tags(make_post):
    post = make_post(tags=["b", "a"])
    build.normalise_tags([post], {})
    assert post.tags == ["b", "a"]               # order is the author's, not sorted


def test_load_tag_registry_reads_the_repo_file():
    registry = build.load_tag_registry()
    assert registry, "tags.yml should list at least one tag"
    for name, info in registry.items():
        assert isinstance(info, dict), f"{name}: an entry is a mapping, even if empty"
        assert set(info) <= {"description", "aliases"}, f"{name}: unknown keys {set(info)}"


def test_tag_registry_has_no_alias_clash():
    """An alias (or a case variant) claimed by two tags would make one of them unreachable."""
    seen: dict[str, str] = {}
    for name, info in build.load_tag_registry().items():
        for spelling in [name, *(info.get("aliases") or [])]:
            key = str(spelling).lower()
            assert key not in seen, f"'{spelling}' belongs to both {seen[key]} and {name}"
            seen[key] = name


def test_featured_posts_order_and_dedup(make_post):
    a, b, c = make_post("a"), make_post("b", featured=True), make_post("c")
    project = make_post("vae", project={"slug": "nirs", "repo": "x/y"})
    pinned = build.featured_posts([a, b, c, project], ["/blog/c/", "missing", "c", "nirs/vae"])
    # site.yml order first, duplicates and unknown names dropped, then featured: true
    assert pinned == [c, project, b]
