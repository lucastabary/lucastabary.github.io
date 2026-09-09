#!/usr/bin/env python3
"""Static site generator for lucastabary.github.io.

Drop a file in ``posts/`` and it becomes a page. Nothing else to edit:

    posts/2026-09-09-my-idea.md         ->  /blog/my-idea/
    posts/experiment.ipynb              ->  /blog/experiment/
    posts/2026-05-01-preprint.pdf       ->  /blog/preprint/
    posts/interactive-demo.html         ->  /blog/interactive-demo/
    posts/my-post/index.ipynb + images  ->  /blog/my-post/   (folder copied as-is)

Title, date, summary and tags are inferred from the file, and can be overridden
with front matter or a ``<name>.meta.yml`` sidecar. See README.md.

Usage:
    python build.py [--drafts] [--out _site] [--serve [PORT]]
"""

from __future__ import annotations

import argparse
import datetime as dt
import html as html_lib
import re
import shutil
import stat
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent
POSTS_DIR = ROOT / "posts"
TEMPLATES_DIR = ROOT / "templates"
ASSETS_DIR = ROOT / "assets"
STATIC_DIR = ROOT / "static"

POST_EXTS = {".ipynb", ".md", ".markdown", ".html", ".htm", ".pdf"}
IGNORED_NAMES = {"readme.md", "readme", "meta.yml", "meta.yaml", ".gitkeep"}
IGNORED_DIRS = {".ipynb_checkpoints", "__pycache__", ".git"}

DATE_PREFIX_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[-_](.+)$")
FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(f"  {msg}")


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-") or "post"


def titleize(slug: str) -> str:
    words = slug.replace("_", " ").replace("-", " ").split()
    return " ".join(words).strip().capitalize() or "Untitled"


def strip_tags(html_text: str) -> str:
    text = re.sub(r"(?is)<(script|style|svg)\b.*?</\1>", " ", html_text)
    text = TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def summarise(text: str, words: int = 42) -> str:
    parts = text.split()
    if len(parts) <= words:
        return " ".join(parts)
    return " ".join(parts[:words]).rstrip(",.;:") + "…"


def coerce_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return dt.date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def coerce_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = re.split(r"[,;]", value)
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def split_date_prefix(stem: str) -> tuple[dt.date | None, str]:
    match = DATE_PREFIX_RE.match(stem)
    if not match:
        return None, stem
    year, month, day, rest = match.groups()
    try:
        return dt.date(int(year), int(month), int(day)), rest
    except ValueError:
        return None, stem


def split_front_matter(text: str) -> tuple[dict, str]:
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        log(f"! front matter ignored ({exc.__class__.__name__})")
        return {}, text
    if not isinstance(data, dict):
        return {}, text
    return data, text[match.end():]


