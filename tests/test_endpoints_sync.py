"""Tests for the endpoint-registry reconciler in ``scripts/sync_endpoints.py``.

These lock down (a) the pure spec-parsing helpers, (b) the version-gating maths, and
(c) the surgical source edits — every reconciliation must leave ``endpoints.py`` as
valid Python whose ``EndpointSpec`` values match what the specs describe. Everything
runs against in-memory fixture specs; there is no network access and no committed
OpenAPI snapshot to read.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import sync_endpoints as se  # noqa: E402
from kolide_mcp.endpoints import ENDPOINTS as RUNTIME_SPECS  # noqa: E402

SUPPORTED = ("2023-05-26", "2026-04-07")


def _query_param(fields: list[str]) -> dict:
    """A ``query`` parameter whose examples encode *fields* (as the live specs do)."""
    examples = {}
    for f in fields:
        examples[f"{f}~"] = {"value": f"{f}~x"}
        examples[f"{f}:"] = {"value": f"{f}:x"}
    return {"in": "query", "name": "query", "examples": examples}


def _spec_from_registry(*, fields_by_name=None, extra_ops=(), drop_names=()) -> dict:
    """Build a minimal OpenAPI spec whose paths mirror the current registry.

    ``fields_by_name`` overrides searchable fields per endpoint name; ``extra_ops``
    adds ``(method, raw_path, [fields], paginated)`` tuples; ``drop_names`` omits
    endpoints so we can simulate an operation missing from a version.
    """
    fields_by_name = fields_by_name or {}
    paths: dict[str, dict] = {}
    for spec in RUNTIME_SPECS:
        if spec.name in drop_names:
            continue
        item = paths.setdefault(spec.path, {})
        params = []
        if spec.paginated:
            params.append({"in": "query", "name": "cursor"})
            params.append({"in": "query", "name": "per_page"})
        fields = fields_by_name.get(spec.name, spec.searchable_fields)
        if fields:
            params.append(_query_param(fields))
        item[spec.method.lower()] = {"parameters": params}
    for method, raw_path, fields, paginated, *rest in extra_ops:
        item = paths.setdefault(raw_path, {})
        params = []
        if paginated:
            params += [{"in": "query", "name": "cursor"}, {"in": "query", "name": "per_page"}]
        if fields:
            params.append(_query_param(fields))
        op = {"parameters": params}
        if rest and rest[0]:
            op["summary"] = rest[0]
        item[method.lower()] = op
    return {"openapi": "3.0.0", "info": {"version": "test"}, "paths": paths}


def _reconcile_with(specs_by_version):
    ops = se.collect_operations(specs_by_version, SUPPORTED)
    source = se.ENDPOINTS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    nodes = se.parse_spec_nodes(tree)
    return se.reconcile(source, tree, nodes, RUNTIME_SPECS, ops, SUPPORTED)


def _load_endpoints_from_source(source: str):
    """Import a modified endpoints.py in isolation and return its ENDPOINTS list."""
    path = Path(se.ENDPOINTS_PATH)
    tmp = path.with_name("_endpoints_under_test.py")
    tmp.write_text(source, encoding="utf-8")
    try:
        spec = importlib.util.spec_from_file_location(
            "kolide_mcp._endpoints_under_test", tmp
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.ENDPOINTS
    finally:
        tmp.unlink(missing_ok=True)


class SpecParsingTests(unittest.TestCase):
    def test_normalize_path(self):
        self.assertEqual(se.normalize_path("/devices/{id}"), "/devices/{}")
        self.assertEqual(
            se.normalize_path("/device_groups/{gid}/memberships/{id}"),
            "/device_groups/{}/memberships/{}",
        )

    def test_extract_searchable_fields_strips_operators(self):
        op = {
            "parameters": [
                {
                    "in": "query",
                    "name": "query",
                    "examples": {"name~": {}, "name:": {}, "registered_at>": {}},
                }
            ]
        }
        self.assertEqual(se.extract_searchable_fields(op), ["name", "registered_at"])

    def test_extract_searchable_fields_none_when_absent(self):
        self.assertIsNone(se.extract_searchable_fields({"parameters": []}))

    def test_paginated_detection(self):
        self.assertTrue(
            se.operation_is_paginated(
                {"parameters": [{"in": "query", "name": "per_page"}]}
            )
        )
        self.assertFalse(se.operation_is_paginated({"parameters": []}))

    def test_collect_operations_records_versions_and_skips_put_alias(self):
        spec = {
            "openapi": "3.0.0",
            "info": {"version": "test"},
            "paths": {"/x/{id}": {"patch": {}, "put": {}}},
        }
        ops = se.collect_operations({"2026-04-07": spec}, SUPPORTED)
        self.assertIn(("PATCH", "/x/{}"), ops)
        self.assertNotIn(("PUT", "/x/{}"), ops)
        self.assertEqual(ops[("PATCH", "/x/{}")].versions, {"2026-04-07"})


class GatingTests(unittest.TestCase):
    def _op(self, versions):
        info = se.OperationInfo("GET", "/x", "/x")
        info.versions = set(versions)
        return info

    def test_gate_none_when_in_all_versions(self):
        self.assertIsNone(self._op(SUPPORTED).api_versions_gate(SUPPORTED))

    def test_gate_subset_when_missing_from_a_version(self):
        self.assertEqual(
            self._op({"2023-05-26"}).api_versions_gate(SUPPORTED),
            frozenset({"2023-05-26"}),
        )


class ReconcileTests(unittest.TestCase):
    def _both(self, **kw):
        spec = _spec_from_registry(**kw)
        return {"2023-05-26": spec, "2026-04-07": spec}

    def test_no_drift_is_a_noop(self):
        source = se.ENDPOINTS_PATH.read_text(encoding="utf-8")
        updated, report = _reconcile_with(self._both())
        self.assertEqual(updated, source)
        self.assertFalse(report.auto_applied)
        self.assertFalse(report.needs_human)

    def test_version_gating_is_inserted_when_op_missing_from_newer_version(self):
        specs = {
            "2023-05-26": _spec_from_registry(),
            "2026-04-07": _spec_from_registry(drop_names={"list_devices"}),
        }
        updated, report = _reconcile_with(specs)
        self.assertTrue(any("kolide_list_devices" in c for c in report.api_version_changes))
        endpoints = _load_endpoints_from_source(updated)
        gated = next(e for e in endpoints if e.name == "list_devices")
        self.assertEqual(gated.api_versions, frozenset({"2023-05-26"}))
        self.assertIsNone(next(e for e in endpoints if e.name == "list_people").api_versions)

    def test_searchable_fields_inline_rewrite(self):
        updated, report = _reconcile_with(
            self._both(
                fields_by_name={
                    "list_audit_logs": ["timestamp", "actor_name", "description", "new_field"]
                }
            )
        )
        self.assertTrue(report.searchable_changes)
        endpoints = _load_endpoints_from_source(updated)
        changed = next(e for e in endpoints if e.name == "list_audit_logs")
        self.assertIn("new_field", changed.searchable_fields)

    def test_shared_constant_drift_is_reported_not_rewritten(self):
        updated, report = _reconcile_with(
            self._both(fields_by_name={"list_devices": ["id", "totally_new"]})
        )
        self.assertTrue(report.searchable_constant_drift)
        self.assertFalse(report.searchable_changes)
        endpoints = _load_endpoints_from_source(updated)
        dev = next(e for e in endpoints if e.name == "list_devices")
        self.assertNotIn("totally_new", dev.searchable_fields)

    def test_new_operation_is_scaffolded_and_parseable(self):
        specs = {
            "2023-05-26": _spec_from_registry(),
            "2026-04-07": _spec_from_registry(
                extra_ops=[("GET", "/widgets", ["color"], True, "Fetch a list of Widgets")]
            ),
        }
        updated, report = _reconcile_with(specs)
        self.assertTrue(report.new_operations)
        endpoints = _load_endpoints_from_source(updated)
        widget = next(e for e in endpoints if e.path == "/widgets")
        self.assertEqual(widget.method, "GET")
        self.assertEqual(widget.api_versions, frozenset({"2026-04-07"}))
        self.assertTrue(widget.paginated)
        self.assertEqual(widget.searchable_fields, ["color"])
        # The scaffold's description comes from the spec operation summary.
        self.assertEqual(widget.description, "Fetch a list of Widgets")

    def test_scaffold_falls_back_to_todo_without_summary(self):
        specs = {
            "2023-05-26": _spec_from_registry(),
            "2026-04-07": _spec_from_registry(extra_ops=[("GET", "/gadgets", None, False)]),
        }
        updated, _report = _reconcile_with(specs)
        gadget = next(e for e in _load_endpoints_from_source(updated) if e.path == "/gadgets")
        self.assertIn("TODO", gadget.description)

    def test_removed_operation_is_reported_never_deleted(self):
        updated, report = _reconcile_with(self._both(drop_names={"whoami"}))
        self.assertTrue(any("whoami" in r for r in report.removed_operations))
        endpoints = _load_endpoints_from_source(updated)
        self.assertTrue(any(e.name == "whoami" for e in endpoints))


if __name__ == "__main__":
    unittest.main()
