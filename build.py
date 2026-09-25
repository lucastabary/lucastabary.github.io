#!/usr/bin/env python3
"""Static site generator for lucastabary.github.io.

Drop a file in ``posts/`` and it becomes a page. Nothing else to edit:

    posts/2026-09-09-my-idea.md         ->  /blog/my-idea/
    posts/experiment.ipynb              ->  /blog/experiment/
    posts/2026-05-01-preprint.pdf       ->  /blog/preprint/
    posts/interactive-demo.html         ->  /blog/interactive-demo/
    posts/my-post/index.ipynb + images  ->  /blog/my-post/   (folder copied as-is)
    posts/my-post/appendix.md           ->  /blog/my-post/appendix/   (every file is a post)

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
CACHE_DIR = ROOT / ".cache" / "sources"

POST_EXTS = {".ipynb", ".md", ".markdown", ".html", ".htm", ".pdf"}
IGNORED_NAMES = {"readme.md", "readme", "meta.yml", "meta.yaml", ".gitkeep"}
IGNORED_DIRS = {".ipynb_checkpoints", "__pycache__", ".git"}

DRAFT_NAME_RE = re.compile(
    r"(^|[-_. ])(draft|wip|todo|scratch|tmp|temp|brouillon|old|backup|copy)([-_. ]|\d|$)", re.I)
DATE_PREFIX_RE =re.compile(r"^(\d{4})-(\d{2})-(\d{2})[-_](.+)$")
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


ANCHOR_RE = re.compile(
    r'(?is)<a[^>]*class="[^"]*(?:heading-anchor|anchor-link)[^"]*"[^>]*>.*?</a>')
FIRST_PARA_RE = re.compile(r"(?is)<p[^>]*>(.*?)</p>")


def strip_tags(html_text: str) -> str:
    text = re.sub(r"(?is)<(script|style|svg)\b.*?</\1>", " ", html_text)
    # Permalink anchors would otherwise leak "#" and "¶" into summaries.
    text = ANCHOR_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def first_paragraph(html_text: str) -> str:
    """Opening paragraph, which makes a far better blurb than the whole body."""
    for match in FIRST_PARA_RE.finditer(html_text):
        text = strip_tags(match.group(1))
        if len(text.split()) >= 5:
            return text
    return ""


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


def git_date(path: Path, repo_root: Path | None = None) -> dt.date | None:
    """Date of the last commit touching ``path`` (falls back to mtime).

    Project repositories are cloned shallow, so there the answer is the tip
    commit's date rather than the file's own history — good enough as a
    fallback, and the build warns when a post relies on it.
    """
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%aI", "--", str(path)],
            cwd=str(repo_root or ROOT), capture_output=True, text=True,
            timeout=20, check=False,
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
    featured: bool = False         # pinned to the home page from its own metadata
    words: int = 0
    bundle: Path | None = None
    raw_name: str | None = None    # downloadable source, inside the post folder
    standalone_html: str | None = None
    pdf_name: str | None = None
    pdf_pages: int | None = None
    project: dict | None = None    # set when the post came from a project repo
    issues: list[str] = field(default_factory=list)  # publishing problems, see --strict
    parent: dict | None = None     # {url, title} of the folder page a nested post belongs to
    folder: dict | None = None     # {url, title} of its multi-post folder, for the blog filter

    KIND_LABELS = {
        "notebook": "Notebook",
        "markdown": "Note",
        "html": "Page",
        "pdf": "PDF",
    }

    @property
    def url(self) -> str:
        """Project posts are namespaced by project, so two repos never collide."""
        if self.project:
            return f"/blog/{self.project['slug']}/{self.slug}/"
        return f"/blog/{self.slug}/"

    @property
    def ref(self) -> str:
        """How site.yml names this post: its URL without /blog/, e.g. 'nirs-spectroscopy/vae'."""
        return self.url.removeprefix("/blog/").strip("/")

    @property
    def source_url(self) -> str | None:
        return f"{self.url}{self.raw_name}" if self.raw_name else None

    @property
    def pdf_url(self) -> str | None:
        return f"{self.url}{self.pdf_name}" if self.pdf_name else None

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

def bundle_post_files(folder: Path) -> list[Path]:
    """Every post file at the top level of a bundle folder; each one is a post."""
    return [
        p for p in sorted(folder.iterdir())
        if p.is_file() and p.suffix.lower() in POST_EXTS
        and not p.name.startswith((".", "_")) and p.name.lower() not in IGNORED_NAMES
    ]


def is_primary(source: Path, bundle: Path | None) -> bool:
    """The post that owns the folder URL: index.*, or the folder's only post file."""
    if bundle is None:
        return True
    return source.stem.lower() == "index" or len(bundle_post_files(bundle)) == 1


