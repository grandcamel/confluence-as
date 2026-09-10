"""Offline contracts for live collection, real CLI scope guards, and receipts.

These tests never authorize a host run. Product calls use the ordinary recording
transport seam; fixture failure tests also use a small scripted argv driver to
exercise abrupt failures without a second implementation of the Confluence API.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import textwrap
import venv
from pathlib import Path

import pytest
import requests
from as_engine.index import ProductIndexes
from as_engine.responder import Responder
from as_engine.transport import Response
from click.testing import CliRunner

from confluence_as import engine
from confluence_as.cli.main import cli
from confluence_as.config_manager import ConfigManager
from tests.live.test_utils import (
    LiveContractError,
    LiveRun,
    Resource,
    validate_live_environment,
)


@pytest.fixture
def recorded(monkeypatch):
    class Recorded(Responder):
        def __init__(self, index):
            super().__init__(index)
            self.roles = []
            self.answer = None

        def call(self, operation, parameters, body):
            self.roles.append(
                "resolution"
                if operation.extensions.get("x-as-resolution-read")
                else "operation"
            )
            if self.answer is not None:
                self.seed(
                    operation.operationId, [self.answer(operation, parameters, body)]
                )
            return super().call(operation, parameters, body)

    indexes = ProductIndexes(Path(__file__).parents[1] / "src/confluence_as/_generated")
    transport = Recorded(indexes.get("v2"))
    monkeypatch.setattr(engine, "Responder", lambda *args, **kwargs: transport)
    monkeypatch.setattr(ConfigManager, "_find_claude_dir", lambda self: None)
    for name in tuple(os.environ):
        if name.startswith("CONFLUENCE_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("CONFLUENCE_ALLOWED_SPACES", "SBX")
    monkeypatch.setenv("CONFLUENCE_AS_TRANSPORT", "responder")
    ConfigManager.reset_instance()

    def forbidden(*args, **kwargs):
        raise AssertionError("Real HTTP attempted by an offline contract")

    monkeypatch.setattr(requests.Session, "request", forbidden)
    yield transport
    ConfigManager.reset_instance()


def invoke(*args):
    return CliRunner().invoke(cli, ["api", "call", *args])


def refusal(result):
    assert result.exit_code == 4, (result.exit_code, result.stdout, result.stderr)
    assert result.stdout == ""
    error = json.loads(result.stderr)
    assert error["status"] is None
    assert error["messages"]


@pytest.mark.parametrize(
    "flags",
    [(), ("--space", "ENG"), ("--space", ""), ("--space", "SBX", "--space-key", "ENG")],
)
def test_create_scope_refuses_before_any_send(recorded, flags):
    body = () if "--space-key" in flags else ("--field", 'spaceId="55"')
    refusal(invoke("createPage", *body, "--field", "title=T", "--confirm", *flags))
    assert recorded.requests == []


@pytest.mark.parametrize("operation", ["getSpaces", "createSpace"])
def test_site_calls_refuse_even_with_sbx_and_confirm(recorded, operation):
    flags = ("--keys", "SBX") if operation == "getSpaces" else ("--field", "key=SBX")
    refusal(invoke(operation, *flags, "--confirm"))
    assert recorded.requests == []


@pytest.mark.parametrize(
    "lookup",
    [
        {"results": []},
        {"results": [{"id": "55", "key": "ENG"}]},
        {"results": [{"id": "55", "key": "SBX"}, {"id": "66", "key": "SBX"}]},
        {"results": [{"id": "55", "key": "SBX"}], "_links": {"next": "?cursor=next"}},
        Response(503, {"message": "unavailable"}),
    ],
)
def test_unproven_lookup_never_creates(recorded, lookup):
    recorded.seed("getSpaces", [lookup])
    refusal(
        invoke(
            "createPage",
            "--space",
            "SBX",
            "--space-key",
            "SBX",
            "--field",
            "title=T",
            "--confirm",
        )
    )
    assert recorded.roles == ["resolution"]
    assert recorded.requests[0] == ("getSpaces", {"keys": ["SBX"]}, None)


def test_numeric_body_mismatch_never_creates(recorded):
    recorded.seed("getSpaces", [{"results": [{"id": "55", "key": "SBX"}]}])
    refusal(
        invoke("createPage", "--space", "SBX", "--field", 'spaceId="66"', "--confirm")
    )
    assert recorded.roles == ["resolution"]


@pytest.mark.parametrize(
    "operation,flags",
    [
        ("getPageById", ["--id", "123", "--body-format", "storage"]),
        ("updatePage", ["--id", "123", "--field", "title=T"]),
        ("deletePage", ["--id", "123"]),
        ("getChildPages", ["--id", "123", "--limit", "2"]),
        ("getPageVersions", ["--id", "123", "--limit", "4"]),
        ("getPageContentProperties", ["--page-id", "123"]),
        ("getPageContentPropertiesById", ["--page-id", "123", "--property-id", "456"]),
        ("createPageProperty", ["--page-id", "123", "--field", "key=owned"]),
        ("updatePagePropertyById", ["--page-id", "123", "--property-id", "456"]),
        ("deletePagePropertyById", ["--page-id", "123", "--property-id", "456"]),
    ],
)
def test_foreign_numeric_page_has_metadata_only(recorded, operation, flags):
    recorded.seed("getPageById", [{"id": "123", "spaceId": "66"}])
    recorded.seed("getSpaces", [{"results": [{"id": "66", "key": "ENG"}]}])
    refusal(invoke(operation, *flags, "--confirm"))
    assert recorded.roles == ["resolution", "resolution"]
    assert recorded.requests == [
        ("getPageById", {"id": 123}, None),
        ("getSpaces", {"ids": [66]}, None),
    ]


def test_empty_policy_refuses_before_metadata(recorded, monkeypatch):
    monkeypatch.setenv("CONFLUENCE_ALLOWED_SPACES", "")
    ConfigManager.reset_instance()
    refusal(invoke("getPageById", "--id", "123"))
    assert recorded.requests == []


@pytest.mark.parametrize(
    "operation,flags,parameters,body",
    [
        (
            "getPageContentProperties",
            ["--page-id", "123"],
            {"page-id": 123},
            {"results": [{"id": "456", "key": "owned", "value": {"count": 3}}]},
        ),
        (
            "getPageContentPropertiesById",
            ["--page-id", "123", "--property-id", "456"],
            {"page-id": 123, "property-id": 456},
            {"id": "456", "key": "owned", "value": {"enabled": True}},
        ),
    ],
)
def test_sbx_property_reads_follow_membership_proof(
    recorded, operation, flags, parameters, body
):
    recorded.seed("getPageById", [{"id": "123", "spaceId": "55"}])
    recorded.seed("getSpaces", [{"results": [{"id": "55", "key": "SBX"}]}])
    recorded.seed(operation, [body])
    result = invoke(operation, *flags)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == body
    assert recorded.roles == ["resolution", "resolution", "operation"]
    assert recorded.requests == [
        ("getPageById", {"id": 123}, None),
        ("getSpaces", {"ids": [55]}, None),
        (operation, parameters, None),
    ]


def test_positive_create_has_one_resolution_and_real_requested_operation(recorded):
    recorded.seed("getSpaces", [{"results": [{"id": "55", "key": "SBX"}]}])
    recorded.seed("createPage", [{"id": "123", "title": "T", "spaceId": "55"}])
    result = invoke(
        "createPage", "--space", "SBX", "--space-key", "SBX", "--field", "title=T"
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["id"] == "123"
    assert recorded.roles == ["resolution", "operation"]
    assert recorded.requests[-1] == ("createPage", {}, {"title": "T", "spaceId": "55"})


def rows(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]


class ScriptedArgv:
    """Explicit expected argv operations and response/failure steps, no API model."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.calls = []
        self.inputs = []

    def __call__(self, argv, stdin=None):
        self.calls.append(argv)
        self.inputs.append(stdin)
        if "--body" in argv:
            assert argv[argv.index("--body") + 1] == "-"
            assert isinstance(stdin, str)
        else:
            assert stdin is None
        assert self.steps, "Unexpected CLI invocation"
        operation, response = self.steps.pop(0)
        actual = (
            " ".join(argv[:2])
            if argv[:2]
            in (["property", "set"], ["page", "copy"], ["hierarchy", "tree"])
            else argv[2]
        )
        assert actual == operation
        if isinstance(response, BaseException):
            raise response
        return response(argv, stdin) if callable(response) else response


def owned_run(*steps):
    stream = io.StringIO()
    driver = ScriptedArgv(*steps)
    run = LiveRun(stream=stream, invoke=driver)
    run.space_id = "55"
    page = Resource("page", "123", None, run.name("root"), "owned")
    run.resources[page.token] = page
    run.root = page
    return run, page, driver, stream


def page_response(page, **overrides):
    return {
        "id": page.id,
        "title": page.name,
        "spaceId": "55",
        "status": "current",
        "body": {"storage": {"representation": "storage", "value": "<p>T</p>"}},
        "version": {"number": 1},
        **overrides,
    }


