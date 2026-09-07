#!/usr/bin/env python3
"""Refresh pinned OpenAPI sources and append oasdiff Markdown review records.

No downloads occur when --from-file is supplied: only the named documents
are refreshed. A failed validation or diff leaves all sources unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen


def contained(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError(f"manifest path escapes spec directory: {name!r}")
    return path


def document_version(data: bytes) -> str:
    document = json.loads(data)
    if (
        not isinstance(document, dict)
        or not str(document.get("openapi", "")).startswith("3.")
        or not isinstance(document.get("paths"), dict)
        or not isinstance(document.get("info"), dict)
        or not isinstance(document["info"].get("version"), str)
        or not document["info"]["version"]
    ):
        raise ValueError("expected an OpenAPI 3 document with paths and info.version")
    return document["info"]["version"]


def atomic_write(path: Path, data: bytes) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def refresh(manifest_path: Path, replacements: dict[str, Path], oasdiff: str) -> None:
    manifest_path = manifest_path.resolve()
    spec_dir = manifest_path.parent
    manifest = json.loads(manifest_path.read_bytes())
    if manifest.get("format_version") != 1:
        raise ValueError("unsupported manifest format_version")
    documents = manifest["documents"]
    ids = [item["id"] for item in documents]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate document id in manifest")
    if replacements.keys() - set(ids):
        raise ValueError(
            f"unknown document ids: {sorted(replacements.keys() - set(ids))}"
        )
    binary = shutil.which(oasdiff)
    stamp = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    pending: list[tuple[Path, bytes, Path, bytes]] = []
    with tempfile.TemporaryDirectory(prefix="confluence-spec-refresh-") as scratch:
        for item in documents:
            doc_id = item["id"]
            if replacements and doc_id not in replacements:
                continue
            path = contained(spec_dir, item["file"])
            old = path.read_bytes()
            if hashlib.sha256(old).hexdigest() != item["sha256"]:
                raise ValueError(
                    f"{doc_id}: existing document sha256 does not match manifest"
                )
            if document_version(old) != item["declared_version"]:
                raise ValueError(
                    f"{doc_id}: existing declared_version does not match manifest"
                )
            if replacements:
                new = replacements[doc_id].read_bytes()
            else:
                if not item["url"].startswith("https://"):
                    raise ValueError(f"{doc_id}: source URL must use HTTPS")
                with urlopen(item["url"], timeout=60) as response:
                    new = response.read()
            version = document_version(new)
            revision = Path(scratch) / f"{len(pending)}.json"
            revision.write_bytes(new)
            if binary:
                result = subprocess.run(
                    [
                        binary,
                        "changelog",
                        str(path),
                        str(revision),
                        "--format",
                        "markdown",
                        "--allow-external-refs=false",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
                if result.returncode:
                    raise ValueError(
                        f"{doc_id}: oasdiff exited {result.returncode}: {result.stderr.strip()}"
                    )
                diff = (
                    result.stdout.strip()
                    or "No consumer-affecting changes reported by oasdiff."
                )
            else:
                diff = f"SKIPPED: oasdiff executable not found: {oasdiff}. Review the source diff manually."
                print(f"{doc_id}: {diff}", file=sys.stderr)
            digest = hashlib.sha256(new).hexdigest()
            changelog = path.with_suffix(".changelog.md")
            entry = (
                f"\n## {stamp}\n\n"
                f"Declared version: {item['declared_version']} → {version}\n\n"
                f"SHA256: `{item['sha256']}` → `{digest}`\n\n{diff}\n"
            ).encode()
            previous = (
                changelog.read_bytes()
                if changelog.exists()
                else b"# Base Document refresh history\n"
            )
            pending.append((path, new, changelog, previous + entry))
            item.update(sha256=digest, declared_version=version, fetched_at=stamp)
        # Prepare every document/diff before publishing any refresh. Each file
        # replacement is atomic; the manifest is written last as the pin record.
        for path, new, changelog, history in pending:
            atomic_write(changelog, history)
            atomic_write(path, new)
            print(f"refreshed {path.name}; changelog: {changelog.name}")
        atomic_write(manifest_path, (json.dumps(manifest, indent=2) + "\n").encode())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "src/confluence_as/specs/manifest.json",
    )
    parser.add_argument("--from-file", action="append", default=[], metavar="ID=PATH")
    parser.add_argument("--oasdiff", default=os.environ.get("OASDIFF", "oasdiff"))
    args = parser.parse_args()
    replacements = {}
    for value in args.from_file:
        doc_id, separator, path = value.partition("=")
        if not separator or not doc_id or not path or doc_id in replacements:
            parser.error("--from-file requires a unique ID=PATH")
        replacements[doc_id] = Path(path)
    try:
        refresh(args.manifest, replacements, args.oasdiff)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        print(f"refresh failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
