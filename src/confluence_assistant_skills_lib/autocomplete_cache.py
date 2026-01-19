"""
Caching layer for Confluence autocomplete data.

Provides efficient caching of space keys, page titles, labels, and
other suggestions to improve performance of Confluence operations.

Features:
- Automatic cache warming on first use
- Configurable TTL (default: 1 day for definitions)
- In-memory cache with SQLite persistence
- Thread-safe access
- Invalidation support
"""

from __future__ import annotations

import threading
import time
from datetime import timedelta
from typing import Any

from assistant_skills_lib.cache import SkillCache, get_skill_cache

# Default TTL for autocomplete suggestions
DEFAULT_SUGGESTION_TTL = timedelta(hours=24)


class AutocompleteCache:
    """
    Caches Confluence autocomplete suggestions to reduce API calls.

    Caches:
    - Space keys and names
    - Page titles (per space)
    - Labels
    - User account IDs and display names
    """

    # Cache key constants
    KEY_SPACES_LIST = "confluence:spaces:all"
    KEY_LABELS_LIST = "confluence:labels:all"
    KEY_USERS_LIST = "confluence:users:all"
    KEY_PAGES_PREFIX = "confluence:pages:"
    KEY_SUGGESTION_PREFIX = "confluence:suggest:"

    # TTL constants
    TTL_SPACES = timedelta(hours=24)  # 24 hours for spaces (rarely change)
    TTL_LABELS = timedelta(hours=12)  # 12 hours for labels
    TTL_USERS = timedelta(hours=24)  # 24 hours for users
    TTL_PAGES = timedelta(hours=1)  # 1 hour for page lists (change more often)
    TTL_SUGGESTIONS = timedelta(hours=1)  # 1 hour for value suggestions

    def __init__(self, cache: SkillCache | None = None):
        """
        Initialize autocomplete cache.

        Args:
            cache: Optional SkillCache instance (creates one if not provided)
        """
        self._cache = cache or get_skill_cache("confluence_autocomplete")
        self._memory_cache: dict[str, Any] = {}
        self._memory_cache_time: dict[str, float] = {}
        self._memory_lock = threading.Lock()

    def get_spaces(
        self, client=None, force_refresh: bool = False
    ) -> list[dict[str, Any]]:
        """
        Get cached space definitions.

        Args:
            client: Confluence client (required if cache miss)
            force_refresh: Force refresh from API

        Returns:
            List of space dicts with key, name, id
        """
        if not force_refresh:
            # Check memory cache first
            with self._memory_lock:
                if self.KEY_SPACES_LIST in self._memory_cache:
                    cache_time = self._memory_cache_time.get(self.KEY_SPACES_LIST, 0)
                    if time.time() - cache_time < 300:  # 5 min memory cache
                        return self._memory_cache[self.KEY_SPACES_LIST]

            # Check persistent cache
            cached = self._cache.get(self.KEY_SPACES_LIST, category="field")
            if cached:
                with self._memory_lock:
                    self._memory_cache[self.KEY_SPACES_LIST] = cached
                    self._memory_cache_time[self.KEY_SPACES_LIST] = time.time()
                return cached

        # Fetch from API if client provided
        if client:
            try:
                spaces = []
                response = client.get("/wiki/api/v2/spaces", params={"limit": 250})
                results = response.get("results", [])
                for space in results:
                    spaces.append(
                        {
                            "id": space.get("id"),
                            "key": space.get("key"),
                            "name": space.get("name"),
                            "type": space.get("type"),
                        }
                    )
                self.set_spaces(spaces)
                return spaces
            except Exception:
                pass

        return []

    def set_spaces(self, spaces: list[dict[str, Any]]) -> None:
        """
        Cache space definitions.

        Args:
            spaces: List of space dicts
        """
        self._cache.set(
            self.KEY_SPACES_LIST,
            spaces,
            category="field",
            ttl=self.TTL_SPACES,
        )
        with self._memory_lock:
            self._memory_cache[self.KEY_SPACES_LIST] = spaces
            self._memory_cache_time[self.KEY_SPACES_LIST] = time.time()

    def get_labels(
        self, client=None, force_refresh: bool = False
    ) -> list[dict[str, Any]]:
        """
        Get cached label definitions.

        Args:
            client: Confluence client (required if cache miss)
            force_refresh: Force refresh from API

        Returns:
            List of label dicts
        """
        if not force_refresh:
            cached = self._cache.get(self.KEY_LABELS_LIST, category="field")
            if cached:
                return cached

        # Labels are typically fetched per-page, so return empty for now
        return []

    def get_pages_in_space(
        self,
        space_key: str,
        client=None,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Get cached pages for a specific space.

        Args:
            space_key: Space key to get pages for
            client: Confluence client (required if cache miss)
            force_refresh: Force refresh from API

        Returns:
            List of page dicts with id, title
        """
        cache_key = f"{self.KEY_PAGES_PREFIX}{space_key}"

        if not force_refresh:
            cached = self._cache.get(cache_key, category="search")
            if cached:
                return cached

        # Fetch from API if client provided
        if client:
            try:
                pages = []
                # Get space ID first
                spaces = self.get_spaces(client)
                space_id = None
                for space in spaces:
                    if space.get("key") == space_key:
                        space_id = space.get("id")
                        break

                if space_id:
                    response = client.get(
                        "/wiki/api/v2/pages",
                        params={"space-id": space_id, "limit": 100},
                    )
                    results = response.get("results", [])
                    for page in results:
                        pages.append(
                            {
                                "id": page.get("id"),
                                "title": page.get("title"),
                                "status": page.get("status"),
                            }
                        )

                    self._cache.set(
                        cache_key,
                        pages,
                        category="search",
                        ttl=self.TTL_PAGES,
                    )
                    return pages
            except Exception:
                pass

        return []

    def warm_cache(self, client) -> dict[str, int]:
        """
        Pre-warm the autocomplete cache.

        Args:
            client: Confluence client

        Returns:
            Dict with counts of cached items
        """
        stats = {"spaces": 0, "pages": 0}

        try:
            spaces = self.get_spaces(client, force_refresh=True)
            stats["spaces"] = len(spaces)

            # Optionally warm first few spaces with pages
            for space in spaces[:3]:
                try:
                    pages = self.get_pages_in_space(
                        space.get("key", ""), client, force_refresh=True
                    )
                    stats["pages"] += len(pages)
                except Exception:
                    pass

        except Exception as e:
            print(f"Warning: Cache warming failed: {e}")

        return stats

    def invalidate(self, space_key: str | None = None) -> int:
        """
        Invalidate cached autocomplete data.

        Args:
            space_key: Specific space to invalidate pages for,
                       or None to invalidate all

        Returns:
            Number of entries invalidated
        """
        count = 0

        if space_key:
            # Invalidate specific space pages
            cache_key = f"{self.KEY_PAGES_PREFIX}{space_key}"
            count += self._cache.invalidate(key=cache_key, category="search")
        else:
            # Invalidate all autocomplete data
            count += self._cache.invalidate(key=self.KEY_SPACES_LIST, category="field")
            count += self._cache.invalidate(key=self.KEY_LABELS_LIST, category="field")
            count += self._cache.invalidate(key=self.KEY_USERS_LIST, category="field")
            count += self._cache.invalidate(pattern=f"{self.KEY_PAGES_PREFIX}*")

            # Clear memory cache
            with self._memory_lock:
                self._memory_cache.clear()
                self._memory_cache_time.clear()

        return count

    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache statistics
        """
        cache_stats = self._cache.get_stats()

        # Check what's currently cached
        has_spaces = self._cache.get(self.KEY_SPACES_LIST, category="field") is not None

        with self._memory_lock:
            memory_cache_size = len(self._memory_cache)

        return {
            "spaces_cached": has_spaces,
            "memory_cache_size": memory_cache_size,
            "total_cache_entries": cache_stats.entry_count,
            "cache_hit_rate": f"{cache_stats.hit_rate * 100:.1f}%",
        }


# Singleton instance for shared access
_autocomplete_cache: AutocompleteCache | None = None
_autocomplete_cache_lock = threading.Lock()


def get_autocomplete_cache() -> AutocompleteCache:
    """
    Get or create the singleton autocomplete cache.

    Thread-safe singleton access using double-checked locking pattern.

    Returns:
        AutocompleteCache instance
    """
    global _autocomplete_cache
    if _autocomplete_cache is None:
        with _autocomplete_cache_lock:
            if _autocomplete_cache is None:
                _autocomplete_cache = AutocompleteCache()
    return _autocomplete_cache
