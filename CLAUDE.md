# lucastabary.github.io

Personal research site. `README.md` is the full reference for how posts, metadata, project blogs and deployment work; read it before changing anything.

- `build.py` renders `templates/` + `site.yml` + `posts/` into `_site/`. Never edit `_site/` or generated HTML; edit data in `site.yml` and layout in `templates/` / `assets/`.
- Deployment is automatic on push to `main`. Never push unless asked.
- To write a new post, use the `create-blogpost` skill.

## Posts

- Every new post is a folder: `posts/YYYY-MM-DD-slug/`, with the main post as `index.<ext>`.
- Every `.ipynb`, `.md`, `.html` and `.pdf` at the top of a post folder is published as its own post (`index.*` at `/blog/slug/`, the others at `/blog/slug/<name>/`). So never leave drafts, notes or LaTeX-generated Markdown there: prefix scratch files with `_` or put them in a `_`-prefixed subfolder. `README.md` is ignored.
- Notebooks are rendered, not executed: commit them with their outputs.
- Tags come from `tags.yml` (canonical spelling, description, aliases). Reuse an existing tag before creating one, and register any new tag there.

## Environments

- `.venv/` at the repo root holds the build dependencies and pytest (`requirements-dev.txt`) only. Build with `.venv/Scripts/python.exe build.py --drafts --offline`; preview with the `site` config in `.claude/launch.json` (port 8000).
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