def discover(directory: Path) -> list[tuple[Path, Path | None]]:
    """Return (source file, bundle folder or None) for every post in a folder."""
    if not directory.is_dir():
        return []
    found: list[tuple[Path, Path | None]] = []
    for entry in sorted(directory.iterdir()):
        # "." and "_" mean "parked here, not published" — same rule inside bundles.
        if entry.name.startswith((".", "_")) or entry.name.lower() in IGNORED_NAMES:
            continue
        if entry.is_dir():
            if entry.name in IGNORED_DIRS:
                continue
            files = bundle_post_files(entry)
            if files:
                found += [(source, entry) for source in files]
            else:
                log(f"! {entry.name}/ has no .ipynb/.md/.html/.pdf inside — skipped")
        elif entry.suffix.lower() in POST_EXTS:
            if entry.name.endswith((".meta.yml", ".meta.yaml")):
                continue
            found.append((entry, None))
    return found


# ---------------------------------------------------------------------------
# project repositories
# ---------------------------------------------------------------------------

def git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd) if cwd else None,
        capture_output=True, text=True, check=False, timeout=180,
    )


def project_ref(project: dict) -> dict:
    """The identity a post carries when it comes from a project repo."""
    slug = slugify(project.get("slug") or project.get("name") or "project")
    repo = project.get("repo")
    name = project.get("name") or slug
    return {
        "slug": slug,
        "name": name,
        # Chips and badges need something that fits; `short` in site.yml, else the name.
        "short": project.get("short") or name,
        "repo": repo,
        "repo_url": f"https://github.com/{repo}" if repo else None,
        "url": f"/projects/{slug}/",
    }


def fetch_project_blog(project: dict, refresh: bool, offline: bool) -> Path | None:
    """Shallow sparse-clone a project's blog folder into the local cache.

    Only the configured folder is checked out, and only its latest commit, so
    this stays fast even for repositories carrying large datasets or models.
    """
    repo = project.get("repo")
    folder = project.get("blog")
    if not repo or not folder:
        return None

    branch = project.get("branch")
    dest = CACHE_DIR / repo.replace("/", "__")
    blog_path = dest / folder

    if dest.exists() and not refresh:
        return blog_path if blog_path.is_dir() else None

    if offline:
        log(f"! {repo} not in the cache and --offline is set — skipped")
        return None

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        clean_output(dest)
        try:
            dest.rmdir()
        except OSError:
            pass

    clone = ["clone", "--depth", "1", "--filter=blob:none", "--sparse",
             "--quiet", f"https://github.com/{repo}.git", str(dest)]
    if branch:
        clone[1:1] = ["--branch", branch]

    result = git(*clone)
    if result.returncode != 0:
        raise SystemExit(
            f"Could not clone {repo}: {result.stderr.strip() or 'git failed'}\n"
            "Check the repo name and branch in site.yml, or build with --offline."
        )

    result = git("sparse-checkout", "set", folder, cwd=dest)
    if result.returncode != 0:
        raise SystemExit(f"Could not sparse-checkout {folder} from {repo}: "
                         f"{result.stderr.strip()}")

    if not blog_path.is_dir():
        log(f"- {repo} has no {folder}/ yet — nothing to pull")
        return None
    return blog_path