def test_positive_live_helper_uses_real_cli_guard_and_stream(recorded):
    stream = io.StringIO()
    run = LiveRun(stream=stream)
    # The helper's random title is supplied explicitly to seeded response bodies.
    title = run.name("root")
    run.name = lambda purpose: title
    page = {"id": "123", "title": title, "spaceId": "55", "status": "current"}
    recorded.seed("getSpaces", [{"results": [{"id": "55", "key": "SBX"}]}] * 5)
    recorded.seed("createPage", [page])
    recorded.seed("getPageById", [page, page])
    recorded.seed("getSpaceById", [{"id": "55", "key": "SBX", "type": "global"}])
    resource = run.create_page("root")
    assert resource.state == "owned"
    assert recorded.requests[0] == ("getSpaces", {"keys": ["SBX"]}, None)
    assert recorded.requests[1] == (
        "createPage",
        {},
        {
            "title": title,
            "status": "current",
            "spaceId": "55",
            "body": {
                "representation": "storage",
                "value": "<p>JAS-43 owned content.</p>",
            },
        },
    )
    events = rows(stream)
    candidate = next(i for i, row in enumerate(events) if row["event"] == "candidate")
    readback = next(
        i
        for i, row in enumerate(events)
        if row.get("operation") == "getPageById" and row["event"] == "intent"
    )
    assert candidate < readback
    assert events[-1]["event"] == "owned"


def test_live_helper_stdin_preserves_typed_json_body(recorded):
    run = LiveRun(stream=io.StringIO())
    body = {
        "key": run.name("property"),
        "value": {
            "count": 3,
            "enabled": True,
            "missing": None,
            "items": ["one", 2],
        },
    }
    recorded.seed("getPageById", [{"id": "123", "spaceId": "55"}])
    recorded.seed("getSpaces", [{"results": [{"id": "55", "key": "SBX"}]}])
    recorded.seed("createPageProperty", [{"id": "456", **body}])
    result = run.call("createPageProperty", {"page-id": "123"}, body, mutation=True)
    assert result == {"id": "456", **body}
    assert recorded.roles == ["resolution", "resolution", "operation"]
    assert recorded.requests[-1] == ("createPageProperty", {"page-id": 123}, body)


@pytest.mark.parametrize(
    "change", ["unowned", "foreign-run", "wrong-kind", "duplicate-object"]
)
def test_delete_refuses_unowned_identity_before_argv(change):
    run, page, driver, stream = owned_run()
    if change == "unowned":
        run.resources.clear()
    elif change == "foreign-run":
        page.name = "jas43-other-run-page"
    elif change == "wrong-kind":
        page.kind = "space"
    else:
        page = Resource("page", "123", None, page.name, "owned")
    with pytest.raises(LiveContractError):
        run.delete_page(page)
    assert driver.calls == []


@pytest.mark.parametrize(
    "kind,state",
    [
        ("page", "owned"),
        ("property", "owned"),
        ("page", "candidate"),
        ("property", "uncertain"),
    ],
)
def test_explicit_parent_delete_refuses_dependencies_before_argv(kind, state):
    run, page, driver, stream = owned_run()
    child = Resource(kind, "456", page.token, run.name("child"), state)
    run.resources[child.token] = child
    with pytest.raises(LiveContractError, match="dependencies"):
        run.delete_page(page)
    assert driver.calls == []
    assert child.state == state


def test_wrong_space_readback_never_deletes():
    run, page, driver, stream = owned_run()
    driver.steps = [("getPageById", page_response(page, spaceId="66"))]
    with pytest.raises(LiveContractError, match="space"):
        run.delete_page(page)
    assert [argv[2] for argv in driver.calls] == ["getPageById"]


def test_parent_substitution_refuses_before_create():
    run, page, driver, stream = owned_run()
    foreign = Resource("page", "456", None, run.name("imposter"), "owned")
    with pytest.raises(LiveContractError):
        run.create_page(parent=foreign)
    assert driver.calls == []


def test_property_wrong_key_refuses_before_mutation():
    run, page, driver, stream = owned_run()
    prop = Resource("property", "456", page.token, run.name("property"), "owned")
    run.resources[prop.token] = prop
    driver.steps = [
        ("getPageById", page_response(page)),
        ("getPageContentPropertiesById", {"id": "456", "key": "foreign-key"}),
    ]
    with pytest.raises(LiveContractError, match="key"):
        run.delete_property(prop)
    assert [argv[2] for argv in driver.calls] == [
        "getPageById",
        "getPageContentPropertiesById",
    ]


def test_property_wrong_id_or_parent_never_mutates():
    run, page, driver, stream = owned_run()
    prop = Resource("property", "456", ("page", "999"), run.name("property"), "owned")
    run.resources[prop.token] = prop
    with pytest.raises(LiveContractError, match="parent"):
        run.delete_property(prop)
    assert driver.calls == []
    prop.parent = page.token
    driver.steps = [
        ("getPageById", page_response(page)),
        ("getPageContentPropertiesById", {"id": "999", "key": prop.name}),
    ]
    with pytest.raises(LiveContractError, match="ID"):
        run.delete_property(prop)
    assert not any(argv[2].startswith("delete") for argv in driver.calls)


def test_successful_delete_requires_filtered_absence_and_does_not_repeat():
    run, page, driver, stream = owned_run()
    driver.steps = [
        ("getPageById", page_response(page)),
        ("deletePage", None),
        ("getPages", {"results": []}),
    ]
    run.delete_page(page)
    assert page.state == "deleted"
    assert driver.calls[-1][driver.calls[-1].index("--space-id") + 1] == '["55"]'
    assert driver.calls[-1][driver.calls[-1].index("--id") + 1] == '["123"]'
    run.cleanup()
    assert len(driver.calls) == 3
    assert rows(stream)[-1]["event"] == "complete"


@pytest.mark.parametrize(
    "absence",
    [
        {"results": [{"id": "123", "spaceId": "55"}]},
        {"results": [], "_links": {"next": "?cursor=next"}},
        LiveContractError("metadata 404"),
    ],
)
def test_uncertain_delete_retains_identity(absence):
    run, page, driver, stream = owned_run()
    driver.steps = [
        ("getPageById", page_response(page)),
        ("deletePage", None),
        ("getPages", absence),
    ]
    with pytest.raises(LiveContractError):
        run.delete_page(page)
    assert page.state == "uncertain"
    with pytest.raises(LiveContractError, match="incomplete"):
        run.cleanup()
    assert any(
        row["event"] == "residual" and row["id"] == "123" for row in rows(stream)
    )


def test_candidate_is_flushed_before_readback_failure():
    run, parent, driver, stream = owned_run()

    def created(argv, stdin):
        body = json.loads(stdin)
        return {"id": "456", "title": body["title"], "spaceId": "55"}

    def failed_read(argv, stdin):
        assert any(
            row["event"] == "candidate" and row["id"] == "456" for row in rows(stream)
        )
        raise RuntimeError("PRIVATE SERVER BODY")

    driver.steps = [
        ("getPageById", page_response(parent)),
        ("createPage", created),
        ("getPageById", failed_read),
    ]
    with pytest.raises(LiveContractError):
        run.create_page(parent=parent)
    assert run.resources[("page", "456")].state == "candidate"
    with pytest.raises(LiveContractError, match="incomplete"):
        run.cleanup()
    assert not any(argv[2] == "deletePage" for argv in driver.calls)
    assert "PRIVATE SERVER BODY" not in stream.getvalue()


def test_unknown_create_blocks_parent_cleanup_without_guessing():
    run, parent, driver, stream = owned_run()
    driver.steps = [
        ("getPageById", page_response(parent)),
        ("createPage", TimeoutError("PRIVATE TOKEN")),
    ]
    with pytest.raises(LiveContractError):
        run.create_page(parent=parent)
    with pytest.raises(LiveContractError, match="incomplete"):
        run.cleanup()
    assert parent.state == "owned"
    assert len(run.pending) == 1
    assert not any(argv[2] == "deletePage" for argv in driver.calls)
    assert "PRIVATE TOKEN" not in stream.getvalue()
    assert any(row["event"] == "unknown-outcome" for row in rows(stream))


def test_duplicate_candidate_preserves_existing_identity():
    run, parent, driver, stream = owned_run()
    driver.steps = [
        ("getPageById", page_response(parent)),
        ("createPage", {"id": "123", "title": "duplicate", "spaceId": "55"}),
    ]
    with pytest.raises(LiveContractError):
        run.create_page(parent=parent)
    assert run.resources[parent.token] is parent
    assert run.pending
    assert any(row["event"] == "candidate" for row in rows(stream))


def test_cleanup_child_failure_does_not_delete_parent_or_infer_cascade():
    run, parent, driver, stream = owned_run()
    child = Resource("page", "456", parent.token, run.name("child"), "owned")
    run.resources[child.token] = child
    driver.steps = [
        ("getPageById", page_response(child, parentId=parent.id)),
        ("deletePage", LiveContractError("failure")),
    ]
    with pytest.raises(LiveContractError, match="incomplete"):
        run.cleanup()
    deletes = [argv for argv in driver.calls if argv[2] == "deletePage"]
    assert len(deletes) == 1 and deletes[0][deletes[0].index("--id") + 1] == child.id
    assert parent.state == child.state == "owned"
    assert {row["id"] for row in rows(stream) if row["event"] == "residual"} == {
        "123",
        "456",
    }


