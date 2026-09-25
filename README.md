# lucastabary.github.io

Personal site: research interests, projects, and a blog that publishes whatever
file you drop into `posts/`.

There is no CMS. A GitHub Action runs `build.py`, which renders `templates/`
into `_site/` and deploys it to GitHub Pages. Publishing is `git push`.

---

## Publishing a post

Put a file in `posts/` and push. That is the whole workflow.

| Drop this | You get |
| --- | --- |
| `posts/2026-09-09-my-idea.md` | a rendered note at `/blog/my-idea/` |
| `posts/experiment.ipynb` | the notebook with code, outputs, tables and figures |
| `posts/preprint.pdf` | an inline PDF reader with a download link |
| `posts/demo.html` | your page, served exactly as written |

A post can also be a **folder**, which is copied wholesale so relative links
keep working:

```
posts/my-study/
  index.ipynb      <- the main post, at /blog/my-study/
  appendix.md      <- also a post, at /blog/my-study/appendix/
  slides.pdf       <- also a post, at /blog/my-study/slides/
  figure.png       <- referenced as ./figure.png, works unchanged
  data.csv
  .venv/           <- the notebook's environment, never published
```

Every `.ipynb`, `.md`, `.html` and `.pdf` at the top of the folder becomes a
post. `index.*` (or the only post file) takes the folder URL; the others nest
under it, and take the folder's date prefix unless they carry their own. The
folder is copied next to each of them, so relative links work from any post.
A `README.md` in the folder is not a post. Nested posts link back to the folder
page in their breadcrumb.

A folder with several posts and no `index.*` gets a generated page at its URL
listing them, in filename order (so `01-intro.md`, `02-method.ipynb` read as a
series). Its title and summary come from the folder's `meta.yml`.

Since every file is published, anything else goes behind a `_`: `_scratch.md`,
`_src/` for LaTeX sources or figure scripts.

The original file is published next to the page, so every post has a
"Download source" link.

### The date

`2026-09-09-my-idea.md` publishes as `/blog/my-idea/` dated 9 September 2026.
Without a date prefix, the build uses the last commit that touched the file.
Either way, `date:` in the metadata wins.

### The title

The first `# Heading` of a Markdown file or notebook becomes the title and is
not repeated in the body. HTML files use their `<title>`, PDFs their embedded
title. Failing all that, the filename is used.

---

## Metadata

Everything is optional. Markdown files take YAML front matter:

```markdown
---
title: A better title than the filename
date: 2026-09-09
tags: [graphs, spectral]
summary: One or two sentences for the blog index.
draft: true
---
```

Notebooks carry the same keys under a `blog` entry in notebook metadata
(*Edit → Notebook metadata* in Jupyter):

```json
{ "blog": { "title": "...", "tags": ["ml"], "summary": "...", "date": "2026-09-09" } }
```

HTML files use standard tags — `<title>`, `<meta name="description">`,
`<meta name="keywords">`.

For anything else — a PDF in particular — drop a sidecar next to the file:

```
posts/preprint.pdf
posts/preprint.meta.yml     ->  title: ...   tags: [...]   summary: ...
```

Inside a folder, `meta.yml` describes the main post; the other files use their
own `<name>.meta.yml`.

| Key | Effect |
| --- | --- |
| `title` | page and index title |
| `date` | `YYYY-MM-DD`, overrides the filename prefix |
| `summary` | index blurb and meta description; otherwise auto-extracted |
| `tags` | chips on the card, and the filter buttons on `/blog/` |
| `slug` | the URL, if you do not want the one derived from the filename |
| `draft` | `true` keeps the post out of the build |
| `featured` | `true` pins the post to the home page |

A file or folder whose name starts with `_` or `.` is ignored entirely — handy
for parking something in `posts/` that is not a post at all.

### Notebook cell tags

| Tag | Effect |
| --- | --- |
| `hide_input` | keep the output, drop the code |
| `hide_output` | keep the code, drop the output |
| `hide_cell` | drop the cell entirely |

---

## Posts that live in a project repository

A project can carry its own `blog/` folder, and those posts join this site.
Nothing is installed in the project repo — no workflow, no token, no submodule.
Write the notebook next to the code it describes, commit it there, done.

Declare the source on the project in `site.yml`:

```yaml
projects:
  - name: Near-infrared spectroscopy analysis of plant specimens
    slug: nirs-spectroscopy     # the URL: /projects/nirs-spectroscopy/
    short: NIRS spectroscopy    # compact label for chips and badges
    repo: lucastabary/PIDR_RICOCHET
    blog: blog                  # the folder to pull; drop the key to stop pulling
    # branch: notes             # only if the posts are not on the default branch
```

At build time the folder is shallow sparse-cloned into `.cache/`, so a repo full
of datasets or checkpoints costs nothing to pull. The posts follow the same
rules as `posts/` — same formats, same metadata, same rendering.