def read_sidecar(source: Path, bundle: Path | None) -> dict:
    candidates = [source.with_suffix(".meta.yml"), source.with_suffix(".meta.yaml")]
    # A folder's meta.yml describes its primary post, not every file beside it.
    if bundle and is_primary(source, bundle):
        candidates += [bundle / "meta.yml", bundle / "meta.yaml"]
    for candidate in candidates:
        data = read_yaml(candidate)
        if data is not None:
            return data
    return {}


def read_yaml(path: Path) -> dict | None:
    """A YAML mapping from disk, or None if the file is missing or not a mapping."""
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        log(f"! {path.name} is not valid YAML ({exc.__class__.__name__}) — ignored")
        return None
    return data if isinstance(data, dict) else None


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

    # The build never executes notebooks, so what was committed is what readers see.
    issues: list[str] = []
    unexecuted = 0
    for number, cell in enumerate(notebook.cells, start=1):
        if cell.get("cell_type") != "code" or not str(cell.get("source", "")).strip():
            continue
        errors = [o for o in cell.get("outputs", []) if o.get("output_type") == "error"]
        if errors:
            issues.append(f"cell {number} raised {errors[0].get('ename', 'an error')}")
        elif cell.get("execution_count") is None:
            unexecuted += 1
    if unexecuted:
        issues.append(f"{unexecuted} code cell(s) never executed — run the notebook "
                      "and commit it with its outputs")

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
    return {"kind": "notebook", "meta": meta, "body": body, "title": title, "issues": issues}


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


def build_post(source: Path, bundle: Path | None,
               project: dict | None = None, repo_root: Path | None = None) -> Post:
    rendered = RENDERERS[source.suffix.lower()](source)
    meta = {**rendered.get("meta", {}), **read_sidecar(source, bundle)}

    # The primary post of a folder takes the folder URL; its siblings nest under it:
    # posts/2026-09-09-study/index.ipynb -> /blog/study/, notes.md -> /blog/study/notes/.
    primary = is_primary(source, bundle)
    stem = bundle.name if bundle and primary else source.stem
    file_date, name_rest = split_date_prefix(stem)
    slug = slugify(meta.get("slug") or name_rest)
    issues = list(rendered.get("issues", []))
    if bundle and not primary:
        folder_date, folder_rest = split_date_prefix(bundle.name)
        file_date = file_date or folder_date
        slug = f"{slugify(folder_rest)}/{slug}"
        # Every file in a folder is published, so a forgotten scratch file goes live.
        if DRAFT_NAME_RE.search(source.stem):
            issues.append(f"looks like a scratch file but would be published as "
                          f"{slug}; prefix it with _ to keep it out")

    title = str(meta.get("title") or rendered.get("title") or titleize(name_rest)).strip()
    date = coerce_date(meta.get("date")) or file_date
    if date is None:
        date = git_date(source, repo_root)
        if project:
            log(f"! {source.name} has no date; using the {project['repo']} tip commit. "
                "Name it YYYY-MM-DD-... or set date: to be exact.")

    body = rendered.get("body") or ""
    plain = strip_tags(body) if body else ""
    summary = str(meta.get("summary") or meta.get("description") or "").strip()
    if not summary and body:
        summary = summarise(first_paragraph(body) or plain)
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
        featured=bool(meta.get("featured", False)),
        words=len(plain.split()),
        bundle=bundle,
        standalone_html=rendered.get("standalone"),
        pdf_pages=rendered.get("pages"),
        project=project,
        issues=issues,
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
    post_dir = out_dir / post.url.strip("/")
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


