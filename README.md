# lucastabary.github.io

Source of my personal research site: **<https://lucastabary.github.io>**

I am an engineering student in AI and data science, working on machine
learning, computational neuroscience and interpretability. The site gathers:

- **Blog**: research notes, Jupyter notebooks and papers, including notes
  written inside each project's own repository.
- **Projects**: research and personal work, with their notes and commit
  activity.

## How it is built

A small static site generator written in Python (`build.py`, Jinja2 templates,
nbconvert for notebooks, Pillow for preview images), with no framework and no
JavaScript build step. GitHub Actions tests it, builds the site and deploys it
to GitHub Pages on every push to `main`, and once a day to collect new notes
from the project repositories.

```bash
pip install -r requirements-dev.txt
python build.py --serve --watch   # local preview at http://localhost:8000
python -m pytest
```
