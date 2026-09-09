---
title: How this blog works
date: 2026-09-09
tags: [meta, notes]
summary: >-
  Every file dropped in posts/ becomes a page. Here is the whole contract,
  written as the first post so it doubles as a formatting test.
---

There is no CMS here and no database. A GitHub Action runs `build.py`, which
walks `posts/`, turns every file it recognises into a page, and publishes the
result. Adding a post means adding a file.

## What counts as a post

| You drop | You get |
| --- | --- |
| `posts/2026-09-09-idea.md` | a rendered note at `/blog/idea/` |
| `posts/experiment.ipynb` | the notebook, code and outputs included |
| `posts/preprint.pdf` | an inline PDF reader with a download link |
| `posts/demo.html` | your page, served as you wrote it |

A folder works too. `posts/my-study/` containing `index.ipynb` alongside its
images and CSVs is copied wholesale, so relative links keep working.

## Metadata is optional

The build guesses the title from the first heading, the date from the filename
prefix (or the last commit that touched the file), and the summary from the
opening lines. Front matter overrides any of it:

```yaml
---
title: A better title
date: 2026-09-09
tags: [graphs, spectral]
draft: true
---
```

`draft: true` keeps a post out of the build until you remove it.

## Maths and code survive the trip

Inline maths like $\lambda_2(G) > 0$ renders, and so do display blocks. The
normalised Laplacian, for instance:

$$
\mathcal{L} = I - D^{-1/2} A D^{-1/2}
$$

Code is highlighted, in posts and in notebook cells alike:

```python
import numpy as np

def fiedler_value(adjacency: np.ndarray) -> float:
    """Algebraic connectivity: the second-smallest Laplacian eigenvalue."""
    degrees = np.diag(adjacency.sum(axis=1))
    eigenvalues = np.linalg.eigvalsh(degrees - adjacency)
    return float(np.sort(eigenvalues)[1])
```

> Notebook cells tagged `hide_input` keep their output and drop the code — handy
> when the plot matters more than the twelve lines that drew it.

That is the whole system. Delete this post whenever it stops being useful.
