"""
Shared pytest fixtures for all Confluence Assistant Skills tests.

Provides common fixtures used across multiple skill tests.
Skill-specific fixtures remain in their respective conftest.py files.

This root conftest.py centralizes:
- pytest hooks (addoption, configure, collection_modifyitems)
- Temporary directory fixtures
- Project structure fixtures
"""

import tempfile
from pathlib import Path

import pytest

LIVE_ROOT = Path(__file__).parent / "live"
LIVE_FILES = {
    "test_page_live.py",
    "test_property_live.py",
    "test_page_copy_live.py",
    "test_hierarchy_live.py",
    "test_page_versions_live.py",
    "test_space_content_live.py",
}
LIVE_SUPPORT = {"__init__.py", "conftest.py", "test_utils.py"}

# =============================================================================
# PYTEST HOOKS
# =============================================================================


def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--live", action="store_true", default=False, help="Run live integration tests"
    )
    parser.addoption(
        "--space-key", default="SBX", help="Live suite space (only SBX is supported)"
    )


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_collect_file(file_path, parent):
    """Secondary file check, not initial admission for arbitrary pytest selectors.

    Initial conftest/plugin imports can precede this hook. Only run_sbx.py is a
    supported live entrypoint; its fixed inputs establish pre-import admission.
    """
    if parent.config.getoption("--live") and file_path.suffix == ".py":
        path = file_path.absolute()
        root = LIVE_ROOT.absolute()
        if path.is_relative_to(root):
            relative = path.relative_to(root)
            allowed = LIVE_FILES | LIVE_SUPPORT
            if (
                len(relative.parts) != 1
                or relative.name not in allowed
                or path.resolve() != LIVE_ROOT.resolve() / relative.name
            ):
                raise pytest.UsageError(
                    "Unmigrated live module refused by secondary file check; "
                    "select only fixed run_sbx.py case choices"
                )
    yield


def pytest_configure(config):
    """Configure pytest with custom markers."""
    if config.getoption("--live") and not config.pluginmanager.hasplugin(
        "jas43_sbx_entrypoint"
    ):
        # An interface diagnostic, not authentication or pre-import containment.
        raise pytest.UsageError(
            "Raw pytest --live is unsupported; use the lane interpreter with "
            "-I and the canonical tests/live/run_sbx.py launcher"
        )
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks integration tests")
    config.addinivalue_line("markers", "live: marks tests requiring live API")
    config.addinivalue_line(
        "markers", "destructive: mark test as making destructive changes"
    )


def pytest_collection_modifyitems(config, items):
    """Skip live tests unless --live is provided."""
    if not config.getoption("--live"):
        skip_live = pytest.mark.skip(reason="Need --live to run")
        root = LIVE_ROOT.resolve()
        for item in items:
            # A checkout ancestor's spelling does not establish live membership.
            if item.get_closest_marker(
                "live"
            ) is not None or item.path.resolve().is_relative_to(root):
                item.add_marker(skip_live)


# =============================================================================
# TEMPORARY DIRECTORY FIXTURES
# =============================================================================


@pytest.fixture
def temp_path():
    """Create a temporary directory as Path object.

    Preferred fixture for new tests. Automatically cleaned up.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_dir(temp_path):
    """Create a temporary directory as string.

    Legacy compatibility. Prefer temp_path for new tests.
    """
    return str(temp_path)


# =============================================================================
# PROJECT STRUCTURE FIXTURES
# =============================================================================


@pytest.fixture
def claude_project_structure(temp_path):
    """Create a standard .claude project structure."""
    project = temp_path / "Test-Project"
    project.mkdir()

    claude_dir = project / ".claude"
    skills_dir = claude_dir / "skills"
    shared_lib = skills_dir / "shared" / "scripts" / "lib"
    shared_lib.mkdir(parents=True)

    settings = claude_dir / "settings.json"
    settings.write_text("{}")

    return {
        "root": project,
        "claude_dir": claude_dir,
        "skills_dir": skills_dir,
        "shared_lib": shared_lib,
        "settings": settings,
    }


@pytest.fixture
def sample_skill_md():
    """Return sample SKILL.md content."""
    return """---
name: sample-skill
description: A sample skill for testing.
---

# Sample Skill

## Quick Start

```bash
echo "Hello"
```
"""
