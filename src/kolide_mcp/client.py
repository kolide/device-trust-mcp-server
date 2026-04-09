"""Kolide K2 API client wrapper."""

import os
from typing import Any

import httpx
from dotenv import load_dotenv


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
    API_VERSION = "2023-05-26"

    def __init__(self) -> None:
        load_dotenv(override=True)
        self.base_url = os.getenv("KOLIDE_API_URL", self.DEFAULT_BASE_URL)
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    def _get_headers(self) -> dict[str, str]:
        api_key = os.getenv("KOLIDE_API_KEY")
        if not api_key:
            raise KolideAPIError(401, "KOLIDE_API_KEY environment variable not set")
        return {
            "Authorization": f"Bearer {api_key}",
            "x-kolide-api-version": self.API_VERSION,
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