def test_property_cleanup_precedes_page_and_proves_both_absent():
    run, page, driver, stream = owned_run()
    prop = Resource("property", "456", page.token, run.name("property"), "owned")
    run.resources[prop.token] = prop
    driver.steps = [
        ("getPageById", page_response(page)),
        ("getPageContentPropertiesById", {"id": "456", "key": prop.name}),
        ("deletePagePropertyById", None),
        ("getPageById", page_response(page)),
        ("getPageContentProperties", []),
        ("getPageById", page_response(page)),
        ("deletePage", None),
        ("getPages", {"results": []}),
    ]
    run.cleanup()
    assert [row["kind"] for row in rows(stream) if row["event"] == "cleanup"] == [
        "property",
        "page",
    ]
    assert page.state == prop.state == "deleted"
    assert not driver.steps


@pytest.mark.parametrize(
    "operation",
    [
        "deleteSpace",
        "createBlogPost",
        "searchByCQL",
        "createAttachment",
        "addLabelsToContent",
        "addRestrictions",
    ],
)
def test_helper_does_not_admit_held_operations(operation):
    run, page, driver, stream = owned_run()
    with pytest.raises(LiveContractError, match="outside"):
        run.call(operation)
    assert driver.calls == []


def clean_subprocess_environment():
    # No parent credentials, inherited pytest options or product transport policy.
    env = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "SYSTEMROOT", "LANG", "LC_ALL", "TMPDIR"}
    }
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


INERT_CASES = {
    "test_page_copy_live.py": ("test_copy_owned_leaf_same_sbx_nonrecursive",),
    "test_hierarchy_live.py": ("test_tree_matches_owned_root_child_grandchild",),
    "test_page_versions_live.py": ("test_versions_match_owned_page_updates",),
    "test_space_content_live.py": ("test_space_listing_matches_exact_owned_ids",),
    "test_page_live.py": (
        "test_create_read_page",
        "test_create_child_page",
        "test_update_page_title",
        "test_markdown_storage_roundtrip",
        "test_page_version_increment",
        "test_delete_page_observed_in_filtered_list",
    ),
    "test_property_live.py": (
        "test_indexed_property_create_read_delete",
        "test_indexed_property_versioned_update",
        "test_property_set_wrapper_create_and_upsert",
    ),
}


