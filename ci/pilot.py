"""Dormant GC-286 fixed benchmark controller; run only after separate Clearance.

A trusted launcher must verify this control checkout *before executing this file*
and supply --admission-sha256 out of band. An editable admission beside candidate
code is not a trust root. No PR mode or local/full-suite evidence waiver exists.
Inputs are pristine product/engine/control Git checkouts and preverified public
assets. The inline workflow verifier authenticates bootstrap code before imports.
Independent result acceptance and protected environment configuration are external.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import platform
import re
import resource
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

try:
    from .pytest_evidence import (
        EvidenceError,
        exact_nodes,
        loads_json,
        read_json,
        require,
        verify_events,
        write_json,
    )
except ImportError:
    from pytest_evidence import (
        EvidenceError,
        exact_nodes,
        loads_json,
        read_json,
        require,
        verify_events,
        write_json,
    )

OWNED = {
    ".github/workflows/confluence-pilot.yml",
    "ci/pins.json",
    "ci/locks/linux-py312.txt",
    "ci/selections/confluence-offline-core-v1.json",
    "ci/pilot.py",
    "ci/pytest_evidence.py",
    "tests/test_ci_evidence.py",
}
PRODUCT = "a653afea42956bc00369cf8a02bababd5fc03dbf"
ENGINE = "1ec67cb4886f1ae1818f303b878a51fd7cc81f37"
SELECTION = "ci/selections/confluence-offline-core-v1.json"
LOCK = "ci/locks/linux-py312.txt"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha(value, length=64):
    require(
        isinstance(value, str) and re.fullmatch(f"[0-9a-f]{{{length}}}", value),
        "missing or malformed digest",
    )
    return value


def member(root, name):
    require(
        isinstance(name, str)
        and name
        and not Path(name).is_absolute()
        and ".." not in Path(name).parts,
        "unsafe relative path",
    )
    path = root / name
    require(
        path.resolve().is_relative_to(root.resolve()) and not path.is_symlink(),
        "symlink or escaped input",
    )
    require(path.is_file(), f"missing input: {name}")
    return path


def lock_text(distributions):
    return (
        "# Linux x86_64 CPython 3.12; wheels only, no resolver, no extras.\n"
        + "".join(
            f"{d['name']}=={d['version']} --hash=sha256:{d['sha256']}\n"
            for d in sorted(distributions, key=lambda d: d["name"])
        )
    )


def selection_nodes(selection, shard):
    require(
        selection.get("schema") == "confluence-selection/v1", "wrong selection schema"
    )
    require(shard in ("serial", "A", "B"), "wrong shard")
    require(selection.get("plugins") == ["pytest_evidence"], "wrong plugin selection")
    modules = selection["modules"]
    require(
        [(m["path"], m["shard"], len(m["nodes"])) for m in modules]
        == [
            ("tests/test_api_cmds.py", "A", 30),
            ("tests/test_wrapper_sequences.py", "A", 6),
            ("tests/test_startup.py", "B", 7),
            ("tests/test_spec_build.py", "B", 4),
        ],
        "changed whole-module partition",
    )
    all_nodes = [n for m in modules for n in m["nodes"]]
    exact_nodes(all_nodes, list(dict.fromkeys(all_nodes)))
    for module in modules:
        sha(module["sha256"])
        require(
            all(n.startswith(module["path"] + "::test_") for n in module["nodes"]),
            "node outside module",
        )
    require(
        selection["count_basis"] == "static-uncollected" and len(all_nodes) == 47,
        "invalid static expectation",
    )
    return [
        n
        for m in modules
        if shard == "serial" or m["shard"] == shard
        for n in m["nodes"]
    ]


def validate_policy(admission, pins, selection, shard):
    """Pure admission checks; callers cannot substitute PR evidence for this benchmark."""
    require(
        admission.get("schema") == "confluence-pilot-admission/v1",
        "wrong admission schema",
    )
    require(
        admission.get("mode") == pins.get("mode") == "fixed-benchmark", "wrong mode"
    )
    require(admission.get("allow_execute") is True, "execution not admitted")
    event = admission["event"]
    require(event.get("name") == "workflow_dispatch", "wrong event mode")
    require(event.get("repository") == "grandcamel/confluence-as", "wrong repository")
    require(
        event.get("sha") == admission["control"]["commit"], "wrong event/control source"
    )
    for key in ("run_id", "attempt"):
        require(
            isinstance(event.get(key), str)
            and event[key].isdigit()
            and int(event[key]) > 0,
            f"invalid {key}",
        )
    require(pins.get("schema") == "confluence-pins/v1", "wrong pins schema")
    require(
        pins["sources"]["product"]["commit"] == PRODUCT
        and pins["sources"]["engine"]["commit"] == ENGINE,
        "wrong fixed source",
    )
    require(admission["sources"] == pins["sources"], "wrong admitted source")
    for identity in [admission["control"], *pins["sources"].values()]:
        sha(identity["commit"], 40)
        sha(identity["tree"], 40)
    sha(admission["control"]["pins_sha256"])
    require(
        set(pins["content"]) == OWNED - {"ci/pins.json"}, "incomplete control manifest"
    )
    require(
        pins["external_bindings"]
        == [
            "ci/pins.json",
            "control.commit",
            "control.tree",
            "runtime.tools",
            "runtime.platform",
            "event",
            "timing",
        ],
        "circular or missing bindings",
    )
    for value in pins["content"].values():
        sha(value)
    require(
        set(pins["actions"]) == {"actions/checkout", "actions/upload-artifact"},
        "wrong actions",
    )
    for value in pins["actions"].values():
        sha(value, 40)
    require(
        pins["python"]["version"] == "3.12.12"
        and pins["python"]["availability"] == "published",
        "unavailable interpreter",
    )
    sha(pins["python"]["sha256"])
    distributions = pins["distributions"]
    names = [d["name"] for d in distributions]
    require(len(names) == len(set(names)), "duplicate distribution")
    require(
        {
            "pip",
            "pytest",
            "responses",
            "requests",
            "click",
            "assistant-skills-lib",
            "build",
            "hatchling",
            "editables",
        }
        <= set(names),
        "missing required pin",
    )
    for dist in distributions:
        sha(dist["sha256"])
        require(
            dist.get("availability") == "archive-verified"
            and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", dist["name"])
            and re.fullmatch(r"[0-9][a-zA-Z0-9.]*", dist["version"]),
            "invalid distribution pin",
        )
        require(set(dist["dependencies"]) <= set(names), "missing transitive pin")
        require(dist["filename"].endswith(".whl"), "source dependency disallowed")
    return selection_nodes(selection, shard)


def git_locations(root):
    """Read locator/ref data only; never ask a candidate-configured Git to run."""
    dotgit = root / ".git"
    require(not dotgit.is_symlink(), "symlink Git locator")
    if dotgit.is_file():
        locator = dotgit.read_text().strip()
        require(locator.startswith("gitdir: "), "invalid Git locator")
        gitdir = (root / locator[8:]).resolve()
    else:
        gitdir = dotgit.resolve()
    require(gitdir.is_dir(), "missing Git metadata")
    common_file = gitdir / "commondir"
    common = (
        (gitdir / common_file.read_text().strip()).resolve()
        if common_file.exists()
        else gitdir
    )
    head = (gitdir / "HEAD").read_text().strip()
    if head.startswith("ref: "):
        ref = head[5:]
        require(
            re.fullmatch(r"refs/heads/[A-Za-z0-9._/-]+", ref) and ".." not in ref,
            "unsupported HEAD reference",
        )
        loose = common / ref
        if loose.is_file():
            head = loose.read_text().strip()
        else:
            packed = common / "packed-refs"
            matches = [
                line.split()[0]
                for line in packed.read_text().splitlines()
                if not line.startswith(("#", "^")) and line.endswith(" " + ref)
            ]
            require(len(matches) == 1, "missing or ambiguous HEAD reference")
            head = matches[0]
    sha(head, 40)
    require((common / "objects").is_dir(), "missing object storage")
    return common / "objects", head


def git_object(isolated, objects, kind, oid):
    """Only object access, from a fresh private Git directory with no local config.

    Candidate config, refs/replacements, index, hooks, filters and promisor remotes
    are never loaded. Object-store alternates are only data; every consumed commit
    and tree is rehashed, and working blobs are checked against those exact trees.
    """
    require(kind in ("commit", "tree"), "unsupported object read")
    sha(oid, 40)
    env = {
        "PATH": "/usr/bin:/bin",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_OBJECT_DIRECTORY": str(objects),
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
    }
    data = subprocess.check_output(
        [
            "/usr/bin/git",
            "--no-pager",
            "--no-replace-objects",
            "--git-dir=" + str(isolated),
            "cat-file",
            kind,
            oid,
        ],
        env=env,
        cwd=isolated,
        timeout=10,
    )
    actual = hashlib.sha1(
        kind.encode() + b" " + str(len(data)).encode() + b"\0" + data
    ).hexdigest()
    require(actual == oid, "object content does not match pinned identity")
    return data


def source_files(root, expected):
    objects, head = git_locations(root)
    require(head == expected["commit"], "wrong checkout commit")
    paths = []
    with tempfile.TemporaryDirectory(prefix="gc286-object-read-") as directory:
        isolated = Path(directory)
        (isolated / "refs").mkdir()
        (isolated / "objects").mkdir()
        (isolated / "HEAD").write_text("ref: refs/heads/unused\n")
        (isolated / "config").write_text(
            "[core]\nrepositoryformatversion = 0\nbare = true\n"
        )
        commit = git_object(isolated, objects, "commit", expected["commit"])
        require(
            commit.split(b"\n", 1)[0] == b"tree " + expected["tree"].encode(),
            "wrong committed tree",
        )
        pending = [("", expected["tree"])]
        while pending:
            prefix, oid = pending.pop()
            data = git_object(isolated, objects, "tree", oid)
            while data:
                header, separator, tail = data.partition(b"\0")
                require(separator and len(tail) >= 20, "malformed tree object")
                mode, name = header.decode().split(" ", 1)
                require(
                    name not in (".", "..", ".git") and "/" not in name,
                    "unsafe tree entry",
                )
                oid, data = tail[:20].hex(), tail[20:]
                relative = prefix + name
                if mode == "40000":
                    pending.append((relative + "/", oid))
                    continue
                require(mode in ("100644", "100755"), "unsupported source entry")
                path = member(root, relative)
                raw = path.read_bytes()
                actual = hashlib.sha1(
                    b"blob " + str(len(raw)).encode() + b"\0" + raw
                ).hexdigest()
                require(
                    actual == oid
                    and bool(path.stat().st_mode & 0o111) == (mode == "100755"),
                    "source bytes/mode differ from committed tree",
                )
                paths.append(relative)
    inventory = []
    for folder, directories, files in os.walk(root, followlinks=False):
        if Path(folder) == root:
            directories[:] = [d for d in directories if d != ".git"]
            files = [f for f in files if f != ".git"]
        require(
            all(not (Path(folder) / d).is_symlink() for d in directories),
            "symlink source directory",
        )
        inventory.extend((Path(folder) / f).relative_to(root).as_posix() for f in files)
    require(
        len(paths) == len(set(paths)) and set(inventory) == set(paths),
        "untracked, ignored, duplicate or missing source content",
    )
    return sorted(paths)


def tree_digest(root):
    """All prefix files, modes and symlink targets; no dereference of directory links."""
    rows = []
    for folder, directories, files in os.walk(root, followlinks=False):
        for name in sorted(directories + files):
            path = Path(folder) / name
            mode = path.lstat().st_mode
            value = (
                "link:" + os.readlink(path)
                if path.is_symlink()
                else digest(path)
                if path.is_file()
                else "directory"
            )
            rows.append((path.relative_to(root).as_posix(), mode, value))
    return hashlib.sha256(
        json.dumps(sorted(rows), separators=(",", ":")).encode()
    ).hexdigest()


def observe_runtime():
    memory = (
        int(
            next(
                line.split()[1]
                for line in Path("/proc/meminfo").read_text().splitlines()
                if line.startswith("MemTotal:")
            )
        )
        * 1024
    )
    cpu = next(
        line.split(":", 1)[1].strip()
        for line in Path("/proc/cpuinfo").read_text().splitlines()
        if line.startswith("model name")
    )
    return {
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "kernel": platform.release(),
            "cpu_count": os.cpu_count(),
            "ram_bytes": memory,
            "cpu_model": cpu,
            "image_os": os.environ.get("ImageOS"),
            "image_version": os.environ.get("ImageVersion"),
        },
        "tools": {
            "python_sha256": digest(sys.executable),
            "python_prefix_sha256": tree_digest(Path(sys.base_prefix)),
            "bash_sha256": digest("/bin/bash"),
            "git_sha256": digest("/usr/bin/git"),
        },
    }


def validate_inputs(
    control, product, engine, assets, admission_path, admission_sha256, shard
):
    require(digest(admission_path) == sha(admission_sha256), "changed admission")
    admission = read_json(admission_path)
    pins = read_json(control / "ci/pins.json")
    require(
        digest(control / "ci/pins.json") == sha(admission["control"]["pins_sha256"]),
        "changed pins",
    )
    for path, expected in pins["content"].items():
        require(
            digest(member(control, path)) == sha(expected),
            f"changed control input: {path}",
        )
    workflow = (control / ".github/workflows/confluence-pilot.yml").read_text()
    require(
        set(re.findall(r"uses: ([a-zA-Z0-9/-]+@[0-9a-f]{40})", workflow))
        == {f"{name}@{value}" for name, value in pins["actions"].items()},
        "wrong workflow action pins",
    )
    selection = read_json(control / SELECTION)
    nodes = validate_policy(admission, pins, selection, shard)
    require(
        (control / LOCK).read_text() == lock_text(pins["distributions"]),
        "changed dependency lock",
    )
    if "control_inventory" in admission:
        snapshot_files(control, admission["control_inventory"])
    else:
        source_files(control, admission["control"])
    files = {
        "product": source_files(product, pins["sources"]["product"]),
        "engine": source_files(engine, pins["sources"]["engine"]),
    }
    for module in selection["modules"]:
        require(
            digest(member(product, module["path"])) == module["sha256"],
            "changed selected module",
        )
    for path, expected in selection["config"].items():
        require(digest(member(product, path)) == expected, "changed product config")
    for dist in pins["distributions"]:
        require(
            digest(member(assets, dist["filename"])) == dist["sha256"],
            "changed dependency asset",
        )
    require(
        digest(member(assets, pins["python"]["filename"])) == pins["python"]["sha256"],
        "changed interpreter archive",
    )
    require(
        platform.system() == "Linux"
        and platform.machine() == "x86_64"
        and platform.python_version() == "3.12.12"
        and os.geteuid() != 0,
        "wrong runtime platform",
    )
    runtime = observe_runtime()
    require(runtime == admission["runtime"], "wrong tool, hardware or image identity")
    require(
        runtime["platform"]["image_os"] == "ubuntu24"
        and bool(runtime["platform"]["image_version"]),
        "missing image identity",
    )
    require(
        {
            "name": os.environ.get("GITHUB_EVENT_NAME"),
            "sha": os.environ.get("GITHUB_SHA"),
            "repository": os.environ.get("GITHUB_REPOSITORY"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        }
        == admission["event"],
        "wrong actual event",
    )
    parse_time(admission["timing"]["request_at"])
    released = parse_time(admission["timing"]["arm_released_at"])
    started = parse_time(admission["timing"]["job_started_at"])
    require(
        parse_time(admission["timing"]["request_at"])
        <= released
        <= started
        <= time.time(),
        "invalid timing order",
    )
    return {
        "admission": admission,
        "pins": pins,
        "selection": selection,
        "nodes": nodes,
        "files": files,
        "file_hashes": {
            name: {p: digest(root / p) for p in files[name]}
            for name, root in (("product", product), ("engine", engine))
        },
        "runtime": runtime,
        "shard": shard,
        "admission_sha256": admission_sha256,
    }


def clean_environment(root, python):
    return {
        "PATH": str(python.parent) + ":/usr/bin:/bin",
        "HOME": str(root / "home"),
        "TMPDIR": str(root / "tmp"),
        "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_DATA_HOME": str(root / "data"),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PIP_CONFIG_FILE": "/dev/null",
        "PIP_NO_INDEX": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "CONFLUENCE_AS_TRANSPORT": "responder",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
    }


class ChildFailure(Exception):
    def __init__(self, code, status="child-failed"):
        self.code = code if code >= 0 else 128 - code
        self.status = status
        super().__init__(f"{status}: exit {self.code}")


class LinuxPhase:
    """One single-threaded controller, one direct leader, no detached-service scope.

    Linux subreaper adoption exposes orphan roots even if they leave the group.
    Such escapes are nonaccepting and never signalled through guessed identities.
    WNOWAIT keeps the direct leader unreaped through the last group signal. All
    reap calls are nonblocking; this is not the GC204 detached-containment proof.
    """

    def __init__(self):
        require(
            sys.platform == "linux" and hasattr(os, "WNOWAIT"),
            "unsupported child observation",
        )
        require(
            signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL,
            "unsupported child reaper",
        )
        require(
            len(list(Path("/proc/self/task").iterdir())) == 1,
            "controller must be single-threaded",
        )
        require(not self.children(), "unowned child present before phase")
        self.libc = ctypes.CDLL(None, use_errno=True)
        previous = ctypes.c_int()
        if self.libc.prctl(37, ctypes.byref(previous), 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "cannot read Linux subreaper state")
        self.previous = previous.value
        if self.libc.prctl(36, 1, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "cannot enable Linux subreaper")
        self.child = None

    def children(self):
        path = Path(f"/proc/self/task/{os.getpid()}/children")
        return [int(value) for value in path.read_text().split()]

    def observe(self):
        result = os.waitid(
            os.P_PID, self.child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT
        )
        if result is None:
            return None
        require(result.si_pid == self.child.pid, "wrong wait identity")
        require(
            result.si_code in (os.CLD_EXITED, os.CLD_KILLED, os.CLD_DUMPED),
            "unknown terminal state",
        )
        return (
            result.si_status
            if result.si_code == os.CLD_EXITED
            else 128 + result.si_status
        )

    def adopted(self):
        live, escaped = [], False
        for pid in self.children():
            if pid == self.child.pid:
                continue
            # This controller is the exclusive reaper: these direct children
            # cannot be recycled between snapshot, stat and nonblocking wait.
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
            require(int(fields[1]) == os.getpid(), "adopted child ownership changed")
            escaped |= (
                int(fields[2]) != self.child.pid or int(fields[3]) != self.child.pid
            )
            terminal = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            if terminal is None:
                live.append(pid)
            else:
                reaped, _ = os.waitpid(pid, os.WNOHANG)
                require(reaped == pid, "adopted child reap uncertain")
        # Reaping a terminal adopted root can expose newly reparented children
        # absent from the first snapshot. Re-read before claiming the set empty.
        return [pid for pid in self.children() if pid != self.child.pid], escaped

    def kill_group(self):
        self.observe()  # ECHILD means lost identity: refuse every signal.
        require(
            os.getpgid(self.child.pid) == self.child.pid
            and os.getsid(self.child.pid) == self.child.pid,
            "leader left owned session/group",
        )
        try:
            os.killpg(self.child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # Leader is still an unreaped direct child; group may be zombie-only.

    def reap(self, terminal):
        pid, status = os.waitpid(self.child.pid, os.WNOHANG)
        require(pid == self.child.pid, "final leader reap uncertain")
        actual = os.waitstatus_to_exitcode(status)
        require(
            (actual if actual >= 0 else 128 - actual) == terminal,
            "leader status changed",
        )
        self.child.returncode = actual

    def restore(self):
        # A failed cleanup retains subreaper status until this controller exits.
        if self.child is None or self.child.returncode is not None:
            if self.libc.prctl(36, self.previous, 0, 0, 0) != 0:
                raise OSError(ctypes.get_errno(), "cannot restore subreaper state")


def finish_phase(
    group,
    timeout,
    clock=time.monotonic,
    pause=time.sleep,
    cleanup_seconds=3,
    cancelled=lambda: None,
):
    """Interceptable lifecycle state machine; original failure wins over cleanup errors."""
    failure = None
    terminal = None
    deadline = clock() + timeout
    try:
        while True:
            if cancelled() is not None:
                raise ChildFailure(128 + cancelled(), "cancelled")
            terminal = group.observe()
            if terminal is not None:
                if terminal:
                    failure = ChildFailure(terminal)
                elif clock() >= deadline:
                    failure = ChildFailure(124, "timed-out")
                break
            if clock() >= deadline:
                raise ChildFailure(124, "timed-out")
            pause(0.02)
        live, escaped = group.adopted()
        if escaped:
            raise ChildFailure(4, "unsupported-group-escape")
        if terminal == 0 and live:
            failure = failure or ChildFailure(4, "descendants-outlived-leader")
    except ChildFailure as exc:
        failure = failure or exc
    except (OSError, ValueError, IndexError) as exc:
        failure = failure or ChildFailure(4, "kernel-observation-uncertain")
        failure.cleanup_uncertainty = str(exc)

    # Cleanup is always bounded, including final reaping. Further cancellation
    # only preserves the first status; it must not interrupt the cleanup deadline.
    cleanup_error = None
    try:
        deadline = clock() + cleanup_seconds
        group.kill_group()
        while True:
            if cancelled() is not None:
                failure = failure or ChildFailure(128 + cancelled(), "cancelled")
            terminal = group.observe()
            live, escaped = group.adopted()
            if escaped:
                failure = failure or ChildFailure(4, "unsupported-group-escape")
                cleanup_error = "escaped child is outside admitted signal coverage"
            if terminal is not None and not live:
                group.reap(terminal)
                break
            if clock() >= deadline:
                raise EvidenceError(
                    "cleanup deadline exceeded; child absence/reap unproved"
                )
            pause(0.02)
    except (OSError, ValueError, IndexError, ChildFailure) as exc:
        cleanup_error = str(exc)
    if cleanup_error:
        failure = failure or ChildFailure(4, "cleanup-uncertain")
        failure.cleanup_uncertainty = cleanup_error
    if failure:
        raise failure


def execute(argv, cwd, env, timeout, log):
    group = LinuxPhase()  # Unsupported kernel/process posture refuses before spawn.
    old_handlers = {}
    cancelled = []

    def cancel(signum, frame):
        if not cancelled:
            cancelled.append(signum)

    failure = None
    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            old_handlers[signum] = signal.signal(signum, cancel)
        with log.open("xb") as stream:
            group.child = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                finish_phase(
                    group,
                    timeout,
                    cancelled=lambda: cancelled[0] if cancelled else None,
                )
            except ChildFailure as exc:
                failure = exc
                if getattr(exc, "cleanup_uncertainty", None):
                    try:
                        stream.write(
                            (
                                "\ncleanup uncertainty: "
                                + exc.cleanup_uncertainty
                                + "\n"
                            ).encode()
                        )
                    except OSError:
                        pass  # Retain original child status even if its log cannot be salvaged.
                raise
    finally:
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
        try:
            group.restore()
        except OSError:
            if failure is None:
                raise


def verify_phase(directory, nodes, identity, collect_only):
    require(directory.is_dir(), "missing phase artifacts")
    terminal = read_json(directory / "terminal.json")
    require(
        terminal
        == {"status": "complete", "error": None, "identity": identity, "exitstatus": 0},
        "nonaccepting terminal artifact",
    )
    events = [
        loads_json(line)
        for line in (directory / "events.jsonl").read_text().splitlines()
    ]
    verify_events(events, nodes, identity, collect_only)
    exact_nodes(read_json(directory / "collection.json")["nodes"], nodes)
    return events


def verify_junit(path, nodes):
    raw = path.read_text()
    require("<!DOCTYPE" not in raw and "<!ENTITY" not in raw, "unsafe XML declaration")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise EvidenceError("invalid JUnit XML") from exc
    cases = list(root.iter("testcase"))
    actual = [(c.get("classname"), c.get("name")) for c in cases]
    expected = [
        (n.split("::", 1)[0][:-3].replace("/", "."), n.split("::", 1)[1]) for n in nodes
    ]
    require(
        actual == expected and len(actual) == len(set(actual)), "JUnit node mismatch"
    )
    require(
        not any(list(root.iter(tag)) for tag in ("failure", "error", "skipped")),
        "nonpassing JUnit outcome",
    )


def parse_time(value):
    require(isinstance(value, str) and value.endswith("Z"), "UTC timestamp required")
    return datetime.fromisoformat(value[:-1] + "+00:00").timestamp()


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def summarize_comparison(admission, jobs, final_verified_at, rate_per_minute):
    """Trusted consumer supplies API job times after verifying every required artifact.

    This pure calculator does not authenticate job records or replace that consumer.
    Serial prerequisite waiting is kept outside the sharded arm's release interval.
    """
    require(
        len(jobs) == 3 and {j["shard"] for j in jobs} == {"serial", "A", "B"},
        "missing or duplicate job",
    )
    require(
        all(j["identity"] == jobs[0]["identity"] for j in jobs),
        "unmatched comparison inputs",
    )
    require(
        set(jobs[0]["identity"])
        == {
            "sources",
            "control",
            "pins_sha256",
            "selection_sha256",
            "runtime",
            "generated",
        },
        "incomplete comparison identity",
    )
    require(
        all(
            j["status"] == "verified" and j["attempt"] == admission["event"]["attempt"]
            for j in jobs
        ),
        "failed, partial or mixed-attempt comparison",
    )
    require(
        type(rate_per_minute) in (float, int)
        and math.isfinite(rate_per_minute)
        and rate_per_minute >= 0,
        "invalid admitted rate",
    )
    end = parse_time(final_verified_at)
    request = parse_time(admission["timing"]["request_at"])
    arms = {}
    minutes = 0
    for name, shards in (("serial", {"serial"}), ("two-shards", {"A", "B"})):
        group = [j for j in jobs if j["shard"] in shards]
        releases = {j["arm_released_at"] for j in group}
        require(len(releases) == 1, "inconsistent arm release")
        release = parse_time(next(iter(releases)))
        verified = max(parse_time(j["verified_at"]) for j in group)
        require(request <= release <= verified <= end, "invalid arm interval")
        details = []
        for job in group:
            start, finish = (
                parse_time(job["started_at"]),
                parse_time(job["completed_at"]),
            )
            require(
                release <= start <= finish <= parse_time(job["verified_at"]),
                "invalid job interval",
            )
            seconds = finish - start
            minutes += math.ceil(seconds / 60)
            details.append(
                {
                    "shard": job["shard"],
                    (
                        "release_to_start_seconds"
                        if "delay_basis" in job
                        else "queue_seconds"
                    ): start - release,
                    "delay_basis": job.get("delay_basis", "eligibility-to-start"),
                    "running_seconds": seconds,
                }
            )
        arms[name] = {"feedback_seconds": verified - release, "jobs": details}
    return {
        "arms": arms,
        "experiment_seconds": end - request,
        "rounded_runner_minutes": minutes,
        "aggregate_compute_cost": minutes * rate_per_minute,
        "topology_decision": "pending-approved-measurements",
    }


def run_admitted(context, control, product, engine, assets, output, runner=execute):
    """Effect seam. Called only with validate_inputs result, never an artifact's code."""
    require(not output.exists(), "output already exists; no overwrite/rerun-to-green")
    if "operator_authority" in context["admission"]:
        require(
            time.time()
            < parse_time(context["admission"]["operator_authority"]["expires_at"]),
            "authority expired before pilot effects",
        )
    output.mkdir(parents=True)
    report = {
        "schema": "confluence-pilot-result/v1",
        "status": "incomplete",
        "exitstatus": None,
        "mode": "fixed-benchmark",
        "admission": context["admission"],
        "admission_sha256": context["admission_sha256"],
        "shard": context["shard"],
        "selection_sha256": digest(control / SELECTION),
        "phases": [],
        "started_at": utc_now(),
    }
    write_json(output / "result.json", report)
    scratch = Path(tempfile.mkdtemp(prefix="confluence-pilot-"))
    report["private_root"] = str(scratch)
    python = scratch / "venv/bin/python"
    env = clean_environment(scratch, python)
    if "operator_authority" in context["admission"]:
        # Pinned archive uses absolute DT_RUNPATH; every subprocess must use the
        # already verified private library, including venv/cold-start children.
        env["LD_LIBRARY_PATH"] = str(Path(sys.base_prefix) / "lib")
    began = time.monotonic()
    usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)

    def phase(name, argv, cwd, timeout=360):
        row = {
            "name": name,
            "argv": [str(x) for x in argv],
            "started_at": utc_now(),
            "status": "incomplete",
        }
        report["phases"].append(row)
        write_json(output / "result.json", report)
        start = time.monotonic()
        try:
            if name not in ("collection", "pytest"):
                timeout = min(timeout, 360 - (time.monotonic() - began))
                if timeout <= 0:
                    raise ChildFailure(124, "timed-out")
            if "operator_authority" in context["admission"]:
                timeout = min(
                    timeout,
                    parse_time(context["admission"]["operator_authority"]["expires_at"])
                    - time.time(),
                )
                if timeout <= 0:
                    raise ChildFailure(124, "authority-expired")
            runner(row["argv"], cwd, env, timeout, output / (name + ".log"))
            row.update(status="complete", exitstatus=0)
        except ChildFailure as exc:
            row.update(
                status=exc.status,
                exitstatus=exc.code,
                cleanup_uncertainty=getattr(exc, "cleanup_uncertainty", None),
            )
            raise
        finally:
            row.update(seconds=time.monotonic() - start, completed_at=utc_now())
            try:
                write_json(output / "result.json", report)
            except OSError:
                if row.get("exitstatus", 0) == 0:
                    raise
                # The first child failure remains authoritative even if salvage fails.
                print("pilot: partial report write failed", file=sys.stderr)

    try:
        for name in (
            "home",
            "tmp",
            "config",
            "cache",
            "data",
            "wheels",
            "plugin",
            "build",
        ):
            (scratch / name).mkdir()
        for name, original in (("product", product), ("engine", engine)):
            for relative in context["files"][name]:
                target = scratch / name / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(member(original, relative), target)
                require(
                    digest(target) == context["file_hashes"][name][relative],
                    "source changed during copy",
                )
        for dist in context["pins"]["distributions"]:
            shutil.copyfile(
                member(assets, dist["filename"]), scratch / "wheels" / dist["filename"]
            )
            require(
                digest(scratch / "wheels" / dist["filename"]) == dist["sha256"],
                "asset changed during copy",
            )
        shutil.copyfile(control / LOCK, scratch / "lock.txt")
        shutil.copyfile(
            control / "ci/pytest_evidence.py", scratch / "plugin/pytest_evidence.py"
        )
        require(
            digest(scratch / "lock.txt") == context["pins"]["content"][LOCK],
            "lock changed during copy",
        )
        require(
            digest(scratch / "plugin/pytest_evidence.py")
            == context["pins"]["content"]["ci/pytest_evidence.py"],
            "plugin changed during copy",
        )
        phase(
            "venv",
            [sys.executable, "-I", "-m", "venv", "--without-pip", scratch / "venv"],
            scratch,
        )
        pip = next(d for d in context["pins"]["distributions"] if d["name"] == "pip")
        bootstrap = "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); runpy.run_module('pip',run_name='__main__')"
        phase(
            "dependencies",
            [
                sys.executable,
                "-I",
                "-c",
                bootstrap,
                scratch / "wheels" / pip["filename"],
                "--python",
                python,
                "install",
                "--no-index",
                "--no-deps",
                "--only-binary=:all:",
                "--require-hashes",
                "--find-links",
                scratch / "wheels",
                "-r",
                scratch / "lock.txt",
            ],
            scratch,
        )
        phase(
            "engine-wheel",
            [
                python,
                "-I",
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                scratch / "build",
            ],
            scratch / "engine",
        )
        wheels = list((scratch / "build").glob("*.whl"))
        require(len(wheels) == 1, "missing or ambiguous engine wheel")
        report["engine_wheel"] = {
            "filename": wheels[0].name,
            "sha256": digest(wheels[0]),
        }
        phase(
            "engine-install",
            [
                python,
                "-I",
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                wheels[0],
            ],
            scratch,
        )
        phase(
            "product-install",
            [
                python,
                "-I",
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--no-build-isolation",
                "--report",
                output / "product-install.json",
                "-e",
                scratch / "product",
            ],
            scratch,
        )
        phase("dependency-check", [python, "-I", "-m", "pip", "check"], scratch)
        generated = scratch / "product/src/confluence_as/_generated"
        report["generated"] = {p.name: digest(p) for p in generated.glob("*.json")}
        require(
            report["generated"] == context["pins"]["generated_expectations"],
            "pristine generated output differs from frozen observation; review required",
        )
        identity = {
            "admission_sha256": context["admission_sha256"],
            "shard": context["shard"],
            "selection_sha256": report["selection_sha256"],
        }
        expectation = {
            "identity": identity,
            "nodes": context["nodes"],
            "config_path": str(scratch / "product/pyproject.toml"),
            "config_sha256": context["selection"]["config"]["pyproject.toml"],
        }
        write_json(scratch / "expectation.json", expectation)
        modules = [
            m["path"]
            for m in context["selection"]["modules"]
            if context["shard"] == "serial" or m["shard"] == context["shard"]
        ]
        env["PYTHONPATH"] = str(
            scratch / "plugin"
        )  # Only reviewed recorder, no inherited path.
        options = [
            python,
            "-m",
            "pytest",
            *modules,
            "-c",
            "pyproject.toml",
            "-q",
            "-ra",
            "-p",
            "no:cacheprovider",
            "-p",
            "pytest_evidence",
            "--durations=0",
            "--durations-min=0",
            "--ci-expectation",
            scratch / "expectation.json",
        ]
        phase(
            "collection",
            [*options, "--collect-only", "--ci-evidence-dir", output / "collection"],
            scratch / "product",
            120,
        )
        verify_phase(output / "collection", context["nodes"], identity, True)
        phase(
            "pytest",
            [
                *options,
                "--ci-evidence-dir",
                output / "pytest",
                "--junitxml",
                output / "junit.xml",
                "--basetemp",
                scratch / "tmp/pytest",
            ],
            scratch / "product",
            480,
        )
        verify_phase(output / "pytest", context["nodes"], identity, False)
        verify_junit(output / "junit.xml", context["nodes"])
        report.update(
            status="locally-verified", exitstatus=0, locally_verified_at=utc_now()
        )
    except ChildFailure as exc:
        report.update(
            status=exc.status,
            exitstatus=exc.code,
            error=str(exc),
            cleanup_uncertainty=getattr(exc, "cleanup_uncertainty", None),
        )
    except (EvidenceError, OSError, ValueError, KeyError, TypeError) as exc:
        report.update(status="incomplete", exitstatus=4, error=str(exc))
    except KeyboardInterrupt:
        report.update(status="cancelled", exitstatus=130)
    finally:
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        report.update(
            completed_at=utc_now(),
            controller_seconds=time.monotonic() - began,
            resources={
                "child_user_seconds": usage.ru_utime - usage_before.ru_utime,
                "child_system_seconds": usage.ru_stime - usage_before.ru_stime,
                "child_peak_rss_kib": usage.ru_maxrss,
                "input_blocks": usage.ru_inblock - usage_before.ru_inblock,
                "output_blocks": usage.ru_oublock - usage_before.ru_oublock,
            },
            acceptance="pending-independent-attempt-and-artifact-verification",
        )
        # Include real fixture wheel/editable/sdist artifacts and generated payloads, even after failure.
        try:
            artifacts = {}
            for path in scratch.rglob("*"):
                if path.is_file() and (
                    path.suffix == ".whl"
                    or path.name.endswith(".tar.gz")
                    or ("_generated" in path.parts and path.suffix == ".json")
                ):
                    artifacts[str(path.relative_to(scratch))] = digest(path)
            write_json(output / "build-manifest.json", artifacts)
            write_json(output / "result.json", report)
            write_json(
                output / "artifacts.json",
                {
                    p.relative_to(output).as_posix(): digest(p)
                    for p in output.rglob("*")
                    if p.is_file() and p.name != "artifacts.json"
                },
            )
        except OSError as exc:
            print(f"pilot: evidence salvage failed: {exc}", file=sys.stderr)
            if report.get("exitstatus") in (None, 0):
                report.update(status="incomplete", exitstatus=4)
        # Retained private scratch permits inspection; no shared checkout/store was mutated.
    return report["exitstatus"]


