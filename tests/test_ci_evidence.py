"""GC-286 public-contract negatives. Source-only charge: these have NOT RUN.

Later run under separately authorized validation. No subprocess, network, build,
installation or global environment mutation is needed by these fixture cases.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Explicit source loading also works when the product is installed from src/.
CI = Path(__file__).resolve().parents[1] / "ci"
_spec = importlib.util.spec_from_file_location(
    "pytest_evidence", CI / "pytest_evidence.py"
)
evidence = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = evidence
_spec.loader.exec_module(evidence)
_spec = importlib.util.spec_from_file_location("pilot", CI / "pilot.py")
pilot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pilot)


@pytest.fixture
def policy():
    pins = evidence.read_json(CI / "pins.json")
    selection = evidence.read_json(CI / pilot.SELECTION.removeprefix("ci/"))
    admission = {
        "schema": "confluence-pilot-admission/v1",
        "mode": "fixed-benchmark",
        "allow_execute": True,
        "sources": copy.deepcopy(pins["sources"]),
        "control": {
            "commit": "c" * 40,
            "tree": "d" * 40,
            "pins_sha256": pilot.digest(CI / "pins.json"),
        },
        "event": {
            "name": "workflow_dispatch",
            "sha": "c" * 40,
            "repository": "grandcamel/confluence-as",
            "run_id": "123",
            "attempt": "1",
        },
        "timing": {"request_at": "2026-09-08T00:00:00Z"},
    }
    return admission, pins, selection


def test_whole_module_selection_is_exact_disjoint_union(policy):
    admission, pins, selection = policy
    groups = {
        s: pilot.validate_policy(admission, pins, selection, s)
        for s in ("serial", "A", "B")
    }
    assert len(groups["serial"]) == 47
    assert len(groups["A"]) == 36 and len(groups["B"]) == 11
    assert groups["serial"] == groups["A"] + groups["B"]
    assert not set(groups["A"]) & set(groups["B"])


@pytest.mark.parametrize(
    "change", ["mode", "event", "event-sha", "product", "control", "permission"]
)
def test_wrong_mode_source_or_permission_refuses(policy, change):
    admission, pins, selection = policy
    if change == "mode":
        admission["mode"] = "pull-request"
    elif change == "event":
        admission["event"]["name"] = "pull_request"
    elif change == "event-sha":
        admission["event"]["sha"] = "e" * 40
    elif change == "product":
        admission["sources"]["product"]["commit"] = "e" * 40
    elif change == "control":
        admission["control"]["tree"] = None
    else:
        admission["allow_execute"] = False
    with pytest.raises(evidence.EvidenceError):
        pilot.validate_policy(admission, pins, selection, "serial")


@pytest.mark.parametrize(
    "change", ["missing", "hash", "transitive", "unavailable", "circular"]
)
def test_missing_changed_or_unresolved_pins_refuse(policy, change):
    admission, pins, selection = policy
    if change == "missing":
        pins["distributions"] = [d for d in pins["distributions"] if d["name"] != "pip"]
    elif change == "hash":
        pins["distributions"][0]["sha256"] = "invented"
    elif change == "transitive":
        pins["distributions"][0]["dependencies"].append("not-pinned")
    elif change == "unavailable":
        pins["python"]["availability"] = "unavailable"
    else:
        pins["content"]["ci/pins.json"] = "a" * 64
    with pytest.raises(evidence.EvidenceError):
        pilot.validate_policy(admission, pins, selection, "serial")


@pytest.mark.parametrize("change", ["omit", "duplicate", "wrong-shard", "wrong-module"])
def test_selection_cannot_shrink_or_reassign(policy, change):
    admission, pins, selection = policy
    if change == "omit":
        selection["modules"][0]["nodes"].pop()
    elif change == "duplicate":
        selection["modules"][0]["nodes"][1] = selection["modules"][0]["nodes"][0]
    elif change == "wrong-shard":
        selection["modules"][0]["shard"] = "B"
    else:
        selection["modules"][0]["nodes"][0] = "tests/test_other.py::test_hidden"
    with pytest.raises(evidence.EvidenceError):
        pilot.validate_policy(admission, pins, selection, "serial")


def event_stream(nodes, identity, collect_only=False):
    rows = [{"event": "start"}, {"event": "collection", "nodes": nodes}]
    if not collect_only:
        rows += [
            {
                "event": "phase",
                "nodeid": n,
                "when": phase,
                "outcome": "passed",
                "duration": 0.02,
                "wasxfail": None,
            }
            for n in nodes
            for phase in ("setup", "call", "teardown")
        ]
    rows += [{"event": "finish", "exitstatus": 0}]
    return [dict(row, seq=i, identity=identity) for i, row in enumerate(rows)]


@pytest.mark.parametrize(
    "problem",
    [
        "missing-terminal",
        "nonzero",
        "omit",
        "duplicate",
        "skip",
        "xfail",
        "setup-failure",
        "collection-failure",
        "identity",
        "duration",
        "gap",
    ],
)
def test_forged_or_partial_success_rejected(problem):
    nodes = ["tests/test_contract.py::test_one", "tests/test_contract.py::test_two"]
    identity = {"shard": "A", "admission_sha256": "a" * 64}
    rows = event_stream(nodes, identity)
    if problem == "missing-terminal":
        rows.pop()
    elif problem == "nonzero":
        rows[-1]["exitstatus"] = 1
    elif problem == "omit":
        rows[1]["nodes"] = nodes[:-1]
    elif problem == "duplicate":
        rows[1]["nodes"] = nodes + [nodes[0]]
    elif problem == "skip":
        rows[3]["outcome"] = "skipped"
    elif problem == "xfail":
        rows[3]["wasxfail"] = "known issue"
    elif problem == "setup-failure":
        rows[2]["outcome"] = "failed"
    elif problem == "collection-failure":
        rows[1]["event"] = "collection_error"
    elif problem == "identity":
        rows[-1]["identity"] = {"shard": "B"}
    elif problem == "duration":
        rows[3]["duration"] = float("nan")
    else:
        rows[3]["seq"] = 8
    with pytest.raises(evidence.EvidenceError):
        evidence.verify_events(rows, nodes, identity)


def test_complete_outcomes_and_collection_are_distinct():
    nodes, identity = ["tests/test_contract.py::test_one"], {"shard": "serial"}
    evidence.verify_events(event_stream(nodes, identity), nodes, identity)
    evidence.verify_events(event_stream(nodes, identity, True), nodes, identity, True)
    with pytest.raises(evidence.EvidenceError, match="test ran"):
        evidence.verify_events(event_stream(nodes, identity), nodes, identity, True)


def test_duplicate_json_key_cannot_override_failure(tmp_path):
    path = tmp_path / "artifact.json"
    path.write_text('{"exitstatus": 1, "exitstatus": 0}')
    with pytest.raises(evidence.EvidenceError, match="duplicate JSON"):
        evidence.read_json(path)


def test_missing_terminal_file_is_not_green(tmp_path):
    (tmp_path / "events.jsonl").write_text("")
    with pytest.raises(FileNotFoundError):
        pilot.verify_phase(tmp_path, [], {}, False)


@pytest.mark.parametrize("problem", ["nodes", "config", "collection-error"])
def test_collection_gate_exits_before_test_execution(tmp_path, problem):
    config_path = tmp_path / "pyproject.toml"
    config_path.write_text("[tool.pytest.ini_options]\n")
    config = SimpleNamespace(inipath=config_path)
    recorder = evidence.Recorder.__new__(evidence.Recorder)
    recorder.target, recorder.identity, recorder.events = tmp_path, {}, []
    recorder.expectation = {
        "nodes": ["tests/test_contract.py::test_one"],
        "config_path": str(config_path),
        "config_sha256": pilot.digest(config_path),
    }
    node = recorder.expectation["nodes"][0]
    if problem == "nodes":
        node = "tests/test_contract.py::test_omitted"
    if problem == "config":
        recorder.expectation["config_sha256"] = "0" * 64
    if problem == "collection-error":
        recorder.emit("collection_error", error="original import failure")
    session = SimpleNamespace(
        items=[SimpleNamespace(nodeid=node)],
        config=config,
        testsfailed=int(problem == "collection-error"),
    )
    with pytest.raises(pytest.exit.Exception) as caught:
        recorder.pytest_collection_finish(session)
    assert caught.value.returncode == (2 if problem == "collection-error" else 4)
    assert not any(e["event"] == "phase" for e in recorder.events)
    assert recorder.events[-1]["event"] == "admission_error"


@pytest.mark.parametrize(
    "xml",
    [
        "",
        "<testsuites/>",
        '<testsuite><testcase classname="tests.test_contract" name="test_one"><skipped/></testcase></testsuite>',
        '<testsuite><testcase classname="tests.test_contract" name="test_one"/><testcase classname="tests.test_contract" name="test_one"/></testsuite>',
    ],
)
def test_missing_skipped_or_duplicate_junit_is_not_success(tmp_path, xml):
    path = tmp_path / "junit.xml"
    path.write_text(xml)
    with pytest.raises(evidence.EvidenceError):
        pilot.verify_junit(path, ["tests/test_contract.py::test_one"])


@pytest.mark.parametrize("target", ["pin-bytes", "lock-bytes", "config-bytes"])
def test_changed_input_refuses_before_source_or_runner_effects(
    tmp_path, monkeypatch, policy, target
):
    admission, pins, selection = policy
    control = tmp_path / "control"
    for name in pilot.OWNED:
        path = control / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((CI.parent / name).read_bytes())
    changed = {
        "pin-bytes": "ci/pins.json",
        "lock-bytes": pilot.LOCK,
        "config-bytes": pilot.SELECTION,
    }[target]
    with (control / changed).open("a") as stream:
        stream.write("\n")
    path = tmp_path / "admission.json"
    evidence.write_json(path, admission)
    calls = []
    monkeypatch.setattr(pilot, "source_files", lambda *a: calls.append(a))
    with pytest.raises(evidence.EvidenceError, match="changed"):
        pilot.validate_inputs(
            control, tmp_path, tmp_path, tmp_path, path, pilot.digest(path), "A"
        )
    assert calls == []


@pytest.mark.parametrize(
    "code,status",
    [(7, "child-failed"), (130, "cancelled"), (143, "cancelled"), (124, "timed-out")],
)
def test_first_child_failure_preserves_status_partial_evidence_and_no_retry(
    tmp_path, monkeypatch, code, status
):
    private = tmp_path / "private"
    private.mkdir()
    monkeypatch.setattr(pilot.tempfile, "mkdtemp", lambda **kw: str(private))
    control = tmp_path / "control"
    (control / "ci/selections").mkdir(parents=True)
    (control / pilot.SELECTION).write_text("{}")
    (control / pilot.LOCK).parent.mkdir(parents=True)
    (control / pilot.LOCK).write_text("")
    (control / "ci/pytest_evidence.py").write_text("")
    context = {
        "admission": {},
        "admission_sha256": "a" * 64,
        "shard": "A",
        "files": {"product": [], "engine": []},
        "pins": {
            "distributions": [],
            "content": {
                pilot.LOCK: pilot.digest(control / pilot.LOCK),
                "ci/pytest_evidence.py": pilot.digest(
                    control / "ci/pytest_evidence.py"
                ),
            },
        },
    }
    calls = []

    def fail(argv, cwd, env, timeout, log):
        calls.append(argv)
        log.write_text("original failure\n")
        raise pilot.ChildFailure(code, status)

    output = tmp_path / "output"
    assert (
        pilot.run_admitted(context, control, tmp_path, tmp_path, tmp_path, output, fail)
        == code
    )
    result = evidence.read_json(output / "result.json")
    assert result["exitstatus"] == code and result["status"] == status
    assert len(calls) == len(result["phases"]) == 1
    assert (output / "venv.log").read_text() == "original failure\n"
    assert "venv.log" in evidence.read_json(output / "artifacts.json")
    with pytest.raises(evidence.EvidenceError, match="output already exists"):
        pilot.run_admitted(context, control, tmp_path, tmp_path, tmp_path, output, fail)
    assert len(calls) == 1


def test_clean_child_environment_does_not_inherit_credentials_or_plugins(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("GITHUB_TOKEN", "fixture-secret")
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k omit")
    monkeypatch.setenv("PYTHONPATH", "/untrusted")
    env = pilot.clean_environment(tmp_path, tmp_path / "venv/bin/python")
    assert all(
        key not in env for key in ("GITHUB_TOKEN", "PYTEST_ADDOPTS", "PYTHONPATH")
    )
    assert env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert env["HOME"] == str(tmp_path / "home")


def test_comparison_separates_release_queue_runtime_and_rounded_cost(policy):
    admission, _, _ = policy

    def job(shard, release, start, finish, verified):
        def stamp(minute):
            return f"2026-09-08T00:{minute:02d}:00Z"

        return {
            "shard": shard,
            "identity": {
                "sources": "same",
                "control": "same",
                "pins_sha256": "a" * 64,
                "selection_sha256": "b" * 64,
                "runtime": {"image": "same", "hardware": "same"},
                "generated": {},
            },
            "status": "verified",
            "attempt": "1",
            "arm_released_at": stamp(release),
            "started_at": stamp(start),
            "completed_at": stamp(finish),
            "verified_at": stamp(verified),
        }

    jobs = [job("serial", 0, 1, 5, 6), job("A", 6, 7, 9, 10), job("B", 6, 8, 11, 12)]
    result = pilot.summarize_comparison(admission, jobs, "2026-09-08T00:13:00Z", 0.006)
    assert result["arms"]["two-shards"]["feedback_seconds"] == 360
    assert result["experiment_seconds"] == 780
    assert result["rounded_runner_minutes"] == 9
    assert result["aggregate_compute_cost"] == pytest.approx(0.054)
    jobs[2]["identity"] = {"source": "same", "image": "changed", "hardware": "same"}
    with pytest.raises(evidence.EvidenceError, match="unmatched"):
        pilot.summarize_comparison(admission, jobs, "2026-09-08T00:13:00Z", 0.006)


def object_fixture(tmp_path, monkeypatch):
    """Actual data files, intercepted object reads; no real Git or hook process."""
    root = tmp_path / "checkout"
    (root / ".git/objects").mkdir(parents=True)
    (root / ".git/config").write_text(
        '[core]\nfsmonitor = /MUST-NOT-EXECUTE\n[filter "trap"]\nclean = /MUST-NOT-EXECUTE\n'
        '[remote "origin"]\npromisor = true\nurl = ext::MUST-NOT-EXECUTE\n'
    )
    content = b"reviewed source\n"
    (root / "source.py").write_bytes(content)

    def oid(kind, data):
        return pilot.hashlib.sha1(
            kind.encode() + b" " + str(len(data)).encode() + b"\0" + data
        ).hexdigest()

    tree = b"100644 source.py\0" + bytes.fromhex(oid("blob", content))
    tree_id = oid("tree", tree)
    commit = ("tree " + tree_id + "\n\nfixture\n").encode()
    commit_id = oid("commit", commit)
    (root / ".git/HEAD").write_text(commit_id + "\n")
    (root / ".git/refs/replace").mkdir(parents=True)
    (root / ".git/refs/replace" / commit_id).write_text("f" * 40 + "\n")
    objects = {("commit", commit_id): commit, ("tree", tree_id): tree}
    commands = []

    def read(argv, *, env, cwd, timeout):
        commands.append(argv)
        assert argv[:3] == ["/usr/bin/git", "--no-pager", "--no-replace-objects"]
        assert argv[-3] == "cat-file" and timeout == 10
        isolated = Path(argv[3].split("=", 1)[1])
        assert isolated != root / ".git" and cwd == isolated
        assert (
            isolated / "config"
        ).read_text() == "[core]\nrepositoryformatversion = 0\nbare = true\n"
        assert env["GIT_NO_REPLACE_OBJECTS"] == env["GIT_NO_LAZY_FETCH"] == "1"
        assert env["GIT_CONFIG_GLOBAL"] == env["GIT_CONFIG_SYSTEM"] == "/dev/null"
        assert "GIT_CONFIG_COUNT" not in env and "GIT_SSH_COMMAND" not in env
        return objects[tuple(argv[-2:])]

    monkeypatch.setattr(pilot.subprocess, "check_output", read)
    return root, {"commit": commit_id, "tree": tree_id}, objects, commands


def test_admission_git_object_timeout_refuses_before_execution(
    tmp_path, monkeypatch, capsys
):
    calls = []
    output = tmp_path / "output"

    def timeout(argv, *, env, cwd, timeout):
        calls.append(argv)
        assert argv[-3:] == ["cat-file", "commit", "a" * 40]
        assert timeout == 10
        raise pilot.subprocess.TimeoutExpired(argv, timeout)

    def validate(*args):
        return pilot.git_object(
            tmp_path / "isolated", tmp_path / "objects", "commit", "a" * 40
        )

    def unexpected_execution(*args):
        pytest.fail("admission timeout must not reach admitted execution")

    argv = ["pilot.py", "run"]
    for name in ("control", "product", "engine", "assets", "admission", "output"):
        argv.extend(["--" + name, str(tmp_path / name)])
    argv.extend(["--admission-sha256", "b" * 64, "--shard", "serial"])
    monkeypatch.setattr(pilot.sys, "argv", argv)
    monkeypatch.setattr(pilot.subprocess, "check_output", timeout)
    monkeypatch.setattr(pilot, "validate_inputs", validate)
    monkeypatch.setattr(pilot, "run_admitted", unexpected_execution)

    assert pilot.main() == 4
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("pilot refused before execution: ")
    assert "timed out after 10 seconds" in captured.err
    assert "Traceback" not in captured.err
    assert len(calls) == 1
    assert not output.exists()
    assert list(tmp_path.iterdir()) == []


def test_candidate_config_filters_replacements_and_promisor_are_not_loaded(
    tmp_path, monkeypatch
):
    root, identity, _, commands = object_fixture(tmp_path, monkeypatch)
    assert pilot.source_files(root, identity) == ["source.py"]
    assert len(commands) == 2


@pytest.mark.parametrize(
    "damage",
    ["commit-object", "tree-object", "working-bytes", "mode", "extra", "missing"],
)
def test_object_and_working_inventory_drift_refuse_without_hooks(
    tmp_path, monkeypatch, damage
):
    root, identity, objects, _ = object_fixture(tmp_path, monkeypatch)
    if damage == "commit-object":
        objects[("commit", identity["commit"])] += b"corrupt"
    elif damage == "tree-object":
        objects[("tree", identity["tree"])] += b"corrupt"
    elif damage == "working-bytes":
        (root / "source.py").write_text("changed")
    elif damage == "mode":
        (root / "source.py").chmod(0o755)
    elif damage == "extra":
        (root / "ignored-output").write_text("unexpected")
    else:
        (root / "source.py").unlink()
    with pytest.raises(evidence.EvidenceError):
        pilot.source_files(root, identity)


class InterceptedGroup:
    def __init__(
        self,
        terminal=0,
        descendants=False,
        stalled=False,
        escaped=False,
        observation_error=False,
    ):
        self.terminal, self.descendants, self.stalled = terminal, descendants, stalled
        self.escaped, self.observation_error = escaped, observation_error
        self.killed = self.reaped = False
        self.events = []

    def observe(self):
        self.events.append("observe")
        if self.observation_error:
            raise ChildProcessError("direct child identity unavailable")
        if self.stalled and self.killed:
            return None
        return (
            (self.terminal if self.terminal is not None else 137)
            if self.killed
            else self.terminal
        )

    def adopted(self):
        self.events.append("adopted")
        return (
            [99] if self.escaped or (self.descendants and not self.killed) else []
        ), self.escaped

    def kill_group(self):
        self.observe()
        assert not self.reaped, "historical PGID used after reaping"
        self.events.append("kill")
        self.killed = True

    def reap(self, terminal):
        assert self.killed and not self.stalled
        self.events.append("reap")
        self.reaped = True


def lifecycle(group, cancel_at=None):
    now = [0.0]

    def pause(seconds):
        now[0] += seconds

    pilot.finish_phase(
        group,
        0.04,
        clock=lambda: now[0],
        pause=pause,
        cleanup_seconds=0.06,
        cancelled=lambda: 15 if cancel_at is not None and now[0] >= cancel_at else None,
    )


def test_zero_exit_retains_leader_until_group_cleanup_then_reaps():
    group = InterceptedGroup()
    lifecycle(group)
    assert group.events.index("kill") < group.events.index("reap")
    assert group.reaped


def test_zero_exit_with_live_descendant_is_nonaccepting_and_cleaned_before_reap():
    group = InterceptedGroup(descendants=True)
    with pytest.raises(pilot.ChildFailure) as caught:
        lifecycle(group)
    assert caught.value.status == "descendants-outlived-leader"
    assert group.reaped and group.events.index("kill") < group.events.index("reap")


@pytest.mark.parametrize(
    "terminal,stalled,code", [(None, False, 124), (None, True, 124), (7, True, 7)]
)
def test_timeout_and_cleanup_deadline_preserve_original_status(terminal, stalled, code):
    group = InterceptedGroup(terminal=terminal, stalled=stalled)
    with pytest.raises(pilot.ChildFailure) as caught:
        lifecycle(group)
    assert caught.value.code == code
    if stalled:
        assert "deadline" in caught.value.cleanup_uncertainty
        assert not group.reaped
    else:
        assert group.reaped
    assert group.events.count("kill") == 1


def test_cancellation_preserved_through_bounded_cleanup():
    group = InterceptedGroup(terminal=None)
    with pytest.raises(pilot.ChildFailure) as caught:
        lifecycle(group, cancel_at=0.02)
    assert (caught.value.code, caught.value.status) == (143, "cancelled")
    assert group.reaped


def test_kernel_identity_loss_never_signals_historical_group():
    group = InterceptedGroup(observation_error=True)
    with pytest.raises(pilot.ChildFailure) as caught:
        lifecycle(group)
    assert caught.value.code == 4 and caught.value.cleanup_uncertainty
    assert "kill" not in group.events and not group.reaped


def test_escaped_descendant_is_not_accepted_or_signalled_as_a_new_group():
    group = InterceptedGroup(escaped=True)
    with pytest.raises(pilot.ChildFailure) as caught:
        lifecycle(group)
    assert caught.value.status == "unsupported-group-escape"
    assert caught.value.cleanup_uncertainty and not group.reaped
    assert group.events.count("kill") == 1


def test_active_workflow_checks_out_only_fixed_sources_before_verified_bootstrap():
    source = (CI.parent / ".github/workflows/confluence-pilot.yml").read_text()
    pins = evidence.read_json(CI / "pins.json")
    jobs = source.split("    steps:\n")[1:]
    assert len(jobs) == 2
    checkouts = []
    for path, repository, ref in (
        ("control", None, "${{ github.sha }}"),
        ("product", "grandcamel/confluence-as", pilot.PRODUCT),
        ("engine", "grandcamel/as-engine", pilot.ENGINE),
    ):
        block = (
            "      - uses: actions/checkout@"
            + pins["actions"]["actions/checkout"]
            + "\n        with:\n"
        )
        if repository:
            block += "          repository: " + repository + "\n"
        checkouts.append(
            block
            + "          ref: "
            + ref
            + "\n          path: "
            + path
            + "\n          persist-credentials: false\n"
        )
    for job, shard in zip(jobs, ("serial", "${{ matrix.shard }}"), strict=True):
        before, bootstrap = job.split(
            "      - name: Verified bootstrap for fixed benchmark\n"
        )
        assert before == "".join(checkouts)
        preamble, code = bootstrap.split("        run: |\n", 1)
        assert preamble == (
            "        shell: bash\n        env:\n"
            "          GC286_OPERATOR_ENVELOPE: ${{ secrets.GC286_OPERATOR_ENVELOPE }}\n"
            "          GC286_METADATA_TOKEN: ${{ github.token }}\n"
            "          SHARD: " + shard + "\n"
        )
        assert code.index("env -i PATH=/usr/bin:/bin") < code.index(
            "# GC286_INLINE_BEGIN"
        )
        assert code.index("# GC286_INLINE_END") < code.index(
            "      - name: Retain original complete or partial evidence"
        )
        # Only the bootstrap shell is run; no pre/post script or retry step.
        assert job.count("      - name:") == 2
        assert job.count("      - uses:") == 3
        assert job.count("        run: |") == 1


# Source-only v4 cases below. These functions have not been executed in this phase.
@pytest.fixture
def inline():
    import textwrap

    source = (CI.parent / ".github/workflows/confluence-pilot.yml").read_text()
    blocks = []
    for fragment in source.split("          # GC286_INLINE_BEGIN\n")[1:]:
        blocks.append(
            textwrap.dedent(fragment.split("          # GC286_INLINE_END")[0])
        )
    assert len(blocks) == 2 and blocks[0] == blocks[1]
    namespace = {"__name__": "gc286_extracted_inline"}
    exec(compile(blocks[0], "<exact workflow verifier>", "exec"), namespace)
    return SimpleNamespace(**namespace)


@pytest.fixture
def bootstrap_fixture(tmp_path, monkeypatch, inline):
    import json

    admission, pins = {}, evidence.read_json(CI / "pins.json")
    root = tmp_path / "control"
    root.mkdir()
    records = {}
    for relative in sorted(inline.FILES - {"ci/pins.json"}):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("verified inert fixture: " + relative)
        path.chmod(0o644)
        records[relative] = pilot.digest(path)
    pins["content"] = records
    evidence.write_json(root / "ci/pins.json", pins)
    (root / "ci/pins.json").chmod(0o644)
    admission.update(
        {
            "schema": "gc286-operator/v1",
            "control": {
                "commit": "a" * 40,
                "tree": "b" * 40,
                "pins_sha256": pilot.digest(root / "ci/pins.json"),
            },
            "repository": "grandcamel/confluence-as",
            "run_id": "123",
            "attempt": "1",
            "ref": "refs/tags/gc286-reviewed-fixture",
            "not_before": "2026-09-08T00:00:00Z",
            "expires_at": "2026-09-08T01:00:00Z",
            "platform": {
                "system": "Linux",
                "machine": "x86_64",
                "image_os": "ubuntu24",
                "runner": "github-hosted",
                "bootstrap": "/usr/bin/python3",
            },
            "sources": pins["sources"],
            "shards": ["serial", "A", "B"],
        }
    )
    env = {
        "GC286_OPERATOR_ENVELOPE": json.dumps(admission),
        "GITHUB_REPOSITORY": admission["repository"],
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_SHA": "a" * 40,
        "GITHUB_WORKFLOW_SHA": "a" * 40,
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": admission["ref"],
        "GITHUB_WORKFLOW_REF": admission["repository"]
        + "/.github/workflows/confluence-pilot.yml@"
        + admission["ref"],
        "GITHUB_WORKSPACE": str(tmp_path),
        "RUNNER_TEMP": str(tmp_path),
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_NAME": "GitHub Actions 1",
        "ImageOS": "ubuntu24",
        "ImageVersion": "fixture-image",
        "SHARD": "serial",
        "GC286_METADATA_TOKEN": "fixture-credential",
    }
    now = pilot.parse_time("2026-09-08T00:10:00Z")
    monkeypatch.setattr(inline.sys, "platform", "linux")
    monkeypatch.setattr(inline.os, "uname", lambda: SimpleNamespace(machine="x86_64"))
    monkeypatch.setattr(inline.os, "geteuid", lambda: 1000)
    manifest = {
        p: {"sha256": pilot.digest(root / p), "mode": 0o644} for p in inline.FILES
    }
    return admission, env, root, manifest, now


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "expired",
        "future",
        "run",
        "attempt",
        "revision",
        "workflow",
        "ref",
        "event",
        "source",
        "platform",
        "extra",
    ],
)
def test_inline_authority_refuses_before_tree_import_fetch_or_launch(
    inline, bootstrap_fixture, change
):
    import json

    authority, env, _, _, now = bootstrap_fixture
    if change == "missing":
        env.pop("GC286_OPERATOR_ENVELOPE")
    elif change == "expired":
        now += 3600
    elif change == "future":
        now -= 3600
    elif change in ("run", "attempt", "revision", "workflow", "ref", "event"):
        key = {
            "run": "GITHUB_RUN_ID",
            "attempt": "GITHUB_RUN_ATTEMPT",
            "revision": "GITHUB_WORKFLOW_SHA",
            "workflow": "GITHUB_WORKFLOW_REF",
            "ref": "GITHUB_REF",
            "event": "GITHUB_EVENT_NAME",
        }[change]
        env[key] = "wrong"
    else:
        if change == "source":
            authority["sources"]["engine"]["commit"] = "f" * 40
        elif change == "platform":
            authority["platform"]["runner"] = "self-hosted"
        else:
            authority["allow_execute"] = True
        env["GC286_OPERATOR_ENVELOPE"] = json.dumps(authority)
    with pytest.raises((ValueError, KeyError)):
        inline.verified_entry(
            env,
            now,
            tree_reader=lambda *args: pytest.fail("unadmitted tree effect"),
            loader=lambda *args: pytest.fail("unadmitted import"),
        )


@pytest.mark.parametrize(
    "target", ["ci/pilot.py", "ci/pytest_evidence.py", "ci/pins.json"]
)
def test_inline_actual_bytes_are_checked_before_import(
    inline, bootstrap_fixture, target
):
    _, env, root, _, now = bootstrap_fixture
    (root / target).write_text("tampered")
    with pytest.raises(ValueError):
        inline.verified_entry(
            env,
            now,
            tree_reader=lambda *args: pytest.fail("tampered input admitted"),
            loader=lambda *args: pytest.fail("tampered import"),
        )


@pytest.mark.parametrize(
    "change", ["file-link", "directory-link", "mode", "extra", "copy-mutation"]
)
def test_inline_inventory_modes_links_and_copy_refuse(
    inline, bootstrap_fixture, monkeypatch, change
):
    _, env, root, manifest, now = bootstrap_fixture
    if change == "file-link":
        source = root / "ci/pilot.py"
        source.rename(root / "saved")
        source.symlink_to(root / "saved")
    elif change == "directory-link":
        (root / "ci").rename(root / "saved-ci")
        (root / "ci").symlink_to(root / "saved-ci", target_is_directory=True)
    elif change == "mode":
        (root / "ci/pilot.py").chmod(0o755)
    elif change == "extra":
        (root / "extra").write_text("untracked")
    else:
        original = Path.write_bytes

        def mutate(path, data):
            return original(
                path, data + b"changed" if path.name == "pilot.py" else data
            )

        monkeypatch.setattr(Path, "write_bytes", mutate)

    def tree_reader(source, control, work):
        inline.need(inline.inventory(source) == set(manifest), "extra input")
        return manifest

    with pytest.raises(ValueError):
        inline.verified_entry(
            env,
            now,
            tree_reader=tree_reader,
            loader=lambda *args: pytest.fail("bad snapshot imported"),
        )


def test_inline_valid_copy_precedes_import_and_second_entry_refuses(
    inline, bootstrap_fixture
):
    _, env, root, manifest, now = bootstrap_fixture
    order = []
    # A candidate-local admission is outside the execution authority channel.
    (root.parent / "admission.json").write_text('{"allow_execute":true}')

    def tree_reader(*args):
        order.append("tree")
        return manifest

    def loader(private, work, authority, received, environment):
        assert private != root and private.parent == work
        assert received == manifest
        assert (
            pilot.digest(private / "ci/pilot.py") == manifest["ci/pilot.py"]["sha256"]
        )
        order.append("verified-private-import")
        return 0

    assert inline.verified_entry(env, now, tree_reader=tree_reader, loader=loader) == 0
    with pytest.raises(FileExistsError):
        inline.verified_entry(env, now, tree_reader=tree_reader, loader=loader)
    assert order == ["tree", "verified-private-import"]


class HTTPSResponse:
    status = 200

    def __init__(self, url, raw, length=None):
        import io

        self.url = url
        self.stream = io.BytesIO(raw)
        self.headers = {} if length is None else {"Content-Length": str(length)}

    def geturl(self):
        return self.url

    def read1(self, count):
        return self.stream.read(count)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stream.close()


@pytest.mark.parametrize(
    "problem",
    [
        "partial",
        "oversized-header",
        "oversized-stream",
        "expired",
        "bad-host",
        "redirect",
    ],
)
def test_https_bounds_fail_closed(problem):
    import time
    import urllib.error

    url = "https://files.pythonhosted.org/packages/fixture.whl"
    raw, length = b"abc", None
    if problem == "partial":
        length = 4
    elif problem == "oversized-header":
        length = 99
    elif problem == "oversized-stream":
        raw = b"12345"
    elif problem == "bad-host":
        url = "https://attacker.invalid/fixture.whl"

    def open_request(request, timeout):
        assert request.get_method() == "GET"
        assert "Authorization" not in request.headers
        if problem == "redirect":
            raise urllib.error.HTTPError(
                url, 302, "redirect", {"Location": "https://attacker.invalid/a"}, None
            )
        return HTTPSResponse(url, raw, length)

    with pytest.raises(evidence.EvidenceError):
        pilot.https_bytes(
            url,
            4,
            time.monotonic() + (-1 if problem == "expired" else 10),
            asset=True,
            opener=SimpleNamespace(open=open_request),
        )


def test_https_exact_github_redirect_and_metadata_credential_scope():
    import time
    import urllib.error

    first = (
        "https://github.com/actions/python-versions/releases/download/fixture/a.tar.gz"
    )
    final = "https://release-assets.githubusercontent.com/fixture?signature=fake"
    calls = []

    def open_request(request, timeout):
        calls.append(request.full_url)
        assert "Authorization" not in request.headers
        if request.full_url == first:
            raise urllib.error.HTTPError(
                first, 302, "redirect", {"Location": final}, None
            )
        return HTTPSResponse(final, b"abc", 3)

    assert (
        pilot.https_bytes(
            first,
            4,
            time.monotonic() + 10,
            asset=True,
            opener=SimpleNamespace(open=open_request),
        )
        == b"abc"
    )
    assert calls == [first, final]
    with pytest.raises(evidence.EvidenceError):
        pilot.https_bytes(
            first,
            4,
            time.monotonic() + 10,
            token="fixture",
            asset=True,
            opener=SimpleNamespace(
                open=lambda *a, **k: pytest.fail("credential sent to asset")
            ),
        )


@pytest.mark.parametrize("problem", ["hash", "oversize", "existing", "success"])
def test_asset_completion_is_hashed_bounded_and_atomic(tmp_path, problem):
    import hashlib
    import time

    raw = b"wheel-bytes"
    pin = {
        "filename": "fixture.whl",
        "url": "https://files.pythonhosted.org/packages/fixture.whl",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    target = tmp_path / pin["filename"]
    if problem == "existing":
        target.write_bytes(b"original")
    if problem == "hash":
        raw = b"corrupted"
    elif problem == "oversize":
        raw = b"x" * (16 * 1024 * 1024 + 1)
    if problem == "success":
        pilot.fetch_asset(pin, target, time.monotonic() + 10, fetch=lambda *a, **k: raw)
        assert (
            target.read_bytes() == raw and not target.with_suffix(".whl.part").exists()
        )
    else:
        with pytest.raises(evidence.EvidenceError):
            pilot.fetch_asset(
                pin, target, time.monotonic() + 10, fetch=lambda *a, **k: raw
            )
        assert (
            target.read_bytes() == b"original"
            if problem == "existing"
            else not target.exists()
        )


@pytest.fixture
def archive_fixture(tmp_path):
    import hashlib
    import io
    import json
    import tarfile

    def make(change="valid"):
        archive = tmp_path / "fixture.tar.gz"
        rows = []
        content = {
            "bin/python3.12": b"not-executed-elf",
            "lib/libpython3.12.so.1.0": b"not-executed-library",
            "setup.sh": b"NEVER EXECUTE",
        }
        if change == "traversal":
            content["../outside"] = b"unsafe"
        if change == "absolute":
            content["/outside"] = b"unsafe"
        with tarfile.open(archive, "w:gz") as bundle:
            for name, raw in content.items():
                item = tarfile.TarInfo(
                    "./" + name if not name.startswith("/") else name
                )
                item.size = len(raw)
                item.mode = 0o4755 if change == "setuid" else 0o644
                bundle.addfile(item, io.BytesIO(raw))
                rows.append(item)
            if change in ("link", "hardlink", "device"):
                item = tarfile.TarInfo("./unsafe")
                item.type = {
                    "link": tarfile.SYMTYPE,
                    "hardlink": tarfile.LNKTYPE,
                    "device": tarfile.CHRTYPE,
                }[change]
                item.linkname = "../outside"
                bundle.addfile(item)
                rows.append(item)
        pin = {
            "sha256": pilot.digest(archive),
            "recipe": {
                "id": "actions-python-3.12.12-ubuntu24-private-v1",
                "member_count": len(rows),
                "unpacked_bytes": sum(r.size for r in rows),
                "inventory_sha256": hashlib.sha256(
                    json.dumps(
                        pilot.archive_rows(rows), sort_keys=True, separators=(",", ":")
                    ).encode()
                ).hexdigest(),
                "setup_sha256": hashlib.sha256(content["setup.sh"]).hexdigest(),
                "links": {},
                "executable_sha256": hashlib.sha256(
                    content["bin/python3.12"]
                ).hexdigest(),
                "library_sha256": hashlib.sha256(
                    content["lib/libpython3.12.so.1.0"]
                ).hexdigest(),
            },
        }
        if change == "recipe":
            pin["recipe"]["id"] = "discovered-setup-script"
        elif change == "layout":
            pin["recipe"]["inventory_sha256"] = "f" * 64
        elif change == "archive-hash":
            pin["sha256"] = "f" * 64
        return archive, pin

    return make


@pytest.mark.parametrize(
    "change",
    [
        "traversal",
        "absolute",
        "link",
        "hardlink",
        "device",
        "setuid",
        "recipe",
        "layout",
        "archive-hash",
    ],
)
def test_archive_rejects_unsafe_or_unreviewed_recipe(tmp_path, archive_fixture, change):
    archive, pin = archive_fixture(change)
    with pytest.raises(evidence.EvidenceError):
        pilot.materialize_python(archive, tmp_path / "prefix", pin)
    assert not (tmp_path / "outside").exists()


def test_reviewed_archive_materializes_without_setup_or_execution(
    tmp_path, archive_fixture
):
    archive, pin = archive_fixture()
    prefix = tmp_path / "prefix"
    python = pilot.materialize_python(archive, prefix, pin)
    assert python.read_bytes() == b"not-executed-elf"
    assert not (prefix / "setup.sh").exists()
    assert (prefix / "bin/python").resolve() == python


@pytest.fixture
def metadata_fixture(bootstrap_fixture, monkeypatch):
    import json

    authority, env, _, _, now = bootstrap_fixture
    monkeypatch.setattr(pilot.time, "time", lambda: now)
    run = {
        "id": 123,
        "run_attempt": 1,
        "head_sha": "a" * 40,
        "event": "workflow_dispatch",
        "repository": {"full_name": authority["repository"]},
        "path": ".github/workflows/confluence-pilot.yml",
        "created_at": authority["not_before"],
    }
    job = {
        "id": 456,
        "name": "gc286-serial",
        "run_id": 123,
        "head_sha": "a" * 40,
        "status": "in_progress",
        "conclusion": None,
        "runner_name": env["RUNNER_NAME"],
        "runner_id": 12,
        "labels": ["ubuntu-24.04"],
        "started_at": "2026-09-08T00:01:00Z",
        "completed_at": None,
    }
    jobs = {"total_count": 1, "jobs": [job]}
    calls = []

    def fetch(url, maximum, deadline, **kwargs):
        calls.append(url)
        assert kwargs == {"token": "fixture-credential"}
        return json.dumps(jobs if "/jobs?" in url else run).encode()

    return authority, env, run, jobs, job, fetch, calls


@pytest.mark.parametrize(
    "change",
    [
        "run",
        "attempt",
        "revision",
        "job-absent",
        "job-duplicate",
        "timestamp",
        "platform",
        "runner",
        "token",
        "serial-incomplete",
    ],
)
def test_metadata_observations_cannot_expand_authority(metadata_fixture, change):
    authority, env, run, jobs, job, fetch, _ = metadata_fixture
    if change in ("run", "attempt", "revision"):
        run[{"run": "id", "attempt": "run_attempt", "revision": "head_sha"}[change]] = (
            "wrong"
        )
    elif change == "job-absent":
        jobs.update(total_count=0, jobs=[])
    elif change == "job-duplicate":
        jobs["jobs"].append(copy.deepcopy(job))
        jobs["total_count"] = 2
    elif change == "timestamp":
        job["started_at"] = None
    elif change == "platform":
        job["labels"] = ["self-hosted"]
    elif change == "runner":
        job["runner_name"] = "some-other-runner"
    elif change == "token":
        env.pop("GC286_METADATA_TOKEN")
    else:
        env["SHARD"] = "A"
        job["name"] = "gc286-A"
    with pytest.raises((evidence.EvidenceError, TypeError, AttributeError)):
        pilot.github_metadata(authority, env, fetch=fetch)


def test_metadata_uses_bounded_attempt_gets_and_common_dependency_release(
    metadata_fixture,
):
    authority, env, _, jobs, job, fetch, calls = metadata_fixture
    serial = copy.deepcopy(job)
    serial.update(
        status="completed", conclusion="success", completed_at="2026-09-08T00:02:00Z"
    )
    job.update(id=789, name="gc286-A", started_at="2026-09-08T00:03:00Z")
    jobs.update(total_count=2, jobs=[serial, job])
    env["SHARD"] = "A"
    first = pilot.github_metadata(authority, env, fetch=fetch)
    env["SHARD"], job["name"] = "B", "gc286-B"
    second = pilot.github_metadata(authority, env, fetch=fetch)
    assert (
        first["timing"]["arm_released_at"]
        == second["timing"]["arm_released_at"]
        == serial["completed_at"]
    )
    assert all(
        url.startswith(
            "https://api.github.com/repos/grandcamel/confluence-as/actions/runs/123/attempts/1"
        )
        for url in calls
    )
    assert len(calls) == 4
    assert "including-protection" in first["timing"]["delay_basis"]


def test_verified_bootstrap_order_and_credential_free_private_process(
    bootstrap_fixture, tmp_path, monkeypatch
):
    authority, env, control, manifest, now = bootstrap_fixture
    monkeypatch.setattr(pilot.time, "time", lambda: now)
    monkeypatch.setattr(pilot, "source_files", lambda *a: [])
    order = []
    work = tmp_path / "boot"
    work.mkdir()

    def metadata(*args):
        order.append("metadata")
        return {"job": {}, "timing": {}}

    def fetch(pin, destination, deadline):
        assert order[0] == "metadata"
        order.append("fetch")
        destination.write_bytes(b"fixture")

    def install(archive, prefix, pin):
        assert order.count("fetch") == 24
        order.append("install")
        (prefix / "bin").mkdir(parents=True)
        (prefix / "bin/python3.12").write_bytes(b"fixture")
        return prefix / "bin/python3.12"

    def launch(executable, argv, child_env):
        order.append("launch")
        assert argv[1:4] == ["-I", "-B", "-c"]
        assert executable == str(work / "python/bin/python3.12")
        assert child_env["LD_LIBRARY_PATH"] == str(work / "python/lib")
        assert (
            not {
                "GC286_METADATA_TOKEN",
                "GC286_OPERATOR_ENVELOPE",
                "JIRA_API_TOKEN",
                "PYTHONPATH",
                "LD_PRELOAD",
            }
            & child_env.keys()
        )
        assert "sys.path.insert" in argv[4]
        return 0

    env.update(
        JIRA_API_TOKEN="fixture-only", PYTHONPATH="/untrusted", LD_PRELOAD="/untrusted"
    )
    assert (
        pilot.bootstrap_verified(
            control,
            work,
            authority,
            manifest,
            env,
            metadata_reader=metadata,
            fetcher=fetch,
            installer=install,
            launch=launch,
        )
        == 0
    )
    assert order == ["metadata"] + ["fetch"] * 24 + ["install", "launch"]


@pytest.mark.parametrize(
    "damage", ["none", "commit", "tree", "head", "bytes", "mode", "extra"]
)
def test_exact_inline_object_reader_authenticates_whole_control_tree(
    tmp_path, monkeypatch, inline, damage
):
    root, identity, objects, commands = object_fixture(tmp_path, monkeypatch)
    (root / "source.py").chmod(0o644)
    if damage in ("commit", "tree"):
        objects[(damage, identity[damage])] += b"corrupt"
    elif damage == "head":
        (root / ".git/HEAD").write_text("f" * 40)
    elif damage == "bytes":
        (root / "source.py").write_bytes(b"changed")
    elif damage == "mode":
        (root / "source.py").chmod(0o755)
    elif damage == "extra":
        (root / "ignored-but-unadmitted").write_text("changed")
    if damage == "none":
        manifest = inline.verified_tree(root, identity, tmp_path)
        assert manifest == {
            "source.py": {"sha256": pilot.digest(root / "source.py"), "mode": 0o644}
        }
        assert len(commands) == 2
    else:
        with pytest.raises(ValueError):
            inline.verified_tree(root, identity, tmp_path)


def test_unavailable_metadata_stops_before_fetch_materialization_or_process(
    bootstrap_fixture, tmp_path, monkeypatch
):
    authority, env, control, manifest, _ = bootstrap_fixture
    monkeypatch.setattr(pilot, "source_files", lambda *a: [])

    def unavailable(*args):
        raise evidence.EvidenceError("metadata unavailable")

    def forbidden(*args):
        pytest.fail("metadata refusal must precede effect")

    with pytest.raises(evidence.EvidenceError):
        pilot.bootstrap_verified(
            control,
            tmp_path / "not-created",
            authority,
            manifest,
            env,
            metadata_reader=unavailable,
            fetcher=forbidden,
            installer=forbidden,
            launch=forbidden,
        )
    assert not (tmp_path / "not-created").exists()


def test_truncated_archive_never_creates_prefix(tmp_path, archive_fixture):
    archive, pin = archive_fixture()
    archive.write_bytes(archive.read_bytes()[:20])
    with pytest.raises(evidence.EvidenceError):
        pilot.materialize_python(archive, tmp_path / "prefix", pin)
    assert not (tmp_path / "prefix").exists()


def test_active_workflow_is_manual_only_with_exact_permissions_and_job_bounds(
    inline,
    bootstrap_fixture,
):
    import json

    source = (CI.parent / ".github/workflows/confluence-pilot.yml").read_text()
    header, jobs = source.split("\njobs:\n")
    assert [
        line for line in header.splitlines() if line and not line.startswith("#")
    ] == [
        "name: confluence-offline-core-pilot (bounded benchmark)",
        '"on":',
        "  workflow_dispatch:",
        "permissions:",
        "  contents: read",
        "  actions: read",
        "concurrency:",
        "  group: gc286-benchmark-${{ github.run_id }}",
        "  cancel-in-progress: false",
    ]
    serial, shards = jobs.split("\n  two_shards:\n")
    serial_header, _ = serial.split("    steps:\n")
    shard_header, _ = shards.split("    steps:\n")
    assert serial_header == (
        "  serial:\n    name: gc286-serial\n    environment: gc286-bounded\n"
        "    runs-on: ubuntu-24.04\n    timeout-minutes: 20\n"
    )
    assert shard_header == (
        "    name: gc286-${{ matrix.shard }}\n    environment: gc286-bounded\n"
        "    needs: serial\n    if: ${{ needs.serial.result == 'success' }}\n"
        "    runs-on: ubuntu-24.04\n    timeout-minutes: 20\n"
        "    strategy:\n      fail-fast: false\n      max-parallel: 2\n"
        "      matrix:\n        shard: [A, B]\n"
    )
    assert "vars.GC286_" not in source and "fromJSON(" not in source
    assert source.count("environment: gc286-bounded") == 2
    assert source.count("3< <(printf") == source.count("4< <(printf") == 2
    assert 'GC286_METADATA_TOKEN="$GC286_METADATA_TOKEN"' not in source
    assert source.count("        if: ${{ always() }}") == 2
    assert source.count("          if-no-files-found: error") == 2
    # The trusted inline admission refuses reruns even with otherwise matching
    # environment strings and envelope. No Git/process/API effect is involved.
    authority, env, _, _, now = bootstrap_fixture
    assert inline.authorize(env["GC286_OPERATOR_ENVELOPE"], env, now) == authority
    authority["attempt"] = env["GITHUB_RUN_ATTEMPT"] = "2"
    with pytest.raises(ValueError, match="replay or wrong attempt"):
        inline.authorize(json.dumps(authority), env, now)


# Source-only v5 contracts. Runtime execution requires a new Boss Clearance.
@pytest.fixture
def child_fixture(bootstrap_fixture, tmp_path, monkeypatch):
    """Real private files and validators; intercept Git, runtime and process effects."""
    authority, env, control, _, now = bootstrap_fixture
    for relative in pilot.OWNED:
        (control / relative).write_bytes((CI.parent / relative).read_bytes())
        (control / relative).chmod(0o644)
    work = tmp_path / "child-work"
    work.mkdir(mode=0o700)
    prefix = work / "python"
    (prefix / "bin").mkdir(parents=True)
    executable = prefix / "bin/python3.12"
    executable.write_bytes(b"inert interpreter fixture, never executable")
    product, engine = tmp_path / "product", tmp_path / "engine"
    product.mkdir()
    engine.mkdir()
    (engine / "fixture.py").write_text("inert engine fixture")
    selection = evidence.read_json(control / pilot.SELECTION)
    product_files = []
    for module in selection["modules"]:
        path = product / module["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("inert selected module fixture")
        module["sha256"] = pilot.digest(path)
        product_files.append(module["path"])
    for relative in selection["config"]:
        path = product / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("inert product config fixture")
        selection["config"][relative] = pilot.digest(path)
        product_files.append(relative)
    evidence.write_json(control / pilot.SELECTION, selection)
    assets = work / "assets"
    assets.mkdir()
    pins = evidence.read_json(control / "ci/pins.json")
    for record in [pins["python"], *pins["distributions"]]:
        path = assets / record["filename"]
        path.write_bytes(b"inert asset fixture")
        record["sha256"] = pilot.digest(path)
    (control / pilot.LOCK).write_text(pilot.lock_text(pins["distributions"]))
    pins["content"] = {
        relative: pilot.digest(control / relative)
        for relative in pilot.OWNED - {"ci/pins.json"}
    }
    evidence.write_json(control / "ci/pins.json", pins)
    authority["control"]["pins_sha256"] = pilot.digest(control / "ci/pins.json")
    manifest = {
        relative: {"sha256": pilot.digest(control / relative), "mode": 0o644}
        for relative in pilot.OWNED
    }
    runtime = {
        "platform": {
            "system": "Linux",
            "machine": "x86_64",
            "python": "3.12.12",
            "kernel": "fixture-kernel",
            "cpu_count": 2,
            "ram_bytes": 1024,
            "cpu_model": "fixture-cpu",
            "image_os": "ubuntu24",
            "image_version": "fixture-image",
        },
        "tools": {
            "python_sha256": pilot.digest(executable),
            "python_prefix_sha256": pilot.tree_digest(prefix),
            "bash_sha256": "b" * 64,
            "git_sha256": "c" * 64,
        },
    }
    payload = {
        "authority": authority,
        "control_inventory": manifest,
        "observed": {
            "run": {"id": 123, "head_sha": authority["control"]["commit"]},
            "job": {"id": 456, "name": "gc286-serial", "runner_id": 12},
            "timing": {
                "request_at": authority["not_before"],
                "arm_released_at": authority["not_before"],
                "job_started_at": "2026-09-08T00:01:00Z",
                "delay_basis": "request-to-start-including-protection-and-scheduling",
            },
        },
        "product": str(product),
        "engine": str(engine),
        "shard": "serial",
        "prefix_sha256": pilot.tree_digest(prefix),
        "bootstrap_observation": {
            "python": "3.12.3",
            "executable_sha256": "d" * 64,
            "image_os": "ubuntu24",
            "image_version": "fixture-image",
        },
    }
    payload_path = work / "bootstrap.json"
    evidence.write_json(payload_path, payload)
    monkeypatch.setattr(pilot.sys, "executable", str(executable))
    monkeypatch.setattr(pilot.sys, "base_prefix", str(prefix))
    monkeypatch.setattr(pilot.time, "time", lambda: now)
    monkeypatch.setattr(pilot.platform, "system", lambda: "Linux")
    monkeypatch.setattr(pilot.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(pilot.platform, "python_version", lambda: "3.12.12")
    monkeypatch.setattr(pilot.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(pilot, "observe_runtime", lambda: copy.deepcopy(runtime))
    for key in (
        "GITHUB_EVENT_NAME",
        "GITHUB_SHA",
        "GITHUB_REPOSITORY",
        "GITHUB_RUN_ID",
        "GITHUB_RUN_ATTEMPT",
    ):
        monkeypatch.setenv(key, env[key])

    def source_files(root, expected):
        assert (root, expected) in (
            (product, pins["sources"]["product"]),
            (engine, pins["sources"]["engine"]),
        )
        return product_files if root == product else ["fixture.py"]

    def forbidden(*args, **kwargs):
        pytest.fail("child contract attempted an unrelated external effect")

    monkeypatch.setattr(pilot, "source_files", source_files)
    monkeypatch.setattr(pilot.os, "execve", forbidden)
    monkeypatch.setattr(pilot.subprocess, "run", forbidden)
    monkeypatch.setattr(pilot.subprocess, "Popen", forbidden)
    monkeypatch.setattr(pilot.urllib.request, "build_opener", forbidden)
    monkeypatch.setattr(pilot, "materialize_python", forbidden)
    order, contexts = [], []
    actual_validate = pilot.validate_inputs

    def validate(*args):
        order.append("validate-enter")
        context = actual_validate(*args)
        order.append("validate-return")
        contexts.append(context)
        return context

    def runner(context, *args):
        assert order == ["validate-enter", "validate-return"]
        assert context is contexts[0]
        assert args == (control, product, engine, assets, work / "evidence-serial")
        order.append("runner")
        return 0

    monkeypatch.setattr(pilot, "validate_inputs", validate)
    monkeypatch.setattr(pilot, "run_admitted", runner)
    return SimpleNamespace(
        control=control,
        work=work,
        payload=payload,
        payload_path=payload_path,
        payload_sha=pilot.digest(payload_path),
        runtime=runtime,
        order=order,
        contexts=contexts,
    )


def test_bootstrap_child_real_admission_provenance_digest_and_validation_order(
    child_fixture,
):
    fixture = child_fixture
    assert (
        pilot.bootstrap_child(
            str(fixture.control), str(fixture.work), fixture.payload_sha
        )
        == 0
    )
    assert fixture.order == ["validate-enter", "validate-return", "runner"]
    context = fixture.contexts[0]
    admission = evidence.read_json(fixture.work / "admission.json")
    assert context["admission"] == admission
    assert context["admission_sha256"] == pilot.digest(fixture.work / "admission.json")
    assert context["runtime"] == admission["runtime"] == fixture.runtime
    assert admission["operator_authority"] == fixture.payload["authority"]
    assert admission["control"] == fixture.payload["authority"]["control"]
    assert admission["sources"] == fixture.payload["authority"]["sources"]
    assert admission["observed_run"] == fixture.payload["observed"]["run"]
    assert admission["observed_job"] == fixture.payload["observed"]["job"]
    assert admission["timing"] == fixture.payload["observed"]["timing"]
    assert admission["observed_bootstrap"] == fixture.payload["bootstrap_observation"]
    assert admission["control_inventory"] == fixture.payload["control_inventory"]
    assert len(context["nodes"]) == 47
    # A completed first entry is not permission to call the runner twice.
    with pytest.raises(FileExistsError):
        pilot.bootstrap_child(
            str(fixture.control), str(fixture.work), fixture.payload_sha
        )
    assert fixture.order.count("runner") == 1


@pytest.mark.parametrize(
    "change, message",
    [
        ("payload-hash", "changed bootstrap handoff"),
        ("expired", "expired child authority"),
        ("child-marker", ""),
        ("executable", "ambient interpreter substitution"),
        ("base-prefix", "ambient interpreter substitution"),
        ("prefix-bytes", "changed materialized prefix"),
        ("snapshot-bytes", "changed private snapshot"),
        ("snapshot-mode", "changed private snapshot"),
        ("runtime-platform", "unavailable runtime identity"),
        ("runtime-mismatch", "wrong tool, hardware or image identity"),
        ("event-name", "wrong actual event"),
        ("event-sha", "wrong actual event"),
        ("event-repository", "wrong actual event"),
        ("event-run", "wrong actual event"),
        ("event-attempt", "wrong actual event"),
    ],
)
def test_bootstrap_child_refuses_before_runner(
    child_fixture, monkeypatch, change, message
):
    fixture = child_fixture
    if change == "payload-hash":
        fixture.payload_path.write_bytes(fixture.payload_path.read_bytes() + b" ")
    elif change == "expired":
        fixture.payload["authority"]["expires_at"] = "2026-09-08T00:10:00Z"
        evidence.write_json(fixture.payload_path, fixture.payload)
        fixture.payload_sha = pilot.digest(fixture.payload_path)
    elif change == "child-marker":
        (fixture.work / "child-started").mkdir()
    elif change == "executable":
        monkeypatch.setattr(pilot.sys, "executable", "/unrelated/python")
    elif change == "base-prefix":
        monkeypatch.setattr(pilot.sys, "base_prefix", "/unrelated/prefix")
    elif change == "prefix-bytes":
        (fixture.work / "python/bin/python3.12").write_bytes(b"changed")
    elif change == "snapshot-bytes":
        (fixture.control / "ci/pilot.py").write_text("changed")
    elif change == "snapshot-mode":
        (fixture.control / "ci/pilot.py").chmod(0o600)
    elif change == "runtime-platform":
        fixture.runtime["platform"]["system"] = "Darwin"
    elif change == "runtime-mismatch":
        observations = [copy.deepcopy(fixture.runtime), copy.deepcopy(fixture.runtime)]
        observations[1]["tools"]["python_sha256"] = "e" * 64
        monkeypatch.setattr(pilot, "observe_runtime", lambda: observations.pop(0))
    else:
        key = {
            "event-name": "GITHUB_EVENT_NAME",
            "event-sha": "GITHUB_SHA",
            "event-repository": "GITHUB_REPOSITORY",
            "event-run": "GITHUB_RUN_ID",
            "event-attempt": "GITHUB_RUN_ATTEMPT",
        }[change]
        monkeypatch.setenv(key, "wrong")
    error = FileExistsError if change == "child-marker" else evidence.EvidenceError
    with pytest.raises(error, match=message):
        pilot.bootstrap_child(
            str(fixture.control), str(fixture.work), fixture.payload_sha
        )
    assert "runner" not in fixture.order and fixture.contexts == []
    if change.startswith("event-") or change == "runtime-mismatch":
        assert fixture.order == ["validate-enter"]
    else:
        assert fixture.order == []


@pytest.mark.parametrize("budget", [30, 300])
@pytest.mark.parametrize("delayed", ["open", "body", "eof", "redirect"])
def test_https_cooperative_budget_refuses_when_delayed_control_returns(
    monkeypatch, budget, delayed
):
    import urllib.error

    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(pilot.time, "monotonic", lambda: clock.now)
    deadline = clock.now + budget
    url = (
        "https://github.com/actions/python-versions/releases/download/fixture/a.tar.gz"
    )
    response = HTTPSResponse(url, b"a")
    calls = []

    def read(count):
        calls.append("read-enter")
        assert count > 0
        clock.now = deadline + 1
        calls.append("read-return")
        return b"" if delayed == "eof" else b"a"

    response.read1 = read

    def open_request(request, timeout):
        calls.append("open-enter")
        assert request.full_url == url and timeout == 15
        if delayed in ("open", "redirect"):
            # No sleep or network: model a blocking operation returning late.
            clock.now = deadline + 1
        calls.append("open-return")
        if delayed == "redirect":
            raise urllib.error.HTTPError(
                url,
                302,
                "redirect",
                {"Location": "https://release-assets.githubusercontent.com/fixture"},
                None,
            )
        return response

    with pytest.raises(evidence.EvidenceError, match="HTTPS deadline exceeded"):
        pilot.https_bytes(
            url,
            4,
            deadline,
            asset=True,
            opener=SimpleNamespace(open=open_request),
        )
    assert clock.now == deadline + 1
    expected = ["open-enter", "open-return"]
    if delayed in ("body", "eof"):
        expected += ["read-enter", "read-return"]
    assert calls == expected  # No retry or second read after the late return.
    if delayed != "redirect":
        assert response.stream.closed


@pytest.mark.parametrize("suffix", ["", "@gc286-reviewed-fixture"])
def test_metadata_accepts_only_bare_or_authorized_short_tag(
    metadata_fixture, inline, suffix
):
    authority, env, run, _, _, fetch, calls = metadata_fixture
    # Exercise the real upstream authority/ref checks before using its short tag.
    admitted = inline.authorize(env["GC286_OPERATOR_ENVELOPE"], env, pilot.time.time())
    assert admitted == authority
    run["path"] = ".github/workflows/confluence-pilot.yml" + suffix
    observed = pilot.github_metadata(admitted, env, fetch=fetch)
    assert observed["run"] == run and len(calls) == 2


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/confluence-pilot.yml@gc286-reviewed-other",
        ".github/workflows/confluence-pilot.yml@main",
        ".github/workflows/confluence-pilot.yml@refs/tags/gc286-reviewed-fixture",
        ".github/workflows/confluence-pilot.yml@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ".github/workflows/confluence-pilot.yml@@gc286-reviewed-fixture",
        ".github/workflows/confluence-pilot.yml@gc286-reviewed-fixture@main",
        ".github/workflows/confluence-pilot.yml.extra@gc286-reviewed-fixture",
        "prefix/.github/workflows/confluence-pilot.yml@gc286-reviewed-fixture",
        ".github/workflows/other.yml@gc286-reviewed-fixture",
        ".github/workflows/other.yml",
    ],
)
def test_metadata_rejects_wrong_path_or_suffix(metadata_fixture, path):
    authority, env, run, _, _, fetch, _ = metadata_fixture
    run["path"] = path
    with pytest.raises(evidence.EvidenceError, match="wrong observed workflow"):
        pilot.github_metadata(authority, env, fetch=fetch)