They are namespaced by project, so two repos can both publish `results.ipynb`:

```
posts/my-note.md                       ->  /blog/my-note/
PIDR_RICOCHET:blog/2026-09-02-vae.md   ->  /blog/nirs-spectroscopy/vae/
```

Each post shows a badge linking back to its project, `/blog/` gains a filter per
project, and every project gets a page at `/projects/<slug>/` listing its notes.

### Filtering the blog

`/blog/` lists every post newest first. Filters only hide posts, so the order
never changes, and they combine:

- **Project**: one chip per project with posts, plus *Standalone* for the posts
  in `posts/`.
- **Folder**: one chip per folder holding several posts (a series, or a post
  with its appendices). Picking a folder selects its project too; picking a
  project only offers its folders.
- **Tag**, and the search box.

The filters live in the URL, so a view can be linked to:
`/blog/?project=nirs-spectroscopy`, `/blog/?folder=my-study`, `/blog/?tag=graphs`.
Project pages link to their filtered view.

**Give project posts a date.** Project repos are cloned shallow, so the build
cannot see a file's own history; without a `YYYY-MM-DD-` prefix or a `date:` key
it falls back to the repo's last commit and warns.

### When they appear

The site rebuilds daily (`schedule` in the workflow), so a post pushed to a
project repo shows up within a day. To publish one immediately, run the
**Build and deploy** workflow from the Actions tab.

---

## Home, about and projects pages

All three come from `site.yml`. Do not edit the generated HTML.

- **Home** (`/`) is an overview: your name, a one-line `intro`, pinned posts,
  the latest posts, and the projects marked `featured: true`.
- **About** (`/about/`) holds the presentation: `role` above the heading, `bio`
  as the lede, the `about:` narrative in Markdown, and the `interests` as cards.
- **Projects** (`/projects/`) lists the projects of `site.yml`, in file order.
  The list is written by hand; what fills in automatically is each project's
  posts, pulled from its repo.

### Page titles

Browser-tab titles say what the page is about, and the author's name only ever
follows them (`Blog: notes, notebooks and experiments · Lucas Tabary`). The four
fixed pages take theirs from `pages:` in `site.yml`; posts and projects use
their own title.

### Pinning posts to the home page

List them under `home.featured_posts`, by URL without `/blog/`:

```yaml
home:
  featured_posts:
    - how-this-blog-works          # /blog/how-this-blog-works/
    - nirs-spectroscopy/vae        # a project post
  recent_posts: 4                  # latest posts shown under the pinned ones
```

They appear in that order. A post can also pin itself with `featured: true` in
its own metadata — handy from a project repo; those follow the listed ones,
newest first. A pinned post is not repeated in the latest posts, and a name
that matches no post is reported in the build log rather than failing.

---

## Running it locally

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
python build.py --serve
```

Then open <http://localhost:8000>. Useful flags:

- `--drafts` — include posts marked `draft: true`
- `--out DIR` — write somewhere other than `_site/`
- `--serve PORT` — serve on a different port
- `--refresh` — re-clone the project blogs instead of reusing `.cache/`
- `--offline` — never touch the network; build from whatever is cached
- `--strict` — fail on publishing problems in `posts/`, as CI does (see below)

The first build clones the project repos; later builds reuse `.cache/`, so add
`--refresh` when you want their newest posts locally.

`_site/` is generated and git-ignored; never edit it by hand. If this repo lives
in a synced folder (OneDrive, Dropbox), excluding `_site/` from sync avoids the
sync client briefly locking files mid-build.

---

## Deployment

`.github/workflows/pages.yml` builds on every push to `main`, once a day on a
schedule (to collect posts from the project repos), and on demand from the
Actions tab. Pull requests get the build as a check without deploying, so a
broken notebook fails before it reaches the live site.

CI builds with `--strict`, which fails when a published post in `posts/` has a
notebook cell that raised an error, a code cell that was never executed (the
build does not run notebooks, so it would show up empty), or a file named like
scratch work (`draft`, `wip`, `todo`, `tmp`, `old`, ...) sitting in a post
folder. Drafts are not checked. The same problems in a project repo only print a
warning, so one broken notebook there never blocks the daily rebuild.

**One-time setup:** in *Settings → Pages*, set **Source** to **GitHub Actions**.
Until that is done the site keeps serving the old branch contents.

---

## Layout

```
build.py                    the generator
site.yml                    profile, interests, projects and their blog sources
posts/                      drop posts here
templates/                  Jinja2 page templates
assets/                     style.css, app.js (copied to /assets/)
static/                     optional: files copied to the site root as-is
.cache/                     shallow clones of the project blogs (git-ignored)
.github/workflows/pages.yml build and deploy
```

`static/` does not exist yet — create it when you need something at a fixed URL,
such as `static/files/cv.pdf` served at `/files/cv.pdf`.
