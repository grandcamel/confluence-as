"""Run-owned SBX resources driven through the public CLI, with streaming receipts.

Importing this module does not initialize product configuration or a transport.
The receipt stream is captured before CliRunner redirects stdout/stderr. Live
pytest must use --capture=no and the supervisor must capture that outer stream.
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TextIO


class LiveContractError(RuntimeError):
    """A scrubbed live contract failure; never includes a raw server response."""


def numeric_id(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise LiveContractError("Missing or invalid resource ID")
    value = str(value)
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise LiveContractError("Missing or invalid resource ID")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LiveContractError(message)


def validate_live_environment(environment, *, space_key: str, capture: str) -> None:
    require(space_key == "SBX", "Only --space-key SBX is supported")
    require(capture == "no", "Live receipts require --capture=no")
    require(
        environment.get("CONFLUENCE_ALLOWED_SPACES") == "SBX",
        "Live scope must be exactly SBX",
    )
    require(
        "CONFLUENCE_ALLOW_SITE_OPERATIONS" not in environment,
        "Live site-operation override must be absent",
    )
    require(
        environment.get("CONFLUENCE_AS_TRANSPORT", "http") == "http",
        "Live transport must be HTTP",
    )
    for name in (
        "CONFLUENCE_AS_CASSETTE",
        "CONFLUENCE_AS_RECORD",
        "CONFLUENCE_AS_SIMULATION_SEED",
        "CONFLUENCE_MOCK_MODE",
    ):
        require(name not in environment, "Live transport override must be absent")
    for name in ("CONFLUENCE_SITE_URL", "CONFLUENCE_EMAIL", "CONFLUENCE_API_TOKEN"):
        require(bool(environment.get(name)), "Host wrapper configuration is incomplete")


def invoke_cli(argv: list[str], stdin: str | None = None) -> Any:
    from click.testing import CliRunner

    from confluence_as.cli.main import cli

    result = CliRunner().invoke(cli, argv, input=stdin)
    if result.exit_code != 0:
        raise LiveContractError("CLI operation failed")
    try:
        return json.loads(result.stdout)
    except (TypeError, ValueError):
        raise LiveContractError("CLI did not return JSON") from None


@dataclass
class Resource:
    kind: str
    id: str
    parent: tuple[str, str] | None
    name: str
    state: str = "candidate"

    @property
    def token(self):
        return self.kind, self.id


class LiveRun:
    """Additional fixture ownership checks; the product Surface still guards calls.

    This helper is not arbitrary-code containment or an auth provenance check.
    Unknown writes remain pending and block dependent cleanup; no inferred cascade.
    """

    OPERATIONS = frozenset(
        {
            "createPage",
            "getPageById",
            "getSpaceById",
            "getPages",
            "getChildPages",
            "getPageVersions",
            "page copy",
            "hierarchy tree",
            "updatePage",
            "deletePage",
            "getPageContentProperties",
            "createPageProperty",
            "getPageContentPropertiesById",
            "updatePagePropertyById",
            "deletePagePropertyById",
            "property set",
        }
    )

    def __init__(
        self,
        *,
        stream: TextIO | None = None,
        invoke: Callable[[list[str], str | None], Any] = invoke_cli,
    ):
        self.run_id = uuid.uuid4().hex
        self.prefix = "jas43-" + self.run_id + "-"
        self.stream = sys.stdout if stream is None else stream
        self.invoke = invoke
        self.resources: dict[tuple[str, str], Resource] = {}
        self.pending: dict[int, tuple[str, str] | None] = {}
        self.blocked_parents: set[tuple[str, str]] = set()
        self.sequence = 0
        self.space_id: str | None = None
        self.root: Resource | None = None
        self.emit("start")

    def emit(self, event: str, *, operation=None, resource=None, intent=None):
        self.sequence += 1
        row = {"jas43": 1, "run": self.run_id, "seq": self.sequence, "event": event}
        if operation is not None:
            require(operation in self.OPERATIONS, "Unsupported receipt operation")
            row["operation"] = operation
        if resource is not None:
            require(
                resource.kind in {"page", "property"}, "Unknown receipt resource kind"
            )
            require(
                resource.state in {"candidate", "owned", "uncertain", "deleted"},
                "Unknown receipt resource state",
            )
            row.update(
                kind=resource.kind, id=numeric_id(resource.id), state=resource.state
            )
            if resource.parent is not None:
                require(
                    resource.parent[0] in {"page", "property"},
                    "Unknown receipt parent kind",
                )
                row["parent_kind"] = resource.parent[0]
                row["parent_id"] = numeric_id(resource.parent[1])
        if intent is not None:
            row["intent"] = intent
        self.stream.write(json.dumps(row, sort_keys=True) + "\n")
        self.stream.flush()
        return self.sequence

    def name(self, purpose: str) -> str:
        require(bool(re.fullmatch(r"[a-z0-9-]+", purpose)), "Invalid run name purpose")
        return self.prefix + purpose + "-" + uuid.uuid4().hex[:8]

    def call(
        self,
        operation: str,
        parameters=None,
        body=None,
        *,
        mutation=False,
        dependency: Resource | None = None,
        candidate: tuple[str, str] | None = None,
        wrapper=False,
    ) -> Any:
        require(operation in self.OPERATIONS, "Operation is outside the live tranche")
        parameters = dict(parameters or {})
        stdin = None
        if wrapper:
            if operation == "page copy":
                require(
                    set(parameters) == {"id", "title", "parent"},
                    "Invalid copy arguments",
                )
                argv = [
                    "page",
                    "copy",
                    parameters["id"],
                    "--title",
                    parameters["title"],
                    "--space",
                    "SBX",
                    "--parent",
                    parameters["parent"],
                    "--output",
                    "json",
                ]
            elif operation == "hierarchy tree":
                require(set(parameters) == {"id"}, "Invalid tree arguments")
                argv = [
                    "hierarchy",
                    "tree",
                    parameters["id"],
                    "--max-depth",
                    "2",
                    "--stats",
                    "--output",
                    "json",
                ]
            else:
                require(operation == "property set", "Unsupported wrapper")
                argv = [
                    "property",
                    "set",
                    parameters["page-id"],
                    parameters["key"],
                    "--value",
                    json.dumps(body),
                    "--output",
                    "json",
                ]
        else:
            argv = ["api", "call", operation, "--format", "json", "--confirm"]
            if operation in {
                "createPage",
                "getPageById",
                "updatePage",
                "getPages",
                "getPageVersions",
            }:
                argv.append("--raw")
            for key, value in parameters.items():
                if key == "all":
                    require(value is True, "Invalid aggregate flag")
                    argv.append("--all")
                    continue
                encoded = (
                    json.dumps(value) if isinstance(value, (list, bool)) else str(value)
                )
                argv.extend(["--" + key, encoded])
            if body is not None:
                # The public parser accepts @file or stdin, never inline JSON.
                argv.extend(["--body", "-"])
                stdin = json.dumps(body)
        intent = self.emit("intent", operation=operation, resource=dependency)
        if mutation:
            self.pending[intent] = dependency.token if dependency else None
        try:
            result = self.invoke(argv, stdin)
            if candidate is not None:
                kind, name = candidate
                payload = (
                    result.get("property") if operation == "property set" else result
                )
                resource_id = numeric_id(payload.get("id"))
                resource = Resource(
                    kind, resource_id, dependency.token if dependency else None, name
                )
                # Emit before validating title/space/key or issuing any read-back.
                self.emit(
                    "candidate", operation=operation, resource=resource, intent=intent
                )
                if (
                    resource.token in self.resources
                    and kind == "page"
                    and "parentId" in payload
                ):
                    self._observe_relationship(payload)
                require(
                    resource.token not in self.resources, "Duplicate candidate identity"
                )
                self.resources[resource.token] = resource
            elif mutation and operation in {
                "updatePage",
                "updatePagePropertyById",
                "property set",
            }:
                payload = result.get("property") if wrapper else result
                returned_id = numeric_id(payload.get("id"))
                if dependency is not None and returned_id != dependency.id:
                    # An upsert can race a remote delete. Preserve any newly returned
                    # identity before rejecting it; never adopt or sweep it.
                    resource = Resource(
                        dependency.kind, returned_id, dependency.parent, dependency.name
                    )
                    self.emit(
                        "candidate",
                        operation=operation,
                        resource=resource,
                        intent=intent,
                    )
                    require(
                        resource.token not in self.resources,
                        "Duplicate returned identity",
                    )
                    self.resources[resource.token] = resource
            self.emit(
                "mutation" if mutation else "response",
                operation=operation,
                resource=dependency,
                intent=intent,
            )
        except BaseException:
            self.emit(
                "unknown-outcome" if mutation else "failed",
                operation=operation,
                resource=dependency,
                intent=intent,
            )
            raise LiveContractError(
                "Operation outcome is unresolved; inspect receipt"
            ) from None
        self.pending.pop(intent, None)
        return result

    def _owned(self, resource: Resource, kind: str) -> Resource:
        require(
            resource.kind == kind
            and self.resources.get(resource.token) is resource
            and resource.state == "owned"
            and resource.name.startswith(self.prefix),
            "Resource is not owned by this run",
        )
        require(
            resource.token not in self.pending.values(),
            "Resource has an unresolved mutation",
        )
        return resource

    def _page_data(self, resource: Resource) -> dict:
        row = self.call("getPageById", {"id": resource.id, "body-format": "storage"})
        require(isinstance(row, dict), "Page read-back shape is invalid")
        self._observe_relationship(row)
        require(numeric_id(row.get("id")) == resource.id, "Page identity changed")
        require(row.get("title") == resource.name, "Page run title changed")
        space_id = numeric_id(row.get("spaceId"))
        require(
            self.space_id is None or space_id == self.space_id, "Page space changed"
        )
        expected_parent = resource.parent[1] if resource.parent else None
        if expected_parent is not None:
            require(str(row.get("parentId")) == expected_parent, "Page parent changed")
        return row

    def read_page(self, resource: Resource) -> dict:
        self._owned(resource, "page")
        return self._page_data(resource)

    def create_page(self, purpose="page", *, parent: Resource | None = None, body=None):
        if parent is not None:
            self.read_page(parent)
        else:
            require(
                not self.resources and not self.pending,
                "Only bootstrap may be parentless",
            )
        title = self.name(purpose)
        payload = {
            "title": title,
            "status": "current",
            "body": body
            or {
                "representation": "storage",
                "value": "<p>JAS-43 owned content.</p>",
            },
        }
        if parent is not None:
            payload["parentId"] = parent.id
        created = self.call(
            "createPage",
            {"space": "SBX", "space-key": "SBX"},
            payload,
            mutation=True,
            dependency=parent,
            candidate=("page", title),
        )
        resource = self.resources[("page", numeric_id(created.get("id")))]
        # The candidate remains journaled if any subsequent assertion fails.
        require(created.get("title") == title, "Created page title mismatch")
        page = self._page_data(resource)
        if self.space_id is None:
            space_id = numeric_id(page.get("spaceId"))
            space = self.call("getSpaceById", {"id": space_id})
            require(
                isinstance(space, dict)
                and numeric_id(space.get("id")) == space_id
                and space.get("key") == "SBX"
                and space.get("type") == "global",
                "Bootstrap did not verify global SBX",
            )
            self.space_id = space_id
            self.root = resource
        require(
            str(created.get("spaceId")) == self.space_id, "Created page space mismatch"
        )
        resource.state = "owned"
        self.emit("owned", resource=resource)
        return resource

    def update_page(self, resource: Resource, *, title=None, body=None):
        before = self.read_page(resource)
        if title is None:
            title = resource.name
        require(title.startswith(self.prefix), "Update title is not run scoped")
        payload = {
            "id": resource.id,
            "title": title,
            "status": "current",
            "body": body or before["body"]["storage"],
        }
        result = self.call(
            "updatePage",
            {"id": resource.id},
            payload,
            mutation=True,
            dependency=resource,
        )
        # Only a matching success response changes expected title. A malformed
        # response leaves the resource uncertain, so cleanup cannot guess its state.
        resource.state = "uncertain"
        require(numeric_id(result.get("id")) == resource.id, "Updated page ID mismatch")
        require(result.get("title") == title, "Updated page title mismatch")
        resource.name = title
        readback = self._page_data(resource)
        require(
            readback["version"]["number"] == before["version"]["number"] + 1,
            "Page version did not increment",
        )
        resource.state = "owned"
        self.emit("owned", resource=resource)
        return readback

    def list_owned_page(self, resource: Resource):
        require(self.resources.get(resource.token) is resource, "Unknown page identity")
        result = self.call(
            "getPages",
            {
                "space-id": [self.space_id],
                "id": [resource.id],
                "status": ["current"],
                "limit": 2,
            },
        )
        require(
            isinstance(result, dict) and isinstance(result.get("results"), list),
            "Page listing shape is invalid",
        )
        for row in result["results"]:
            self._observe_relationship(row)
        require(not result.get("_links", {}).get("next"), "Page listing is incomplete")
        for row in result["results"]:
            require(
                numeric_id(row.get("id")) == resource.id,
                "Unexpected page in filtered list",
            )
            require(
                str(row.get("spaceId")) == self.space_id, "Listed page is outside SBX"
            )
        return result["results"]

    def _dependencies_removed(self, resource: Resource):
        require(
            resource.token not in self.blocked_parents,
            "Observed child relationship blocks parent deletion",
        )
        require(
            not any(
                r.parent == resource.token and r.state != "deleted"
                for r in self.resources.values()
            ),
            "Owned dependencies remain",
        )
        require(
            not any(
                parent is None or parent == resource.token
                for parent in self.pending.values()
            ),
            "Unresolved creation or mutation remains",
        )

    def _block_parent(self, parent: Resource):
        if parent.token not in self.blocked_parents:
            self.blocked_parents.add(parent.token)
            self.emit("child-relationship-unresolved", resource=parent)

    def _observe_relationship(self, row):
        """Record an observed unowned dependency without adopting its identity."""
        if not isinstance(row, dict) or "parentId" not in row:
            return
        parent = self.resources.get(("page", str(row.get("parentId"))))
        child = self.resources.get(("page", str(row.get("id"))))
        if parent is not None and (
            child is None or child.parent != parent.token or child.state == "deleted"
        ):
            self._block_parent(parent)
        if child is not None and child.parent is not None:
            if str(row.get("parentId")) != child.parent[1]:
                self._block_parent(self.resources[child.parent])

    @staticmethod
    def _complete_rows(result, limit):
        require(
            isinstance(result, dict) and isinstance(result.get("results"), list),
            "Listing shape is invalid",
        )
        links = result.get("_links", {})
        require(
            isinstance(links, dict) and not links.get("next"), "Listing is incomplete"
        )
        require(len(result["results"]) < limit, "Listing reached its bound")
        require(
            all(isinstance(row, dict) for row in result["results"]),
            "Invalid listing row",
        )
        return result["results"]

    def children_match(self, parent: Resource, children=()):
        self._owned(parent, "page")
        require(len(children) <= 1, "Only a tiny owned hierarchy is supported")
        for child in children:
            self._owned(child, "page")
            require(child.parent == parent.token, "Unexpected owned parent")
        self.read_page(parent)
        result = self.call("getChildPages", {"id": parent.id, "limit": 2})
        try:
            if isinstance(result, dict) and isinstance(result.get("results"), list):
                for row in result["results"]:
                    if isinstance(row, dict) and "parentId" in row:
                        self._observe_relationship(row)
            rows = self._complete_rows(result, 2)
            expected = {child.id: child for child in children}
            ids = [numeric_id(row.get("id")) for row in rows]
            require(
                len(ids) == len(set(ids)) and set(ids) == set(expected),
                "Unexpected immediate children",
            )
            for row in rows:
                require(
                    row.get("title") == expected[str(row["id"])].name,
                    "Child title changed",
                )
                require(
                    "parentId" not in row or str(row["parentId"]) == parent.id,
                    "Child parent changed",
                )
        except LiveContractError:
            self._block_parent(parent)
            raise
        return rows

    def copy_leaf(self, source: Resource, parent: Resource):
        # Validate every input before making any argv call.
        self._owned(source, "page")
        self._owned(parent, "page")
        require(
            parent is self.root and source.parent == parent.token,
            "Copy requires an owned leaf beneath the run root",
        )
        before = self.read_page(source)
        require(before.get("status") == "current", "Copy source is not current")
        storage = before.get("body", {}).get("storage", {})
        require(
            isinstance(storage, dict) and isinstance(storage.get("value"), str),
            "Copy source storage is missing",
        )
        self.read_page(parent)
        self.children_match(source)
        title = self.name("copy")
        result = self.call(
            "page copy",
            {"id": source.id, "title": title, "parent": parent.id},
            wrapper=True,
            mutation=True,
            dependency=parent,
            candidate=("page", title),
        )
        resource = self.resources[("page", numeric_id(result.get("id")))]
        # call() journals and rejects duplicate/source/parent IDs before reaching here.
        self._observe_relationship(result)
        require(result.get("title") == title, "Copied title mismatch")
        require(str(result.get("spaceId")) == self.space_id, "Copied space mismatch")
        require(
            str(result.get("parentId")) == parent.id
            and result.get("status") == "current",
            "Copied parent/status mismatch",
        )
        page = self._page_data(resource)
        require(page.get("status") == "current", "Copied page is not current")
        require(
            page.get("body", {}).get("storage", {}).get("value") == storage["value"],
            "Copied body mismatch",
        )
        resource.state = "owned"
        self.emit("owned", resource=resource)
        return resource

    def tree_matches(self, root: Resource, child: Resource, grandchild: Resource):
        for page in (root, child, grandchild):
            self._owned(page, "page")
        require(
            child.parent == root.token and grandchild.parent == child.token,
            "Unexpected owned tree relationships",
        )
        self.children_match(root, (child,))
        self.children_match(child, (grandchild,))
        self.children_match(grandchild)
        try:
            result = self.call("hierarchy tree", {"id": root.id}, wrapper=True)
        except LiveContractError:
            for page in (root, child, grandchild):
                self._block_parent(page)
            raise
        expected = {
            "root": {"id": root.id, "title": root.name},
            "tree": [
                {
                    "id": child.id,
                    "title": child.name,
                    "depth": 1,
                    "children": [
                        {
                            "id": grandchild.id,
                            "title": grandchild.name,
                            "depth": 2,
                            "children": [],
                        }
                    ],
                }
            ],
            "stats": {"totalPages": 2, "maxDepth": 2, "rootChildren": 1},
        }
        if result != expected:
            # The wrapper output is never an ownership source. Preserve all three
            # affected parents on any ambiguous/mismatched tree, including extras.
            for page in (root, child, grandchild):
                self._block_parent(page)
            raise LiveContractError(
                "Tree differs from exact owned identities/depth/stats"
            )
        return result

    def versions_match(self, page: Resource, versions):
        self._owned(page, "page")
        require(
            len(versions) == 3
            and all(type(v) is int and v > 0 for v in versions)
            and len(set(versions)) == 3,
            "Expected three recorded unique versions",
        )
        current = self.read_page(page)
        require(
            current["version"]["number"] == max(versions), "Current version changed"
        )
        result = self.call(
            "getPageVersions", {"id": page.id, "body-format": "storage", "limit": 4}
        )
        rows = self._complete_rows(result, 4)
        numbers = [row.get("number") for row in rows]
        require(
            all(type(v) is int for v in numbers)
            and len(numbers) == 3
            and len(set(numbers)) == 3
            and set(numbers) == set(versions),
            "Versions differ from exact recorded updates",
        )
        for row in rows:
            if "page" in row:
                require(
                    isinstance(row["page"], dict)
                    and numeric_id(row["page"].get("id")) == page.id,
                    "Version embedded page mismatch",
                )
        return rows

    def pages_match(self, pages):
        require(
            len(pages) == 2 and len({page.id for page in pages}) == 2,
            "Expected two distinct owned pages",
        )
        for page in pages:
            self._owned(page, "page")
        for page in pages:
            self.read_page(page)
        result = self.call(
            "getPages",
            {
                "space-id": [self.space_id],
                "id": [page.id for page in pages],
                "status": ["current"],
                "limit": 3,
            },
        )
        # Observe relationships even when completeness/identity checks will fail.
        if isinstance(result, dict) and isinstance(result.get("results"), list):
            for row in result["results"]:
                self._observe_relationship(row)
        rows = self._complete_rows(result, 3)
        expected = {page.id: page for page in pages}
        ids = [numeric_id(row.get("id")) for row in rows]
        require(
            len(ids) == 2 and len(set(ids)) == 2 and set(ids) == set(expected),
            "Listing differs from exact owned IDs",
        )
        for row in rows:
            page = expected[str(row["id"])]
            require(
                str(row.get("spaceId")) == self.space_id
                and row.get("status") == "current"
                and row.get("title") == page.name
                and page.parent is not None
                and str(row.get("parentId")) == page.parent[1],
                "Listed page identity changed",
            )
        return rows

    def delete_page(self, resource: Resource):
        self._owned(resource, "page")
        # Check before even reading the parent: explicit deletion shares cleanup's rule.
        self._dependencies_removed(resource)
        self.read_page(resource)
        self.call("deletePage", {"id": resource.id}, mutation=True, dependency=resource)
        resource.state = "uncertain"
        require(self.list_owned_page(resource) == [], "Page deletion is unproven")
        resource.state = "deleted"
        self.emit("cleanup", resource=resource)

    def _property_data(self, resource: Resource):
        require(resource.parent in self.resources, "Property has no known parent")
        page = self.resources[resource.parent]
        self.read_page(page)
        row = self.call(
            "getPageContentPropertiesById",
            {
                "page-id": page.id,
                "property-id": resource.id,
            },
        )
        require(isinstance(row, dict), "Property read-back shape is invalid")
        require(numeric_id(row.get("id")) == resource.id, "Property ID changed")
        require(row.get("key") == resource.name, "Property run key changed")
        return row

    def read_property(self, resource: Resource):
        self._owned(resource, "property")
        return self._property_data(resource)

    def properties(self, page: Resource):
        self.read_page(page)
        # A bounded aggregate cap; hitting it is not proof of absence.
        rows = self.call(
            "getPageContentProperties", {"page-id": page.id, "all": True, "limit": 100}
        )
        require(
            isinstance(rows, list) and len(rows) < 100, "Property list is incomplete"
        )
        return rows

    def create_property(self, page: Resource, value, *, wrapper=False):
        self.read_page(page)
        key = self.name("property")
        require(
            not any(row.get("key") == key for row in self.properties(page)),
            "Property key already exists",
        )
        op = "property set" if wrapper else "createPageProperty"
        parameters = {"page-id": page.id}
        if wrapper:
            parameters["key"] = key
        result = self.call(
            op,
            parameters,
            value if wrapper else {"key": key, "value": value},
            mutation=True,
            dependency=page,
            candidate=("property", key),
            wrapper=wrapper,
        )
        row = result["property"] if wrapper else result
        resource = self.resources[("property", numeric_id(row.get("id")))]
        require(row.get("key") == key, "Created property key mismatch")
        readback = self._property_data(resource)
        require(readback.get("value") == value, "Created property value mismatch")
        resource.state = "owned"
        self.emit("owned", resource=resource)
        return resource

    def update_property(self, resource: Resource, value, *, wrapper=False):
        before = self.read_property(resource)
        page = self.resources[resource.parent]
        op = "property set" if wrapper else "updatePagePropertyById"
        parameters = {"page-id": page.id}
        if wrapper:
            parameters["key"] = resource.name
        else:
            parameters["property-id"] = resource.id
        result = self.call(
            op,
            parameters,
            value if wrapper else {"key": resource.name, "value": value},
            mutation=True,
            dependency=resource,
            wrapper=wrapper,
        )
        resource.state = "uncertain"
        row = result["property"] if wrapper else result
        require(
            numeric_id(row.get("id")) == resource.id, "Updated property ID mismatch"
        )
        after = self._property_data(resource)
        require(after.get("value") == value, "Updated property value mismatch")
        require(
            after["version"]["number"] == before["version"]["number"] + 1,
            "Property version did not increment",
        )
        resource.state = "owned"
        self.emit("owned", resource=resource)
        return after

    def delete_property(self, resource: Resource):
        self.read_property(resource)
        page = self.resources[resource.parent]
        self.call(
            "deletePagePropertyById",
            {"page-id": page.id, "property-id": resource.id},
            mutation=True,
            dependency=resource,
        )
        resource.state = "uncertain"
        rows = self.properties(page)
        require(
            not any(
                str(row.get("id")) == resource.id or row.get("key") == resource.name
                for row in rows
            ),
            "Property deletion is unproven",
        )
        resource.state = "deleted"
        self.emit("cleanup", resource=resource)

    def cleanup(self):
        for resource in reversed(list(self.resources.values())):
            if resource.state != "owned":
                continue
            try:
                if resource.kind == "property":
                    self.delete_property(resource)
                elif resource.kind == "page":
                    self.delete_page(resource)
                else:
                    raise LiveContractError("Unknown cleanup kind")
            except Exception:
                self.emit("cleanup-failed", resource=resource)
        residual = [r for r in self.resources.values() if r.state != "deleted"]
        for resource in residual:
            self.emit("residual", resource=resource)
        for intent in self.pending:
            self.emit("unresolved-intent", intent=intent)
        if residual or self.pending:
            self.emit("incomplete")
            raise LiveContractError("Run cleanup incomplete; inspect streamed receipt")
        self.emit("complete")