def git_date(path: Path) -> dt.date | None:
    """Date of the last commit touching ``path`` (falls back to mtime)."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%aI", "--", str(path)],
            cwd=ROOT, capture_output=True, text=True, timeout=20, check=False,
        )
        stamp = result.stdout.strip()
        if stamp:
            return dt.datetime.fromisoformat(stamp).date()
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    try:
        return dt.date.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


# ---------------------------------------------------------------------------
# the post model
# ---------------------------------------------------------------------------

@dataclass
class Post:
    slug: str
    title: str
    kind: str                      # notebook | markdown | html | pdf
    source: Path
    date: dt.date | None = None
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    body: str = ""                 # rendered HTML (empty for pdf / standalone html)
    draft: bool = False
    words: int = 0
    bundle: Path | None = None
    raw_name: str | None = None    # downloadable source, inside the post folder
    standalone_html: str | None = None
    pdf_name: str | None = None
    pdf_pages: int | None = None

    KIND_LABELS = {
        "notebook": "Notebook",
        "markdown": "Note",
        "html": "Page",
        "pdf": "PDF",
    }

    @property
    def url(self) -> str:
        return f"/blog/{self.slug}/"

    @property
    def source_url(self) -> str | None:
        return f"/blog/{self.slug}/{self.raw_name}" if self.raw_name else None

    @property
    def pdf_url(self) -> str | None:
        return f"/blog/{self.slug}/{self.pdf_name}" if self.pdf_name else None

    @property
    def reading_time(self) -> int:
        return max(1, round(self.words / 220)) if self.words else 0

    @property
    def date_iso(self) -> str:
        return self.date.isoformat() if self.date else ""

    @property
    def date_label(self) -> str:
        return self.date.strftime("%d %B %Y").lstrip("0") if self.date else "Undated"

    @property
    def kind_label(self) -> str:
        return self.KIND_LABELS.get(self.kind, self.kind.title())

    @property
    def search_text(self) -> str:
        """Body text carried into the blog index so search reaches inside posts."""
        return strip_tags(self.body)[:1500].lower() if self.body else ""


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------

def find_main_file(folder: Path) -> Path | None:
    """The post file inside a bundle folder: index.* wins, else the only one."""
    candidates = [
        p for p in sorted(folder.iterdir())
        if p.is_file() and p.suffix.lower() in POST_EXTS and not p.name.startswith((".", "_"))
    ]
    if not candidates:
        return None
    for candidate in candidates:
        if candidate.stem.lower() == "index":
            return candidate
    if len(candidates) > 1:
        log(f"! {folder.name}/ holds several post files; using {candidates[0].name} "
            f"(rename one to index{candidates[0].suffix} to be explicit)")
    return candidates[0]


def discover() -> list[tuple[Path, Path | None]]:
    """Return (source file, bundle folder or None) for every post in posts/."""
    if not POSTS_DIR.is_dir():
        return []
    found: list[tuple[Path, Path | None]] = []
    for entry in sorted(POSTS_DIR.iterdir()):
        # "." and "_" mean "parked here, not published" — same rule inside bundles.
        if entry.name.startswith((".", "_")) or entry.name.lower() in IGNORED_NAMES:
            continue
        if entry.is_dir():
            if entry.name in IGNORED_DIRS:
                continue
            main = find_main_file(entry)
            if main:
                found.append((main, entry))
            else:
                log(f"! {entry.name}/ has no .ipynb/.md/.html/.pdf inside — skipped")
        elif entry.suffix.lower() in POST_EXTS:
            if entry.name.endswith((".meta.yml", ".meta.yaml")):
                continue
            found.append((entry, None))
    return found


def read_sidecar(source: Path, bundle: Path | None) -> dict:
    candidates = [source.with_suffix(".meta.yml"), source.with_suffix(".meta.yaml")]
    if bundle:
        candidates += [bundle / "meta.yml", bundle / "meta.yaml"]
    for candidate in candidates:
        if candidate.is_file():
            try:
                data = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as exc:
                log(f"! {candidate.name} is not valid YAML ({exc.__class__.__name__}) — ignored")
                continue
            if isinstance(data, dict):
                return data
    return {}


# ---------------------------------------------------------------------------
# renderers, one per file type
# ---------------------------------------------------------------------------

def render_markdown_text(text: str) -> str:
    import markdown

    converter = markdown.Markdown(
        extensions=[
            "abbr", "attr_list", "def_list", "footnotes", "md_in_html", "tables",
            "admonition", "sane_lists", "toc",
            "pymdownx.superfences", "pymdownx.highlight", "pymdownx.arithmatex",
            "pymdownx.tasklist", "pymdownx.smartsymbols", "pymdownx.caret", "pymdownx.tilde",
        ],
        extension_configs={
            "pymdownx.highlight": {"css_class": "highlight", "guess_lang": False},
            "pymdownx.arithmatex": {"generic": True},
            "pymdownx.tasklist": {"custom_checkbox": True},
            "toc": {"permalink": "#", "permalink_class": "heading-anchor"},
        },
    )
    return converter.convert(text)


def render_markdown_post(source: Path) -> dict:
    raw = source.read_text(encoding="utf-8")
    meta, text = split_front_matter(raw)
    title = meta.get("title")
    stripped = text.lstrip()
    if not title and stripped.startswith("# "):
        first, _, rest = stripped.partition("\n")
        title = first[2:].strip()
        text = rest
    return {"kind": "markdown", "meta": meta, "body": render_markdown_text(text), "title": title}


def render_notebook_post(source: Path) -> dict:
    import nbformat
    from nbconvert import HTMLExporter
    from nbconvert.preprocessors import TagRemovePreprocessor

    notebook = nbformat.read(str(source), as_version=4)
    meta = dict(notebook.metadata.get("blog") or {})
    title = meta.get("title")

    # A leading "# Title" cell becomes the page title instead of being repeated.
    for cell in notebook.cells:
        if cell.get("cell_type") != "markdown" or not str(cell.get("source", "")).strip():
            continue
        lines = str(cell["source"]).lstrip().split("\n")
        if lines[0].startswith("# "):
            title = title or lines[0][2:].strip()
            cell["source"] = "\n".join(lines[1:]).lstrip("\n")
        break

    exporter = HTMLExporter(template_name="basic")
    exporter.exclude_input_prompt = False
    exporter.exclude_output_prompt = False
    remover = TagRemovePreprocessor(
        remove_cell_tags=["remove_cell", "hide_cell"],
        remove_input_tags=["remove_input", "hide_input"],
        remove_all_outputs_tags=["remove_output", "hide_output"],
    )
    exporter.register_preprocessor(remover, enabled=True)
    body, _ = exporter.from_notebook_node(notebook)
    return {"kind": "notebook", "meta": meta, "body": body, "title": title}


def render_html_post(source: Path) -> dict:
    raw = source.read_text(encoding="utf-8", errors="replace")
    meta, text = split_front_matter(raw)

    def meta_tag(name: str) -> str | None:
        match = re.search(
            r'<meta\s+name=["\']' + name + r'["\']\s+content=["\'](.*?)["\']',
            text, re.I | re.S)
        return html_lib.unescape(match.group(1)).strip() if match else None

    title = meta.get("title")
    if not title:
        match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        if match:
            title = strip_tags(match.group(1))
    if not title:
        match = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.I | re.S)
        if match:
            title = strip_tags(match.group(1))

    for key, name in (("summary", "description"), ("date", "date"), ("tags", "keywords")):
        if key not in meta:
            value = meta_tag(name)
            if value:
                meta[key] = value

    head = text[:4000].lower()
    standalone = "<html" in head or "<!doctype html" in head
    return {
        "kind": "html",
        "meta": meta,
        "title": title,
        "body": "" if standalone else text,
        "standalone": text if standalone else None,
    }


def render_pdf_post(source: Path) -> dict:
    meta: dict[str, Any] = {}
    pages = None
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(source))
        pages = len(reader.pages)
        info = reader.metadata
        if info:
            if (info.title or "").strip():
                meta["title"] = info.title.strip()
            if (info.subject or "").strip():
                meta["summary"] = info.subject.strip()
    except Exception as exc:  # a malformed PDF must not break the whole build
        log(f"! could not read PDF metadata from {source.name} ({exc.__class__.__name__})")
    return {"kind": "pdf", "meta": meta, "body": "", "title": meta.get("title"), "pages": pages}


RENDERERS = {
    ".md": render_markdown_post,
    ".markdown": render_markdown_post,
    ".ipynb": render_notebook_post,
    ".html": render_html_post,
    ".htm": render_html_post,
    ".pdf": render_pdf_post,
}


def build_post(source: Path, bundle: Path | None) -> Post:
    rendered = RENDERERS[source.suffix.lower()](source)
    meta = {**rendered.get("meta", {}), **read_sidecar(source, bundle)}

    stem = bundle.name if bundle else source.stem
    file_date, name_rest = split_date_prefix(stem)
    slug = slugify(meta.get("slug") or name_rest)

    title = str(meta.get("title") or rendered.get("title") or titleize(name_rest)).strip()
    date = coerce_date(meta.get("date")) or file_date or git_date(source)

    body = rendered.get("body") or ""
    plain = strip_tags(body) if body else ""
    summary = str(meta.get("summary") or meta.get("description") or "").strip()
    if not summary and plain:
        summary = summarise(plain)
    if not summary and rendered["kind"] == "pdf":
        pages = rendered.get("pages")
        summary = "PDF document" + (f", {pages} pages." if pages else ".")

    return Post(
        slug=slug,
        title=title,
        kind=rendered["kind"],
        source=source,
        date=date,
        summary=summary,
        tags=coerce_tags(meta.get("tags")),
        body=body,
        draft=bool(meta.get("draft", False)),
        words=len(plain.split()),
        bundle=bundle,
        standalone_html=rendered.get("standalone"),
        pdf_pages=rendered.get("pages"),
    )


# ---------------------------------------------------------------------------
# writing the site
# ---------------------------------------------------------------------------

BACK_BAR = (
    '<a href="/blog/" style="position:fixed;top:12px;left:12px;z-index:99999;'
    "font:500 13px/1 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;"
    "background:#111;color:#fff;padding:8px 12px;border-radius:999px;"
    'text-decoration:none;opacity:.82">&larr; Blog</a>'
)


def copy_tree(src: Path, dst: Path) -> None:
    def ignore(directory: str, names: list[str]) -> set[str]:
        skipped = {n for n in names if n in IGNORED_DIRS or n.startswith(".")}
        skipped |= {n for n in names if n.endswith((".meta.yml", ".meta.yaml"))}
        skipped |= {n for n in names if n in {"meta.yml", "meta.yaml"}}
        return skipped

    shutil.copytree(src, dst, ignore=ignore, dirs_exist_ok=True)


def clean_output(out_dir: Path) -> None:
    """Empty the output directory, keeping the directory itself.

    A sync client or an open preview can hold a file for a moment on Windows,
    so clear read-only flags and retry instead of failing the whole build. The
    directory is never removed, only emptied — Windows refuses to delete a
    folder that any process is still watching.
    """
    if not out_dir.exists():
        return

    last_error: OSError | None = None
    for attempt in range(5):
        stuck: list[Path] = []
        for child in out_dir.iterdir():
            try:
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            except OSError as exc:
                last_error = exc
                stuck.append(child)
                try:
                    child.chmod(stat.S_IWRITE | stat.S_IREAD)
                except OSError:
                    pass
        if not stuck:
            return
        if attempt == 4:
            raise SystemExit(
                f"Could not clear {out_dir}: {last_error}\n"
                "Close whatever is holding it open (preview server, editor, "
                "file sync) and run the build again."
            )
        time.sleep(0.6)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_post(post: Post, out_dir: Path, env: Environment, ctx: dict) -> None:
    post_dir = out_dir / "blog" / post.slug
    post_dir.mkdir(parents=True, exist_ok=True)

    if post.bundle:
        copy_tree(post.bundle, post_dir)
    else:
        shutil.copy2(post.source, post_dir / post.source.name)
    post.raw_name = post.source.name

    if post.kind == "pdf":
        post.pdf_name = post.source.name
        post.raw_name = None
        page = env.get_template("pdf.html").render(post=post, **ctx)
    elif post.standalone_html is not None:
        page = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + BACK_BAR,
                      post.standalone_html, count=1, flags=re.I)
        if page == post.standalone_html:      # no <body> tag to hook onto
            page = BACK_BAR + page
    else:
        page = env.get_template("post.html").render(post=post, **ctx)

    write(post_dir / "index.html", page)


def build_pygments_css() -> str:
    from pygments.formatters import HtmlFormatter

    def defs(style: str, selector: str) -> str:
        try:
            css = HtmlFormatter(style=style).get_style_defs(selector)
        except Exception:
            css = HtmlFormatter(style="default").get_style_defs(selector)
        # Drop the wrapper rule so the theme's own background token wins.
        return "\n".join(
            line for line in css.splitlines() if not line.startswith(selector + " {")
        )

    light = defs("friendly", ".highlight")
    dark_toggle = defs("github-dark", ':root[data-theme="dark"] .highlight')
    dark_auto = defs("github-dark", ':root:not([data-theme="light"]) .highlight')
    return (
        "/* Generated by build.py - do not edit. */\n"
        f"{light}\n\n"
        f"@media (prefers-color-scheme: dark) {{\n{dark_auto}\n}}\n\n"
        f"{dark_toggle}\n"
    )


def build_feed(posts: list[Post], config: dict) -> str:
    base = str(config.get("url", "")).rstrip("/")
    title = html_lib.escape(str(config.get("title", "Blog")))
    description = html_lib.escape(" ".join(str(config.get("description", "")).split()))
    now = dt.datetime.now(dt.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    items = []
    for post in posts[:25]:
        pub = ""
        if post.date:
            stamp = dt.datetime.combine(post.date, dt.time(12, 0), dt.timezone.utc)
            pub = f"      <pubDate>{stamp.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>\n"
        link = html_lib.escape(f"{base}{post.url}")
        items.append(
            "    <item>\n"
            f"      <title>{html_lib.escape(post.title)}</title>\n"
            f"      <link>{link}</link>\n"
            f'      <guid isPermaLink="true">{link}</guid>\n'
            f"{pub}"
            f"      <description>{html_lib.escape(post.summary)}</description>\n"
            "    </item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{title}</title>\n"
        f"    <link>{base}/blog/</link>\n"
        f"    <description>{description}</description>\n"
        "    <language>en</language>\n"
        f"    <lastBuildDate>{now}</lastBuildDate>\n"
        f'    <atom:link href="{base}/feed.xml" rel="self" type="application/rss+xml"/>\n'
        + "\n".join(items)
        + "\n  </channel>\n</rss>\n"
    )


def build(out_dir: Path, include_drafts: bool = False) -> list[Post]:
    config = yaml.safe_load((ROOT / "site.yml").read_text(encoding="utf-8")) or {}

    print("Building site")
    posts: list[Post] = []
    for source, bundle in discover():
        post = build_post(source, bundle)
        if post.draft and not include_drafts:
            log(f"- {source.name} (draft, skipped)")
            continue
        posts.append(post)

    seen: dict[str, Post] = {}
    for post in posts:
        if post.slug in seen:
            original, post.slug = post.slug, f"{post.slug}-{post.kind}"
            log(f"! two posts want the slug '{original}'; this one becomes '{post.slug}'")
        seen[post.slug] = post

    posts.sort(key=lambda p: (p.date or dt.date.min, p.title), reverse=True)

    clean_output(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    projects = config.get("projects") or []
    tags = sorted({t for p in posts for t in p.tags}, key=str.lower)
    ctx = {
        "config": config,
        "author": config.get("author") or {},
        "site_title": config.get("title", "Site"),
        "posts": posts,
        "projects": projects,
        "tags": tags,
        "build_date": dt.date.today(),
    }

    for post in posts:
        write_post(post, out_dir, env, ctx)
        log(f"+ {post.url}  ({post.kind}) {post.title}")

    home_count = int((config.get("blog") or {}).get("posts_on_home", 3))
    pages = [
        ("home.html", "index.html",
         {"active": "home", "recent": posts[:home_count],
          "featured": [p for p in projects if p.get("featured")]}),
        ("projects.html", "projects/index.html", {"active": "projects"}),
        ("blog.html", "blog/index.html", {"active": "blog"}),
        ("404.html", "404.html", {"active": ""}),
    ]
    for template_name, target, extra in pages:
        write(out_dir / target, env.get_template(template_name).render(**ctx, **extra))
        log(f"+ /{target}")

    if ASSETS_DIR.is_dir():
        copy_tree(ASSETS_DIR, out_dir / "assets")
    if STATIC_DIR.is_dir():
        copy_tree(STATIC_DIR, out_dir)
    write(out_dir / "assets" / "pygments.css", build_pygments_css())
    write(out_dir / "feed.xml", build_feed(posts, config))
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Done - {len(posts)} post(s) written to {out_dir}")
    return posts


def serve(out_dir: Path, port: int) -> None:
    import functools
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(out_dir))
    print(f"Serving {out_dir} at http://localhost:{port}/  (Ctrl+C to stop)")
    try:
        ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build lucastabary.github.io")
    parser.add_argument("--out", default="_site", help="output directory (default: _site)")
    parser.add_argument("--drafts", action="store_true", help="include posts marked draft")
    parser.add_argument("--serve", nargs="?", const=8000, type=int, metavar="PORT",
                        help="serve the result locally after building")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir

    build(out_dir, include_drafts=args.drafts)
    if args.serve:
        serve(out_dir, args.serve)
    return 0


if __name__ == "__main__":
    sys.exit(main())
