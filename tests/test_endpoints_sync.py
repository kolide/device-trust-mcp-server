"""Tests for the endpoint-registry reconciler in ``scripts/sync_endpoints.py``.

These lock down (a) the pure spec-parsing helpers, (b) the version-gating maths,
(c) the surgical source edits — every reconciliation must leave ``endpoints.py`` as
valid Python whose ``EndpointSpec`` values match what the specs describe — and (d) the
CI plumbing, where a crash or a report that needs a human must never look like a clean
run. Everything runs against in-memory fixture specs; there is no network access and no
committed OpenAPI snapshot to read.
"""

from __future__ import annotations

import ast
import contextlib
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

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


def _spec_from_registry(
    *, version=None, fields_by_name=None, extra_ops=(), drop_names=()
) -> dict:
    """Build a minimal OpenAPI spec whose paths mirror the current registry.

    ``version`` restricts the spec to the operations that version exposes, honouring
    each ``EndpointSpec.api_versions`` gate — without it, a spec shared across versions
    claims every gated endpoint is in every version and the registry looks like drift.
    ``fields_by_name`` overrides searchable fields per endpoint name; ``extra_ops``
    adds ``(method, raw_path, [fields], paginated)`` tuples; ``drop_names`` omits
    endpoints so we can simulate an operation missing from a version.
    """
    fields_by_name = fields_by_name or {}
    paths: dict[str, dict] = {}
    for spec in RUNTIME_SPECS:
        if spec.name in drop_names:
            continue
        gate = spec.api_versions
        if version is not None and gate and version not in gate:
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
    return {
        "openapi": "3.0.0",
        "info": {"version": version or "test"},
        "paths": paths,
    }


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
        return {v: _spec_from_registry(version=v, **kw) for v in SUPPORTED}

    def test_no_drift_is_a_noop(self):
        source = se.ENDPOINTS_PATH.read_text(encoding="utf-8")
        updated, report = _reconcile_with(self._both())
        self.assertEqual(updated, source)
        self.assertFalse(report.auto_applied)
        self.assertFalse(report.needs_human)

    def test_version_gating_is_inserted_when_op_missing_from_newer_version(self):
        specs = {
            "2023-05-26": _spec_from_registry(version="2023-05-26"),
            "2026-04-07": _spec_from_registry(
                version="2026-04-07", drop_names={"list_devices"}
            ),
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
            "2023-05-26": _spec_from_registry(version="2023-05-26"),
            "2026-04-07": _spec_from_registry(
                version="2026-04-07",
                extra_ops=[("GET", "/widgets", ["color"], True, "Fetch a list of Widgets")],
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
            "2023-05-26": _spec_from_registry(version="2023-05-26"),
            "2026-04-07": _spec_from_registry(
                version="2026-04-07", extra_ops=[("GET", "/gadgets", None, False)]
            ),
        }
        updated, _report = _reconcile_with(specs)
        gadget = next(e for e in _load_endpoints_from_source(updated) if e.path == "/gadgets")
        self.assertIn("TODO", gadget.description)

    def test_removed_operation_is_reported_never_deleted(self):
        updated, report = _reconcile_with(self._both(drop_names={"whoami"}))
        self.assertTrue(any("whoami" in r for r in report.removed_operations))
        endpoints = _load_endpoints_from_source(updated)
        self.assertTrue(any(e.name == "whoami" for e in endpoints))


# A registry entry written without a trailing comma after its last keyword argument, and
# an ENDPOINTS list whose last element has no trailing comma either. Both insertion
# points used to search for the next "," with no upper bound, which would splice the new
# text in after the comma inside TRAILING and leave unparseable source behind.
_SOURCE_WITHOUT_TRAILING_COMMAS = '''\
ENDPOINTS = [
    EndpointSpec(
        name="a",
        description="first",
        method="GET",
        path="/a"
    )
]

TRAILING = ("this", "tuple", "has", "commas")
'''


class TrailingCommaTests(unittest.TestCase):
    """Surgical edits must survive registry entries with no trailing commas."""

    def _reconcile(self, source, ops):
        tree = ast.parse(source)
        nodes = se.parse_spec_nodes(tree)
        runtime = [
            types.SimpleNamespace(
                name="a",
                api_versions=None,
                paginated=False,
                searchable_fields=None,
                params=None,
            )
        ]
        return se.reconcile(source, tree, nodes, runtime, ops, SUPPORTED)

    def _op(self, method, path, versions, summary=""):
        info = se.OperationInfo(method, se.normalize_path(path), path)
        info.versions = set(versions)
        info.summary = summary
        return info

    def test_keyword_insert_adds_the_missing_comma(self):
        ops = {("GET", "/a"): self._op("GET", "/a", {"2023-05-26"})}
        updated, report = self._reconcile(_SOURCE_WITHOUT_TRAILING_COMMAS, ops)
        ast.parse(updated)  # must not raise
        self.assertTrue(report.api_version_changes)
        self.assertIn('path="/a",\n        api_versions=', updated)
        self.assertIn('TRAILING = ("this", "tuple", "has", "commas")', updated)

    def test_scaffold_insert_adds_the_missing_comma(self):
        ops = {
            ("GET", "/a"): self._op("GET", "/a", SUPPORTED),
            ("GET", "/b"): self._op("GET", "/b", SUPPORTED, "Scaffolded"),
        }
        updated, report = self._reconcile(_SOURCE_WITHOUT_TRAILING_COMMAS, ops)
        ast.parse(updated)  # must not raise
        self.assertTrue(report.new_operations)
        self.assertIn('path="/b",', updated)
        self.assertIn('TRAILING = ("this", "tuple", "has", "commas")', updated)


class SpecIndexTests(unittest.TestCase):
    """``GET /openapi_specifications`` is how published versions are discovered."""

    def _index(self, payload, base_url="https://api.kolide.com"):
        with mock.patch.object(se, "_get_json", return_value=payload):
            return se.fetch_spec_index(base_url)

    def test_maps_each_version_to_its_advertised_spec_url(self):
        index = self._index(
            {
                "data": [
                    {
                        "version": "2023-05-26",
                        "spec_url": "https://api.kolide.com/openapi_specifications/2023-05-26",
                    },
                    {
                        "version": "2026-04-07",
                        "spec_url": "https://api.kolide.com/openapi_specifications/2026-04-07",
                    },
                ]
            }
        )
        self.assertEqual(sorted(index), ["2023-05-26", "2026-04-07"])
        self.assertEqual(
            index["2026-04-07"],
            "https://api.kolide.com/openapi_specifications/2026-04-07",
        )

    def test_spec_url_pointing_off_host_is_rebuilt_from_the_base_url(self):
        # An override must never be silently redirected to the production spec.
        index = self._index(
            {
                "data": [
                    {
                        "version": "2026-04-07",
                        "spec_url": "https://api.kolide.com/openapi_specifications/2026-04-07",
                    }
                ]
            },
            base_url="https://api.example.test",
        )
        self.assertEqual(
            index["2026-04-07"],
            "https://api.example.test/openapi_specifications/2026-04-07",
        )

    def test_rejects_a_payload_without_published_specs(self):
        with self.assertRaises(ValueError):
            self._index({"data": []})
        with self.assertRaises(ValueError):
            self._index({"specs": []})


class SummaryTests(unittest.TestCase):
    def test_clean_run_says_so(self):
        summary = se.build_summary(se.Report(), changed=False)
        self.assertIn("already mirrors the published specs", summary)

    def test_needs_human_without_a_diff_says_no_pr_carries_it(self):
        report = se.Report(searchable_constant_drift=["kolide_list_devices: ..."])
        summary = se.build_summary(report, changed=False)
        self.assertIn("no pull request carries this", summary)
        self.assertIn("Shared `_*_FIELDS` constant differs from spec", summary)

    def test_drift_found_but_not_applied_is_not_reported_as_reconciled(self):
        report = se.Report(new_operations=["GET /widgets (versions: 2026-04-07)"])
        summary = se.build_summary(report, changed=False)
        self.assertIn("not applied", summary)
        self.assertNotIn("already mirrors", summary)


class FailureModeTests(unittest.TestCase):
    """Nothing about a failed run may look like a clean one."""

    def _run_main(self, argv, index=None, reconcile=None):
        """Run ``main()`` with the network stubbed out, capturing its side effects."""
        specs = {v: _spec_from_registry(version=v) for v in SUPPORTED}
        index = index or {
            v: f"https://api.kolide.com/openapi_specifications/{v}" for v in SUPPORTED
        }
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "GITHUB_STEP_SUMMARY": str(Path(tmp) / "step-summary.md"),
                "GITHUB_OUTPUT": str(Path(tmp) / "outputs.txt"),
                "SYNC_SUMMARY_PATH": str(Path(tmp) / "body.md"),
            }
            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.dict(os.environ, env))
                stack.enter_context(
                    mock.patch.object(sys, "argv", ["sync_endpoints.py", *argv])
                )
                stack.enter_context(
                    mock.patch.object(se, "fetch_spec_index", return_value=index)
                )
                stack.enter_context(
                    mock.patch.object(se, "load_specs", return_value=(specs, False))
                )
                if reconcile is not None:
                    stack.enter_context(mock.patch.object(se, "reconcile", reconcile))
                code = se.main()
            return code, {
                key: Path(path).read_text(encoding="utf-8")
                if Path(path).exists()
                else None
                for key, path in env.items()
            }

    def test_unexpected_exception_exits_2_not_1(self):
        def boom(*_args, **_kwargs):
            raise ValueError("mangled source")

        # 1 means "registry updated", which the workflow treats as success; a crash has
        # to be distinguishable from it.
        code, files = self._run_main([], reconcile=boom)
        self.assertEqual(code, 2)
        self.assertIn("unexpected exception", files["GITHUB_STEP_SUMMARY"])
        self.assertIn("mangled source", files["GITHUB_STEP_SUMMARY"])
        # No outputs, so the workflow's guard step fails the job as well.
        self.assertIsNone(files["GITHUB_OUTPUT"])

    def test_clean_run_still_writes_the_job_summary(self):
        code, files = self._run_main(["--check"])
        self.assertEqual(code, 0)
        self.assertIn("Endpoint registry sync", files["GITHUB_STEP_SUMMARY"])
        self.assertIn("changed=false", files["GITHUB_OUTPUT"])
        self.assertIn("needs_human=false", files["GITHUB_OUTPUT"])

    def test_unsupported_published_version_needs_a_human(self):
        index = {
            **{
                v: f"https://api.kolide.com/openapi_specifications/{v}"
                for v in SUPPORTED
            },
            "2099-01-01": "https://api.kolide.com/openapi_specifications/2099-01-01",
        }
        code, files = self._run_main(["--check"], index=index)
        self.assertEqual(code, 3)
        self.assertIn("needs_human=true", files["GITHUB_OUTPUT"])
        self.assertIn("2099-01-01", files["GITHUB_STEP_SUMMARY"])
        self.assertIn("SUPPORTED_KOLIDE_API_VERSIONS", files["GITHUB_STEP_SUMMARY"])


if __name__ == "__main__":
    unittest.main()
