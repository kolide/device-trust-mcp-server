"""Contract tests pinning write-tool request bodies to the published API schema.

``server._dispatch`` builds the JSON body from the ``Param`` names declared in
:data:`kolide_mcp.endpoints.ENDPOINTS` — each non-path param becomes a body key
verbatim. A misnamed or mistyped ``Param`` is therefore a 400 that no tool input
can work around, which is why these names are pinned here rather than left to
review.

The pinned values mirror ``GET /openapi_specifications/{version}`` for both
2023-05-26 and 2026-04-07 (the two agree on every body below). This module is
hermetic; ``scripts/sync_endpoints.py`` does the live comparison and will flag any
divergence from the published specs.

Regression coverage for KS-270: ``kolide_add_device_to_group`` declared a singular
``device_id`` string while the memberships endpoint requires a ``device_ids`` array
of strings, so every invocation returned
``The device_ids parameter is required. (status: 400)``.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kolide_mcp.endpoints import ENDPOINTS, build_tool, get_path_params  # noqa: E402

#: ``{endpoint_name: {param_name: (json_type, items_type_or_None)}}`` as published.
EXPECTED_BODIES: dict[str, dict[str, tuple[str, str | None]]] = {
    "update_device_authentication_mode": {
        "authentication_mode": ("string", None),
    },
    "create_check_refresh": {
        "check_id": ("string", None),
    },
    "add_device_to_group": {
        "device_ids": ("array", "string"),
    },
    "update_check_configuration": {
        "paused": ("boolean", None),
        "block_auth_grace_period_days": ("integer", None),
        "auth_check_run_shelf_life_seconds": ("integer", None),
        "snooze_disallowed": ("boolean", None),
        "exemptions_disallowed": ("boolean", None),
        "targeted_groups": ("array", "string"),
        "excluded_groups": ("array", "string"),
        "blocking_allowed_groups": ("array", "string"),
        "blocking_excluded_groups": ("array", "string"),
        "options": ("string", None),
        "remediation_strategy": ("string", None),
    },
    "create_external_check_run": {
        "device_id": ("integer", None),
        "person_id": ("integer", None),
        "person_email": ("string", None),
        "check_data": ("string", None),
    },
    "create_live_query_campaign": {
        "sql": ("string", None),
        "name": ("string", None),
        "targeted_device_ids": ("array", "integer"),
        "target_all_devices": ("boolean", None),
        "target_macs": ("boolean", None),
        "target_windows_devices": ("boolean", None),
        "target_linux_devices": ("boolean", None),
    },
    "update_live_query_campaign": {
        "name": ("string", None),
        "sql": ("string", None),
        "targeted_device_ids": ("array", "integer"),
        "target_all_devices": ("boolean", None),
        "target_macs": ("boolean", None),
        "target_windows_devices": ("boolean", None),
        "target_linux_devices": ("boolean", None),
    },
    "update_exemption_request": {
        "status": ("string", None),
        "internal_message": ("string", None),
        "denial_explanation": ("string", None),
    },
    "update_registration_request": {
        "status": ("string", None),
        "internal_message": ("string", None),
        "end_user_denial_message": ("string", None),
    },
}

#: Body params the API rejects the request without, as ``{endpoint_name: {param_name}}``.
#:
#: Unlike the names and types above, this is *not* derivable from the published spec:
#: neither version declares a top-level ``required`` list on any of its request body
#: schemas, so ``scripts/sync_endpoints.py`` cannot reconcile this field and must not
#: try. These entries are pinned from observed API behaviour instead — an unmarked
#: required param lets a caller send a schema-valid request that always fails.
REQUIRED_BODY_PARAMS: dict[str, set[str]] = {
    "update_device_authentication_mode": {"authentication_mode"},
    "create_check_refresh": {"check_id"},
    "add_device_to_group": {"device_ids"},
    # A PATCH of a check configuration may carry any subset of its fields.
    "update_check_configuration": set(),
    # device_id / person_id / person_email are deliberately all optional: the API
    # enforces exactly one, which JSON Schema ``required`` cannot express.
    "create_external_check_run": {"check_data"},
    "create_live_query_campaign": {"sql"},
    "update_live_query_campaign": set(),
    "update_exemption_request": set(),
    "update_registration_request": set(),
}

#: Documented properties deliberately not exposed, with the reason.
INTENTIONALLY_UNEXPOSED: dict[str, dict[str, str]] = {
    "update_registration_request": {
        "internal_denial_reason": "deprecated by the API in favour of internal_message",
    },
    "update_device_authentication_mode": {
        "person_group_ids": "not yet surfaced as a tool input",
    },
}

#: Enum-constrained params, so a caller cannot invent a value.
EXPECTED_ENUMS: dict[tuple[str, str], list[str]] = {
    ("update_check_configuration", "remediation_strategy"): [
        "block_immediately",
        "warn_then_block",
        "notify_only",
        "report_only",
    ],
    ("update_exemption_request", "status"): ["approved", "denied"],
    ("update_registration_request", "status"): ["approved", "denied"],
}


def _spec(name: str):
    matches = [e for e in ENDPOINTS if e.name == name]
    assert len(matches) == 1, f"expected exactly one endpoint named {name!r}"
    return matches[0]


def _body_params(spec) -> dict[str, tuple[str, str | None]]:
    """The params ``_dispatch`` would turn into JSON body keys."""
    path_params = set(get_path_params(spec.path))
    return {
        p.name: (p.type, p.items_type)
        for p in spec.params
        if p.name not in path_params
    }


def _required_body_params(spec) -> set[str]:
    """The body params ``build_tool`` marks required in the tool's input schema."""
    path_params = set(get_path_params(spec.path))
    return {
        p.name for p in spec.params if p.required and p.name not in path_params
    }


