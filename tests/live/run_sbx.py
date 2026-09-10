"""Controlled SBX test entrypoint; invoke with the lane's python -I.

Only standard-library code runs before argument, environment and path admission.
The interpreter, installed dependencies and named source are trusted and frozen
by the supervisor. This is not arbitrary-code containment or atomic protection
against concurrent source replacement. It does not establish live authority.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import stat
import sys
from collections import Counter
from pathlib import Path

PAGE_CASES = (
    "test_create_read_page",
    "test_create_child_page",
    "test_update_page_title",
    "test_markdown_storage_roundtrip",
    "test_page_version_increment",
    "test_delete_page_observed_in_filtered_list",
)
PROPERTY_CASES = (
    "test_indexed_property_create_read_delete",
    "test_indexed_property_versioned_update",
    "test_property_set_wrapper_create_and_upsert",
)
TRANCHE2 = {
    "copy": {
        "tests/live/test_page_copy_live.py": (
            "test_copy_owned_leaf_same_sbx_nonrecursive",
        )
    },
    "tree": {
        "tests/live/test_hierarchy_live.py": (
            "test_tree_matches_owned_root_child_grandchild",
        )
    },
    "versions": {
        "tests/live/test_page_versions_live.py": (
            "test_versions_match_owned_page_updates",
        )
    },
    "space-content": {
        "tests/live/test_space_content_live.py": (
            "test_space_listing_matches_exact_owned_ids",
        )
    },
}
CASES = {
    "pages": {"tests/live/test_page_live.py": PAGE_CASES},
    "properties": {"tests/live/test_property_live.py": PROPERTY_CASES},
    "all": {
        "tests/live/test_page_live.py": PAGE_CASES,
        "tests/live/test_property_live.py": PROPERTY_CASES,
    },
    **TRANCHE2,
    "tranche2": {
        path: names for choice in TRANCHE2.values() for path, names in choice.items()
    },
}
SUPPORT = (
    "tests/live/run_sbx.py",
    "tests/__init__.py",
    "tests/live/__init__.py",
    "tests/conftest.py",
    "tests/live/conftest.py",
    "tests/live/test_utils.py",
)


def validate_paths(root, selected):
    """Require canonical regular files, rejecting every in-lane symlink component."""
    for relative in (*SUPPORT, *selected):
        path = root
        parts = Path(relative).parts
        for index, part in enumerate(parts):
            path = path / part
            mode = path.lstat().st_mode
            valid_type = stat.S_ISREG if index == len(parts) - 1 else stat.S_ISDIR
            if stat.S_ISLNK(mode) or not valid_type(mode):
                raise ValueError(f"Non-regular or symlink source refused: {relative}")
        if path.resolve(strict=True) != path or not path.is_relative_to(root):
            raise ValueError(f"Noncanonical source refused: {relative}")


def load_trusted_module(name, path, *, package=False):
    """Load named package/support files explicitly, never discover conftests."""
    if name in sys.modules:
        raise ValueError(f"Trusted module name already loaded: {name}")
    spec = importlib.util.spec_from_file_location(
        name, path, submodule_search_locations=[str(path.parent)] if package else None
    )
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load trusted module: {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def validate_import_path(root):
    """Refuse repository-root search paths without rewriting the environment."""
    if any(Path(entry).resolve() == root for entry in sys.path):
        raise ValueError("Repository root must remain absent from sys.path")


class Admission:
    # Pytest uses __name__ for registration of explicitly supplied plugin objects.
    __name__ = "jas43_sbx_entrypoint"

    def __init__(self, root, selected, pytest):
        self.root = root
        self.selected = selected
        self.pytest = pytest

    def pytest_ignore_collect(self, collection_path):
        """Limit traversal to the already admitted files and their ancestors.

        Pytest visits siblings while resolving explicit files. This avoids
        feeding unrelated siblings to the secondary file hook; it is not the
        initial argument/path admission boundary and accepts no raw selectors.
        """
        return not any(
            collection_path == self.root / relative
            or collection_path in (self.root / relative).parents
            for relative in self.selected
        )

    def pytest_collection_finish(self, session):
        """Compare the final collection before any fixture setup, including counts."""
        try:
            validate_import_path(self.root)
        except ValueError as error:
            raise self.pytest.UsageError(str(error)) from error
        expected = Counter(
            f"{path}::{name}" for path, names in self.selected.items() for name in names
        )
        actual = Counter(item.nodeid for item in session.items)
        paths_match = all(
            item.path == self.root / item.nodeid.split("::", 1)[0]
            for item in session.items
        )
        if not expected or actual != expected or not paths_match:
            raise self.pytest.UsageError(
                "SBX collection must contain exactly the approved nonempty nodes "
                "without missing, extra or duplicate cases"
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--case", choices=tuple(CASES), default="all")
    parser.add_argument("--collect-only", action="store_true")
    if "--" in sys.argv[1:]:
        parser.error("Raw selectors and -- are not supported")
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]) and len(sys.argv) != 2:
        parser.error("Help must be requested alone")
    options = parser.parse_args()
    selected = CASES[options.case]
    try:
        root = Path(__file__).parents[2].resolve(strict=True)
        launcher = root / "tests/live/run_sbx.py"
        if not sys.flags.isolated:
            raise ValueError("Use the exact lane interpreter with -I")
        if sys.executable != str(root / ".venv/bin/python"):
            raise ValueError("Use the exact lane interpreter with -I")
        if sys.argv[0] != str(launcher) or Path(__file__) != launcher:
            raise ValueError("Use the canonical absolute launcher path")
        validate_paths(root, selected)
        validate_import_path(root)
        for name in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
            if os.environ.get(name):
                raise ValueError(f"Ambient {name} is not supported")
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))

    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    # Installed pytest/dependencies use the prepared environment. Only the
    # explicitly loaded tests packages receive repository-local __path__ values.
    import pytest

    try:
        validate_import_path(root)
        load_trusted_module("tests", root / "tests/__init__.py", package=True)
        load_trusted_module("tests.live", root / "tests/live/__init__.py", package=True)
        root_plugin = load_trusted_module("tests.conftest", root / "tests/conftest.py")
        live_plugin = load_trusted_module(
            "tests.live.conftest", root / "tests/live/conftest.py"
        )
        admission = Admission(root, selected, pytest)
        args = [
            *(str(root / path) for path in selected),
            "--noconftest",
            "--import-mode=importlib",
            "-c",
            "/dev/null",
            "--rootdir",
            str(root),
            "--live",
            "--space-key",
            "SBX",
            "--capture=no",
            "-v",
            "--tb=short",
            "--maxfail=1",
            "-o",
            "addopts=",
            "-o",
            "pythonpath=",
        ]
        if options.collect_only:
            args.append("--collect-only")
        validate_paths(root, selected)
        validate_import_path(root)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    return int(pytest.main(args, plugins=[root_plugin, live_plugin, admission]))


if __name__ == "__main__":
    raise SystemExit(main())
