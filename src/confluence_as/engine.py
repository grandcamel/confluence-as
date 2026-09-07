"""Confluence configuration and packaged indexes for the Generic Surface."""

from __future__ import annotations

import base64
import os
from pathlib import Path

from as_engine.cassette import Player, Recorder, Scrubber
from as_engine.index import OperationIndex, ProductIndexes
from as_engine.responder import Responder
from as_engine.surface import Surface
from as_engine.transport import HTTPTransport, Transport


def create_surface(*, transport: str | None = None, respond_with: int = 200) -> Surface:
    """Keep discovery and responder mode credential-free; configure HTTP at call time."""
    mode = transport or os.environ.get("CONFLUENCE_AS_TRANSPORT", "http")
    if mode not in ("http", "responder", "cassette"):
        raise ValueError("CONFLUENCE_AS_TRANSPORT must be http, responder or cassette")
    cassette_path = os.environ.get("CONFLUENCE_AS_CASSETTE")
    record_path = os.environ.get("CONFLUENCE_AS_RECORD")
    if mode == "cassette" and not cassette_path:
        raise ValueError("cassette transport requires CONFLUENCE_AS_CASSETTE")
    if record_path and mode != "http":
        raise ValueError("CONFLUENCE_AS_RECORD requires http transport")
    if cassette_path and mode != "cassette":
        raise ValueError("CONFLUENCE_AS_CASSETTE requires cassette transport")
    if not 100 <= respond_with <= 599:
        raise ValueError("--respond-with must be an HTTP status from 100 to 599")
    if respond_with != 200 and mode != "responder":
        raise ValueError("--respond-with requires responder transport")
    indexes = ProductIndexes(Path(__file__).parent / "_generated")

    recorder: Recorder | None = None

    def factory(document: str, index: OperationIndex) -> Transport:
        nonlocal recorder
        if mode == "cassette":
            if cassette_path is None:
                raise ValueError("cassette transport requires CONFLUENCE_AS_CASSETTE")
            return Player(cassette_path)
        if mode == "responder":
            return Responder(index, status=respond_with)
        from confluence_as.config_manager import ConfigManager
        from confluence_as.error_handler import handle_confluence_error

        config = ConfigManager.get_instance()
        credentials = config.get_credentials()
        settings = config.get_api_config()
        site = credentials["url"].rstrip("/").removesuffix("/wiki")
        base = site + "/wiki/api/v2" if document == "v2" else site
        live = HTTPTransport(
            base,
            auth=(credentials["email"], credentials["api_token"]),
            timeout=settings.get("timeout", 30),
            max_retries=settings.get("max_retries", 3),
            retry_backoff=settings.get("retry_backoff", 2),
            verify_ssl=settings.get("verify_ssl", True),
            error_handler=(lambda *_: None) if record_path else handle_confluence_error,
        )

        if not record_path:
            return live
        scrubber = recorder.scrubber if recorder is not None else Scrubber()
        scrubber.register(site, "site")
        scrubber.register(credentials["email"])
        scrubber.register(credentials["api_token"])
        # Register the wire's Basic value too, including echoes in free text.
        basic = base64.b64encode(
            (credentials["email"] + ":" + credentials["api_token"]).encode()
        ).decode()
        scrubber.register(basic)
        if recorder is None:
            try:
                recorder = Recorder(live, record_path, scrubber=scrubber)
            except (ValueError, OSError):
                live.close()
                raise
        else:
            recorder.transport = live
        return recorder

    from confluence_as.config_manager import ConfigManager

    return Surface(
        indexes,
        factory,
        **ConfigManager.get_instance().get_scope_config(),
        scope_resolution_rules={
            "v2:getPageById": (("id",),),
            "v2:getSpaceById": (("id",),),
            "v2:getSpaces": (("ids",), ("keys",)),
        },
    )
