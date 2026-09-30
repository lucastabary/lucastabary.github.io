"""Citations, structured data, sitemap and the Publications page."""

from __future__ import annotations

import base64
import datetime as dt
from io import BytesIO

import pytest
from PIL import Image

import build
import scholar

DAY = dt.date(2026, 9, 9)


@pytest.mark.parametrize("name, expected", [
    ("Lucas Tabary", ("Lucas", "Tabary")),
    ("Tabary, Lucas", ("Lucas", "Tabary")),
    ("Jean-Pierre de la Tour", ("Jean-Pierre de la", "Tour")),
    ("Plato", ("", "Plato")),
])
def test_split_name(name, expected):
    assert scholar.split_name(name) == expected


def test_bibtex_key_skips_stopwords_and_accents():
    assert scholar.bibtex_key("Lucas Tabary", 2026, "How this blog works") == "tabary2026blog"
    assert scholar.bibtex_key("Élodie Müller", 2025, "Réseaux et graphes") == "muller2025reseaux"


def test_post_bibtex():
    entry = scholar.post_bibtex(title="PCA & t-SNE: 100% of the variance?",
                                author="Lucas Tabary", url="https://x.io/blog/pca/",
                                date=DAY, kind_label="Notebook")
    assert entry.startswith("@misc{tabary2026pca,\n")
    assert "author       = {Tabary, Lucas}," in entry
    # LaTeX specials escaped, capitalisation protected by double braces
    assert r"title        = {{PCA \& t-SNE: 100\% of the variance?}}," in entry
    assert "month        = sep," in entry
    assert r"howpublished = {\url{https://x.io/blog/pca/}}," in entry
    assert entry.endswith("note         = {Notebook}\n}")


def test_post_bibtex_without_date():
    entry = scholar.post_bibtex(title="Undated", author="Lucas Tabary", url="u",
                                date=None, kind_label="Note")
    assert "year" not in entry and "month" not in entry


def test_citation_meta():
    meta = dict(scholar.citation_meta(title="T", author="Lucas Tabary", date=DAY,
                                      pdf_url="https://x.io/p.pdf"))
    assert meta == {"citation_title": "T", "citation_author": "Tabary, Lucas",
                    "citation_publication_date": "2026/09/09",
                    "citation_online_date": "2026/09/09",
                    "citation_pdf_url": "https://x.io/p.pdf"}


def test_structured_data():
    author = {"name": "Lucas Tabary", "role": "Student",
              "links": [{"label": "Email", "url": "mailto:a@b.c"},
                        {"label": "GitHub", "url": "https://github.com/x"}]}
    person = scholar.person_ld(author, "https://x.io", [{"name": "ML"}])
    assert person["sameAs"] == ["https://github.com/x"]      # no mailto: in profiles
    assert person["knowsAbout"] == ["ML"]
    post = scholar.post_ld(title="T", summary="S", url="https://x.io/blog/t/", date=DAY,
                           tags=["a"], kind="pdf", image=None, author=author,
                           site_url="https://x.io")
    assert post["@type"] == "ScholarlyArticle" and post["datePublished"] == "2026-09-09"
    assert "image" not in post


def test_sitemap_and_robots():
    xml = scholar.sitemap("https://x.io", [("/b/", DAY), ("/a/?q=1&r", None), ("/b/", DAY)])
    assert xml.count("<url>") == 2                                  # duplicates merged
    assert xml.index("/a/") < xml.index("/b/")                     # sorted
    assert "<loc>https://x.io/a/?q=1&amp;r</loc></url>" in xml     # escaped
    assert "<lastmod>2026-09-09</lastmod>" in xml
    assert scholar.robots("https://x.io").endswith("Sitemap: https://x.io/sitemap.xml\n")


