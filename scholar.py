"""What makes the site readable by search engines and citable by researchers.

- ``post_bibtex``: a BibTeX entry for every post ("Cite this post").
- ``person_ld`` / ``post_ld``: schema.org JSON-LD, so search engines know who
  wrote what; ``citation_meta`` adds the Highwire ``citation_*`` tags that
  Google Scholar reads on a paper's page.
- ``sitemap`` / ``robots``: every public URL, and where to find the list.
- ``load_publications``: ``publications.bib`` parsed and grouped for the
  Publications page.

Everything here is pure: it takes data from build.py and returns strings or
dicts, so it is easy to test.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

# --- names --------------------------------------------------------------------

def split_name(name: str) -> tuple[str, str]:
    """("Lucas", "Tabary") from "Lucas Tabary" or "Tabary, Lucas"."""
    name = " ".join(str(name).split())
    if "," in name:
        last, first = (part.strip() for part in name.split(",", 1))
        return first, last
    parts = name.rsplit(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("", parts[0])


# --- BibTeX for posts ---------------------------------------------------------

LATEX_SPECIALS = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
                  "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
                  "\\": r"\textbackslash{}"}
STOPWORDS = {"a", "an", "the", "of", "on", "in", "for", "and", "or", "to", "with", "how",
             "what", "why", "when", "where", "which", "who", "is", "are", "was", "were", "be",
             "do", "does", "can", "not", "from", "by", "at", "as", "into", "about", "this",
             "that", "these", "those", "its", "our", "my", "your", "their", "we", "you", "one"}
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def latex_escape(text: str) -> str:
    return "".join(LATEX_SPECIALS.get(ch, ch) for ch in text)


def bibtex_key(author: str, year: int | None, title: str) -> str:
    """tabary2026blog: last name, year, first meaningful word of the title."""
    _, last = split_name(author)
    words = re.findall(r"[a-z0-9]+", _ascii(title).lower())
    word = next((w for w in words if w not in STOPWORDS and len(w) > 2), words[0] if words else "")
    return f"{re.sub(r'[^a-z]', '', _ascii(last).lower())}{year or ''}{word}"


def _ascii(text: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def post_bibtex(*, title: str, author: str, url: str, date: dt.date | None,
                kind_label: str) -> str:
    """An @misc entry, the usual way to cite a blog post or notebook."""
    first, last = split_name(author)
    fields = [
        ("author", f"{{{latex_escape(last)}, {latex_escape(first)}}}" if first
         else f"{{{latex_escape(last)}}}"),
        # Double braces keep the title's capitalisation in any bibliography style.
        ("title", f"{{{{{latex_escape(title)}}}}}"),
    ]
    if date:
        fields += [("year", f"{{{date.year}}}"), ("month", MONTHS[date.month - 1])]
    fields += [
        ("howpublished", f"{{\\url{{{url}}}}}"),
        ("url", f"{{{url}}}"),
        ("note", f"{{{latex_escape(kind_label)}}}"),
    ]
    width = max(len(name) for name, _ in fields)
    body = ",\n".join(f"  {name.ljust(width)} = {value}" for name, value in fields)
    key = bibtex_key(author, date.year if date else None, title)
    return f"@misc{{{key},\n{body}\n}}"


# --- structured data ----------------------------------------------------------

def person_ld(author: dict, site_url: str, interests: list[dict] | None = None) -> dict:
    """schema.org Person for the site's author: name, profiles and interests."""
    data: dict[str, Any] = {"@type": "Person", "name": author.get("name", ""), "url": site_url + "/"}
    same_as = [link["url"] for link in author.get("links") or []
               if str(link.get("url", "")).startswith("http")]
    if same_as:
        data["sameAs"] = same_as
    if author.get("role"):
        data["description"] = author["role"]
    if interests:
        data["knowsAbout"] = [item["name"] for item in interests if item.get("name")]
    return data


def site_ld(config: dict, site_url: str) -> dict:
    author = config.get("author") or {}
    return {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebSite", "name": config.get("title", ""), "url": site_url + "/",
             "description": config.get("description", "")},
            person_ld(author, site_url, config.get("interests")),
        ],
    }