def _write_endpoints() -> set[str]:
    return {
        e.name
        for e in ENDPOINTS
        if e.method in ("POST", "PATCH", "PUT")
        and not e.body_param
        and _body_params(e)
    }


class RequestBodyContractTests(unittest.TestCase):
    def test_every_write_endpoint_is_pinned(self):
        """A new write tool must be added to EXPECTED_BODIES, not silently shipped."""
        self.assertEqual(_write_endpoints(), set(EXPECTED_BODIES))

    def test_body_params_match_published_schema(self):
        for name, expected in EXPECTED_BODIES.items():
            with self.subTest(endpoint=name):
                self.assertEqual(_body_params(_spec(name)), expected)

    def test_enums_are_declared(self):
        for (name, param_name), values in EXPECTED_ENUMS.items():
            with self.subTest(endpoint=name, param=param_name):
                param = next(
                    p for p in _spec(name).params if p.name == param_name
                )
                self.assertEqual(param.enum, values)
                schema = build_tool(_spec(name)).inputSchema
                self.assertEqual(schema["properties"][param_name]["enum"], values)

    def test_unexposed_properties_are_not_silently_declared(self):
        """The allowlist documents omissions; it must not contradict the registry."""
        for name, omitted in INTENTIONALLY_UNEXPOSED.items():
            declared = _body_params(_spec(name))
            for prop in omitted:
                with self.subTest(endpoint=name, prop=prop):
                    self.assertNotIn(prop, declared)


class RequiredBodyParamTests(unittest.TestCase):
    """A param the API demands must be ``required=True`` in the registry.

    ``Param.required`` defaults to False, so omitting it is silent: the generated
    tool schema accepts a call the API then rejects, and no tool input can recover.
    """

    def test_every_write_endpoint_pins_its_required_params(self):
        """A new write tool must declare its required params here, even if none."""
        self.assertEqual(_write_endpoints(), set(REQUIRED_BODY_PARAMS))

    def test_required_params_match_pin(self):
        for name, expected in REQUIRED_BODY_PARAMS.items():
            with self.subTest(endpoint=name):
                self.assertEqual(_required_body_params(_spec(name)), expected)

    def test_pinned_required_params_are_real_body_params(self):
        """Catches a pin left behind by a renamed or removed param."""
        for name, required in REQUIRED_BODY_PARAMS.items():
            with self.subTest(endpoint=name):
                self.assertLessEqual(required, set(EXPECTED_BODIES[name]))

    def test_tool_schema_requires_path_and_required_body_params(self):
        """``required`` in the input schema is what actually constrains a caller."""
        for name in REQUIRED_BODY_PARAMS:
            spec = _spec(name)
            with self.subTest(endpoint=name):
                self.assertCountEqual(
                    build_tool(spec).inputSchema["required"],
                    list(get_path_params(spec.path)) + sorted(_required_body_params(spec)),
                )

    def test_creates_require_at_least_one_body_param(self):
        """A POST that requires nothing is the create_check_refresh bug class.

        A create with an all-optional body means an empty call is schema-valid, which
        is almost always wrong. PATCH is exempt: a partial update legitimately takes
        any subset of its fields. Add a documented entry here only if the API really
        does accept an empty create body.
        """
        allowed_empty: set[str] = set()
        for name, required in REQUIRED_BODY_PARAMS.items():
            if _spec(name).method != "POST" or name in allowed_empty:
                continue
            with self.subTest(endpoint=name):
                self.assertTrue(
                    required, f"kolide_{name}: POST marks no body param required"
                )


class CheckRefreshRegressionTests(unittest.TestCase):
    """``check_id`` was optional in the registry but is mandatory in practice.

    ``POST /devices/{device_id}/check_refreshes`` with no ``check_id`` answers
    ``404 Not found`` (verified against api.kolide.com), so leaving it optional only
    exposed a call that can never succeed. The published spec is no help here: it
    lists ``check_id`` as a body property but declares no ``required`` list.
    """

    def test_check_id_is_required(self):
        spec = _spec("create_check_refresh")
        param = next(p for p in spec.params if p.name == "check_id")

        self.assertTrue(param.required, "a refresh without check_id 404s")
        self.assertCountEqual(
            build_tool(spec).inputSchema["required"], ["device_id", "check_id"]
        )


class AddDeviceToGroupRegressionTests(unittest.TestCase):
    """KS-270: a singular device_id string can never satisfy the endpoint."""

    def test_sends_device_ids_array(self):
        spec = _spec("add_device_to_group")
        body = _body_params(spec)

        self.assertNotIn("device_id", body, "device_id is rejected with a 400 by the API")
        self.assertEqual(body["device_ids"], ("array", "string"))

        param = next(p for p in spec.params if p.name == "device_ids")
        self.assertTrue(param.required, "the memberships endpoint requires device_ids")

    def test_tool_schema_is_an_array_of_strings(self):
        schema = build_tool(_spec("add_device_to_group")).inputSchema

        self.assertEqual(
            schema["properties"]["device_ids"],
            {
                "type": "array",
                "description": "The IDs of the devices to add to the group",
                "items": {"type": "string"},
            },
        )
        self.assertCountEqual(schema["required"], ["device_group_id", "device_ids"])


if __name__ == "__main__":
    unittest.main()
