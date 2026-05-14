"""Ensure MCP :class:`~kolide_mcp.endpoints.EndpointSpec` entries match OpenAPI snapshots.

The OpenAPI JSON files are the canonical REST contract; ``ENDPOINTS`` is the implementation
checklist. Each supported Kolide API version has a matching snapshot under ``openapi/``.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from kolide_mcp.api_version import SUPPORTED_KOLIDE_API_VERSIONS
from kolide_mcp.endpoints import ENDPOINTS, endpoint_available_for_api_version

# Intentional gaps between the OpenAPI contract and MCP tools, keyed by API
# version so allowlist entries only suppress drift for the snapshot they were
# observed in (prefer adding an EndpointSpec instead). Example:
# ``{"2026-04-07": frozenset({("POST", "/new/path/{}/segment")})}``.
OPENAPI_OPERATIONS_WITHOUT_MCP_TOOL: dict[str, frozenset[tuple[str, str]]] = {
    version: frozenset() for version in SUPPORTED_KOLIDE_API_VERSIONS
}


def _normalize_path_template(path: str) -> str:
    """Map equivalent path templates to one string (dynamic segments become ``{}``)."""
    parts: list[str] = []
    for segment in path.strip("/").split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            parts.append("{}")
        else:
            parts.append(segment)
    return "/" + "/".join(parts) if parts else "/"


def _operations_from_openapi(spec: dict) -> set[tuple[str, str]]:
    """Return ``(METHOD, normalized_path)`` for each HTTP operation in the spec."""
    operations: set[tuple[str, str]] = set()
    for raw_path, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        normalized = _normalize_path_template(raw_path)
        for method in ("get", "post", "put", "patch", "delete"):
            if method in path_item:
                operations.add((method.upper(), normalized))
    # OpenAPI lists PUT alongside PATCH for some resources; MCP implements PATCH only.
    for method, path in list(operations):
        if method == "PUT" and ("PATCH", path) in operations:
            operations.discard((method, path))
    return operations


def _operations_from_endpoints_for_version(api_version: str) -> set[tuple[str, str]]:
    """Operations implemented by MCP tools that are valid for *api_version*."""
    ops: set[tuple[str, str]] = set()
    for spec in ENDPOINTS:
        if not endpoint_available_for_api_version(spec, api_version):
            continue
        ops.add((spec.method, _normalize_path_template(spec.path)))
    return ops


class OpenapiDriftTests(unittest.TestCase):
    def test_mcp_endpoints_are_in_openapi_for_all_supported_versions(self) -> None:
        """Every MCP tool must exist in each supported OpenAPI snapshot file."""
        root = Path(__file__).resolve().parent.parent
        for version in SUPPORTED_KOLIDE_API_VERSIONS:
            mcp_ops = _operations_from_endpoints_for_version(version)
            path = root / "openapi" / f"openapi{version}.json"
            self.assertTrue(
                path.is_file(),
                f"Missing OpenAPI snapshot for supported version {version!r}: {path}",
            )
            spec = json.loads(path.read_text(encoding="utf-8"))
            openapi_ops = _operations_from_openapi(spec)
            missing = sorted(mcp_ops - openapi_ops)
            self.assertEqual(
                missing,
                [],
                f"MCP operations for API {version} missing from openapi snapshot:\n"
                + "\n".join(f"  {m} {p}" for m, p in missing),
            )

    def test_openapi_operations_are_in_mcp_or_allowlisted_for_all_versions(self) -> None:
        """Each OpenAPI operation must be implemented or allowlisted, for every snapshot."""
        root = Path(__file__).resolve().parent.parent
        for version in SUPPORTED_KOLIDE_API_VERSIONS:
            mcp_ops = _operations_from_endpoints_for_version(version)
            path = root / "openapi" / f"openapi{version}.json"
            self.assertTrue(
                path.is_file(),
                f"Missing OpenAPI snapshot for supported version {version!r}: {path}",
            )
            spec = json.loads(path.read_text(encoding="utf-8"))
            openapi_ops = _operations_from_openapi(spec)
            allowlist = OPENAPI_OPERATIONS_WITHOUT_MCP_TOOL.get(version, frozenset())
            extra = sorted(openapi_ops - mcp_ops - allowlist)
            self.assertEqual(
                extra,
                [],
                f"OpenAPI {version} exposes operations with no MCP tool:\n"
                + "\n".join(f"  {m} {p}" for m, p in extra),
            )


if __name__ == "__main__":
    unittest.main()
