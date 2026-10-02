# lucastabary.github.io

Personal research site, used by Lucas alone. `README.md` is a short public presentation, not a manual: keep it that way. How the build behaves is documented where it lives: the docstrings of `build.py`, `activity.py`, `og_image.py` and `scholar.py`, the comments in `site.yml`, `tags.yml` and `publications.bib`, and the tests in `tests/`. Read the relevant ones before changing anything.

- `build.py` renders `templates/` + `site.yml` + `posts/` into `_site/`. Never edit `_site/` or generated HTML; edit data in `site.yml` and layout in `templates/` / `assets/`.
- Deployment is automatic on push to `main` (`.github/workflows/pages.yml`, which also rebuilds daily to collect project posts). It needs the GitHub Pages source set to "GitHub Actions". Never push unless asked.
- To write a new post, use the `create-blogpost` skill.
- AI review: adding the `ai-review` label to a PR that touches `posts/` runs `.github/workflows/ai-review.yml`, which reviews the changed posts with Copilot (`actions/ai-inference`, prompt in `.github/prompts/post-review.prompt.yml`) and comments on the PR. The model answers in JSON, rendered by `.github/scripts/ai_review_report.py`; the check fails when there are "must fix" items or the answer is not valid JSON. It spends the owner's Copilot credits (secret `COPILOT_GITHUB_TOKEN`), so it is on demand only.

## Posts

- Every new post is a folder: `posts/YYYY-MM-DD-slug/`, with the main post as `index.<ext>`.
- Every `.ipynb`, `.md`, `.html` and `.pdf` at the top of a post folder is published as its own post (`index.*` at `/blog/slug/`, the others at `/blog/slug/<name>/`). So never leave drafts, notes or LaTeX-generated Markdown there: prefix scratch files with `_` or put them in a `_`-prefixed subfolder. `README.md` is ignored.
- Notebooks are rendered, not executed: commit them with their outputs.
- Tags come from `tags.yml` (canonical spelling, description, aliases). Reuse an existing tag before creating one, and register any new tag there.

## Environments

- `.venv/` at the repo root holds the build dependencies and pytest (`requirements-dev.txt`) only. Build with `.venv/Scripts/python.exe build.py --drafts --offline`; preview with the `site` config in `.claude/launch.json` (port 8000), which runs `build.py --watch`: it rebuilds on every change and reloads open pages, so no manual rebuild is needed while it runs.
- Tests: `.venv/Scripts/python.exe -m pytest` (offline, ~15 s). Add or update tests in `tests/` with any change to the build logic; CI runs them before building.
- Each notebook post is its own uv project, with its environment in its folder: `posts/<post-folder>/.venv/`. From the post folder:

  ```bash
  uv init --bare --python 3.13 --no-workspace   # creates pyproject.toml
  uv add ipykernel nbconvert numpy matplotlib   # plus what the post needs; writes uv.lock
  uv run jupyter nbconvert --to notebook --execute --inplace index.ipynb
  ```

  Commit `pyproject.toml` and `uv.lock` with the post (they are published too, which documents the exact environment); `uv sync` recreates `.venv` identically. Never install research libraries in the root `.venv`.
- `.venv/` is git-ignored at any depth and dot-folders are never copied to the site.
- CI builds with `--strict`: a published notebook with an error or an unexecuted code cell, or a scratch-named file (`draft`, `wip`, `tmp`, ...) in a post folder, fails the deploy. Run `.venv/Scripts/python.exe build.py --offline --strict` before committing a post.
