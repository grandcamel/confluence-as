#!/usr/bin/env python3
"""Render and verify the 2.0.0 removed-wrapper-verb changelog section."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="product root (defaults to the directory containing scripts/)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail unless CHANGELOG.md's 2.0.0 Removed section matches the inventory",
    )
    return parser.parse_args()


def render_removed_verbs(root: Path) -> str:
    records = json.loads((root / "tests" / "wrapper_verbs.json").read_text())
    dropped = [record for record in records if record.get("decision") == "dropped"]
    verbs = [record.get("verb") for record in dropped]
    if len(verbs) != len(set(verbs)):
        raise ValueError("dropped wrapper verbs must be unique")

    lines = []
    for record in sorted(dropped, key=lambda item: item["verb"]):
        verb = record["verb"]
        replacement = record.get("replacement")
        if not isinstance(replacement, str) or not replacement.startswith("api call "):
            raise ValueError(f"{verb!r} has no api call replacement")
        lines.append(f"- `{verb}` → `{replacement}`")
    return "\n".join(lines)


def removed_section(changelog: str) -> str:
    release_match = re.search(
        r"^## \[2\.0\.0(?:(?:a|b|rc)\d+)?\]", changelog, re.MULTILINE
    )
    if release_match is None:
        raise ValueError("CHANGELOG.md has no 2.0.0 release section")
    release = changelog[release_match.start() :]
    next_release = release.find("\n## [")
    if next_release >= 0:
        release = release[:next_release]

    heading = "### Removed\n"
    section_start = release.find(heading)
    if section_start < 0:
        raise ValueError("CHANGELOG.md's 2.0.0 section has no Removed subsection")
    section = release[section_start + len(heading) :]
    next_section = section.find("\n### ")
    if next_section >= 0:
        section = section[:next_section]
    return "\n".join(line for line in section.splitlines() if line.startswith("- "))


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    try:
        rendered = render_removed_verbs(root)
        if not args.check:
            print(rendered)
            return 0
        actual = removed_section((root / "CHANGELOG.md").read_text())
    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError) as error:
        print(f"changelog removed verbs: {error}", file=sys.stderr)
        return 1

    if actual != rendered:
        print(
            "changelog removed verbs: CHANGELOG.md differs from wrapper_verbs.json",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
