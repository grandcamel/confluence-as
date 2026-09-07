"""Release-documentation contracts exercised through public script argv."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from confluence_as import __version__
from confluence_as.cli.main import cli

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "changelog_removed_verbs.py"
TAG_CHECKER = ROOT / "scripts" / "check_release_tag.py"
INDEXES = (
    ROOT / "src/confluence_as/_generated/v1.index.json",
    ROOT / "src/confluence_as/_generated/v2.index.json",
)


def run(*arguments: str, root: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT)]
    if root is not None:
        command.extend(["--root", str(root)])
    command.extend(arguments)
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )


def markdown_lines(records: list[dict[str, str]]) -> list[str]:
    return [
        f"- `{record['verb']}` → `{record['replacement']}`"
        for record in sorted(records, key=lambda record: record["verb"])
    ]


def compiled_legacy_records() -> list[dict[str, str]]:
    records = []
    for index_path in INDEXES:
        index = json.loads(index_path.read_text())
        for operation in index["operations"].values():
            for legacy in operation.get("extensions", {}).get("x-as-legacy-verbs", []):
                records.append(
                    {
                        "verb": f"{legacy['group']} {legacy['verb']}",
                        "replacement": legacy["invocation"],
                    }
                )
    return records


def removed_section(changelog: str) -> list[str]:
    release_match = re.search(
        r"^## \[2\.0\.0(?:(?:a|b|rc)\d+)?\]", changelog, re.MULTILINE
    )
    assert release_match is not None
    release = changelog[release_match.start() :].split("\n## [", 1)[0]
    section = release.split("### Removed\n", 1)[1].split("\n### ", 1)[0]
    return [line for line in section.splitlines() if line.startswith("- ")]


def test_removed_verbs_script_default_output_matches_inventory():
    rows = json.loads((ROOT / "tests/wrapper_verbs.json").read_text())
    dropped = [row for row in rows if row["decision"] == "dropped"]

    result = run()

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.splitlines() == markdown_lines(dropped)
    assert len(result.stdout.splitlines()) == 70


def test_removed_verbs_changelog_matches_compiled_legacy_rename_entries():
    compiled = compiled_legacy_records()

    assert len(compiled) == 70
    assert len({record["verb"] for record in compiled}) == 70
    assert removed_section((ROOT / "CHANGELOG.md").read_text()) == markdown_lines(
        compiled
    )


def test_check_rejects_missing_extra_and_changed_changelog_entries(tmp_path):
    fixture = tmp_path / "product"
    (fixture / "tests").mkdir(parents=True)
    rows = [
        {
            "verb": "page get",
            "decision": "dropped",
            "replacement": "api call getPage --id ID",
        },
        {
            "verb": "page list",
            "decision": "dropped",
            "replacement": "api call getPages --all",
        },
    ]
    (fixture / "tests/wrapper_verbs.json").write_text(json.dumps(rows))
    expected = "\n".join(markdown_lines(rows))
    (fixture / "CHANGELOG.md").write_text(
        "## [2.0.0] - Unreleased\n\n### Removed\n\n" + expected + "\n\n### Added\n"
    )

    assert run("--check", root=fixture).returncode == 0

    for altered in (
        expected.splitlines()[0],
        expected + "\n- `page search` → `api call searchPages --all`",
        expected.replace("getPage --id ID", "getPages --id ID"),
    ):
        (fixture / "CHANGELOG.md").write_text(
            "## [2.0.0] - Unreleased\n\n### Removed\n\n" + altered + "\n\n### Added\n"
        )
        result = run("--check", root=fixture)
        assert result.returncode == 1
        assert "differs" in result.stderr


def test_script_rejects_duplicate_dropped_verbs(tmp_path):
    fixture = tmp_path / "product"
    (fixture / "tests").mkdir(parents=True)
    (fixture / "tests/wrapper_verbs.json").write_text(
        json.dumps(
            [
                {
                    "verb": "page get",
                    "decision": "dropped",
                    "replacement": "api call getPage --id ID",
                },
                {
                    "verb": "page get",
                    "decision": "dropped",
                    "replacement": "api call getPages --id ID",
                },
            ]
        )
    )

    result = run(root=fixture)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "must be unique" in result.stderr


def release_tree(tmp_path: Path, version: str = "2.0.0rc1") -> Path:
    root = tmp_path / "release"
    (root / "scripts").mkdir(parents=True)
    (root / "src/confluence_as").mkdir(parents=True)
    shutil.copyfile(TAG_CHECKER, root / "scripts/check_release_tag.py")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "confluence-as"\nversion = "' + version + '"\n'
    )
    (root / "src/confluence_as/__init__.py").write_text(
        '__version__ = "' + version + '"\n'
    )
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [" + version + "] - 2026-09-07\n"
    )
    return root


def run_tag_check(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(root / "scripts/check_release_tag.py"), *arguments],
        cwd=root.parent,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("version", ["2.0.0", "2.0.0a1", "2.0.0b1", "2.0.0rc1"])
def test_release_tag_checker_accepts_canonical_release_versions(tmp_path, version):
    root = release_tree(tmp_path, version)

    result = run_tag_check(root, f"v{version}")

    assert result.returncode == 0, result.stderr
    assert result.stdout == f"release check: v{version} matches package and changelog\n"


@pytest.mark.parametrize(
    "path, old, new",
    [
        ("pyproject.toml", 'version = "2.0.0rc1"', 'version = "9.9.9"'),
        (
            "src/confluence_as/__init__.py",
            '__version__ = "2.0.0rc1"',
            '__version__ = "9.9.9"',
        ),
        ("CHANGELOG.md", "## [2.0.0rc1]", "## [9.9.9]"),
    ],
)
def test_release_tag_checker_rejects_release_file_mismatches(tmp_path, path, old, new):
    root = release_tree(tmp_path)
    target = root / path
    target.write_text(target.read_text().replace(old, new, 1))

    result = run_tag_check(root, "v2.0.0rc1")

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("release check: ")


def test_release_tag_checker_uses_first_release_not_historical_duplicate(tmp_path):
    root = release_tree(tmp_path)
    changelog = root / "CHANGELOG.md"
    changelog.write_text("## [9.9.9] - 2026-09-07\n\n" + changelog.read_text())

    result = run_tag_check(root, "v2.0.0rc1")

    assert result.returncode == 1
    assert "top CHANGELOG.md release" in result.stderr


@pytest.mark.parametrize(
    "tag",
    ["2.0.0rc1", "v2.0.0", "v2.0.0rc2", "v2.0.0rc1\n"],
)
def test_release_tag_checker_rejects_wrong_tag(tmp_path, tag):
    root = release_tree(tmp_path)

    result = run_tag_check(root, tag)

    assert result.returncode == 1
    assert "tag must be v2.0.0rc1" in result.stderr


def test_release_tag_checker_rejects_missing_tag(tmp_path):
    root = release_tree(tmp_path)

    result = run_tag_check(root)

    assert result.returncode == 1
    assert result.stderr == "release check: expected one v<version> tag\n"


def test_release_tag_checker_accepts_tag_time_copy_of_actual_release_files(tmp_path):
    root = tmp_path / "release"
    (root / "scripts").mkdir(parents=True)
    (root / "src/confluence_as").mkdir(parents=True)
    shutil.copyfile(TAG_CHECKER, root / "scripts/check_release_tag.py")
    shutil.copyfile(ROOT / "pyproject.toml", root / "pyproject.toml")
    shutil.copyfile(
        ROOT / "src/confluence_as/__init__.py", root / "src/confluence_as/__init__.py"
    )
    changelog = (ROOT / "CHANGELOG.md").read_text()
    changelog = changelog.replace(
        "## [2.0.0] - Unreleased", f"## [{__version__}] - 2026-09-07", 1
    )
    (root / "CHANGELOG.md").write_text(changelog)

    result = run_tag_check(root, f"v{__version__}")

    assert result.returncode == 0, result.stderr


def test_cli_reports_exact_package_version():
    result = CliRunner().invoke(cli, ["--version"])

    assert re.fullmatch(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?", __version__)
    assert result.exit_code == 0
    assert result.output == f"confluence-as, version {__version__}\n"
