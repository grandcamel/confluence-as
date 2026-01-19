#!/usr/bin/env python3
"""
Space context loader for Confluence Assistant Skills.

Provides lazy loading and caching of space-specific context including
metadata, templates, and defaults. Context is loaded from:
1. Environment variables (highest priority)
2. settings.local.json (personal overrides)
3. Skill directories (.claude/skills/confluence-space-{KEY}/)
4. Hardcoded defaults (fallback)
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Module-level cache for session persistence with thread-safe access
_context_cache: dict[str, SpaceContext] = {}
_context_cache_lock = threading.Lock()


@dataclass
class SpaceContext:
    """Structured space context data."""

    space_key: str
    space_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    templates: dict[str, Any] = field(default_factory=dict)
    patterns: dict[str, Any] = field(default_factory=dict)
    defaults: dict[str, Any] = field(default_factory=dict)
    source: str = "none"  # 'skill', 'settings', 'merged', 'none'
    discovered_at: str | None = None

    def has_context(self) -> bool:
        """Check if any context data is available."""
        return bool(self.metadata or self.templates or self.patterns or self.defaults)

    def get_page_templates(self) -> list[dict[str, Any]]:
        """Get available page templates."""
        return self.templates.get("page_templates", [])

    def get_labels(self) -> list[str]:
        """Get commonly used labels in this space."""
        return self.metadata.get("common_labels", [])

    def get_content_types(self) -> list[str]:
        """Get content types used in this space."""
        return self.metadata.get("content_types", ["page", "blogpost"])

    def get_page_count(self) -> int | None:
        """Get approximate page count if discovered."""
        return self.metadata.get("page_count")


def get_skills_root() -> Path:
    """Get the root path of the skills directory."""
    # Look for .claude directory in current working directory or parents
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        claude_dir = parent / ".claude"
        if claude_dir.exists():
            return claude_dir
    return cwd / ".claude"


def get_space_skill_path(space_key: str) -> Path:
    """Get the path to a space-specific skill directory."""
    return get_skills_root() / "skills" / f"confluence-space-{space_key}"


def load_json_file(path: Path) -> dict[str, Any] | None:
    """Load a JSON file if it exists."""
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
    return None


def load_skill_context(space_key: str) -> dict[str, Any] | None:
    """
    Load context from a space skill directory.

    Looks for .claude/skills/confluence-space-{SPACE_KEY}/context/

    Returns:
        Dict with 'metadata', 'templates', 'patterns', 'defaults' keys
        or None if skill directory doesn't exist
    """
    skill_path = get_space_skill_path(space_key)

    if not skill_path.exists():
        return None

    context: dict[str, Any] = {}

    # Load context files
    context_dir = skill_path / "context"
    if context_dir.exists():
        metadata = load_json_file(context_dir / "metadata.json")
        if metadata:
            context["metadata"] = metadata

        templates = load_json_file(context_dir / "templates.json")
        if templates:
            context["templates"] = templates

        patterns = load_json_file(context_dir / "patterns.json")
        if patterns:
            context["patterns"] = patterns

    # Load defaults from skill root
    defaults = load_json_file(skill_path / "defaults.json")
    if defaults:
        context["defaults"] = defaults

    return context if context else None


def load_settings_context(space_key: str) -> dict[str, Any] | None:
    """
    Load context overrides from settings.local.json.

    Looks for:
    {
      "confluence": {
        "spaces": {
          "{SPACE_KEY}": {
            "defaults": { ... },
            "metadata": { ... }  # optional overrides
          }
        }
      }
    }

    Returns:
        Dict with context overrides or None if not configured
    """
    # Find settings.local.json
    settings_path = get_skills_root().parent / "settings.local.json"

    if not settings_path.exists():
        settings_path = get_skills_root() / "settings.local.json"

    if not settings_path.exists():
        return None

    settings = load_json_file(settings_path)
    if not settings:
        return None

    # Navigate to space config
    confluence_config = settings.get("confluence", {})
    spaces = confluence_config.get("spaces", {})
    space_config = spaces.get(space_key, {})

    if not space_config:
        return None

    return space_config


def merge_contexts(
    skill_ctx: dict[str, Any] | None, settings_ctx: dict[str, Any] | None
) -> tuple[dict[str, Any], str]:
    """
    Merge settings overrides on top of skill context.

    Returns:
        Tuple of (merged_context, source_string)
    """
    if not skill_ctx and not settings_ctx:
        return {}, "none"

    if not skill_ctx:
        assert settings_ctx is not None
        return settings_ctx, "settings"

    if not settings_ctx:
        return skill_ctx, "skill"

    # Deep merge settings on top of skill context
    merged: dict[str, Any] = {}

    for key in ["metadata", "templates", "patterns", "defaults"]:
        skill_data = skill_ctx.get(key, {})
        settings_data = settings_ctx.get(key, {})

        if skill_data and settings_data:
            merged[key] = _deep_merge(skill_data, settings_data)
        elif settings_data:
            merged[key] = settings_data
        elif skill_data:
            merged[key] = skill_data

    return merged, "merged"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override dict into base dict."""
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def get_space_context(space_key: str, force_refresh: bool = False) -> SpaceContext:
    """
    Lazy-load space context with caching.

    Priority:
    1. Check memory cache (unless force_refresh)
    2. Load from skill directory
    3. Merge with settings.local.json overrides
    4. Cache in memory

    Args:
        space_key: Confluence space key (e.g., 'TEST', 'DEV')
        force_refresh: If True, bypass cache and reload

    Returns:
        SpaceContext with merged data from all sources
    """
    cache_key = space_key

    # Check cache unless force refresh (thread-safe read)
    if not force_refresh:
        with _context_cache_lock:
            if cache_key in _context_cache:
                return _context_cache[cache_key]

    # Load from sources (outside lock - I/O operations)
    skill_ctx = load_skill_context(space_key)
    settings_ctx = load_settings_context(space_key)

    # Merge contexts
    merged, source = merge_contexts(skill_ctx, settings_ctx)

    # Extract discovered_at timestamp
    discovered_at = None
    if merged.get("metadata", {}).get("discovered_at"):
        discovered_at = merged["metadata"]["discovered_at"]

    # Extract space ID if available
    space_id = merged.get("metadata", {}).get("space_id")

    # Create context object
    context = SpaceContext(
        space_key=space_key,
        space_id=space_id,
        metadata=merged.get("metadata", {}),
        templates=merged.get("templates", {}),
        patterns=merged.get("patterns", {}),
        defaults=merged.get("defaults", {}),
        source=source,
        discovered_at=discovered_at,
    )

    # Cache and return (thread-safe write)
    with _context_cache_lock:
        _context_cache[cache_key] = context
    return context


