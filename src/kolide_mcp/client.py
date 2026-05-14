"""Kolide K2 API client wrapper."""

import os
from typing import Any

import httpx
from dotenv import load_dotenv

from .api_version import get_kolide_api_version

try:
    from kolide_mcp._main_sha import MAIN_SHA
except ImportError:
    MAIN_SHA = "unknown"

PRODUCT_NAME = "1Password-Device-Trust-MCP-Client"


def _build_user_agent(main_sha: str = MAIN_SHA) -> str:
    """Build the User-Agent header value.

    Resolved at build time by ``hatch_build.py``:

    * ``<product>/sha:<short-sha>`` — official build from canonical upstream;
      short SHA is the first 9 chars of ``origin/main``.
    * ``<product>/fork`` — built from a non-upstream ``origin`` remote.
    * ``<product>`` — no SHA available (e.g. installed from a source tarball
      with no git metadata).
    """
    sha = (main_sha or "").strip()
    if not sha or sha == "unknown":
        return PRODUCT_NAME
    if sha == "fork":
        return f"{PRODUCT_NAME}/fork"
    return f"{PRODUCT_NAME}/{sha[:9]}"


class KolideAPIError(Exception):
    """Exception raised for Kolide API errors."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Kolide API error ({status_code}): {message}")


class KolideClient:
    """Async HTTP client for the Kolide K2 API.

    Uses a persistent ``httpx.AsyncClient`` for connection pooling.
    Call :meth:`close` (or use the Starlette lifespan) to release
    connections when the server shuts down.
    """

    DEFAULT_BASE_URL = "https://api.kolide.com"
    USER_AGENT = _build_user_agent()

    def __init__(self) -> None:
        load_dotenv(override=True)
        self.base_url = os.getenv("KOLIDE_API_URL", self.DEFAULT_BASE_URL)
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    def _get_headers(self) -> dict[str, str]:
        api_key = os.getenv("KOLIDE_API_KEY")
        if not api_key:
            raise KolideAPIError(401, "KOLIDE_API_KEY environment variable not set")
        try:
            api_version = get_kolide_api_version()
        except ValueError as exc:
            # Re-surface invalid KOLIDE_API_VERSION as a Kolide-style error so it
            # flows through the same handling as other upstream failures instead
            # of bubbling up as a raw ValueError from the hot request path.
            raise KolideAPIError(500, str(exc)) from exc
        return {
            "Authorization": f"Bearer {api_key}",
            "x-kolide-api-version": api_version,
            "User-Agent": self.USER_AGENT,
            "Content-Type": "application/json",
        }

    async def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_data: Any = None,
    ) -> dict[str, Any]:
        """Make an authenticated API request to the Kolide REST API."""
        if params:
            params = {k: v for k, v in params.items() if v is not None}

        response = await self._http.request(
            method=method,
            url=path,
            headers=self._get_headers(),
            params=params,
            json=json_data,
            timeout=30.0,
        )

        if response.status_code >= 400:
            try:
                body = response.json()
                message = (
                    body.get("message")
                    or body.get("error")
                    or f"HTTP {response.status_code}"
                )
            except Exception:
                message = f"HTTP {response.status_code}"
            raise KolideAPIError(response.status_code, message)

        if response.status_code == 204:
            return {"success": True}

        return response.json()

    async def close(self) -> None:
        """Shut down the underlying HTTP connection pool."""
        await self._http.aclose()