def post_ld(*, title: str, summary: str, url: str, date: dt.date | None, tags: list[str],
            kind: str, image: str | None, author: dict, site_url: str) -> dict:
    """BlogPosting for notes and notebooks, ScholarlyArticle for PDFs."""
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "ScholarlyArticle" if kind == "pdf" else "BlogPosting",
        "headline": title,
        "url": url,
        "mainEntityOfPage": url,
        "author": {"@type": "Person", "name": author.get("name", ""), "url": site_url + "/"},
    }
    if summary:
        data["description"] = summary
    if date:
        data["datePublished"] = date.isoformat()
    if tags:
        data["keywords"] = tags
    if image:
        data["image"] = image
    return data


def citation_meta(*, title: str, author: str, date: dt.date | None,
                  pdf_url: str | None) -> list[tuple[str, str]]:
    """Highwire Press tags, what Google Scholar reads to index a paper's page."""
    first, last = split_name(author)
    meta = [("citation_title", title), ("citation_author", f"{last}, {first}" if first else last)]
    if date:
        meta += [("citation_publication_date", date.strftime("%Y/%m/%d")),
                 ("citation_online_date", date.strftime("%Y/%m/%d"))]
    if pdf_url:
        meta.append(("citation_pdf_url", pdf_url))
    return meta


# --- sitemap and robots.txt ---------------------------------------------------