BIB = r"""
% A comment line, ignored.
@article{a2024, author = {Tabary, Lucas and Doe, Jane}, title = {A {GNN} Paper},
  journal = {Journal of Things}, year = {2024}, doi = {10.1/xyz}, code = {https://c.io}}
@inproceedings{b2025, author = {Doe, Jane and Tabary, L.}, title = {Later Paper},
  booktitle = {Conf}, year = {2025}, month = mar, pdf = {/files/b.pdf}}
@misc{c2026, author = {Tabary, Lucas}, title = {On Spectra}, year = {2026},
  eprint = {2601.00001}, archiveprefix = {arXiv}, abstract = {We study {spectra}.}}
@techreport{d2025, author = {Tabary, Lucas}, title = {Rapport sur les donn{\'e}es},
  institution = {Universit{\'e} de Lorraine}, year = {2025}, post = {/blog/nirs/}}
@misc{e2026, author = {Tabary, Lucas}, title = {Invited talk}, year = {2026},
  howpublished = {Talk at a seminar}}
@misc{f2026, author = {Tabary, Lucas}, title = {Forced}, year = {2026}, category = {report}}
"""


def test_load_publications(tmp_path):
    bib = tmp_path / "publications.bib"
    bib.write_text(BIB, encoding="utf-8")
    groups = scholar.load_publications(bib, "Lucas Tabary")
    by_key = {g["key"]: g for g in groups}
    assert [g["title"] for g in groups] == ["Publications", "Preprints", "Reports & theses",
                                            "Talks & posters"]
    assert [e["id"] for e in by_key["publication"]["entries"]] == ["b2025", "a2024"]
    assert [e["id"] for e in by_key["report"]["entries"]] == ["f2026", "d2025"]

    paper = by_key["publication"]["entries"][1]
    assert paper["title"] == "A GNN Paper"
    assert paper["authors"] == [{"name": "Lucas Tabary", "me": True},
                                {"name": "Jane Doe", "me": False}]
    assert paper["venue"] == "Journal of Things"
    assert [l["label"] for l in paper["links"]] == ["DOI", "Code"]
    assert "code" not in paper["bibtex"] and "doi" in paper["bibtex"]
    names = [line.split("=")[0].strip() for line in paper["bibtex"].splitlines()[1:-1]]
    assert names == ["author", "title", "journal", "year", "doi"]     # conventional order

    later = by_key["publication"]["entries"][0]
    assert later["authors"][1] == {"name": "L. Tabary", "me": True}   # initial matches

    report = by_key["report"]["entries"][1]
    assert report["title"] == "Rapport sur les données"               # LaTeX accents decoded
    assert report["venue"] == "Université de Lorraine"
    assert report["links"] == [{"label": "Blog post", "url": "/blog/nirs/"}]

    preprint = by_key["preprint"]["entries"][0]
    assert preprint["links"] == [{"label": "arXiv", "url": "https://arxiv.org/abs/2601.00001"}]
    assert preprint["abstract"] == "We study spectra."
    assert "abstract" not in preprint["bibtex"]


def test_publications_missing_or_comment_only(tmp_path):
    assert scholar.load_publications(tmp_path / "none.bib", "X") == []
    bib = tmp_path / "publications.bib"
    bib.write_text("% only comments\n% @article{x, title={Commented out}}\n", encoding="utf-8")
    assert scholar.load_publications(bib, "X") == []


def test_repo_publications_file_parses():
    """The committed publications.bib must always load, even while it is empty."""
    scholar.load_publications(build.PUBLICATIONS_FILE, "Lucas Tabary")


def png_data_uri(width: int, height: int) -> str:
    buffer = BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def test_externalise_images(tmp_path):
    svg = "data:image/svg+xml;base64," + base64.b64encode(b"<svg/>").decode()
    body = (f'<p><img alt="a" src="{png_data_uri(30, 20)}"></p>'
            f'<img src="{png_data_uri(30, 20)}" width="15">'
            f'<img src="{svg}"><img src="./figure.png" loading="eager">')
    out = build.externalise_images(body, tmp_path)

    assert "base64" not in out
    files = sorted(p.name for p in tmp_path.iterdir())
    assert len(files) == 2                        # the two identical PNGs share one file
    png = next(f for f in files if f.endswith(".png"))
    assert f'<img loading="lazy" decoding="async" alt="a" src="{png}" width="30" height="20">' in out
    assert f'src="{png}" width="15">' in out      # an explicit width is kept, not doubled
    assert 'loading="eager"' in out and out.count("loading=") == 4