@pytest.fixture
def entrypoint(tmp_path):
    """Copy trusted support; inert cases never request the real live fixtures.

    Real CLI/Surface contracts above retain the product guard. This fixture only
    exercises the subprocess admission interface and pytest's plugin discovery.
    """
    scratch = tmp_path.resolve()
    root = scratch / "project"
    live = root / "tests/live"
    live.mkdir(parents=True)
    source = Path(__file__).parent
    for relative in (
        "__init__.py",
        "conftest.py",
        "live/__init__.py",
        "live/conftest.py",
        "live/test_utils.py",
        "live/run_sbx.py",
    ):
        shutil.copyfile(source / relative, root / "tests" / relative)
    # A real private venv preserves exact interpreter identity on macOS; a
    # whole-venv symlink can normalize sys.executable to the original lane.
    # No pip/install/network or writes to the prepared environment.
    private_venv = root / ".venv"
    venv.EnvBuilder(with_pip=False, symlinks=True).create(private_venv)
    private_site = (
        private_venv
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    prepared_paths = dict.fromkeys(
        [
            sysconfig.get_path("purelib"),
            sysconfig.get_path("platlib"),
            str(Path(engine.__file__).resolve().parents[1]),
        ]
    )
    # Referenced site-packages .pth files are not executed recursively. Include
    # the exact prepared editable product's src directory, never its repo root.
    (private_site / "prepared-dependencies.pth").write_text(
        "\n".join(prepared_paths) + "\n", encoding="utf-8"
    )
    prepared_product = Path(engine.__file__).resolve().parent / "__init__.py"
    cwd = scratch / "private/work"
    home = scratch / "private/home"
    cwd.mkdir(parents=True)
    home.mkdir()
    poison = scratch / "POISON_IMPORTED"
    trusted = scratch / "TRUSTED_IMPORTED"
    setup = scratch / "FIXTURE_SETUP"
    poison_code = (
        "from pathlib import Path\n"
        f"Path({str(poison)!r}).write_text('poison')\n"
        "raise RuntimeError('POISON IMPORT EXECUTED')\n"
    )
    nested = live / "nested"
    nested.mkdir()
    for path in (
        scratch / "conftest.py",
        root / "conftest.py",
        cwd.parent / "conftest.py",
        cwd / "conftest.py",
        nested / "conftest.py",
        nested / "test_poison.py",
        live / "test_poison.py",
        root / "outside.py",
        root / "jas43_poison.py",
        root / "confluence_as.py",
        root / "as_engine.py",
        root / "jas43_untrusted_root_only.py",
        root / "pytest.py",
        live / "pytest.py",
    ):
        path.write_text(poison_code, encoding="utf-8")
    (root / "outside_alias.py").symlink_to(live / "test_poison.py")
    (root / "pytest.ini").write_text(
        "[pytest]\naddopts = --unapproved-config-option\n"
        "pythonpath = unapproved-pythonpath\n",
        encoding="utf-8",
    )
    # Both entry-point metadata and its importable module are PRIVATE, so the
    # autoload control does not depend on exposing the repository root.
    (private_site / "jas43_poison.py").write_text(poison_code, encoding="utf-8")
    distribution = private_site / "jas43_poison-1.0.dist-info"
    distribution.mkdir()
    (distribution / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: jas43-poison\nVersion: 1.0\n",
        encoding="utf-8",
    )
    (distribution / "entry_points.txt").write_text(
        "[pytest11]\njas43_poison = jas43_poison\n",
        encoding="utf-8",
    )
    package = root / "tests/__init__.py"
    package.write_text(
        package.read_text() + "\nimport sys\nfrom pathlib import Path\n"
        f"assert all(Path(p).resolve() != Path({str(root)!r}) for p in sys.path)\n"
        f"Path({str(trusted)!r}).write_text('trusted')\n",
        encoding="utf-8",
    )
    root_plugin = root / "tests/conftest.py"
    private_poison_plugin_path = str(private_site / "jas43_poison.py")
    root_plugin.write_text(
        root_plugin.read_text()
        + textwrap.dedent(f"""

        import os
        import importlib.metadata
        import importlib.util
        import sys
        Path({str(trusted)!r}).write_text('trusted')
        assert os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] == '1'
        assert sys.executable == {str(private_venv / "bin/python")!r}
        assert all(Path(p).resolve() != Path({str(root)!r}) for p in sys.path)

        def pytest_sessionstart(session):
            config = session.config
            conftests = {{str(Path(p.__file__).resolve())
                         for p in config.pluginmanager.get_plugins()
                         if getattr(p, '__file__', '').endswith('/conftest.py')}}
            assert conftests == {{
                {str(root_plugin)!r}, {str(live / "conftest.py")!r}}}
            assert config.pluginmanager.hasplugin('jas43_sbx_entrypoint')
            assert not config.pluginmanager.hasplugin('jas43_poison')
            assert any(ep.name == 'jas43_poison' for ep in
                       importlib.metadata.entry_points(group='pytest11'))
            assert importlib.util.find_spec('jas43_poison').origin == {private_poison_plugin_path!r}
            assert config.getoption('noconftest') is True
            assert config.getoption('importmode') == 'importlib'
            assert str(config.inipath) == '/dev/null'
            assert config.rootpath == Path({str(root)!r})
            assert config.getini('addopts') == []
            assert config.getini('pythonpath') == []
            assert config.getoption('--live') is True
            assert config.getoption('--space-key') == 'SBX'
            assert config.getoption('capture') == 'no'
            assert config.getoption('tbstyle') == 'short'
            assert config.getoption('maxfail') == 1
            assert config.getoption('verbose') == 1
            assert Path.cwd() == Path({str(cwd)!r})
            assert os.environ['HOME'] == {str(home)!r}
            assert all(Path(p).resolve() != Path({str(root)!r}) for p in sys.path)

        def pytest_collection_finish(session):
            assert all(Path(p).resolve() != Path({str(root)!r}) for p in sys.path)

        @pytest.fixture(autouse=True)
        def entrypoint_setup():
            Path({str(setup)!r}).write_text('setup')
        """),
        encoding="utf-8",
    )
    for filename, names in INERT_CASES.items():
        (live / filename).write_text(
            "import os, sys, importlib.util\nfrom pathlib import Path\n"
            f"assert all(Path(p).resolve() != Path({str(root)!r}) for p in sys.path)\n"
            "import confluence_as, as_engine\n"
            f"assert Path(confluence_as.__file__).resolve() == Path({str(prepared_product)!r})\n"
            "assert importlib.util.find_spec('jas43_untrusted_root_only') is None\n"
            + "\n".join(
                f"def {name}():\n"
                f"    assert all(Path(p).resolve() != Path({str(root)!r}) for p in sys.path)\n"
                f"    assert Path(confluence_as.__file__).resolve() == Path({str(prepared_product)!r})\n"
                f"    assert Path.cwd() == Path({str(cwd)!r})\n"
                f"    assert os.environ['HOME'] == {str(home)!r}\n"
                for name in names
            ),
            encoding="utf-8",
        )
    env = clean_subprocess_environment()
    # The launcher must disable autoload itself, even if the caller set it to 0.
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "0"
    env["HOME"] = str(home)
    return {
        "root": root,
        "live": live,
        "cwd": cwd,
        "home": home,
        "poison": poison,
        "trusted": trusted,
        "setup": setup,
        "env": env,
        "python": root / ".venv/bin/python",
        "launcher": live / "run_sbx.py",
    }


def run_entrypoint(entrypoint, *args, isolated=True, launcher=None):
    return subprocess.run(
        [
            str(entrypoint["python"]),
            *(["-I"] if isolated else []),
            "-B",
            str(launcher or entrypoint["launcher"]),
            *args,
        ],
        cwd=entrypoint["cwd"],
        env=entrypoint["env"],
        capture_output=True,
        text=True,
        timeout=30,
    )


def assert_entrypoint_refused(entrypoint, result, *, before_import=True):
    assert result.returncode != 0, result.stdout + result.stderr
    assert not entrypoint["poison"].exists()
    assert not entrypoint["setup"].exists()
    if before_import:
        assert not entrypoint["trusted"].exists()


@pytest.mark.parametrize(
    "args",
    [
        ("tests/live",),
        ("tests/live/nested",),
        ("tests/live/nested/test_poison.py",),
        ("tests/live/test_poison.py",),
        ("tests/live/test_poison.py::test_never",),
        ("tests/live/test_page_live.py::test_create_read_page",),
        ("outside.py",),
        ("outside_alias.py",),
        ("--case", "unknown"),
        ("--cas", "pages"),
        ("--case",),
        ("-p", "jas43_poison"),
        ("--pyargs", "jas43_poison"),
        ("--override-ini", "addopts=-p jas43_poison"),
        ("-o", "pythonpath=outside"),
        ("-c", "pytest.ini"),
        ("-k", "create"),
        ("-m", "live"),
        ("@options.txt",),
        ("--", "tests/live/test_page_live.py"),
        ("--",),
        ("--rootdir", "/tmp"),
        ("--space-key", "ENG"),
        ("--capture", "sys"),
        ("--keep-space",),
        ("--live",),
        ("--help", "-p", "jas43_poison"),
    ],
)
def test_entrypoint_rejects_raw_selectors_and_overrides_before_import(entrypoint, args):
    (entrypoint["cwd"] / "options.txt").write_text(
        "-p jas43_poison\n", encoding="utf-8"
    )
    result = run_entrypoint(entrypoint, *args)
    assert_entrypoint_refused(entrypoint, result)
    assert "error:" in result.stderr


@pytest.mark.parametrize(
    "selector",
    [
        "tests/live",
        "tests/live/nested",
        "tests/live/nested/test_poison.py",
        "tests/live/test_poison.py::test_never",
        "outside.py",
        "outside_alias.py",
    ],
)
def test_entrypoint_rejects_absolute_existing_poison_selectors(entrypoint, selector):
    path, separator, node = selector.partition("::")
    selection = str(entrypoint["root"] / path) + separator + node
    result = run_entrypoint(entrypoint, selection)
    assert_entrypoint_refused(entrypoint, result)
    assert "error:" in result.stderr


@pytest.mark.parametrize("name", ["PYTEST_ADDOPTS", "PYTEST_PLUGINS"])
def test_entrypoint_rejects_ambient_pytest_injection_before_import(entrypoint, name):
    entrypoint["env"][name] = (
        "-p jas43_poison" if name == "PYTEST_ADDOPTS" else "jas43_poison"
    )
    result = run_entrypoint(entrypoint)
    assert_entrypoint_refused(entrypoint, result)
    assert f"Ambient {name}" in result.stderr


@pytest.mark.parametrize(
    "relative",
    [
        "tests/__init__.py",
        "tests/conftest.py",
        "tests/live/__init__.py",
        "tests/live/conftest.py",
        "tests/live/test_utils.py",
        "tests/live/test_page_live.py",
        "tests/live/test_property_live.py",
    ],
)
@pytest.mark.parametrize("change", ["missing", "symlink", "directory"])
def test_entrypoint_validates_all_selected_and_support_files(
    entrypoint, relative, change
):
    path = entrypoint["root"] / relative
    path.unlink()
    if change == "symlink":
        path.symlink_to(entrypoint["root"] / "outside.py")
    elif change == "directory":
        path.mkdir()
    result = run_entrypoint(entrypoint)
    assert_entrypoint_refused(entrypoint, result)
    assert "error:" in result.stderr
    assert "Use the exact lane interpreter" not in result.stderr
    assert str(path) in result.stderr or relative in result.stderr


@pytest.mark.parametrize("component", ["tests", "tests/live"])
def test_entrypoint_rejects_symlink_directory_escape(entrypoint, component):
    original = entrypoint["root"] / component
    moved = entrypoint["root"].parent / "outside-tree"
    original.rename(moved)
    original.symlink_to(moved, target_is_directory=True)
    result = run_entrypoint(entrypoint)
    assert_entrypoint_refused(entrypoint, result)
    assert "symlink source refused" in result.stderr


@pytest.mark.parametrize(
    "mode", ["symlink", "relative", "no-isolation", "wrong-python"]
)
def test_entrypoint_requires_canonical_launcher_and_lane_python(entrypoint, mode):
    launcher = entrypoint["launcher"]
    if mode == "symlink":
        alias = entrypoint["live"] / "alias.py"
        alias.symlink_to(launcher)
        launcher = alias
    elif mode == "relative":
        launcher = os.path.relpath(launcher, entrypoint["cwd"])
    elif mode == "wrong-python":
        entrypoint["python"] = Path(sys.executable)
    result = run_entrypoint(
        entrypoint, launcher=launcher, isolated=mode != "no-isolation"
    )
    assert_entrypoint_refused(entrypoint, result)
    expected = (
        "Use the exact lane interpreter"
        if mode in {"no-isolation", "wrong-python"}
        else "Use the canonical absolute launcher path"
    )
    assert expected in result.stderr


@pytest.mark.parametrize(
    "case,count",
    [
        ("pages", 6),
        ("properties", 3),
        ("all", 9),
        ("copy", 1),
        ("tree", 1),
        ("versions", 1),
        ("space-content", 1),
        ("tranche2", 4),
    ],
)
@pytest.mark.parametrize("collect_only", [False, True])
def test_entrypoint_exact_admission_ignores_poison_config_and_autoload(
    entrypoint, case, count, collect_only
):
    args = ["--case", case, *(["--collect-only"] if collect_only else [])]
    result = run_entrypoint(entrypoint, *args)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = (
        ("test collected" if count == 1 else "tests collected")
        if collect_only
        else "passed"
    )
    assert f"{count} {summary}" in result.stdout
    assert entrypoint["trusted"].exists()
    assert entrypoint["setup"].exists() == (not collect_only)
    assert not entrypoint["poison"].exists()
    for filename, names in INERT_CASES.items():
        selected_files = {
            "pages": {"test_page_live.py"},
            "properties": {"test_property_live.py"},
            "all": {"test_page_live.py", "test_property_live.py"},
            "copy": {"test_page_copy_live.py"},
            "tree": {"test_hierarchy_live.py"},
            "versions": {"test_page_versions_live.py"},
            "space-content": {"test_space_content_live.py"},
            "tranche2": {
                "test_page_copy_live.py",
                "test_hierarchy_live.py",
                "test_page_versions_live.py",
                "test_space_content_live.py",
            },
        }
        selected = filename in selected_files[case]
        if selected:
            assert all(name in result.stdout for name in names)
        else:
            assert all(name not in result.stdout for name in names)


def test_entrypoint_default_is_all(entrypoint):
    result = run_entrypoint(entrypoint)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "9 passed" in result.stdout
    assert not entrypoint["poison"].exists()


def test_entrypoint_help_exits_without_loading_repository(entrypoint):
    result = run_entrypoint(entrypoint, "--help")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--case" in result.stdout and "--collect-only" in result.stdout
    assert not entrypoint["trusted"].exists()
    assert not entrypoint["poison"].exists()
    assert not entrypoint["setup"].exists()


@pytest.mark.parametrize("change", ["extra", "empty", "missing", "duplicate"])
def test_entrypoint_refuses_inexact_collection_before_fixture_setup(entrypoint, change):
    page_file = entrypoint["live"] / "test_page_live.py"
    if change == "empty":
        page_file.write_text("", encoding="utf-8")
    elif change == "missing":
        page_file.write_text(
            page_file.read_text().replace("def test_create_read_page", "def held_case"),
            encoding="utf-8",
        )
    elif change == "extra":
        page_file.write_text(
            page_file.read_text() + "\ndef test_extra():\n    assert False\n",
            encoding="utf-8",
        )
    else:
        plugin = entrypoint["root"] / "tests/conftest.py"
        plugin.write_text(
            plugin.read_text() + "\ndef pytest_collection_modifyitems(items):\n"
            "    items.append(items[0])\n",
            encoding="utf-8",
        )
    result = run_entrypoint(entrypoint, "--case", "pages")
    assert_entrypoint_refused(entrypoint, result, before_import=False)
    assert "exactly the approved nonempty nodes" in result.stdout + result.stderr


def test_entrypoint_rechecks_paths_after_trusted_plugin_loading(entrypoint):
    plugin = entrypoint["root"] / "tests/conftest.py"
    selected = entrypoint["live"] / "test_page_live.py"
    plugin.write_text(
        plugin.read_text() + f"\nPath({str(selected)!r}).unlink()\n"
        f"Path({str(selected)!r}).symlink_to({str(entrypoint['root'] / 'outside.py')!r})\n",
        encoding="utf-8",
    )
    result = run_entrypoint(entrypoint)
    assert_entrypoint_refused(entrypoint, result, before_import=False)
    assert entrypoint["trusted"].exists()
    assert "symlink source refused" in result.stderr


def test_raw_live_diagnostic_and_default_offline_optout(tmp_path):
    # This only asserts a diagnostic and offline skipping, never pre-import safety.
    live = tmp_path / "tests/live"
    live.mkdir(parents=True)
    shutil.copyfile(Path(__file__).parent / "conftest.py", live.parent / "conftest.py")
    (live / "test_page_live.py").write_text(
        "def test_active():\n    assert True\n", encoding="utf-8"
    )
    for flags, expected in [((), 0), (("--live",), 4)]:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/live/test_page_live.py",
                "-q",
                *flags,
            ],
            cwd=tmp_path,
            env=clean_subprocess_environment(),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == expected, result.stdout + result.stderr
        if flags:
            assert "Raw pytest --live is unsupported" in result.stderr
        else:
            assert "1 skipped" in result.stdout