def sitemap(site_url: str, pages: list[tuple[str, dt.date | None]]) -> str:
    """pages: (site-relative URL, last modification date or None)."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url, lastmod in sorted(set(pages), key=lambda p: p[0]):
        lines.append(f"  <url><loc>{xml_escape(site_url + url)}</loc>"
                     + (f"<lastmod>{lastmod.isoformat()}</lastmod>" if lastmod else "")
                     + "</url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def robots(site_url: str) -> str:
    return f"User-agent: *\nAllow: /\n\nSitemap: {site_url}/sitemap.xml\n"


# --- publications.bib -----------------------------------------------------------

# Page sections, in order. `category = {...}` in an entry overrides the guess.
GROUPS = [
    ("publication", "Publications"),
    ("preprint", "Preprints"),
    ("report", "Reports & theses"),
    ("talk", "Talks & posters"),
    ("other", "Other"),
]
PUBLISHED_TYPES = {"article", "inproceedings", "conference", "incollection", "book",
                   "inbook", "proceedings"}
REPORT_TYPES = {"techreport", "report", "phdthesis", "mastersthesis", "thesis"}
# Fields that only drive the page; they are left out of the BibTeX shown to readers.
SITE_FIELDS = {"category", "pdf", "code", "slides", "poster", "video", "post", "abstract",
               "keywords", "file"}
MONTH_NUMBERS = {name: i for i, name in enumerate(MONTHS, 1)}


def _plain(text: str) -> str:
    """BibTeX value to display text: accents decoded, no protective braces, no \\url{}."""
    from bibtexparser.latexenc import latex_to_unicode
    text = re.sub(r"\\url\{([^}]*)\}", r"\1", str(text))
    text = latex_to_unicode(text)
    return " ".join(text.replace("{", "").replace("}", "").replace("\\&", "&").split())


def _category(entry: dict) -> str:
    explicit = entry.get("category", "").strip().lower()
    if explicit in dict(GROUPS):
        return explicit
    kind = entry.get("ENTRYTYPE", "").lower()
    if kind in PUBLISHED_TYPES:
        return "publication"
    if kind in REPORT_TYPES:
        return "report"
    how = (entry.get("howpublished", "") + " " + entry.get("note", "")).lower()
    if kind == "unpublished" or entry.get("eprint") or "arxiv" in how or "preprint" in how:
        return "preprint"
    if any(word in how for word in ("talk", "poster", "presentation", "seminar")):
        return "talk"
    return "other"


def _authors(field: str, me: str) -> list[dict]:
    """[{name, me}], "First Last" order; `me` marks the site author (same last name
    and same first initial), so the page can highlight it."""
    my_first, my_last = split_name(me)
    people = []
    for raw in re.split(r"\s+and\s+", _plain(field)) if field.strip() else []:
        first, last = split_name(raw)
        is_me = (last.lower() == my_last.lower()
                 and first[:1].lower() == my_first[:1].lower())
        people.append({"name": f"{first} {last}".strip(), "me": is_me})
    return people


def _links(entry: dict) -> list[dict]:
    links = []
    if entry.get("pdf"):
        links.append({"label": "PDF", "url": entry["pdf"]})
    if entry.get("doi"):
        doi = entry["doi"].removeprefix("https://doi.org/")
        links.append({"label": "DOI", "url": f"https://doi.org/{doi}"})
    if entry.get("eprint") and "arxiv" in (entry.get("archiveprefix", "arxiv")).lower():
        links.append({"label": "arXiv", "url": f"https://arxiv.org/abs/{entry['eprint']}"})
    for field, label in (("code", "Code"), ("slides", "Slides"), ("poster", "Poster"),
                         ("video", "Video"), ("post", "Blog post")):
        if entry.get(field):
            links.append({"label": label, "url": entry[field]})
    if entry.get("url") and not any(l["url"] == entry["url"] for l in links):
        links.append({"label": "Link", "url": entry["url"]})
    return links


# Conventional field order for the BibTeX shown to readers; others follow, sorted.
FIELD_ORDER = ["author", "title", "journal", "booktitle", "editor", "institution", "school",
               "publisher", "type", "series", "volume", "number", "pages", "year", "month",
               "doi", "eprint", "archiveprefix", "primaryclass", "url", "howpublished", "note"]


def _entry_bibtex(entry: dict) -> str:
    """The entry as readers should copy it: standard fields only, in the usual order."""
    rank = {name: i for i, name in enumerate(FIELD_ORDER)}
    fields = sorted(((k, v) for k, v in entry.items()
                     if k not in SITE_FIELDS and k not in ("ENTRYTYPE", "ID")),
                    key=lambda kv: (rank.get(kv[0], len(rank)), kv[0]))
    width = max((len(k) for k, _ in fields), default=0)
    body = ",\n".join(f"  {k.ljust(width)} = {{{v}}}" for k, v in fields)
    return f"@{entry['ENTRYTYPE']}{{{entry['ID']},\n{body}\n}}"


def load_publications(path: Path, me: str) -> list[dict]:
    """publications.bib, grouped for the page: [{key, title, entries}], newest first.

    A missing or empty file gives an empty list, and then the site has no
    Publications page at all.
    """
    if not path.is_file():
        return []
    import bibtexparser
    from bibtexparser.bparser import BibTexParser

    parser = BibTexParser(common_strings=True, ignore_nonstandard_types=False)
    raw_db = bibtexparser.loads(path.read_text(encoding="utf-8"), parser)

    entries = []
    for entry in raw_db.entries:
        entry = {k.lower() if k not in ("ENTRYTYPE", "ID") else k: v for k, v in entry.items()}
        year = int(re.sub(r"\D", "", entry.get("year", "")) or 0) or None
        month = MONTH_NUMBERS.get(entry.get("month", "").strip().lower()[:3], 0)
        venue = next((entry[f] for f in ("journal", "booktitle", "institution", "school",
                                         "publisher", "howpublished") if entry.get(f)), "")
        entries.append({
            "id": entry["ID"],
            "category": _category(entry),
            "title": _plain(entry.get("title", entry["ID"])),
            "authors": _authors(entry.get("author", ""), me),
            "venue": _plain(venue),
            "year": year,
            "note": _plain(entry.get("note", "")),
            "abstract": _plain(entry.get("abstract", "")),
            "links": _links(entry),
            "bibtex": _entry_bibtex(entry),
            "sort": (year or 0, month),
        })

    groups = []
    for key, title in GROUPS:
        members = sorted((e for e in entries if e["category"] == key),
                         key=lambda e: e["sort"], reverse=True)
        if members:
            groups.append({"key": key, "title": title, "entries": members})
    return groups
