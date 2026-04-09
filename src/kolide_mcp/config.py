"""Centralized server configuration read from environment variables."""

import os
from dataclasses import dataclass, field


def _parse_origins(raw: str) -> list[str]:
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


@dataclass
class ServerConfig:
    # Network
    host: str = field(default_factory=lambda: os.getenv("MCP_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("MCP_PORT", "8000")))
    # MCP_DEBUG enables Starlette debug mode, which renders an interactive Python
    # debugger in HTTP error responses. Only enable in local development.
    debug: bool = field(
        default_factory=lambda: os.getenv("MCP_DEBUG", "false").lower() == "true"
    )

    # Auth — required at startup (see server.py)
    auth_token: str | None = field(
        default_factory=lambda: os.getenv("MCP_AUTH_TOKEN")
    )

    # CORS — comma-separated list of allowed origins.
    # MCP clients such as Claude Desktop are native apps and do not trigger CORS.
    # Add browser-based client origins here as needed.
    cors_allowed_origins: list[str] = field(
        default_factory=lambda: _parse_origins(
            os.getenv("MCP_CORS_ALLOWED_ORIGINS", "http://localhost,http://127.0.0.1")
        )
    )

    # Enrichment cap — maximum number of records that enrich_device_owner will
    # process in a single call to prevent runaway upstream API usage.
    max_enrich_records: int = field(
        default_factory=lambda: int(os.getenv("MCP_MAX_ENRICH_RECORDS", "500"))
    )

    # Logging — write structured JSON logs to this file path in addition to stdout.
    # If unset, logs go to stdout only.
    log_file: str | None = field(default_factory=lambda: os.getenv("MCP_LOG_FILE"))