def test_offline_optout_ignores_tests_live_in_checkout_ancestors(tmp_path):
    root = tmp_path.resolve() / "tests/live/checkout"
    test_dir = root / "tests"
    live = test_dir / "live"
    live.mkdir(parents=True)
    shutil.copyfile(Path(__file__).parent / "conftest.py", test_dir / "conftest.py")
    ordinary = test_dir / "test_ordinary.py"
    ordinary.write_text(
        "import pytest\n"
        "def test_ordinary():\n    assert True\n"
        "@pytest.mark.live\n"
        "def test_marked_live():\n    raise AssertionError('marked live ran')\n",
        encoding="utf-8",
    )
    actual_live = live / "test_page_live.py"
    actual_live.write_text(
        "def test_actual_live():\n    raise AssertionError('actual live ran')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-m",
            "pytest",
            "-c",
            "/dev/null",
            "--rootdir",
            str(root),
            str(ordinary),
            str(actual_live),
            "-q",
        ],
        cwd=tmp_path,
        env=clean_subprocess_environment(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed, 2 skipped" in result.stdout


def test_receipt_survives_abrupt_stop_outside_cli_capture(tmp_path):
    helper = Path(__file__).parent / "live" / "test_utils.py"
    script = tmp_path / "abrupt.py"
    script.write_text(
        "import json, os, runpy\n"
        "from click.testing import CliRunner\nimport click\n"
        f"LiveRun = runpy.run_path({str(helper)!r})['LiveRun']\n"
        "@click.command()\ndef abrupt():\n"
        "    click.echo('PRIVATE CAPTURED BODY')\n"
        "    os._exit(23)\n"
        "def invoke(argv, stdin=None):\n"
        "    if argv[2] == 'createPage':\n"
        "        assert argv[argv.index('--body') + 1] == '-'\n"
        "        body = json.loads(stdin)\n"
        "        return {'id': '123', 'title': body['title'], 'spaceId': '55'}\n"
        "    CliRunner().invoke(abrupt, [])\n"
        "run = LiveRun(invoke=invoke)\n"
        "run.create_page('root')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        env=clean_subprocess_environment(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 23
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert [row["event"] for row in events] == [
        "start",
        "intent",
        "candidate",
        "mutation",
        "intent",
    ]
    assert events[2]["id"] == "123" and events[2]["state"] == "candidate"
    assert events[-1]["operation"] == "getPageById"
    assert "PRIVATE CAPTURED BODY" not in result.stdout + result.stderr


def test_live_environment_requires_exact_host_policy():
    base = {
        "CONFLUENCE_ALLOWED_SPACES": "SBX",
        "CONFLUENCE_SITE_URL": "https://example.invalid",
        "CONFLUENCE_EMAIL": "offline@example.invalid",
        "CONFLUENCE_API_TOKEN": "offline-placeholder",
    }
    validate_live_environment(base, space_key="SBX", capture="no")
    variants = [
        {**base, "CONFLUENCE_ALLOWED_SPACES": "SBX,ENG"},
        {**base, "CONFLUENCE_ALLOWED_SPACES": ""},
        {**base, "CONFLUENCE_ALLOW_SITE_OPERATIONS": "0"},
        {**base, "CONFLUENCE_AS_TRANSPORT": "responder"},
        {**base, "CONFLUENCE_AS_CASSETTE": ""},
        {**base, "CONFLUENCE_MOCK_MODE": "false"},
        {},
    ]
    for environment in variants:
        with pytest.raises(LiveContractError):
            validate_live_environment(environment, space_key="SBX", capture="no")
    with pytest.raises(LiveContractError):
        validate_live_environment(base, space_key="ENG", capture="no")
    with pytest.raises(LiveContractError):
        validate_live_environment(base, space_key="SBX", capture="fd")


def test_upsert_unexpected_new_id_is_preserved_before_rejection():
    run, page, driver, stream = owned_run()
    prop = Resource("property", "456", page.token, run.name("property"), "owned")
    run.resources[prop.token] = prop
    driver.steps = [
        ("getPageById", page_response(page)),
        (
            "getPageContentPropertiesById",
            {"id": "456", "key": prop.name, "value": 1, "version": {"number": 1}},
        ),
        ("property set", {"property": {"id": "789", "key": prop.name, "value": 2}}),
    ]
    with pytest.raises(LiveContractError, match="ID mismatch"):
        run.update_property(prop, 2, wrapper=True)
    candidate = run.resources[("property", "789")]
    assert candidate.state == "candidate" and candidate.parent == page.token
    assert any(
        row["event"] == "candidate" and row["id"] == "789" for row in rows(stream)
    )
    assert prop.state == "uncertain"
    with pytest.raises(LiveContractError, match="incomplete"):
        run.cleanup()
    assert not any(
        argv[:2] == ["api", "call"] and argv[2].startswith("delete")
        for argv in driver.calls
    )


def test_failed_assertion_after_owned_create_keeps_cleanup_obligation():
    run, parent, driver, stream = owned_run()
    created = {}

    def create(argv, stdin):
        payload = json.loads(stdin)
        created.update(
            id="456", title=payload["title"], spaceId="55", parentId=parent.id
        )
        return dict(created)

    driver.steps = [
        ("getPageById", page_response(parent)),
        ("createPage", create),
        ("getPageById", lambda argv, stdin: dict(created)),
        ("getPageById", lambda argv, stdin: dict(created)),
        ("deletePage", None),
        ("getPages", {"results": []}),
        ("getPageById", page_response(parent)),
        ("deletePage", None),
        ("getPages", {"results": []}),
    ]
    with pytest.raises(AssertionError, match="test assertion"):
        try:
            child = run.create_page(parent=parent)
            assert child.state == "owned"
            raise AssertionError("test assertion")
        finally:
            run.cleanup()
    assert [row["id"] for row in rows(stream) if row["event"] == "cleanup"] == [
        "456",
        "123",
    ]
    assert rows(stream)[-1]["event"] == "complete"
    assert not driver.steps


def test_real_fixture_finalizer_survives_bootstrap_setup_failure(entrypoint):
    """Exercise pytest's actual setup/finalizer lifecycle using the shipped fixture."""
    live = entrypoint["live"]
    # No product or HTTP double here: the fake run isolates pytest's lifecycle
    # obligation. The transport and resource contracts are exercised above.
    fixture_source = (live / "conftest.py").read_text()
    fixture_source += """
class SetupFailureRun:
    def create_page(self, purpose):
        print("SETUP-CANDIDATE-123", flush=True)
        raise RuntimeError("injected setup failure")
    def cleanup(self):
        print("REGISTERED-CLEANUP-123", flush=True)
LiveRun = SetupFailureRun
"""
    (live / "conftest.py").write_text(fixture_source, encoding="utf-8")
    (live / "test_page_live.py").write_text(
        "\n".join(
            f"def {name}(live_run):\n"
            "    print('TEST-BODY-EXECUTED', flush=True)\n"
            "    raise AssertionError('test body executed')\n"
            for name in INERT_CASES["test_page_live.py"]
        ),
        encoding="utf-8",
    )
    entrypoint["env"].update(
        CONFLUENCE_ALLOWED_SPACES="SBX",
        CONFLUENCE_API_TOKEN="offline-placeholder",
        CONFLUENCE_EMAIL="offline@example.invalid",
        CONFLUENCE_SITE_URL="https://example.invalid",
    )
    result = run_entrypoint(entrypoint, "--case", "pages")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "collected 6 items" in result.stdout
    assert result.stdout.count("SETUP-CANDIDATE-123") == 1
    assert result.stdout.count("REGISTERED-CLEANUP-123") == 1
    assert result.stdout.index("SETUP-CANDIDATE-123") < result.stdout.index(
        "REGISTERED-CLEANUP-123"
    )
    assert "TEST-BODY-EXECUTED" not in result.stdout
    assert "exactly the approved nonempty nodes" not in result.stdout + result.stderr
    assert not entrypoint["poison"].exists()
    assert "1 error" in result.stdout


@pytest.fixture
def tranche(recorded):
    """Explicit transport responses; CLI parsing, transforms and scope stay real."""
    stream = io.StringIO()
    run = LiveRun(stream=stream)
    run.space_id = "55"
    root = Resource("page", "123", None, run.name("root"), "owned")
    leaf = Resource("page", "456", root.token, run.name("leaf"), "owned")
    other = Resource("page", "789", root.token, run.name("other"), "owned")
    run.root = root
    run.resources.update({p.token: p for p in (root, leaf, other)})
    data = {
        p.id: page_response(p, **({"parentId": p.parent[1]} if p.parent else {}))
        for p in (root, leaf, other)
    }
    answers = {
        "getPageById": lambda parameters, body: data[str(parameters["id"])],
        "getSpaces": {"results": [{"id": "55", "key": "SBX"}]},
        "getSpaceById": {"id": "55", "key": "SBX", "type": "global"},
        "getChildPages": {"results": []},
    }

    def answer(operation, parameters, body):
        assert operation.operationId in answers, "Unplanned transport operation"
        response = answers[operation.operationId]
        return response(parameters, body) if callable(response) else response

    recorded.answer = answer
    return run, root, leaf, other, data, answers, recorded, stream


def operations(recorded):
    return [
        request
        for request, role in zip(recorded.requests, recorded.roles)
        if role == "operation"
    ]


def prepare_copy(tranche, *, change=None):
    run, root, leaf, other, data, answers, recorded, stream = tranche

    def create(parameters, body):
        assert parameters == {}
        assert body == {
            "title": body["title"],
            "status": "current",
            "spaceId": "55",
            "parentId": root.id,
            "body": data[leaf.id]["body"]["storage"],
        }
        assert body["title"].startswith(run.prefix + "copy-")
        copied = {**data[leaf.id], "id": "999", "title": body["title"]}
        if change:
            copied.update(change)
        data["999"] = copied
        return copied

    answers["createPage"] = create


def test_copy_real_cli_parent_snapshot_one_create_candidate_and_cleanup(tranche):
    run, root, leaf, other, data, answers, recorded, stream = tranche
    prepare_copy(tranche)
    read_page = answers["getPageById"]

    def read_after_journal(parameters, body):
        if str(parameters["id"]) == "999":
            assert any(
                row["event"] == "candidate" and row["id"] == "999"
                for row in rows(stream)
            )
        return read_page(parameters, body)

    answers["getPageById"] = read_after_journal
    copied = run.copy_leaf(leaf, root)
    assert copied.id == "999" and copied.state == "owned"
    requested = operations(recorded)
    assert [(op, parameters) for op, parameters, body in requested] == [
        ("getPageById", {"id": 456, "body-format": "storage"}),
        ("getPageById", {"id": 123, "body-format": "storage"}),
        ("getPageById", {"id": 456, "body-format": "storage"}),
        ("getChildPages", {"id": 456, "limit": 2}),
        ("getPageById", {"id": 456, "body-format": "storage"}),
        ("getSpaceById", {"id": 55}),
        ("getChildPages", {"id": 456}),
        ("createPage", {}),
        ("getPageById", {"id": 999, "body-format": "storage"}),
    ]
    events = rows(stream)
    candidate = next(i for i, row in enumerate(events) if row["event"] == "candidate")
    assert events[candidate]["id"] == copied.id
    assert events[candidate + 1]["event"] == "mutation"
    assert events[candidate + 2]["operation"] == "getPageById"
    assert events[candidate + 2]["event"] == "intent"
    answers["deletePage"] = None
    answers["getPages"] = {"results": []}
    run.cleanup()
    deleted = [
        parameters["id"]
        for op, parameters, body in operations(recorded)
        if op == "deletePage"
    ]
    assert deleted == [999, 789, 456, 123]
    assert rows(stream)[-1]["event"] == "complete"
    assert not run.pending


@pytest.mark.parametrize(
    "change",
    [
        {"id": "456"},
        {"id": "123"},
        {"id": "789"},
        {"id": None},
        {"spaceId": "66"},
        {"title": "foreign"},
        {"parentId": "789"},
        {"body": {"storage": {"value": "wrong"}}},
        {"status": "archived"},
    ],
)
def test_copy_real_cli_rejects_wrong_result_and_keeps_receipt(tranche, change):
    run, root, leaf, other, data, answers, recorded, stream = tranche
    prepare_copy(tranche, change=change)
    with pytest.raises(LiveContractError):
        run.copy_leaf(leaf, root)
    assert len([r for r in operations(recorded) if r[0] == "createPage"]) == 1
    assert run.resources[leaf.token] is leaf and run.resources[root.token] is root
    if change.get("id", "999") is not None:
        assert any(row["event"] == "candidate" for row in rows(stream))
    else:
        assert run.pending
    with pytest.raises(LiveContractError):
        run.delete_page(root)
    assert not any(r[0] == "deletePage" for r in recorded.requests)


@pytest.mark.parametrize(
    "response",
    [
        {"results": [{"id": "888", "title": "unknown"}]},
        {"results": [], "_links": {"next": "?cursor=more"}},
        {"results": [{"id": "456"}, {"id": "456"}]},
        {"results": [None]},
        {},
    ],
)
def test_copy_preflight_refuses_unknown_or_incomplete_children_and_blocks_parent(
    tranche, response
):
    run, root, leaf, other, data, answers, recorded, stream = tranche
    answers["getChildPages"] = response
    with pytest.raises(LiveContractError):
        run.copy_leaf(leaf, root)
    assert not any(r[0] == "createPage" for r in recorded.requests)
    assert ("page", "888") not in run.resources
    before = len(recorded.requests)
    with pytest.raises(LiveContractError, match="relationship"):
        run.delete_page(leaf)
    assert len(recorded.requests) == before
    assert leaf.token in run.blocked_parents
    assert any(
        row["event"] == "child-relationship-unresolved" and row["id"] == leaf.id
        for row in rows(stream)
    )
    answers["deletePage"] = None
    answers["getPages"] = {"results": []}
    with pytest.raises(LiveContractError, match="incomplete"):
        run.cleanup()
    assert [p["id"] for op, p, body in operations(recorded) if op == "deletePage"] == [
        789
    ]
    assert {row["id"] for row in rows(stream) if row["event"] == "residual"} == {
        root.id,
        leaf.id,
    }


@pytest.mark.parametrize("wrapper", ["copy", "tree"])
@pytest.mark.parametrize(
    "lookup",
    [
        {"results": []},
        {"results": [{"id": "66", "key": "ENG"}]},
        {"results": [{"id": "66", "key": "SBX"}, {"id": "66", "key": "SBX"}]},
        {"results": [{"id": "66", "key": "SBX"}], "_links": {"next": "?cursor=more"}},
    ],
)
def test_new_wrappers_refuse_unproven_source_with_metadata_only(
    recorded, wrapper, lookup
):
    recorded.seed("getPageById", [{"id": "456", "spaceId": "66"}])
    recorded.seed("getSpaces", [lookup])
    argv = (
        ["page", "copy", "456", "--title", "T", "--space", "SBX", "--parent", "123"]
        if wrapper == "copy"
        else ["hierarchy", "tree", "456", "--max-depth", "2", "--stats"]
    )
    result = CliRunner().invoke(cli, [*argv, "--output", "json"])
    assert result.exit_code != 0
    assert result.stdout == ""
    assert recorded.roles == ["resolution", "resolution"]
    assert [r[0] for r in recorded.requests] == ["getPageById", "getSpaces"]


def test_copy_real_cli_disallowed_target_refuses_before_create(tranche):
    run, root, leaf, other, data, answers, recorded, stream = tranche
    result = CliRunner().invoke(
        cli,
        [
            "page",
            "copy",
            leaf.id,
            "--title",
            run.name("copy"),
            "--space",
            "ENG",
            "--parent",
            root.id,
            "--output",
            "json",
        ],
    )
    assert result.exit_code != 0 and result.stdout == ""
    assert [r[0] for r in operations(recorded)] == [
        "getPageById",
        "getSpaceById",
        "getChildPages",
    ]
    assert not any(r[0] == "createPage" for r in recorded.requests)


def prepare_tree(tranche):
    run, root, leaf, other, data, answers, recorded, stream = tranche
    other.parent = leaf.token
    data[other.id]["parentId"] = leaf.id
    children = {
        root.id: [{"id": leaf.id, "title": leaf.name}],
        leaf.id: [{"id": other.id, "title": other.name}],
        other.id: [],
    }
    answers["getChildPages"] = lambda parameters, body: {
        "results": children[str(parameters["id"])]
    }
    return children


def test_tree_real_cli_exact_depth_two_and_no_grandchild_expansion(tranche):
    run, root, leaf, other, data, answers, recorded, stream = tranche
    prepare_tree(tranche)
    result = run.tree_matches(root, leaf, other)
    assert result == {
        "root": {"id": root.id, "title": root.name},
        "tree": [
            {
                "id": leaf.id,
                "title": leaf.name,
                "depth": 1,
                "children": [
                    {"id": other.id, "title": other.name, "depth": 2, "children": []}
                ],
            }
        ],
        "stats": {"totalPages": 2, "maxDepth": 2, "rootChildren": 1},
    }
    requested = operations(recorded)
    assert [op for op, p, body in requested] == [
        "getPageById",
        "getChildPages",
        "getPageById",
        "getChildPages",
        "getPageById",
        "getChildPages",
        "getPageById",
        "getChildPages",
        "getChildPages",
    ]
    assert [p for op, p, body in requested if op == "getChildPages"] == [
        {"id": 123, "limit": 2},
        {"id": 456, "limit": 2},
        {"id": 789, "limit": 2},
        {"id": 123},
        {"id": 456},
    ]
    assert not run.blocked_parents


@pytest.mark.parametrize("change", ["missing", "extra", "duplicate", "wrong-title"])
def test_tree_real_cli_changed_after_preflight_retains_parents(tranche, change):
    run, root, leaf, other, data, answers, recorded, stream = tranche
    children = prepare_tree(tranche)
    data["888"] = {"id": "888", "spaceId": "55", "title": "unknown"}
    children["888"] = []

    def child_rows(parameters, body):
        result = children[str(parameters["id"])]
        if "limit" not in parameters and str(parameters["id"]) == root.id:
            if change == "missing":
                result = []
            elif change == "extra":
                result = [*result, {"id": "888", "title": "unknown"}]
            elif change == "duplicate":
                result = result * 2
            else:
                result = [{"id": leaf.id, "title": "wrong"}]
        return {"results": result}

    answers["getChildPages"] = child_rows
    with pytest.raises(LiveContractError, match="Tree differs"):
        run.tree_matches(root, leaf, other)
    assert ("page", "888") not in run.resources
    assert run.blocked_parents == {root.token, leaf.token, other.token}
    before = len(recorded.requests)
    with pytest.raises(LiveContractError, match="incomplete"):
        run.cleanup()
    assert len(recorded.requests) == before
    assert len([r for r in rows(stream) if r["event"] == "residual"]) == 3


@pytest.mark.parametrize("embedded", [False, True])
def test_versions_real_cli_two_guarded_updates_and_exact_optional_page(
    tranche, embedded
):
    run, root, leaf, other, data, answers, recorded, stream = tranche
    versions = [run.read_page(leaf)["version"]["number"]]

    def update(parameters, body):
        assert parameters == {"id": 456}
        assert body["id"] == leaf.id and body["status"] == "current"
        assert body["version"]["number"] == data[leaf.id]["version"]["number"] + 1
        data[leaf.id] = {
            **data[leaf.id],
            "title": body["title"],
            "version": body["version"],
        }
        return data[leaf.id]

    answers["updatePage"] = update
    for purpose in ("version-two", "version-three"):
        versions.append(
            run.update_page(leaf, title=run.name(purpose))["version"]["number"]
        )
    answers["getPageVersions"] = {
        "results": [
            {"number": v, **({"page": {"id": leaf.id}} if embedded else {})}
            for v in reversed(versions)
        ]
    }
    result = run.versions_match(leaf, versions)
    assert sorted(row["number"] for row in result) == [1, 2, 3]
    assert len([r for r in operations(recorded) if r[0] == "updatePage"]) == 2
    assert operations(recorded)[-1] == (
        "getPageVersions",
        {"id": 456, "body-format": "storage", "limit": 4},
        None,
    )
    assert recorded.roles[-3:] == ["resolution", "resolution", "operation"]
    assert not run.pending and leaf.state == "owned"


@pytest.mark.parametrize(
    "result",
    [
        {"results": [{"number": 1}, {"number": 2}]},
        {"results": [{"number": 1}, {"number": 2}, {"number": 2}]},
        {"results": [{"number": 1}, {"number": 2}, {"number": 4}]},
        {"results": [{"number": 1}, {"number": 2}, {"number": 3}, {"number": 4}]},
        {
            "results": [{"number": 1}, {"number": 2}, {"number": 3}],
            "_links": {"next": "?cursor=more"},
        },
        {
            "results": [
                {"number": 1, "page": {"id": "789"}},
                {"number": 2},
                {"number": 3},
            ]
        },
        {"results": [{"number": 1, "page": None}, {"number": 2}, {"number": 3}]},
        {"results": [{"number": True}, {"number": 2}, {"number": 3}]},
        {"results": [None]},
        {},
    ],
)
def test_versions_real_cli_refuses_ambiguous_incomplete_or_foreign_rows(
    tranche, result
):
    run, root, leaf, other, data, answers, recorded, stream = tranche
    data[leaf.id]["version"]["number"] = 3
    answers["getPageVersions"] = result
    with pytest.raises(LiveContractError):
        run.versions_match(leaf, [1, 2, 3])
    assert [r[0] for r in operations(recorded)] == ["getPageById", "getPageVersions"]
    assert set(run.resources) == {root.token, leaf.token, other.token}


def test_filtered_space_listing_real_cli_exact_scope_ids_status_and_limit(tranche):
    run, root, leaf, other, data, answers, recorded, stream = tranche
    answers["getPages"] = {"results": [data[other.id], data[leaf.id]]}
    result = run.pages_match((leaf, other))
    assert {row["id"] for row in result} == {leaf.id, other.id}
    assert operations(recorded)[-1] == (
        "getPages",
        {"space-id": [55], "id": [456, 789], "status": ["current"], "limit": 3},
        None,
    )
    assert recorded.roles[-2:] == ["resolution", "operation"]
    assert recorded.requests[-2] == ("getSpaces", {"ids": [55]}, None)
    assert not run.blocked_parents


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "extra",
        "duplicate",
        "foreign-id",
        "foreign-space",
        "wrong-title",
        "wrong-parent",
        "wrong-status",
        "incomplete",
        "malformed",
    ],
)
def test_filtered_space_listing_real_cli_refuses_changed_results(tranche, change):
    run, root, leaf, other, data, answers, recorded, stream = tranche
    listed = [dict(data[leaf.id]), dict(data[other.id])]
    result = {"results": listed}
    if change == "missing":
        listed.pop()
    elif change == "extra":
        listed.append({"id": "888", "parentId": root.id, "spaceId": "55"})
    elif change == "duplicate":
        listed[1] = dict(listed[0])
    elif change == "foreign-id":
        listed[0]["id"] = "888"
    elif change == "foreign-space":
        listed[0]["spaceId"] = "66"
    elif change == "wrong-title":
        listed[0]["title"] = "foreign"
    elif change == "wrong-parent":
        listed[0]["parentId"] = other.id
    elif change == "wrong-status":
        listed[0]["status"] = "archived"
    elif change == "incomplete":
        result["_links"] = {"next": "?cursor=more"}
    else:
        listed[0] = None
    answers["getPages"] = result
    with pytest.raises(LiveContractError):
        run.pages_match((leaf, other))
    assert ("page", "888") not in run.resources
    assert not any(r[0] == "deletePage" for r in recorded.requests)
    if change in {"extra", "foreign-id", "wrong-parent"}:
        assert root.token in run.blocked_parents
        assert any(
            row["event"] == "child-relationship-unresolved" and row["id"] == root.id
            for row in rows(stream)
        )
    if change == "wrong-parent":
        assert other.token in run.blocked_parents


