"""Fixtures for the first guarded SBX tranche; runtime is supervisor owned.

Live execution uses the controlled run_sbx.py entrypoint. Raw pytest --live is
unsupported; root conftest supplies only a secondary diagnostic, not protection
from initial plugin/conftest imports. Nothing here initializes credentials at
import time.
"""

import os

import pytest

from tests.live.test_utils import LiveRun, validate_live_environment


@pytest.fixture(scope="session")
def live_run(request):
    validate_live_environment(
        os.environ,
        space_key=request.config.getoption("--space-key"),
        capture=request.config.getoption("capture"),
    )
    run = LiveRun()
    # Register before bootstrap, so a later setup assertion cannot lose a candidate.
    request.addfinalizer(run.cleanup)
    run.create_page("root")
    return run


@pytest.fixture
def live_page(live_run):
    # Every creation is registered immediately in the session finalizer's journal.
    # A setup failure or a failing test therefore retains all known identities.
    return live_run.create_page("case", parent=live_run.root)
