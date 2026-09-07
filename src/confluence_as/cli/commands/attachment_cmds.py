"""Attachment management commands - CLI-only implementation."""

from __future__ import annotations

from typing import Any

import click
from assistant_skills_lib import validate_file_path_secure

from confluence_as import (
    ValidationError,
    engine,
    handle_errors,
    print_info,
    print_success,
    validate_attachment_id,
)


def _format_attachment(attachment: dict[str, Any]) -> dict[str, Any]:
    """Format an attachment for display."""
    return {
        "id": attachment.get("id", ""),
        "title": attachment.get("title", "Untitled"),
        "mediaType": attachment.get("mediaType", "unknown"),
        "fileSize": _format_file_size(attachment.get("fileSize", 0)),
        "version": attachment.get("version", {}).get("number", 1),
    }


def _format_file_size(size_bytes: int) -> str:
    """Format file size for human readability."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


@click.group()
def attachment() -> None:
    """Manage file attachments."""
    pass






@attachment.command(name="download")
@click.argument("attachment_id")
@click.option(
    "--output",
    "--output-dir",
    "-o",
    "output_path",
    default=".",
    help="Output file or directory",
)
@click.option(
    "--all",
    "-a",
    "download_all",
    is_flag=True,
    help="Download all attachments from page (attachment_id is page_id)",
)
@click.pass_context
@handle_errors
def download_attachment(
    ctx: click.Context,
    attachment_id: str,
    output_path: str,
    download_all: bool,
) -> None:
    """Download an attachment."""
    attachment_id = validate_attachment_id(attachment_id)
    output_dir = validate_file_path_secure(output_path, "output", allow_absolute=True)

    surface = engine.create_surface()

    if download_all:
        # attachment_id is actually page_id
        page_id = attachment_id

        if output_dir.exists() and not output_dir.is_dir():
            raise ValidationError("Output must be a directory when downloading all")

        output_dir.mkdir(parents=True, exist_ok=True)

        attachments = surface.call(
            "getPageAttachments", {"id": page_id}, all_pages=True
        ).body

        if not attachments:
            click.echo("No attachments found on page.")
            return

        print_info(f"Downloading {len(attachments)} attachment(s)...")

        for att in attachments:
            att_id = att.get("id")
            if not att_id:
                raise ValidationError("Attachment metadata is missing an ID")
            title = _attachment_filename(att.get("title"))
            file_path = output_dir / title
            surface.call(
                "downloadAttatchment",
                {"id": page_id, "attachmentId": att_id},
                output=file_path,
            )
            print_info(f"  Downloaded: {title}")

        print_success(f"Downloaded {len(attachments)} attachment(s) to {output_dir}")

    else:
        # Download single attachment
        att_info = surface.call("getAttachmentById", {"id": attachment_id}).body
        title = _attachment_filename(att_info.get("title"))
        page_id = att_info.get("pageId") or att_info.get("blogPostId")
        if not page_id:
            raise ValidationError("Attachment metadata does not include a containing content ID")

        if output_dir.is_dir():
            file_path = output_dir / title
        else:
            file_path = output_dir

        file_path.parent.mkdir(parents=True, exist_ok=True)

        surface.call(
            "downloadAttatchment",
            {"id": page_id, "attachmentId": attachment_id},
            output=file_path,
        )

        print_success(f"Downloaded {title} to {file_path}")


def _attachment_filename(title: Any) -> str:
    """Use the server filename only as a basename beneath the selected output."""
    value = str(title or "attachment")
    value = value.replace("\\", "/").rsplit("/", 1)[-1]
    value = "".join(char for char in value if ord(char) >= 32 and ord(char) != 127)
    return value if value not in ("", ".", "..") else "attachment"