@pytest.mark.parametrize("scope", [None, [], [66], [55, 66]])
def test_filtered_list_real_cli_missing_or_foreign_scope_refuses(recorded, scope):
    recorded.seed(
        "getSpaces",
        [{"results": [{"id": "55", "key": "SBX"}, {"id": "66", "key": "ENG"}]}],
    )
    flags = [] if scope is None else ["--space-id", json.dumps(scope)]
    refusal(
        invoke(
            "getPages",
            *flags,
            "--id",
            "[456,789]",
            "--status",
            '["current"]',
            "--limit",
            "3",
            "--raw",
            "--confirm",
        )
    )
    assert not operations(recorded)
    assert all(role == "resolution" for role in recorded.roles)


@pytest.mark.parametrize("operation", ["getChildPages", "getPageVersions", "getPages"])
@pytest.mark.parametrize(
    "lookup",
    [
        {"results": []},
        {"results": [{"id": "55", "key": "SBX"}, {"id": "55", "key": "SBX"}]},
        {"results": [{"id": "55", "key": "SBX"}], "_links": {"next": "?cursor=more"}},
    ],
)
def test_new_reads_refuse_unproven_scope_before_requested_operation(
    recorded, operation, lookup
):
    recorded.seed("getPageById", [{"id": "456", "spaceId": "55"}])
    recorded.seed("getSpaces", [lookup])
    flags = (
        ["--space-id", "[55]", "--id", "[456,789]"]
        if operation == "getPages"
        else ["--id", "456"]
    )
    refusal(invoke(operation, *flags, "--limit", "2", "--confirm"))
    assert not operations(recorded)
    assert recorded.roles == (
        ["resolution"] if operation == "getPages" else ["resolution", "resolution"]
    )