def clear_context_cache(space_key: str | None = None) -> None:
    """
    Clear the context cache.

    Thread-safe cache clearing.

    Args:
        space_key: If specified, only clear cache for this space.
                   If None, clear all cached contexts.
    """
    with _context_cache_lock:
        if space_key is None:
            _context_cache.clear()
        elif space_key in _context_cache:
            del _context_cache[space_key]


def get_page_defaults(
    context: SpaceContext, content_type: str = "page"
) -> dict[str, Any]:
    """
    Get creation defaults for a specific content type.

    Merges global defaults with content-type-specific defaults.

    Args:
        context: SpaceContext object
        content_type: Content type name (e.g., 'page', 'blogpost')

    Returns:
        Dict with default values: labels, parent, status, etc.
    """
    defaults = context.defaults

    # Start with global defaults
    result = dict(defaults.get("global", {}))

    # Merge content-type-specific defaults
    by_type = defaults.get("by_content_type", {})
    type_defaults = by_type.get(content_type, {})

    for key, value in type_defaults.items():
        if key == "labels" and key in result:
            # Merge label lists
            result[key] = list(set(result[key] + value))
        else:
            result[key] = value

    return result


def get_common_labels(context: SpaceContext, limit: int = 10) -> list[str]:
    """
    Get the most commonly used labels in this space.

    Args:
        context: SpaceContext object
        limit: Maximum number of labels to return

    Returns:
        List of label strings, sorted by frequency
    """
    patterns = context.patterns
    labels = patterns.get("labels", {})

    # Sort by count and return top N
    sorted_labels = sorted(labels.items(), key=lambda x: x[1], reverse=True)
    return [label for label, _ in sorted_labels[:limit]]


def get_top_contributors(context: SpaceContext, limit: int = 5) -> list[dict[str, Any]]:
    """
    Get the top contributors in this space.

    Args:
        context: SpaceContext object
        limit: Maximum number of contributors to return

    Returns:
        List of contributor dicts with 'account_id', 'display_name', 'count'
    """
    patterns = context.patterns
    contributors = patterns.get("contributors", [])

    return contributors[:limit]


def suggest_parent_page(context: SpaceContext) -> str | None:
    """
    Suggest a parent page based on patterns.

    Args:
        context: SpaceContext object

    Returns:
        Page ID of suggested parent, or None if no pattern data
    """
    defaults = context.defaults
    parent = defaults.get("parent_id") or defaults.get("global", {}).get("parent_id")
    return parent


def format_context_summary(context: SpaceContext) -> str:
    """
    Format a human-readable summary of the space context.

    Args:
        context: SpaceContext object

    Returns:
        Formatted string summary
    """
    lines = []
    lines.append(f"Space: {context.space_key}")
    lines.append(f"Source: {context.source}")

    if context.space_id:
        lines.append(f"Space ID: {context.space_id}")

    if context.discovered_at:
        lines.append(f"Discovered: {context.discovered_at}")

    # Page count
    page_count = context.get_page_count()
    if page_count:
        lines.append(f"Page Count: ~{page_count:,}")

    # Templates
    templates = context.get_page_templates()
    if templates:
        template_names = [t.get("name", "Unknown") for t in templates[:5]]
        lines.append(f"Templates: {', '.join(template_names)}")

    # Common labels
    common_labels = get_common_labels(context, limit=5)
    if common_labels:
        lines.append(f"Common Labels: {', '.join(common_labels)}")

    # Top contributors
    contributors = get_top_contributors(context, limit=3)
    if contributors:
        names = [c.get("display_name", "Unknown") for c in contributors]
        lines.append(f"Top Contributors: {', '.join(names)}")

    # Defaults summary
    if context.defaults:
        defaults_types = list(context.defaults.get("by_content_type", {}).keys())
        if defaults_types:
            lines.append(f"Defaults configured for: {', '.join(defaults_types)}")

    return "\n".join(lines)


def has_space_context(space_key: str) -> bool:
    """
    Check if space context exists without fully loading it.

    Args:
        space_key: Confluence space key

    Returns:
        True if skill directory or settings config exists
    """
    # Check skill directory
    skill_path = get_space_skill_path(space_key)
    if skill_path.exists():
        return True

    # Check settings.local.json
    settings_ctx = load_settings_context(space_key)
    return settings_ctx is not None