def collect_posts(config: dict, include_drafts: bool,
                  refresh: bool, offline: bool) -> list[Post]:
    """Posts from posts/, then from every project repo that declares a blog."""
    posts: list[Post] = []

    def add(source: Path, bundle: Path | None,
            project: dict | None, repo_root: Path | None) -> None:
        post = build_post(source, bundle, project, repo_root)
        if post.draft and not include_drafts:
            log(f"- {source.name} (draft, skipped)")
            return
        posts.append(post)

    for source, bundle in discover(POSTS_DIR):
        add(source, bundle, None, ROOT)

    for project in config.get("projects") or []:
        if not project.get("blog") or not project.get("repo"):
            continue
        blog_dir = fetch_project_blog(project, refresh, offline)
        if not blog_dir:
            continue
        ref = project_ref(project)
        found = discover(blog_dir)
        for source, bundle in found:
            add(source, bundle, ref, blog_dir.parent)
        log(f"~ {project['repo']}: {len(found)} post(s)")

    # Slugs only need to be unique within a project (or within posts/).
    seen: set[tuple[str, str]] = set()
    for post in posts:
        scope = post.project["slug"] if post.project else ""
        if (scope, post.slug) in seen:
            original, post.slug = post.slug, f"{post.slug}-{post.kind}"
            log(f"! two posts want the slug '{original}'; this one becomes '{post.slug}'")
        seen.add((scope, post.slug))

    posts.sort(key=lambda p: (p.date or dt.date.min, p.title), reverse=True)
    return posts


def featured_posts(posts: list[Post], refs: list | None) -> list[Post]:
    """Posts pinned to the home page: site.yml order first, then `featured: true` by date."""
    by_ref = {p.ref: p for p in posts}
    pinned: list[Post] = []
    for ref in refs or []:
        post = by_ref.get(str(ref).removeprefix("/blog/").strip("/"))
        if post is None:
            log(f"! home.featured_posts: no post at /blog/{ref}/ (draft, renamed or not pulled?)")
        elif post not in pinned:
            pinned.append(post)
    pinned += [p for p in posts if p.featured and p not in pinned]
    return pinned


def report_issues(posts: list[Post], strict: bool) -> None:
    """Log publishing problems; with --strict, fail on those in posts/.

    Project posts only warn: a broken notebook in a project repo must not block
    the daily rebuild of the whole site.
    """
    blocking = 0
    for post in posts:
        where = f"{post.project['repo']}:" if post.project else "posts/"
        name = f"{post.bundle.name}/{post.source.name}" if post.bundle else post.source.name
        for issue in post.issues:
            log(f"! {where}{name}: {issue}")
            blocking += post.project is None
    if strict and blocking:
        raise SystemExit(f"{blocking} problem(s) in posts/ (see above); fix them or mark "
                         "the post draft: true")


def link_folder_pages(posts: list[Post]) -> tuple[list[dict], list[dict]]:
    """Attach nested posts to their folder page, creating one when the folder has no index.

    A folder with several post files and no index.* would leave its own URL empty,
    so it gets a generated page listing its posts instead.

    Returns the generated folder pages, and every multi-post folder (with or
    without an index) as a filter entry for the blog index.
    """
    by_url = {p.url: p for p in posts}
    groups: dict[str, list[Post]] = {}
    for post in posts:
        if post.bundle and not is_primary(post.source, post.bundle):
            groups.setdefault(post.url.rstrip("/").rsplit("/", 1)[0] + "/", []).append(post)

    series: list[dict] = []
    folders: list[dict] = []
    for url, members in groups.items():
        members.sort(key=lambda p: p.source.name)
        owner = by_url.get(url)
        if owner:
            parent = {"url": url, "title": owner.title}
        else:
            bundle = members[0].bundle
            meta = read_yaml(bundle / "meta.yml") or read_yaml(bundle / "meta.yaml") or {}
            date, rest = split_date_prefix(bundle.name)
            page = {
                "url": url,
                "title": str(meta.get("title") or titleize(rest)),
                "summary": str(meta.get("summary") or "").strip(),
                "date": coerce_date(meta.get("date")) or date,
                "project": members[0].project,
                "posts": members,
            }
            series.append(page)
            parent = {"url": url, "title": page["title"]}
        for post in members:
            post.parent = parent
        # The folder's own post belongs to it too, so filtering shows the whole folder.
        everyone = members + ([owner] if owner else [])
        folder = {**parent, "key": url.removeprefix("/blog/").strip("/")}
        for post in everyone:
            post.folder = folder
        folders.append({
            **folder,
            "project": members[0].project["slug"] if members[0].project else "",
            "count": len(everyone),
            "latest": max((p.date for p in everyone if p.date), default=None),
        })
    folders.sort(key=lambda f: (f["latest"] or dt.date.min, f["title"]), reverse=True)
    return series, folders