@pytest.mark.parametrize(
    "operation", ["copy-source", "copy-parent", "tree", "versions", "list"]
)
@pytest.mark.parametrize("change", ["unowned", "foreign-run", "duplicate-object"])
def test_new_helpers_refuse_nonowned_inputs_before_any_cli(tranche, operation, change):
    run, root, leaf, other, data, answers, recorded, stream = tranche
    target = root if operation == "copy-parent" else leaf
    if change == "unowned":
        run.resources.pop(target.token)
    elif change == "foreign-run":
        target.name = "jas43-foreign-run-page"
    else:
        replacement = Resource(
            target.kind, target.id, target.parent, target.name, "owned"
        )
        if operation == "copy-parent":
            root = replacement
        else:
            leaf = replacement
    with pytest.raises(LiveContractError):
        if operation.startswith("copy"):
            run.copy_leaf(leaf, root)
        elif operation == "tree":
            run.tree_matches(root, leaf, other)
        elif operation == "versions":
            run.versions_match(leaf, [1, 2, 3])
        else:
            run.pages_match((other, leaf))
    assert recorded.requests == []


@pytest.mark.parametrize(
    "outcome", [TimeoutError("PRIVATE"), None, "not-json", {"id": "456"}, {}]
)
def test_copy_unknown_return_journal_blocks_root_without_retry(outcome):
    run, root, driver, stream = owned_run()
    leaf = Resource("page", "456", root.token, run.name("leaf"), "owned")
    run.resources[leaf.token] = leaf
    driver.steps = [
        ("getPageById", page_response(leaf, parentId=root.id)),
        ("getPageById", page_response(root)),
        ("getPageById", page_response(leaf, parentId=root.id)),
        ("getChildPages", {"results": []}),
        ("page copy", outcome),
    ]
    with pytest.raises(LiveContractError):
        run.copy_leaf(leaf, root)
    assert (
        run.pending
        and len([argv for argv in driver.calls if argv[:2] == ["page", "copy"]]) == 1
    )
    with pytest.raises(LiveContractError):
        run.delete_page(root)
    assert not any(argv[:3] == ["api", "call", "deletePage"] for argv in driver.calls)
    assert "PRIVATE" not in stream.getvalue()
    assert any(row["event"] == "unknown-outcome" for row in rows(stream))


