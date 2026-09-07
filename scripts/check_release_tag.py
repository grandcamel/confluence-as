#!/usr/bin/env python3
"""Check a release tag against source versions without importing the package."""

import ast
import re
import sys
from pathlib import Path


def check_release_tag(tag: str, root: Path) -> None:
    """Raise ValueError with a one-line reason when a release disagrees."""
    project = (root / "pyproject.toml").read_text(encoding="utf-8")
    section = re.search(r"(?ms)^\[project\]\s*\n(.*?)(?=^\[|\Z)", project)
    matches = re.findall(
        r"(?m)^version\s*=\s*([\"'][^\"'\n]+[\"'])\s*(?:#.*)?$",
        section[1] if section else "",
    )
    if len(matches) != 1:
        raise ValueError("pyproject.toml must contain one literal project version")
    package_version = ast.literal_eval(matches[0])
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?", package_version):
        raise ValueError("pyproject.toml has an unsupported release version")
    tree = ast.parse((root / "src/confluence_as/__init__.py").read_text(encoding="utf-8"))
    versions = [
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets)
    ]
    if versions != [package_version]:
        raise ValueError("__version__ does not match pyproject.toml")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = re.findall(r"(?m)^## \[([^\]\n]+)\]", changelog)
    releases = [heading for heading in headings if heading != "Unreleased"]
    if not releases or releases[0] != package_version:
        raise ValueError("top CHANGELOG.md release does not match pyproject.toml")
    if tag != f"v{package_version}":
        raise ValueError(f"tag must be v{package_version}")


def main() -> int:
    if len(sys.argv) != 2:
        print("release check: expected one v<version> tag", file=sys.stderr)
        return 1
    try:
        check_release_tag(sys.argv[1], Path(__file__).resolve().parents[1])
    except (OSError, ValueError, SyntaxError) as exc:
        reason = " ".join(str(exc).splitlines())
        print(f"release check: {reason}", file=sys.stderr)
        return 1
    print(f"release check: {sys.argv[1]} matches package and changelog")
    return 0


if __name__ == "__main__":
    sys.exit(main())
