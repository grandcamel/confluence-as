#!/usr/bin/env python3
"""Report Base Document drift without changing the pinned sources.

``--from-file`` is deliberately the offline seam: when present no URL is
opened.  A non-breaking change is reported only when it can affect an
operation carrying an enrichment entry.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from as_engine.overlay import _target_steps
from refresh_base_documents import contained, document_version

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "src/confluence_as/specs/manifest.json"


def _json_pointer(steps: list[tuple[str, str | int]]) -> str:
    return "/" + "/".join(
        str(value).replace("~", "~0").replace("/", "~1") for _, value in steps
    )


def _changed_paths(old: Any, new: Any, pointer: str = "") -> set[str]:
    if type(old) is not type(new):
        return {pointer or "/"}
    if isinstance(old, dict):
        changed: set[str] = set()
        for key in old.keys() | new.keys():
            child = f"{pointer}/{key.replace('~', '~0').replace('/', '~1')}"
            if key not in old or key not in new:
                changed.add(child)
            else:
                changed |= _changed_paths(old[key], new[key], child)
        return changed
    if isinstance(old, list):
        if len(old) != len(new):
            return {pointer or "/"}
        return (
            set().union(
                *(
                    _changed_paths(a, b, f"{pointer}/{index}")
                    for index, (a, b) in enumerate(zip(old, new))
                )
            )
            if old
            else set()
        )
    return {pointer or "/"} if old != new else set()


def enriched_operation_pointers(spec_dir: Path, record: dict[str, Any]) -> set[str]:
    pointers: set[str] = set()
    for name in record.get("overlays", []):
        overlay = json.loads(contained(spec_dir, name).read_text(encoding="utf-8"))
        for action in overlay.get("actions", []):
            if not isinstance(action, dict):
                raise ValueError(f"{name}: overlay action must be an object")
            target = action.get("target")
            steps = _target_steps(target)
            if len(steps) < 3 or steps[0] != ("key", "paths"):
                raise ValueError(f"unsupported enrichment target: {target!r}")
            if "x-as-test" in action:
                pointers.add(_json_pointer(steps[:3]))
    return pointers


def changed_enriched_operations(
    old: dict[str, Any], new: dict[str, Any], spec_dir: Path, record: dict[str, Any]
) -> list[str]:
    changed = _changed_paths(old, new)
    if not changed:
        return []
    targets = enriched_operation_pointers(spec_dir, record)
    global_dependency = any(_is_global_dependency(path) for path in changed)
    affected = [
        target
        for target in sorted(targets)
        if global_dependency
        or any(
            path == target
            or path.startswith(target + "/")
            or target.startswith(path + "/")
            for path in changed
        )
    ]
    return [_operation_label(old, pointer) for pointer in affected]


def _is_global_dependency(pointer: str) -> bool:
    parts = pointer.split("/")
    return (
        pointer == "/security"
        or pointer.startswith("/security/")
        or pointer == "/components"
        or pointer.startswith("/components/")
        or pointer == "/servers"
        or pointer.startswith("/servers/")
        or pointer == "/parameters"
        or pointer.startswith("/parameters/")
        or (
            len(parts) >= 4
            and parts[1] == "paths"
            and parts[3] in ("parameters", "servers", "$ref")
        )
    )


def _operation_label(document: dict[str, Any], pointer: str) -> str:
    _root, _paths, encoded_path, method = pointer.split("/")
    path = encoded_path.replace("~1", "/").replace("~0", "~")
    operation = document["paths"][path][method]
    if not isinstance(operation, dict) or not isinstance(
        operation.get("operationId"), str
    ):
        raise ValueError(
            f"enriched operation has no operationId: {method.upper()} {path}"
        )
    return f"{operation['operationId']} ({method.upper()} {path})"


def _run_oasdiff(binary: str, command: str, old: Path, new: Path, fmt: str) -> str:
    executable = shutil.which(binary)
    if not executable:
        raise ValueError(f"oasdiff executable not found: {binary}")
    result = subprocess.run(
        [
            executable,
            command,
            str(old),
            str(new),
            "--format",
            fmt,
            "--allow-external-refs=false",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            f"oasdiff {command} exited {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _is_breaking(report: str) -> bool:
    if not report or report in ("{}", "[]", "null"):
        return False
    try:
        value = json.loads(report)
    except json.JSONDecodeError as error:
        raise ValueError("oasdiff breaking returned invalid JSON") from error
    return _has_data(value)


def _has_data(value: Any) -> bool:
    """Treat an empty structured oasdiff report as no breaking change."""
    if isinstance(value, dict):
        return any(_has_data(child) for child in value.values())
    if isinstance(value, list):
        return any(_has_data(child) for child in value)
    return bool(value)


def _ticket(records: list[dict[str, Any]]) -> dict[str, Any]:
    ids = ", ".join(item["id"] for item in records)
    summary = f"Confluence Base Document drift: {ids}"
    sections = [f"# {summary}", ""]
    for item in records:
        sections += [f"## {item['id']}", f"Breaking changes: {item['breaking']}"]
        if item["enriched"]:
            sections += ["", "Enriched operations: " + ", ".join(item["enriched"])]
        sections += ["", item["changelog"] or "No changelog text."]
        if item["breaking_report"]:
            sections += [
                "",
                "Breaking report:",
                "```json",
                item["breaking_report"],
                "```",
            ]
        if item["changed"]:
            sections += ["", "Changed JSON pointers: " + ", ".join(item["changed"])]
        sections.append("")
    return {
        "project": {"key": "JAS"},
        "issuetype": {"name": "Task"},
        "summary": summary,
        "description": _bounded_description("\n".join(sections)),
        "components": [{"name": "confluence-as"}],
        "labels": ["base-document-drift"],
    }


def _bounded_description(text: str) -> str:
    """Keep large upstream diffs within Jira description limits."""
    if len(text) <= 28000:
        return text
    return (
        text[:28000]
        + "\n\n[Diff summary truncated; rerun oasdiff for the complete report.]"
    )


def _adf(text: str) -> dict[str, Any]:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": line or " "}]}
            for line in text.splitlines() or [""]
        ],
    }


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def _jira_credentials() -> tuple[str, str, str]:
    site, email, token = (
        os.environ.get(key) for key in ("JIRA_SITE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")
    )
    if not all((site, email, token)):
        raise ValueError(
            "--file-ticket requires JIRA_SITE_URL, JIRA_EMAIL and JIRA_API_TOKEN"
        )
    parsed = urlparse(site)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("JIRA_SITE_URL must be an HTTPS URL")
    return site, email, token


def file_ticket(payload: dict[str, Any]) -> None:
    site, email, token = _jira_credentials()
    parsed = urlparse(site)
    issue = {**payload, "description": _adf(payload["description"])}
    request = Request(
        parsed.geturl().rstrip("/") + "/rest/api/3/issue",
        data=json.dumps({"fields": issue}).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Basic "
            + base64.b64encode(f"{email}:{token}".encode()).decode(),
        },
    )
    try:
        with build_opener(_NoRedirect).open(request, timeout=30) as response:
            if response.status not in (200, 201):
                raise ValueError(
                    f"Jira ticket request failed with HTTP {response.status}"
                )
    except (HTTPError, URLError, ValueError) as error:
        status = getattr(error, "code", None)
        detail = f"HTTP {status}" if status else "connection error"
        raise ValueError(f"Jira ticket request failed: {detail}") from error


def check(
    manifest_path: Path, replacements: dict[str, Path], oasdiff: str
) -> list[dict[str, Any]]:
    manifest_path = manifest_path.resolve()
    spec_dir = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != 1 or not isinstance(
        manifest.get("documents"), list
    ):
        raise ValueError("unsupported manifest format_version")
    ids = [item.get("id") for item in manifest["documents"]]
    if len(ids) != len(set(ids)) or replacements.keys() - set(ids):
        raise ValueError("unknown or duplicate document ids")
    findings: list[dict[str, Any]] = []
    for record in manifest["documents"]:
        doc_id = record["id"]
        if replacements and doc_id not in replacements:
            continue
        old_path = contained(spec_dir, record["file"])
        old_bytes = old_path.read_bytes()
        if (
            hashlib.sha256(old_bytes).hexdigest() != record["sha256"]
            or document_version(old_bytes) != record["declared_version"]
        ):
            raise ValueError(f"{doc_id}: existing document does not match manifest pin")
        if replacements:
            new_bytes = replacements[doc_id].read_bytes()
        else:
            if not record["url"].startswith("https://"):
                raise ValueError(f"{doc_id}: source URL must use HTTPS")
            with urlopen(record["url"], timeout=60) as response:
                new_bytes = response.read()
        document_version(new_bytes)
        if old_bytes == new_bytes:
            continue
        with tempfile.NamedTemporaryFile(suffix=".json") as stream:
            stream.write(new_bytes)
            stream.flush()
            revision = Path(stream.name)
            breaking_report = _run_oasdiff(
                oasdiff, "breaking", old_path, revision, "json"
            )
            breaking = _is_breaking(breaking_report)
            changelog = _run_oasdiff(
                oasdiff, "changelog", old_path, revision, "markdown"
            )
        enriched = changed_enriched_operations(
            json.loads(old_bytes), json.loads(new_bytes), spec_dir, record
        )
        if breaking or enriched:
            findings.append(
                {
                    "id": doc_id,
                    "breaking": breaking,
                    "breaking_report": breaking_report,
                    "enriched": enriched,
                    "changelog": changelog,
                    "changed": sorted(
                        _changed_paths(json.loads(old_bytes), json.loads(new_bytes))
                    ),
                }
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--from-file", action="append", default=[], metavar="ID=PATH")
    parser.add_argument("--oasdiff", default=os.environ.get("OASDIFF", "oasdiff"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--file-ticket", action="store_true")
    args = parser.parse_args()
    replacements: dict[str, Path] = {}
    for value in args.from_file:
        doc_id, sep, filename = value.partition("=")
        if not sep or not doc_id or not filename or doc_id in replacements:
            parser.error("--from-file requires a unique ID=PATH")
        replacements[doc_id] = Path(filename)
    try:
        if args.file_ticket:
            # Validate this CI-required authority before a matching document can
            # hide a broken secrets configuration.
            _jira_credentials()
        findings = check(args.manifest, replacements, args.oasdiff)
        if not findings:
            return 0
        payload = _ticket(findings)
        if args.file_ticket:
            file_ticket(payload)
        elif args.dry_run:
            print(json.dumps(payload, indent=2))
        else:
            print(payload["description"] + "\n" + json.dumps(payload, indent=2))
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        print(f"drift check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