# Bootstrap code is reached only through the workflow's byte-verified private copy.
def snapshot_files(root, manifest):
    """Recheck the complete private control snapshot bound by launcher admission."""
    actual = set()
    for folder, directories, files in os.walk(root, followlinks=False):
        require(
            all(not (Path(folder) / d).is_symlink() for d in directories),
            "symlink snapshot directory",
        )
        actual.update((Path(folder) / f).relative_to(root).as_posix() for f in files)
    require(actual == set(manifest), "changed snapshot inventory")
    for relative, record in manifest.items():
        path = member(root, relative)
        require(
            digest(path) == record["sha256"]
            and stat.S_IMODE(path.stat().st_mode) == record["mode"],
            "changed private snapshot",
        )
    return sorted(actual)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def https_bytes(url, maximum, deadline, *, token=None, asset=False, opener=None):
    """Fixed GET transport with cooperative elapsed checks and socket idle timeout.

    The deadline cannot preempt DNS or continuously arriving HTTP headers. Check
    elapsed time when control returns; the socket timeout is not a wall cap.
    No proxies/cookies, bounded redirects, and no credential forwarding.
    """
    opener = opener or urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect()
    )
    original = urllib.parse.urlsplit(url)
    for redirects in range(3):
        parsed = urllib.parse.urlsplit(url)
        require(
            parsed.scheme == "https"
            and not parsed.username
            and not parsed.password
            and parsed.port in (None, 443)
            and not parsed.fragment,
            "unsafe HTTPS URL",
        )
        allowed = (
            {
                "github.com",
                "release-assets.githubusercontent.com",
                "files.pythonhosted.org",
            }
            if asset
            else {"api.github.com"}
        )
        require(parsed.hostname in allowed, "unapproved HTTPS host")
        require(not asset or token is None, "asset credential forbidden")
        headers = {
            "Accept": "application/octet-stream"
            if asset
            else "application/vnd.github+json",
            "User-Agent": "gc286-pinned-bootstrap",
        }
        if token:
            require(not asset and redirects == 0, "credential redirect forbidden")
            headers["Authorization"] = "Bearer " + token
            headers["X-GitHub-Api-Version"] = "2026-03-10"
        remaining = deadline - time.monotonic()
        require(remaining > 0, "HTTPS deadline exceeded")
        try:
            response = opener.open(
                urllib.request.Request(url, headers=headers, method="GET"),
                timeout=min(15, remaining),
            )
        except urllib.error.HTTPError as exc:
            try:
                location = exc.headers.get("Location")
                require(
                    asset
                    and redirects == 0
                    and original.hostname == "github.com"
                    and exc.code in (301, 302, 303, 307, 308)
                    and location,
                    "HTTP refusal",
                )
                target = urllib.parse.urlsplit(urllib.parse.urljoin(url, location))
                require(
                    target.hostname == "release-assets.githubusercontent.com",
                    "unapproved redirect",
                )
                url = target.geturl()
            finally:
                exc.close()
            continue
        with response:
            require(
                response.status == 200 and response.geturl() == url,
                "unexpected response or redirect",
            )
            length = response.headers.get("Content-Length")
            require(
                length is None or (length.isdigit() and int(length) <= maximum),
                "oversized response",
            )
            data = bytearray()
            while True:
                require(time.monotonic() < deadline, "HTTPS deadline exceeded")
                block = response.read1(min(65536, maximum + 1 - len(data)))
                if not block:
                    break
                data.extend(block)
                require(len(data) <= maximum, "oversized response")
            require(time.monotonic() <= deadline, "HTTPS deadline exceeded")
            require(length is None or len(data) == int(length), "partial response")
            return bytes(data)
    raise EvidenceError("redirect limit exceeded")


