"""Structured JSON logging setup for the Kolide MCP server."""

import json
import logging
import sys
from datetime import datetime, timezone


class StructuredFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "extra", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload)


def setup_logging(log_file: str | None = None) -> logging.Logger:
    """Configure and return the kolide_mcp logger.

    Logs are written to stderr (so they don't corrupt the JSON-RPC channel
    when running under stdio transport). If log_file is provided, logs are
    also written to that file path. Both handlers use structured JSON format.
    """
    logger = logging.getLogger("kolide_mcp")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = StructuredFormatter()

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
