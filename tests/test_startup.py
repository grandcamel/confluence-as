"""Discovery runs through the installed entry point without the HTTP stack."""

from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "arguments",
    [
        ["api", "describe", "getPages"],
        ["api", "search", "page"],
        ["help"],
        ["--version"],
    ],
)
def test_discovery_does_not_import_http_or_legacy_stack(arguments, monkeypatch):
    monkeypatch.setenv("CONFLUENCE_AS_TRANSPORT", "responder")
    program = """
import runpy
import sys
from pathlib import Path

def reject_network(event, args):
    if event == 'socket.connect':
        raise AssertionError('discovery attempted a network connection')

sys.addaudithook(reject_network)
entry = Path(sys.executable).with_name('confluence-as')
sys.argv = ['confluence-as', *sys.argv[1:]]
try:
    runpy.run_path(str(entry), run_name='__main__')
except SystemExit as exc:
    assert exc.code in (None, 0), exc.code
for module in (
    'requests', 'assistant_skills_lib', 'jsonschema', 'yaml',
    'confluence_as.confluence_client', 'confluence_as.config_manager',
    'as_engine.converters',
):
    assert module not in sys.modules, module
"""
    result = subprocess.run(
        [sys.executable, "-c", program, *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()


def test_first_call_loads_scope_before_guard_and_transport(monkeypatch):
    program = """
import json
import sys
from click.testing import CliRunner
from confluence_as.cli.main import cli
from confluence_as import engine

surface = engine.create_surface(transport='responder')
assert 'confluence_as.config_manager' not in sys.modules
assert 'assistant_skills_lib' not in sys.modules
def forbidden(*args, **kwargs):
    raise AssertionError('scope refusal must precede transport construction')
surface.transport_factory = forbidden
engine.create_surface = lambda **kwargs: surface
result = CliRunner().invoke(cli, [
    'api', 'call', 'createPage', '--field', 'spaceId="55"', '--field', 'title=T',
])
assert result.exit_code == 4, (result.output, result.exception)
assert result.stdout == ''
error = json.loads(result.stderr)
assert error['operation'] == 'createPage', error
assert surface.scope_allowlist == ('DOCS',)
assert surface.scope_allow_site is False
assert 'confluence_as.config_manager' in sys.modules
"""
    monkeypatch.setenv("CONFLUENCE_ALLOWED_SPACES", "DOCS")
    monkeypatch.setenv("CONFLUENCE_ALLOW_SITE_OPERATIONS", "false")
    result = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_first_call_keeps_configuration_validation_error(monkeypatch):
    import json

    from click.testing import CliRunner

    from confluence_as.cli.main import cli
    from confluence_as.config_manager import ConfigManager

    monkeypatch.delenv("CONFLUENCE_ALLOWED_SPACES", raising=False)
    monkeypatch.setenv("CONFLUENCE_AS_TRANSPORT", "responder")
    monkeypatch.setattr(
        ConfigManager, "_load_config", lambda self: {"confluence": {"allowed_spaces": []}}
    )
    ConfigManager.reset_instance()
    try:
        result = CliRunner().invoke(cli, ["api", "call", "getPages"])
        assert result.exit_code == 2
        assert result.stdout == ""
        assert json.loads(result.stderr) == {
            "status": None,
            "messages": ["allowed_spaces must be comma-separated space keys"],
            "operation": None,
            "note": None,
        }
    finally:
        ConfigManager.reset_instance()


def test_scope_configuration_loads_once_and_preserves_consumer_overrides(monkeypatch):
    from as_engine.errors import SurfaceError

    from confluence_as.config_manager import ConfigManager
    from confluence_as.engine import create_surface

    scopes = []

    def scope(self):
        scopes.append(True)
        return {"scope_allowlist": ("DOCS",), "scope_allow_site": False}

    monkeypatch.setattr(ConfigManager, "get_scope_config", scope)
    surface = create_surface(transport="responder")
    surface.scope_allowlist = ()
    surface.scope_allow_site = True
    assert scopes == []
    for _ in range(2):
        with pytest.raises(SurfaceError):
            surface.call("missing-operation", {})
    assert scopes == [True]
    assert surface.scope_allowlist == ()
    assert surface.scope_allow_site is True
