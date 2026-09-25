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
  index.ipynb      <- the post (index.* wins if the folder has several)
  figure.png       <- referenced as ./figure.png, works unchanged
  data.csv
```

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

Inside a folder post the sidecar is just `meta.yml`.

| Key | Effect |
| --- | --- |
| `title` | page and index title |
| `date` | `YYYY-MM-DD`, overrides the filename prefix |
| `summary` | index blurb and meta description; otherwise auto-extracted |
| `tags` | chips on the card, and the filter buttons on `/blog/` |
| `slug` | the URL, if you do not want the one derived from the filename |
| `draft` | `true` keeps the post out of the build |

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

**Give project posts a date.** Project repos are cloned shallow, so the build
cannot see a file's own history; without a `YYYY-MM-DD-` prefix or a `date:` key
it falls back to the repo's last commit and warns.

### When they appear

The site rebuilds daily (`schedule` in the workflow), so a post pushed to a
project repo shows up within a day. To publish one immediately, run the
**Build and deploy** workflow from the Actions tab.

---

## Home and projects pages

Both come from `site.yml` — bio, links, research interests, projects. Adding a
project is a few lines of YAML; `featured: true` also shows it on the home page.
Do not edit the generated HTML.

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