def fetch_asset(record, destination, deadline, fetch=https_bytes):
    require(
        not destination.exists() and not destination.is_symlink(),
        "asset already exists",
    )
    require(
        destination.name == record["filename"]
        and re.fullmatch(r"[A-Za-z0-9_.+-]+", destination.name),
        "unsafe asset name",
    )
    url = urllib.parse.urlsplit(record["url"])
    if destination.name.endswith(".whl"):
        require(
            url.hostname == "files.pythonhosted.org"
            and url.path.endswith("/" + destination.name)
            and not url.query,
            "wrong wheel URL",
        )
        maximum = 16 * 1024 * 1024
    else:
        require(
            record["filename"] == "python-3.12.12-linux-24.04-x64.tar.gz"
            and record["url"]
            == "https://github.com/actions/python-versions/releases/download/3.12.12-18393146713/"
            + record["filename"],
            "wrong interpreter URL",
        )
        maximum = 150 * 1024 * 1024
    raw = fetch(record["url"], maximum, deadline, asset=True)
    require(
        len(raw) <= maximum
        and hashlib.sha256(raw).hexdigest() == sha(record["sha256"]),
        "changed asset hash/size",
    )
    part = destination.with_name(destination.name + ".part")
    with part.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require(digest(part) == record["sha256"], "mutated asset staging")
    os.rename(part, destination)
    require(digest(destination) == record["sha256"], "mutated asset completion")