TRANCHE_SELECTIONS = [
    ("copy", "test_page_copy_live.py"),
    ("tree", "test_hierarchy_live.py"),
    ("versions", "test_page_versions_live.py"),
    ("space-content", "test_space_content_live.py"),
]


@pytest.mark.parametrize("case,filename", TRANCHE_SELECTIONS)
@pytest.mark.parametrize(
    "change",
    [
        "missing-file",
        "symlink",
        "directory",
        "missing-node",
        "extra-node",
        "duplicate-node",
    ],
)
@pytest.mark.parametrize("combined", [False, True])
def test_tranche_entrypoint_new_source_and_exact_node_refusals(
    entrypoint, case, filename, change, combined
):
    target = entrypoint["live"] / filename
    before_import = change in {"missing-file", "symlink", "directory"}
    if before_import:
        target.unlink()
        if change == "symlink":
            target.symlink_to(entrypoint["root"] / "outside.py")
        elif change == "directory":
            target.mkdir()
    elif change == "missing-node":
        target.write_text(
            target.read_text().replace("def test_", "def held_"), encoding="utf-8"
        )
    elif change == "extra-node":
        target.write_text(
            target.read_text() + "\ndef test_extra():\n    assert False\n",
            encoding="utf-8",
        )
    else:
        plugin = entrypoint["root"] / "tests/conftest.py"
        plugin.write_text(
            plugin.read_text()
            + "\ndef pytest_collection_modifyitems(items):\n    items.append(items[0])\n",
            encoding="utf-8",
        )
    result = run_entrypoint(entrypoint, "--case", "tranche2" if combined else case)
    assert_entrypoint_refused(entrypoint, result, before_import=before_import)
    assert (
        "error:" if before_import else "exactly the approved nonempty nodes"
    ) in result.stdout + result.stderr


@pytest.mark.parametrize("case,filename", TRANCHE_SELECTIONS)
def test_tranche_entrypoint_rechecks_new_selected_path_after_plugins(
    entrypoint, case, filename
):
    plugin = entrypoint["root"] / "tests/conftest.py"
    selected = entrypoint["live"] / filename
    plugin.write_text(
        plugin.read_text() + f"\nPath({str(selected)!r}).unlink()\n"
        f"Path({str(selected)!r}).symlink_to({str(entrypoint['root'] / 'outside.py')!r})\n",
        encoding="utf-8",
    )
    result = run_entrypoint(entrypoint, "--case", case)
    assert_entrypoint_refused(entrypoint, result, before_import=False)
    assert "symlink source refused" in result.stderr


def test_child_preflight_present_wrong_parent_blocks_both_owned_parents(tranche):
    run, root, leaf, other, data, answers, recorded, stream = tranche
    answers["getChildPages"] = {
        "results": [{"id": leaf.id, "title": leaf.name, "parentId": other.id}]
    }
    with pytest.raises(LiveContractError, match="Child parent"):
        run.children_match(root, (leaf,))
    assert run.blocked_parents == {root.token, other.token}
    assert not any(r[0] in {"createPage", "deletePage"} for r in recorded.requests)


def test_deletion_filtered_list_unknown_dependency_blocks_its_observed_parent(tranche):
    run, root, leaf, other, data, answers, recorded, stream = tranche
    answers["deletePage"] = None
    answers["getPages"] = {
        "results": [{"id": "888", "spaceId": "55", "parentId": other.id}]
    }
    with pytest.raises(LiveContractError, match="Unexpected page"):
        run.delete_page(leaf)
    assert leaf.state == "uncertain" and other.token in run.blocked_parents
    assert ("page", "888") not in run.resources
    before = len(recorded.requests)
    with pytest.raises(LiveContractError, match="relationship"):
        run.delete_page(other)
    assert len(recorded.requests) == before


def test_tree_real_cli_unreadable_new_child_after_preflight_blocks_cleanup(tranche):
    run, root, leaf, other, data, answers, recorded, stream = tranche
    children = prepare_tree(tranche)
    data["888"] = {"id": "888", "spaceId": "66", "title": "foreign"}

    def spaces(parameters, body):
        return (
            {"results": [{"id": "66", "key": "ENG"}]}
            if parameters.get("ids") == [66]
            else {"results": [{"id": "55", "key": "SBX"}]}
        )

    answers["getSpaces"] = spaces
    answers["getChildPages"] = lambda p, body: {
        "results": (
            [{"id": "888", "title": "foreign"}]
            if "limit" not in p and str(p["id"]) == root.id
            else children[str(p["id"])]
        )
    }
    with pytest.raises(LiveContractError):
        run.tree_matches(root, leaf, other)
    assert run.blocked_parents == {root.token, leaf.token, other.token}
    assert ("page", "888") not in run.resources
    assert recorded.roles[-2:] == ["resolution", "resolution"]
    assert not any(
        op == "getChildPages" and str(p["id"]) == "888"
        for op, p, body in operations(recorded)
    )


def test_copy_bad_title_does_not_hide_observed_unexpected_parent(tranche):
    run, root, leaf, other, data, answers, recorded, stream = tranche
    prepare_copy(tranche, change={"title": "wrong", "parentId": other.id})
    with pytest.raises(LiveContractError, match="title"):
        run.copy_leaf(leaf, root)
    assert run.resources[("page", "999")].state == "candidate"
    assert run.blocked_parents == {root.token, other.token}
    assert any(
        row["event"] == "candidate" and row["id"] == "999" for row in rows(stream)
    )


def test_duplicate_copy_result_cannot_hide_changed_parent(tranche):
    run, root, leaf, other, data, answers, recorded, stream = tranche
    prepare_copy(tranche, change={"id": leaf.id, "parentId": other.id})
    with pytest.raises(LiveContractError):
        run.copy_leaf(leaf, root)
    assert run.resources[leaf.token] is leaf and run.pending
    assert run.blocked_parents == {root.token, other.token}
    assert any(
        row["event"] == "candidate" and row["id"] == leaf.id for row in rows(stream)
    )
