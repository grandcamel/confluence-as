"""Confluence configuration and packaged indexes for the Generic Surface."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from as_engine.errors import SurfaceError
from as_engine.index import OperationIndex, ProductIndexes
from as_engine.responder import Responder
from as_engine.surface import Surface
from as_engine.transport import HTTPTransport, Response, Transport

if TYPE_CHECKING:
    from as_engine.cassette import Recorder
    from as_engine.simulation import SimulationStore


class _ConfiguredSurface(Surface):
    """Defer scope configuration until the first call, before guards or sends."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._scope_loaded = False
        self._scope_overrides: set[str] = set()

    def __setattr__(self, name: str, value: Any) -> None:
        # Consumers can still override either policy field before their first call.
        if name in {"scope_allowlist", "scope_allow_site"}:
            overrides = self.__dict__.get("_scope_overrides")
            if overrides is not None:
                overrides.add(name)
        super().__setattr__(name, value)

    def call(self, *args: Any, **kwargs: Any) -> Response:
        if not self._scope_loaded:
            from confluence_as.config_manager import ConfigManager

            try:
                scope = ConfigManager.get_instance().get_scope_config()
            except ValueError as exc:
                # Keep the API group's original configuration-error envelope;
                # the call adapter must not relabel it as an operation error.
                raise SurfaceError(None, [str(exc)], code=2) from exc
            for name, value in scope.items():
                if name not in self._scope_overrides:
                    setattr(self, name, value)
            self._scope_loaded = True
        return super().call(*args, **kwargs)


def create_surface(
    *,
    transport: str | None = None,
    respond_with: int = 200,
    store: SimulationStore | None = None,
) -> Surface:
    """Keep discovery and responder mode credential-free; configure HTTP at call time."""
    mode = transport or os.environ.get("CONFLUENCE_AS_TRANSPORT", "http")
    if mode not in ("http", "responder", "cassette", "simulation"):
        raise ValueError("CONFLUENCE_AS_TRANSPORT must be http, responder, cassette or simulation")
    cassette_path = os.environ.get("CONFLUENCE_AS_CASSETTE")
    record_path = os.environ.get("CONFLUENCE_AS_RECORD")
    if mode == "cassette" and not cassette_path:
        raise ValueError("cassette transport requires CONFLUENCE_AS_CASSETTE")
    if record_path and mode != "http":
        raise ValueError("CONFLUENCE_AS_RECORD requires http transport")
    if cassette_path and mode != "cassette":
        raise ValueError("CONFLUENCE_AS_CASSETTE requires cassette transport")
    seed_path = os.environ.get("CONFLUENCE_AS_SIMULATION_SEED")
    if seed_path and mode != "simulation":
        raise ValueError("CONFLUENCE_AS_SIMULATION_SEED requires simulation transport")
    if store is not None and mode != "simulation":
        raise ValueError("simulation store requires simulation transport")
    if not 100 <= respond_with <= 599:
        raise ValueError("--respond-with must be an HTTP status from 100 to 599")
    if respond_with != 200 and mode != "responder":
        raise ValueError("--respond-with requires responder transport")
    indexes = ProductIndexes(Path(__file__).parent / "_generated")
    simulation_store = store
    if mode == "simulation" and simulation_store is None:
        from as_engine.simulation import SimulationStore

        if seed_path:
            try:
                seed = json.loads(Path(seed_path).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError("unable to load CONFLUENCE_AS_SIMULATION_SEED") from exc
            simulation_store = SimulationStore(seed)
        else:
            simulation_store = SimulationStore()

    recorder: Recorder | None = None

    def factory(document: str, index: OperationIndex) -> Transport:
        nonlocal recorder
        if mode == "cassette":
            if cassette_path is None:
                raise ValueError("cassette transport requires CONFLUENCE_AS_CASSETTE")
            from as_engine.cassette import Player

            return Player(cassette_path)
        if mode == "responder":
            return Responder(index, status=respond_with)
        if mode == "simulation":
            if simulation_store is None:
                raise AssertionError("simulation store was not initialized")
            from as_engine.simulation import Simulation

            return Simulation(simulation_store)
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
        from as_engine.cassette import Recorder, Scrubber

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

    return _ConfiguredSurface(
        indexes,
        factory,
        scope_resolution_rules={
            "v2:getPageById": (("id",),),
            "v2:getSpaceById": (("id",),),
            "v2:getSpaces": (("ids",), ("keys",)),
        },
    )