def archive_rows(members):
    return [
        {
            "name": m.name,
            "type": m.type.decode("ascii"),
            "size": m.size,
            "mode": oct(m.mode),
            "link": m.linkname,
        }
        for m in members
    ]


def materialize_python(archive, prefix, pin):
    """Reviewed actions/python-versions archive only; never execute setup.sh.

    The official recipe copies the prefix and creates aliases, but then upgrades
    pip without a pin. Here aliases are explicit and pip comes from the hash lock.
    DT_RUNPATH is absolute; the clean child receives only this prefix/lib as
    LD_LIBRARY_PATH. No toolcache fallback, mutation, patchelf or root operation.
    """
    recipe = pin["recipe"]
    require(
        recipe["id"] == "actions-python-3.12.12-ubuntu24-private-v1",
        "unsupported install recipe",
    )
    require(digest(archive) == pin["sha256"], "changed interpreter archive")
    require(not prefix.exists() and not prefix.is_symlink(), "prefix already exists")
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        require(
            len(members) == recipe["member_count"] <= 10000
            and sum(m.size for m in members)
            == recipe["unpacked_bytes"]
            <= 400 * 1024 * 1024,
            "unsupported archive layout",
        )
        rows = json.dumps(
            archive_rows(members), sort_keys=True, separators=(",", ":")
        ).encode()
        require(
            hashlib.sha256(rows).hexdigest() == recipe["inventory_sha256"],
            "changed archive inventory",
        )
        paths, links = {}, {}
        for item in members:
            name = item.name.removeprefix("./")
            if name == ".":
                require(item.isdir(), "invalid archive root")
                continue
            require(
                name
                and not Path(name).is_absolute()
                and all(p not in ("..", ".") for p in name.split("/")),
                "unsafe archive member",
            )
            require(
                name not in paths
                and (item.isfile() or item.isdir() or item.issym())
                and not item.mode & 0o7000,
                "unsafe archive type/mode",
            )
            paths[name] = item
            if item.issym():
                require(
                    "/" not in item.linkname and item.linkname not in ("", ".", ".."),
                    "unsafe archive link",
                )
                links[name] = item.linkname
        require(links == recipe["links"], "unsupported archive links")
        for name in paths:
            require(
                all(p.as_posix() not in links for p in Path(name).parents),
                "member beneath symlink",
            )
        require(
            hashlib.sha256(bundle.extractfile(paths["setup.sh"]).read()).hexdigest()
            == recipe["setup_sha256"],
            "changed official recipe",
        )
        prefix.mkdir(mode=0o700)
        # Regular files first, no extractall, no archive ownership/time application.
        for name, item in paths.items():
            if item.issym() or name == "setup.sh":
                continue
            target = prefix / name
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(item) as source, target.open("xb") as output:
                    remaining = item.size
                    while remaining:
                        block = source.read(min(65536, remaining))
                        require(block, "partial archive member")
                        output.write(block)
                        remaining -= len(block)
                # Official archive contains 0666/0777 members. Normalize only
                # writable bits; keep its executable classification.
                target.chmod(0o755 if item.mode & 0o111 else 0o644)
        for name, target in links.items():
            require(
                (prefix / name).parent.joinpath(target).is_file(), "missing link target"
            )
            (prefix / name).symlink_to(target)
        for name, target in {
            "python": "bin/python3.12",
            "bin/python312": "python3.12",
            "bin/python": "python3.12",
        }.items():
            require(not (prefix / name).exists(), "unexpected Python alias")
            (prefix / name).symlink_to(target)
    require(
        digest(prefix / "bin/python3.12") == recipe["executable_sha256"]
        and digest(prefix / "lib/libpython3.12.so.1.0") == recipe["library_sha256"],
        "changed installed interpreter",
    )
    return prefix / "bin/python3.12"


