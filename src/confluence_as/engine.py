"""Confluence configuration and packaged indexes for the Generic Surface."""

from __future__ import annotations

import os
from pathlib import Path

from as_engine.index import OperationIndex, ProductIndexes
from as_engine.responder import Responder
from as_engine.surface import Surface
from as_engine.transport import HTTPTransport, Transport


def create_surface(*, transport: str | None = None, respond_with: int = 200) -> Surface:
    """Keep discovery and responder mode credential-free; configure HTTP at call time."""
    mode = transport or os.environ.get("CONFLUENCE_AS_TRANSPORT", "http")
    if mode not in ("http", "responder"):
        raise ValueError("CONFLUENCE_AS_TRANSPORT must be http or responder")
    if not 100 <= respond_with <= 599:
        raise ValueError("--respond-with must be an HTTP status from 100 to 599")
    if respond_with != 200 and mode != "responder":
        raise ValueError("--respond-with requires responder transport")
    indexes = ProductIndexes(Path(__file__).parent / "_generated")

    def factory(document: str, index: OperationIndex) -> Transport:
        if mode == "responder":
            return Responder(index, status=respond_with)
        from confluence_as.config_manager import ConfigManager
        from confluence_as.error_handler import handle_confluence_error

        config = ConfigManager.get_instance()
        credentials = config.get_credentials()
        settings = config.get_api_config()
        site = credentials["url"].rstrip("/").removesuffix("/wiki")
        base = site + "/wiki/api/v2" if document == "v2" else site
        return HTTPTransport(
            base,
            auth=(credentials["email"], credentials["api_token"]),
            timeout=settings.get("timeout", 30),
            max_retries=settings.get("max_retries", 3),
            retry_backoff=settings.get("retry_backoff", 2),
            verify_ssl=settings.get("verify_ssl", True),
            error_handler=handle_confluence_error,
        )

    return Surface(indexes, factory)
