"""Explicit, stdlib-only pytest recorder; evidence is data, never an authority.

Enable with -p pytest_evidence and PYTEST_DISABLE_PLUGIN_AUTOLOAD=1. The trusted
runner supplies an expectation file; every incomplete session remains nonaccepting.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path


class EvidenceError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def loads_json(value):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(value, object_pairs_hook=unique)


def read_json(path):
    return loads_json(Path(path).read_text())


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    temporary.replace(path)


def exact_nodes(actual, expected):
    require(
        isinstance(actual, list) and all(isinstance(n, str) for n in actual),
        "invalid node list",
    )
    require(len(expected) == len(set(expected)), "duplicate expected node")
    require(len(actual) == len(set(actual)), "duplicate collected node")
    require(actual == expected, "missing, unexpected or reordered node")


def verify_events(events, expected, identity, collect_only=False):
    """Accept only a complete ordered protocol and three passing phases per node."""
    require(bool(events) and events[0].get("event") == "start", "missing start")
    require(events[-1].get("event") == "finish", "missing terminal artifact")
    require(
        [e.get("seq") for e in events] == list(range(len(events))), "event sequence gap"
    )
    require(
        all(e.get("identity") == identity for e in events), "wrong evidence identity"
    )
    kinds = [e.get("event") for e in events]
    require(
        kinds.count("start") == kinds.count("collection") == kinds.count("finish") == 1,
        "duplicate or missing protocol event",
    )
    require(
        set(kinds) <= {"start", "collection", "phase", "finish"},
        "error or unknown event",
    )
    collection = next(e for e in events if e["event"] == "collection")
    exact_nodes(collection["nodes"], expected)
    require(events[-1].get("exitstatus") == 0, "pytest nonzero")
    phases = [e for e in events if e["event"] == "phase"]
    if collect_only:
        require(not phases, "test ran during collection")
        return
    require(kinds[1] == "collection", "phase before collection")
    require(
        [(e.get("nodeid"), e.get("when")) for e in phases]
        == [
            (node, phase)
            for node in expected
            for phase in ("setup", "call", "teardown")
        ],
        "missing, duplicate or reordered phase",
    )
    for event in phases:
        require(
            event.get("outcome") == "passed" and not event.get("wasxfail"),
            "failed, skipped or xfail outcome",
        )
        duration = event.get("duration")
        require(
            type(duration) in (int, float)
            and math.isfinite(duration)
            and duration >= 0,
            "invalid phase duration",
        )


class Recorder:
    def __init__(self, config):
        self.config = config
        self.target = Path(config.getoption("--ci-evidence-dir"))
        self.expectation = read_json(config.getoption("--ci-expectation"))
        self.identity = self.expectation["identity"]
        self.events = []
        self.target.mkdir(parents=True, exist_ok=False)
        self.emit(
            "start",
            collect_only=config.option.collectonly,
            argv=list(config.invocation_params.args),
            plugins=sorted(
                name
                for name, plugin in config.pluginmanager.list_name_plugin()
                if plugin is not None
            ),
        )

    def emit(self, event, **fields):
        row = dict(seq=len(self.events), event=event, identity=self.identity, **fields)
        self.events.append(row)
        with (self.target / "events.jsonl").open("a") as stream:
            stream.write(json.dumps(row, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def pytest_collectreport(self, report):
        if report.failed or report.skipped:
            self.emit(
                "collection_error",
                nodeid=report.nodeid,
                outcome=report.outcome,
                error=str(report.longrepr),
            )

    def pytest_deselected(self, items):
        self.emit("deselected", nodes=[item.nodeid for item in items])

    def pytest_collection_finish(self, session):
        import pytest

        nodes = [item.nodeid for item in session.items]
        self.emit("collection", nodes=nodes)
        write_json(
            self.target / "collection.json", {"identity": self.identity, "nodes": nodes}
        )
        try:
            exact_nodes(nodes, self.expectation["nodes"])
            require(
                not any(
                    e["event"] in ("collection_error", "deselected")
                    for e in self.events
                ),
                "collection error or deselection",
            )
            config = session.config
            require(
                str(config.inipath.resolve()) == self.expectation["config_path"],
                "wrong pytest config",
            )
            require(
                hashlib.sha256(config.inipath.read_bytes()).hexdigest()
                == self.expectation["config_sha256"],
                "changed pytest config",
            )
        except EvidenceError as exc:
            self.emit("admission_error", error=str(exc))
            pytest.exit(str(exc), returncode=2 if session.testsfailed else 4)

    def pytest_runtest_logreport(self, report):
        self.emit(
            "phase",
            nodeid=report.nodeid,
            when=report.when,
            outcome=report.outcome,
            duration=report.duration,
            wasxfail=getattr(report, "wasxfail", None),
            error=str(report.longrepr) if report.longrepr else None,
            sections=list(report.sections),
        )

    def pytest_internalerror(self, excrepr, excinfo):
        self.emit("internal_error", error=str(excrepr))

    def pytest_keyboard_interrupt(self, excinfo):
        self.emit("cancelled", error=str(excinfo))

    def pytest_sessionfinish(self, session, exitstatus):
        self.emit("finish", exitstatus=int(exitstatus))
        status = "complete"
        try:
            verify_events(
                self.events,
                self.expectation["nodes"],
                self.identity,
                collect_only=session.config.option.collectonly,
            )
        except EvidenceError as exc:
            status = "nonaccepting"
            # Never replace a real pytest failure with a green/reclassified exit.
            if int(session.exitstatus) == 0:
                session.exitstatus = 4
            error = str(exc)
        else:
            error = None
        write_json(
            self.target / "terminal.json",
            {
                "status": status,
                "error": error,
                "identity": self.identity,
                "exitstatus": int(session.exitstatus),
            },
        )


def pytest_addoption(parser):
    parser.addoption("--ci-evidence-dir", required=True)
    parser.addoption("--ci-expectation", required=True)


def pytest_configure(config):
    require(
        os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") == "1",
        "ambient plugin autoload",
    )
    require(
        not os.environ.get("PYTEST_ADDOPTS") and not os.environ.get("PYTEST_PLUGINS"),
        "ambient pytest options/plugins",
    )
    config.pluginmanager.register(Recorder(config), "ci-evidence-recorder")