def github_metadata(authority, env, fetch=https_bytes):
    """Exactly two read-only per-attempt API resources, no list/search/private inputs."""
    # The inline verifier already authenticated this exact protected tag and the
    # actual GITHUB_REF/GITHUB_WORKFLOW_REF. Derive no ref from API metadata.
    ref = authority["ref"]
    require(
        re.fullmatch(r"refs/tags/gc286-reviewed-[A-Za-z0-9._-]+", ref),
        "wrong authorized workflow ref",
    )
    tag = ref.removeprefix("refs/tags/")
    workflow_path = ".github/workflows/confluence-pilot.yml"
    run_id = authority["run_id"]
    base = (
        "https://api.github.com/repos/grandcamel/confluence-as/actions/runs/"
        + run_id
        + "/attempts/1"
    )
    # Shared cooperative elapsed budget, not a DNS/HTTP-header wall cap.
    deadline = time.monotonic() + 30
    token = env.get("GC286_METADATA_TOKEN")
    require(token, "missing read-only Actions credential")
    run = loads_json(fetch(base, 1024 * 1024, deadline, token=token).decode())
    jobs = loads_json(
        fetch(base + "/jobs?per_page=100", 1024 * 1024, deadline, token=token).decode()
    )
    require(
        str(run["id"]) == run_id
        and run["run_attempt"] == 1
        and run["head_sha"] == authority["control"]["commit"]
        and run["event"] == "workflow_dispatch",
        "wrong observed run/attempt",
    )
    require(
        run["repository"]["full_name"] == authority["repository"]
        # GitHub documents build.yml@main and referenced workflow @v2 with
        # refs/tags/v2: https://docs.github.com/en/rest/actions/workflow-runs
        # Admit only the bare path or this exact authorized short-tag suffix.
        and run["path"] in (workflow_path, workflow_path + "@" + tag),
        "wrong observed workflow",
    )
    rows = jobs["jobs"]
    require(
        jobs["total_count"] == len(rows) and 1 <= len(rows) <= 3,
        "unavailable or ambiguous jobs",
    )
    allowed = {"gc286-serial", "gc286-A", "gc286-B"}
    require(
        len({j["id"] for j in rows}) == len(rows)
        and len({j["name"] for j in rows}) == len(rows)
        and all(
            j["name"] in allowed
            and str(j["run_id"]) == run_id
            and j["head_sha"] == authority["control"]["commit"]
            for j in rows
        ),
        "duplicate or unexpected jobs",
    )
    name = "gc286-" + env["SHARD"]
    matched = [j for j in rows if j["name"] == name]
    require(len(matched) == 1, "missing or ambiguous current job")
    job = matched[0]
    require(
        str(job["run_id"]) == run_id
        and job["head_sha"] == authority["control"]["commit"]
        and job["status"] == "in_progress"
        and job["runner_name"] == env["RUNNER_NAME"]
        and type(job["runner_id"]) is int
        and job["runner_id"] > 0,
        "wrong allocated job",
    )
    require(
        "ubuntu-24.04" in job["labels"] and "self-hosted" not in job["labels"],
        "wrong allocated platform",
    )
    requested = run["created_at"]
    # Serial release is request time, explicitly request-to-start (includes approval).
    # A/B share the completed serial dependency timestamp, not bootstrap wall time.
    released = requested
    basis = "request-to-start-including-protection-and-scheduling"
    if env["SHARD"] != "serial":
        serial = [j for j in rows if j["name"] == "gc286-serial"]
        require(
            len(serial) == 1
            and serial[0]["conclusion"] == "success"
            and serial[0]["status"] == "completed",
            "serial dependency unavailable",
        )
        released = serial[0]["completed_at"]
        basis = "dependency-release-to-start-including-protection-and-scheduling"
    require(
        parse_time(authority["not_before"])
        <= parse_time(requested)
        <= parse_time(released)
        <= parse_time(job["started_at"])
        <= time.time()
        < parse_time(authority["expires_at"]),
        "missing or invalid observed timestamps",
    )
    return {
        "job": job,
        "run": run,
        "timing": {
            "request_at": requested,
            "arm_released_at": released,
            "job_started_at": job["started_at"],
            "delay_basis": basis,
        },
    }


