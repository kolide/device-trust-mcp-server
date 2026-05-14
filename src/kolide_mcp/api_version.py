"""Kolide REST API version sent on every request as ``X-Kolide-Api-Version``.

Kolide publishes multiple dated API versions; this server supports a fixed set.
See https://www.kolide.com/docs/developers/api (Developers → API) and ``openapi/openapi*.json`` snapshots.
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

# Tuple order: older first, current Kolide default last (per public API docs).
SUPPORTED_KOLIDE_API_VERSIONS: tuple[str, ...] = ("2023-05-26", "2026-04-07")

# Default follows Kolide’s current documented API line (`2026-04-07`). Override with
# KOLIDE_API_VERSION=2023-05-26 if you need the older spec.
DEFAULT_KOLIDE_API_VERSION: str = "2026-04-07"


@lru_cache(maxsize=1)
def get_kolide_api_version() -> str:
    """Return the API version string from ``KOLIDE_API_VERSION`` after validation.

    Loads ``.env`` from the current working directory (same as the rest of the app)
    so you can set the version in a ``.env`` file next to your config. The
    resolved value is memoized for the process lifetime so hot paths (every
    upstream HTTP request, ``list_tools``, ``call_tool``) do not repeatedly
    parse ``.env`` from disk. Call :func:`refresh_kolide_api_version` to
    invalidate the cache if the environment changes at runtime.
    """
    load_dotenv(override=True)
    raw = os.getenv("KOLIDE_API_VERSION", DEFAULT_KOLIDE_API_VERSION).strip()
    if raw not in SUPPORTED_KOLIDE_API_VERSIONS:
        allowed = ", ".join(repr(v) for v in SUPPORTED_KOLIDE_API_VERSIONS)
        raise ValueError(
            f"KOLIDE_API_VERSION must be one of ({allowed}), not {raw!r}"
        )
    return raw


def refresh_kolide_api_version() -> str:
    """Invalidate the cached API version and re-resolve it from the environment."""
    get_kolide_api_version.cache_clear()
    return get_kolide_api_version()
