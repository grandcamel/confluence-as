#!/usr/bin/env python3
"""Generate paging enrichment from pinned local Base Documents, never overrides.

Adapted from JAS-9's atlassian-paging-styles.py (2026-09-06): resolve local
refs/allOf, detect collection schemas, then classify by parameter/response
vocabulary. Broad-only vocabularies and links without a cursor input require
hand review. These are printed, never guessed or written into override files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

METHODS = ("get", "put", "post", "delete", "patch", "options", "head", "trace")
SIGNALS = {
    "startAt",
    "maxResults",
    "total",
    "isLast",
    "nextPageToken",
    "nextPage",
    "cursor",
    "start",
    "limit",
    "size",
    "totalSize",
    "offset",
    "isLastPage",
}
ORIGIN = "research/atlassian-paging-styles-2026-09.md (JAS-9)"
EVIDENCE_DATE = "2026-09-06"


def resolve(value, document, seen=()):
    """Resolve structural local references and shallow object composition."""
    if not isinstance(value, dict):
        return {}
    if "$ref" in value:
        ref = value["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/") or ref in seen:
            raise ValueError(f"unsupported or cyclic local reference: {ref!r}")
        node = document
        for part in ref[2:].split("/"):
            node = node[part.replace("~1", "/").replace("~0", "~")]
        return resolve(node, document, (*seen, ref))
    if "allOf" in value:
        merged = {**value, "type": value.get("type", "object"), "properties": {}}
        for child in value["allOf"]:
            item = resolve(child, document, seen)
            merged["properties"].update(item.get("properties", {}))
            if "type" in item:
                merged["type"] = item["type"]
        merged["properties"].update(value.get("properties", {}))
        return merged
    return value


def parameters(item, operation, document):
    result = {}
    for raw in [*item.get("parameters", []), *operation.get("parameters", [])]:
        param = resolve(raw, document)
        result[(param["in"], param["name"])] = param
    return result


def pointer(key):
    return "/" + key.replace("~", "~0").replace("/", "~1")


def classify(item, operation, document):
    response = resolve(operation.get("responses", {}).get("200", {}), document)
    schema = resolve(
        response.get("content", {}).get("application/json", {}).get("schema", {}),
        document,
    )
    props = schema.get("properties", {})
    arrays = [
        name
        for name, value in props.items()
        if resolve(value, document).get("type") == "array"
    ]
    links_next = "next" in resolve(props.get("_links", {}), document).get(
        "properties", {}
    )
    top_array = schema.get("type") == "array"
    if not (
        top_array
        or arrays
        and (SIGNALS.intersection(props) or links_next or len(props) <= 2)
    ):
        return None, None
    query = {
        name
        for location, name in parameters(item, operation, document)
        if location == "query"
    }
    tag = {"style": "none", "request": {}}
    if len(arrays) > 1:
        tag["itemsPaths"] = [pointer(name) for name in arrays]
    else:
        tag["itemsPath"] = "" if top_array else pointer(arrays[0])
    if "nextPageToken" in query or "nextPageToken" in props:
        if "nextPageToken" not in query:
            return None, "token response without a query input"
        tag.update(
            style="nextPageToken", next={"kind": "token", "path": "/nextPageToken"}
        )
        tag["request"]["token"] = {"in": "query", "name": "nextPageToken"}
    elif "cursor" in query or links_next:
        if "cursor" not in query:
            return None, "next-link response without a cursor query input"
        if links_next:
            continuation = {"kind": "link", "path": "/_links/next"}
        elif "cursor" in props:
            continuation = {"kind": "token", "path": "/cursor"}
        elif "Link" in response.get("headers", {}):
            return None, "header-only continuation requires hand review"
        else:
            # Confluence v1 CQL describes the link in prose; its _links schema
            # is an open map rather than named properties.
            if "_links" not in props:
                return None, "cursor input without a resolvable response continuation"
            continuation = {"kind": "link", "path": "/_links/next"}
        tag.update(style="cursor", next=continuation)
        tag["request"]["token"] = {"in": "query", "name": "cursor"}
    elif {"startAt", "maxResults"} <= query and ("total" in props or "isLast" in props):
        tag["style"] = "offset/limit"
        tag["request"]["offset"] = {"in": "query", "name": "startAt"}
        tag["request"]["limit"] = {"in": "query", "name": "maxResults"}
        tag["response"] = (
            {"totalPath": "/total"} if "total" in props else {"isLastPath": "/isLast"}
        )
    elif SIGNALS.intersection(props) or "next" in props:
        return None, "broad or ambiguous response vocabulary; hand review required"
    for name in ("limit", "maxResults"):
        if tag["style"] != "none" and name in query:
            tag["request"]["limit"] = {"in": "query", "name": name}
            break
    if tag["style"] != "none" and "itemsPaths" in tag:
        return None, "multiple collection arrays with paging signals"
    return tag, None


def action_for(document_id, path, method, operation_id, tag):
    return {
        "target": f"$.paths[{json.dumps(path)}].{method}",
        "update": {"x-as-paging": tag},
        "description": f"Declare {tag['style']} paging for {operation_id}.",
        "x-as-reason": "Local response-schema and request-parameter classification; hand decisions layer separately.",
        "x-as-evidence": {
            "url": f"https://developer.atlassian.com/cloud/confluence/rest/{document_id}/intro/#pagination",
            "date": EVIDENCE_DATE,
        },
        "x-as-origin": ORIGIN,
        "x-as-test": f"paging_{document_id}_{operation_id}",
    }


def generate(spec_dir):
    spec_dir = Path(spec_dir).resolve()
    manifest = json.loads((spec_dir / "manifest.json").read_text())
    pending = []
    for entry in manifest["documents"]:
        document_id = entry["id"]
        if document_id not in {"v1", "v2"}:
            raise ValueError(f"unsupported Confluence document id: {document_id}")
        source = (spec_dir / entry["file"]).resolve()
        if not source.is_relative_to(spec_dir):
            raise ValueError("Base Document escapes spec directory")
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError(f"{source.name}: sha256 mismatch")
        document = json.loads(raw)
        actions, review = [], []
        for path, item in sorted(document["paths"].items()):
            for method in METHODS:
                operation = item.get(method)
                if not isinstance(operation, dict):
                    continue
                tag, reason = classify(item, operation, document)
                if reason:
                    review.append(f"{operation['operationId']}: {reason}")
                elif tag is not None:
                    actions.append(
                        action_for(
                            document_id, path, method, operation["operationId"], tag
                        )
                    )
        overlay = {
            "overlay": "1.0.0",
            "info": {
                "title": f"Confluence {document_id} generated paging (do not edit)",
                "version": "1.0.0",
            },
            "actions": actions,
        }
        output = spec_dir / f"{document_id}.paging.overlay.json"
        if output.is_symlink():
            raise ValueError(f"refusing symlink output: {output.name}")
        pending.append(
            (output, (json.dumps(overlay, indent=2, sort_keys=True) + "\n"), review)
        )
    for output, content, review in pending:
        output.write_text(content, encoding="utf-8")
        print(f"{output.name}: {len(json.loads(content)['actions'])} generated entries")
        for decision in review:
            print(f"HAND REVIEW: {decision}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--spec-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "src/confluence_as/specs",
    )
    args = parser.parse_args()
    generate(args.spec_dir)


if __name__ == "__main__":
    main()