def build(out_dir: Path, include_drafts: bool = False, refresh: bool = False,
          offline: bool = False, strict: bool = False) -> list[Post]:
    config = yaml.safe_load((ROOT / "site.yml").read_text(encoding="utf-8")) or {}

    print("Building site")
    posts = collect_posts(config, include_drafts, refresh, offline)
    report_issues(posts, strict)
    series, folders = link_folder_pages(posts)

    clean_output(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["markdown"] = render_markdown_text

    # Each project carries its own identity and the posts pulled from its repo.
    projects = []
    for entry in config.get("projects") or []:
        ref = project_ref(entry)
        projects.append({
            **entry, **ref,
            "posts": [p for p in posts if p.project and p.project["slug"] == ref["slug"]],
        })

    tags = sorted({t for p in posts for t in p.tags}, key=str.lower)
    ctx = {
        "config": config,
        "author": config.get("author") or {},
        "site_title": config.get("title", "Site"),
        "posts": posts,
        "projects": projects,
        "projects_with_posts": [p for p in projects if p["posts"]],
        "has_standalone_posts": any(p.project is None for p in posts),
        "folders": folders,
        "tags": tags,
        "build_date": dt.date.today(),
    }

    for post in posts:
        write_post(post, out_dir, env, ctx)
        log(f"+ {post.url}  ({post.kind}) {post.title}")

    series_template = env.get_template("series.html")
    for page in series:
        write(out_dir / page["url"].strip("/") / "index.html",
              series_template.render(**ctx, active="blog", series=page))
        log(f"+ {page['url']}  (folder, {len(page['posts'])} post(s)) {page['title']}")

    home = config.get("home") or {}
    pinned = featured_posts(posts, home.get("featured_posts"))
    recent_count = int(home.get("recent_posts", 4))
    recent = [p for p in posts if p not in pinned][:recent_count]
    pages = [
        ("home.html", "index.html",
         {"active": "home", "pinned": pinned, "recent": recent,
          "featured": [p for p in projects if p.get("featured")]}),
        ("about.html", "about/index.html", {"active": "about"}),
        ("projects.html", "projects/index.html", {"active": "projects"}),
        ("blog.html", "blog/index.html", {"active": "blog"}),
        ("404.html", "404.html", {"active": ""}),
    ]
    for template_name, target, extra in pages:
        write(out_dir / target, env.get_template(template_name).render(**ctx, **extra))
        log(f"+ /{target}")

    project_template = env.get_template("project.html")
    for project in projects:
        target = f"projects/{project['slug']}/index.html"
        write(out_dir / target, project_template.render(
            **ctx, active="projects", project=project))
        log(f"+ /{target}  ({len(project['posts'])} post(s))")

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
    parser.add_argument("--refresh", action="store_true",
                        help="re-clone project blogs instead of reusing the cache")
    parser.add_argument("--offline", action="store_true",
                        help="never reach the network; use whatever is already cached")
    parser.add_argument("--strict", action="store_true",
                        help="fail on publishing problems in posts/ (unexecuted or "
                             "failing notebooks, scratch files); used by CI")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir

    build(out_dir, include_drafts=args.drafts, refresh=args.refresh,
          offline=args.offline, strict=args.strict)
    if args.serve:
        serve(out_dir, args.serve)
    return 0


if __name__ == "__main__":
    sys.exit(main())