def bootstrap_verified(
    control,
    work,
    authority,
    manifest,
    env,
    *,
    metadata_reader=github_metadata,
    fetcher=fetch_asset,
    installer=materialize_python,
    launch=os.execve,
):
    """Trusted bootstrap only; fixtures intercept every effect. Not a CLI entry."""
    snapshot_files(control, manifest)
    pins = read_json(control / "ci/pins.json")
    require(
        digest(control / "ci/pins.json") == authority["control"]["pins_sha256"],
        "changed verified pins",
    )
    product = Path(env["GITHUB_WORKSPACE"]) / "product"
    engine = Path(env["GITHUB_WORKSPACE"]) / "engine"
    source_files(product, pins["sources"]["product"])
    source_files(engine, pins["sources"]["engine"])
    observed = metadata_reader(authority, env)
    assets = work / "assets"
    assets.mkdir(mode=0o700)
    # Shared cooperative asset budget, additionally limited by authority expiry.
    # Socket idle timeouts cannot preempt DNS or continuously arriving headers.
    deadline = time.monotonic() + min(
        300, parse_time(authority["expires_at"]) - time.time()
    )
    for record in [pins["python"], *pins["distributions"]]:
        fetcher(record, assets / record["filename"], deadline)
    prefix = work / "python"
    python = installer(assets / pins["python"]["filename"], prefix, pins["python"])
    snapshot_files(control, manifest)
    payload = {
        "authority": authority,
        "control_inventory": manifest,
        "observed": observed,
        "product": str(product),
        "engine": str(engine),
        "shard": env["SHARD"],
        "prefix_sha256": tree_digest(prefix),
        "bootstrap_observation": {
            "python": platform.python_version(),
            "executable_sha256": digest(sys.executable),
            "image_os": env["ImageOS"],
            "image_version": env["ImageVersion"],
        },
    }
    payload_path = work / "bootstrap.json"
    write_json(payload_path, payload)
    # Retain only GitHub identity/image observations, never bearer/envelope/credential
    # discovery, inherited PATH, Python settings, proxies, LD_PRELOAD or user homes.
    child_env = {
        key: env[key]
        for key in (
            "GITHUB_EVENT_NAME",
            "GITHUB_SHA",
            "GITHUB_REPOSITORY",
            "GITHUB_RUN_ID",
            "GITHUB_RUN_ATTEMPT",
            "ImageOS",
            "ImageVersion",
        )
    }
    child_env.update(
        {
            "PATH": str(prefix / "bin") + ":/usr/bin:/bin",
            "LC_ALL": "C.UTF-8",
            "LD_LIBRARY_PATH": str(prefix / "lib"),
        }
    )
    require(
        time.time() < parse_time(authority["expires_at"]),
        "authority expired during preparation",
    )
    code = "import sys; sys.path.insert(0,sys.argv[1]); import pilot; raise SystemExit(pilot.bootstrap_child(*sys.argv[2:]))"
    return launch(
        str(python),
        [
            str(python),
            "-I",
            "-B",
            "-c",
            code,
            str(control / "ci"),
            str(control),
            str(work),
            digest(payload_path),
        ],
        child_env,
    )


