"""Minimal smoke checks so CI can validate imports after dependency bumps."""

from __future__ import annotations

import unittest


class SmokeImportTests(unittest.TestCase):
    def test_import_server_without_side_effects(self) -> None:
        import kolide_mcp.server  # noqa: F401 — import side-effect registers MCP server


if __name__ == "__main__":
    unittest.main()
