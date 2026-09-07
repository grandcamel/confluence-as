"""Attachment download uses only Surface metadata and binary operations."""

from __future__ import annotations

import base64

import pytest
import requests
from as_engine.simulation import SimulationStore
from click.testing import CliRunner

from confluence_as import engine
from confluence_as.cli import cli_utils
from confluence_as.cli.main import cli


def _surface(store: SimulationStore):
    return engine.create_surface(transport="simulation", store=store)


@pytest.fixture
def attachments(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_ALLOWED_SPACES", "DOCS")
    monkeypatch.setenv("CONFLUENCE_ALLOW_SITE_OPERATIONS", "true")
    store = SimulationStore(
        {
            "attachments": [
                {
                    "id": "att1",
                    "pageId": "1",
                    "title": "first.bin",
                    "mediaType": "application/octet-stream",
                    "data_base64": base64.b64encode(b"first bytes").decode(),
                },
                {
                    "id": "att2",
                    "pageId": "1",
                    "title": "../../escape.bin",
                    "mediaType": "application/octet-stream",
                    "data_base64": base64.b64encode(b"second bytes").decode(),
                },
            ]
        }
    )
    surface = _surface(store)
    monkeypatch.setattr(engine, "create_surface", lambda **_: surface)

    def forbidden(*_args, **_kwargs):
        pytest.fail("attachment survivor bypassed Surface or acquired legacy client")

    monkeypatch.setattr(requests.Session, "send", forbidden)
    monkeypatch.setattr(cli_utils, "get_confluence_client", forbidden)
    import confluence_as

    monkeypatch.setattr(confluence_as, "get_confluence_client", forbidden)
    return store


def test_attachment_download_uses_metadata_then_binary_surface_call(attachments, tmp_path):
    target = tmp_path / "named.bin"
    result = CliRunner().invoke(cli, ["attachment", "download", "att1", "-o", str(target)])
    assert result.exit_code == 0, result.output
    assert target.read_bytes() == b"first bytes"
    assert [name for name, _, _ in attachments.calls] == [
        "getAttachmentById",
        "downloadAttatchment",
    ]


def test_attachment_download_all_uses_paged_metadata_and_sanitizes_names(attachments, tmp_path):
    target = tmp_path / "downloads"
    result = CliRunner().invoke(
        cli,
        ["attachment", "download", "1", "--all", "--output-dir", str(target)],
    )
    assert result.exit_code == 0, result.output
    assert (target / "first.bin").read_bytes() == b"first bytes"
    assert (target / "escape.bin").read_bytes() == b"second bytes"
    assert not (tmp_path / "escape.bin").exists()
    assert [name for name, _, _ in attachments.calls] == [
        "getPageById",
        "getSpaces",
        "getPageAttachments",
        "downloadAttatchment",
        "downloadAttatchment",
    ]


@pytest.mark.parametrize("title", ["", ".", "..", "\x00..", "\x7f."])
def test_attachment_download_sanitizes_empty_dot_and_control_names(attachments, tmp_path, title):
    attachments.attachments[0]["title"] = title
    result = CliRunner().invoke(cli, ["attachment", "download", "att1", "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "attachment").read_bytes() == b"first bytes"


def test_attachment_download_all_reports_empty_collection(attachments, tmp_path):
    attachments.attachments.clear()
    result = CliRunner().invoke(
        cli,
        ["attachment", "download", "1", "--all", "--output-dir", str(tmp_path / "downloads")],
    )
    assert result.exit_code == 0, result.output
    assert "No attachments found on page." in result.output
    assert "Downloaded" not in result.output


def test_attachment_download_all_refuses_metadata_without_an_id(attachments, tmp_path):
    attachments.attachments.append(
        {"pageId": "1", "title": "missing-id.bin", "data_base64": ""}
    )
    result = CliRunner().invoke(
        cli,
        ["attachment", "download", "1", "--all", "--output-dir", str(tmp_path / "downloads")],
    )
    assert result.exit_code != 0
    assert "Attachment metadata is missing an ID" in result.output


def test_attachment_download_accepts_blog_post_container_metadata(attachments, tmp_path):
    metadata = attachments.attachments[0]
    del metadata["pageId"]
    metadata["blogPostId"] = "10"
    target = tmp_path / "blog.bin"
    result = CliRunner().invoke(cli, ["attachment", "download", "att1", "-o", str(target)])
    assert result.exit_code == 0, result.output
    assert target.read_bytes() == b"first bytes"
    assert attachments.calls[-1][1] == {"id": "10", "attachmentId": "att1"}