def bootstrap_child(control_name, work_name, payload_sha):
    control, work = Path(control_name), Path(work_name)
    require(digest(work / "bootstrap.json") == payload_sha, "changed bootstrap handoff")
    payload = read_json(work / "bootstrap.json")
    authority = payload["authority"]
    require(
        time.time() < parse_time(authority["expires_at"]), "expired child authority"
    )
    (work / "child-started").mkdir(mode=0o700)
    require(
        Path(sys.executable) == work / "python/bin/python3.12"
        and Path(sys.base_prefix) == work / "python",
        "ambient interpreter substitution",
    )
    require(
        tree_digest(work / "python") == payload["prefix_sha256"],
        "changed materialized prefix",
    )
    snapshot_files(control, payload["control_inventory"])
    runtime = observe_runtime()
    require(
        runtime["platform"]["system"] == "Linux"
        and runtime["platform"]["machine"] == "x86_64"
        and runtime["platform"]["python"] == "3.12.12"
        and runtime["platform"]["image_os"] == "ubuntu24"
        and runtime["platform"]["image_version"]
        and runtime["platform"]["cpu_count"] > 0
        and runtime["platform"]["ram_bytes"] > 0
        and runtime["platform"]["cpu_model"],
        "unavailable runtime identity",
    )
    admission = {
        "schema": "confluence-pilot-admission/v1",
        "mode": "fixed-benchmark",
        "allow_execute": True,
        "control": authority["control"],
        "sources": authority["sources"],
        "event": {
            "name": "workflow_dispatch",
            "sha": authority["control"]["commit"],
            "repository": authority["repository"],
            "run_id": authority["run_id"],
            "attempt": "1",
        },
        "runtime": runtime,
        "timing": payload["observed"]["timing"],
        "operator_authority": authority,
        "observed_job": payload["observed"]["job"],
        "observed_run": payload["observed"]["run"],
        "observed_bootstrap": payload["bootstrap_observation"],
        "control_inventory": payload["control_inventory"],
    }
    admission_path = work / "admission.json"
    write_json(admission_path, admission)
    context = validate_inputs(
        control,
        Path(payload["product"]),
        Path(payload["engine"]),
        work / "assets",
        admission_path,
        digest(admission_path),
        payload["shard"],
    )
    return run_admitted(
        context,
        control,
        Path(payload["product"]),
        Path(payload["engine"]),
        work / "assets",
        work / ("evidence-" + payload["shard"]),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run"])
    for name in ("control", "product", "engine", "assets", "admission", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--admission-sha256", required=True)
    parser.add_argument("--shard", choices=["serial", "A", "B"], required=True)
    args = parser.parse_args()
    try:
        context = validate_inputs(
            args.control.resolve(),
            args.product.resolve(),
            args.engine.resolve(),
            args.assets.resolve(),
            args.admission.resolve(),
            args.admission_sha256,
            args.shard,
        )
        return run_admitted(
            context,
            args.control.resolve(),
            args.product.resolve(),
            args.engine.resolve(),
            args.assets.resolve(),
            args.output.resolve(),
        )
    except (
        EvidenceError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as exc:
        # Admission failure occurs before output/workspace/install/build/test effects.
        print(f"pilot refused before execution: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
