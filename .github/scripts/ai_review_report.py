"""Turn the model's JSON review into a PR comment and a pass/fail signal.

The workflow fails when the review has "must fix" items, so the check can gate a
merge. A response that is not valid JSON is posted as-is and also fails, rather
than silently passing.

Usage: python ai_review_report.py RESPONSE_FILE COMMENT_OUT MODEL
Writes `must_fix=<n>` and `parsed=<true|false>` to $GITHUB_OUTPUT when set.
Stdlib only, so it runs on the bare Actions runner.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

VERDICTS = {
    "ready": "✅ Ready to publish",
    "minor": "🟡 Minor fixes",
    "major": "🔴 Major issues",
}
FOOTER = ("<sub>Automated review ({model} via Copilot), not a substitute for checking "
          "claims and references yourself. Add the `ai-review` label again for a new "
          "review.</sub>")


def parse(raw: str) -> dict | None:
    """The JSON object in the response, tolerating a Markdown fence or stray text."""
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    elif not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        text = text[start:end + 1] if start != -1 and end > start else text
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def items(data: dict, key: str) -> list:
    value = data.get(key) or []
    return value if isinstance(value, list) else [value]


def issue_section(title: str, entries: list) -> list[str]:
    lines = [f"### {title} ({len(entries)})"]
    if not entries:
        return lines + ["None.", ""]
    for n, entry in enumerate(entries, start=1):
        if isinstance(entry, dict):
            lines.append(f"{n}. **{entry.get('location', '?')}**: {entry.get('problem', '')}")
            if entry.get("fix"):
                lines.append(f"   *Fix:* {entry['fix']}")
        else:
            lines.append(f"{n}. {entry}")
    return lines + [""]


def list_section(title: str, entries: list) -> list[str]:
    lines = [f"### {title}"]
    lines += [f"- {entry}" for entry in entries] if entries else ["None."]
    return lines + [""]


def render(data: dict) -> tuple[str, int]:
    must_fix = items(data, "must_fix")
    verdict = VERDICTS.get(str(data.get("verdict", "")).lower(), f"❔ {data.get('verdict')}")
    lines = [f"## AI review of the post: {verdict}", "", str(data.get("summary", "")).strip(), ""]
    lines += issue_section("Must fix", must_fix)
    lines += issue_section("Should fix", items(data, "should_fix"))
    lines += list_section("Nitpicks", items(data, "nitpicks")[:5])
    lines += list_section("Could not check", items(data, "could_not_check"))
    return "\n".join(lines), len(must_fix)


def main(response_file: str, comment_out: str, model: str) -> None:
    raw = Path(response_file).read_text(encoding="utf-8")
    data = parse(raw)
    if data is None:
        body = ("## AI review of the post: ⚠️ unreadable response\n\n"
                "The model did not return valid JSON, so this check fails. Raw answer:\n\n"
                f"<details><summary>Response</summary>\n\n{raw}\n\n</details>\n")
        must_fix, parsed = -1, False
    else:
        body, must_fix = render(data)
        parsed = True

    Path(comment_out).write_text(f"{body}\n---\n{FOOTER.format(model=model)}\n", encoding="utf-8")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
            out.write(f"must_fix={must_fix}\nparsed={str(parsed).lower()}\n")
    print(f"parsed={parsed} must_fix={must_fix}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
