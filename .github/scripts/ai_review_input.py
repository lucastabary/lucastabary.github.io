"""Flatten changed blog posts into one Markdown document for the AI review.

Notebooks are reduced to what a reader sees and what matters for a review:
Markdown cells, code, short text outputs, and markers for figures and errors.
Everything is capped so a large post cannot burn through the Copilot credits.

Usage: python ai_review_input.py OUT.md FILE [FILE ...]
Stdlib only, so it runs on the bare Actions runner.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MAX_CHARS = 60_000        # whole review input
MAX_OUTPUT_LINES = 15     # per code cell output


def text_of(value) -> str:
    return "".join(value) if isinstance(value, list) else str(value or "")


def truncate_lines(text: str, limit: int) -> str:
    lines = text.rstrip("\n").split("\n")
    if len(lines) <= limit:
        return "\n".join(lines)
    return "\n".join(lines[:limit] + [f"... ({len(lines) - limit} more lines)"])


def render_outputs(outputs: list) -> list[str]:
    parts = []
    for out in outputs:
        kind = out.get("output_type")
        if kind == "stream":
            parts.append(truncate_lines(text_of(out.get("text")), MAX_OUTPUT_LINES))
        elif kind == "error":
            parts.append(f"[ERROR {out.get('ename')}: {out.get('evalue')}]")
        elif kind in ("execute_result", "display_data"):
            data = out.get("data", {})
            if any(key.startswith("image/") for key in data):
                parts.append("[figure]")
            elif "text/plain" in data:
                parts.append(truncate_lines(text_of(data["text/plain"]), MAX_OUTPUT_LINES))
    return parts


def notebook_to_markdown(path: Path) -> str:
    nb = json.loads(path.read_text(encoding="utf-8"))
    blocks = [f"Notebook metadata (blog): {json.dumps(nb.get('metadata', {}).get('blog', {}))}"]
    for number, cell in enumerate(nb.get("cells", []), start=1):
        source = text_of(cell.get("source")).strip()
        tags = cell.get("metadata", {}).get("tags", [])
        tag_note = f" tags={tags}" if tags else ""
        if cell.get("cell_type") == "markdown":
            blocks.append(f"<!-- cell {number} markdown{tag_note} -->\n{source}")
        elif cell.get("cell_type") == "code" and source:
            block = f"<!-- cell {number} code{tag_note} -->\n```python\n{source}\n```"
            outputs = render_outputs(cell.get("outputs", []))
            if outputs:
                block += "\nOutput:\n```\n" + "\n".join(outputs) + "\n```"
            elif cell.get("execution_count") is None:
                block += "\n[not executed]"
            blocks.append(block)
    return "\n\n".join(blocks)


def main(out_path: str, files: list[str]) -> None:
    sections = []
    for name in files:
        path = Path(name)
        if not path.is_file():
            continue
        body = (notebook_to_markdown(path) if path.suffix == ".ipynb"
                else path.read_text(encoding="utf-8", errors="replace"))
        sections.append(f"# FILE: {name}\n\n{body}")

    text = "\n\n---\n\n".join(sections) or "(no reviewable post in this pull request)"
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + f"\n\n[TRUNCATED: input capped at {MAX_CHARS} characters]"
    Path(out_path).write_text(text, encoding="utf-8")
    print(f"{len(sections)} file(s), {len(text)} characters -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
