"""Declarative endpoint registry and tool builder for the Kolide MCP server."""

import re
from dataclasses import dataclass, field
from typing import Any, Iterator

from mcp.types import Tool

from .api_version import SUPPORTED_KOLIDE_API_VERSIONS


# ===== Data Structures =====


@dataclass
class Param:
    """A non-path parameter for an API endpoint (body param or extra tool input)."""

    name: str
    description: str
    type: str = "string"
    required: bool = False
    items_type: str | None = None


@dataclass
class EndpointSpec:
    """Declarative specification for a single API endpoint exposed as an MCP tool.

    The tool name is derived as ``kolide_{name}``.  Path parameters are
    auto-detected from ``{placeholders}`` in *path* and always treated as
    required string inputs.  Pagination (cursor / per_page) is added when
    *paginated* is True.  A search *query* input with full syntax documentation
    is added when *searchable_fields* is non-empty.
    """

    name: str
    description: str
    method: str
    path: str
    paginated: bool = False
    searchable_fields: list[str] | None = None
    search_examples: list[str] | None = None
    params: list[Param] = field(default_factory=list)
    body_param: str | None = None
    #: If ``None``, this tool is exposed for every supported Kolide API version.
    #: If set, the tool is listed and callable only when ``KOLIDE_API_VERSION`` is
    #: one of these dated version strings (e.g. ``frozenset({"2026-04-07"})``).
    api_versions: frozenset[str] | None = None


# ===== Internal Helpers =====

_PATH_PARAM_RE = re.compile(r"\{(\w+)\}")

PATH_PARAM_DESCRIPTIONS: dict[str, str] = {
    "audit_log_id": "The ID of the audit log",
    "auth_log_id": "The ID of the auth log",
    "device_id": "The ID of the device",
    "device_group_id": "The ID of the device group",
    "membership_id": "The ID of the membership to remove",
    "issue_id": "The ID of the issue",
    "person_id": "The ID of the person",
    "person_group_id": "The ID of the person group",
    "check_id": "The ID of the check",
    "campaign_id": "The ID of the campaign",
    "request_id": "The ID of the request",
    "package_id": "The ID of the package",
    "admin_user_id": "The ID of the admin user",
    "table_name": "The name of the reporting table",
    "query_id": "The ID of the report query",
}

# Reusable search-field sets for endpoints that share the same schema.

_DEVICE_FIELDS = [
    "id", "name", "registered_at", "last_authenticated_at",
    "serial", "note", "hardware_uuid", "device_type", "will_block_at",
]
_DEVICE_EXAMPLES = [
    'name~"MacBook"', 'serial:"ABC123"',
    'device_type:"Mac" AND registered_at>"2025-01-01T00:00:00Z"',
]

_ISSUE_FIELDS = [
    "id", "detected_at", "resolved_at", "blocks_device_at", "title",
    "issue_key", "issue_value", "exempted", "check_id", "device_id",
    "last_rechecked_at",
]
_ISSUE_EXAMPLES = [
    'title~"firewall"', 'exempted:false',
    'detected_at>"2025-01-01T00:00:00Z"',
]

_PEOPLE_FIELDS = ["id", "email", "name", "last_authenticated_at"]
_PEOPLE_EXAMPLES = [
    'email~"@example.com"', 'name~"John"',
    'last_authenticated_at>"2025-01-01T00:00:00Z"',
]

_CHECK_RESULT_FIELDS = ["device_display_name", "ran_at", "check_name", "status"]
_CHECK_RESULT_EXAMPLES = [
    'status:"fail"', 'check_name~"encryption"',
    'ran_at>"2025-01-01T00:00:00Z"',
]


# ===== Endpoint Registry =====

ENDPOINTS: list[EndpointSpec] = [
    # --- Organization ---
    EndpointSpec(
        name="whoami",
        description="Fetch information about the organization from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/whoami",
    ),

    # --- Audit Logs ---
    EndpointSpec(
        name="list_audit_logs",
        description="Fetch a list of Audit logs from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/audit_logs",
        paginated=True,
        searchable_fields=["timestamp", "actor_name", "description"],
        search_examples=['actor_name~"john"', 'timestamp>"2025-01-01T00:00:00Z"'],
    ),
    EndpointSpec(
        name="get_audit_log",
        description="Fetch information for a specific Audit log from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/audit_logs/{audit_log_id}",
    ),

    # --- Auth Logs ---
    EndpointSpec(
        name="list_auth_logs",
        description="Fetch a list of Auth log sessions from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/auth_logs",
        paginated=True,
        searchable_fields=[
            "timestamp", "city", "country", "ip_address", "agent_version",
            "browser_name", "person_name", "person_email", "person_id",
            "device_id", "result",
        ],
        search_examples=[
            'person_email~"@example.com"', 'result:"Success"',
            'timestamp>"2025-01-01T00:00:00Z" AND country:"US"',
        ],
    ),
    EndpointSpec(
        name="get_auth_log",
        description="Fetch information for a specific Auth log session from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/auth_logs/{auth_log_id}",
    ),

    # --- Devices ---
    EndpointSpec(
        name="list_devices",
        description="Fetch a list of Devices from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/devices",
        paginated=True,
        searchable_fields=_DEVICE_FIELDS,
        search_examples=_DEVICE_EXAMPLES,
    ),
    EndpointSpec(
        name="get_device",
        description="Fetch information for a specific Device from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/devices/{device_id}",
    ),
    EndpointSpec(
        name="delete_device",
        description="Delete a specific Device from 1Password Device Trust (Kolide K2)",
        method="DELETE",
        path="/devices/{device_id}",
    ),
    EndpointSpec(
        name="get_device_open_issues",
        description="Fetch a list of open Device Trust Issues for a Device from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/devices/{device_id}/open_issues",
        paginated=True,
        searchable_fields=_ISSUE_FIELDS,
        search_examples=_ISSUE_EXAMPLES,
    ),
    EndpointSpec(
        name="update_device_authentication_mode",
        description="Update a Device's authentication mode in 1Password Device Trust (Kolide K2)",
        method="PATCH",
        path="/devices/{device_id}/authentication_mode",
        params=[
            Param("authentication_mode", "The new authentication mode", required=True),
        ],
    ),
    EndpointSpec(
        name="delete_device_registration",
        description="Delete a device registration from 1Password Device Trust (Kolide K2)",
        method="DELETE",
        path="/devices/{device_id}/registration",
    ),
    EndpointSpec(
        name="create_check_refresh",
        description="Create a new Check refresh for a device to re-run Device Trust checks in 1Password Device Trust (Kolide K2)",
        method="POST",
        path="/devices/{device_id}/check_refreshes",
        params=[
            Param("check_ids", "Optional list of specific check IDs to refresh",
                  type="array", items_type="string"),
        ],
    ),
    EndpointSpec(
        name="get_device_check_results",
        description="Fetch a list of Device Trust Check results for a Device from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/devices/{device_id}/check_results",
        paginated=True,
        searchable_fields=_CHECK_RESULT_FIELDS,
        search_examples=_CHECK_RESULT_EXAMPLES,
    ),

    # --- Device Groups ---
    EndpointSpec(
        name="list_device_groups",
        description="Fetch a list of Device groups from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/device_groups",
        paginated=True,
        searchable_fields=["created_at", "name", "description"],
        search_examples=['name~"engineering"', 'created_at>"2025-01-01T00:00:00Z"'],
    ),
    EndpointSpec(
        name="get_device_group",
        description="Fetch information for a specific Device group from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/device_groups/{device_group_id}",
    ),
    EndpointSpec(
        name="list_device_group_devices",
        description="Fetch a list of Devices in a Device group from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/device_groups/{device_group_id}/devices",
        paginated=True,
        searchable_fields=_DEVICE_FIELDS,
        search_examples=[
            'name~"MacBook"', 'device_type:"Mac"',
            'last_authenticated_at>"2025-01-01T00:00:00Z"',
        ],
    ),
    EndpointSpec(
        name="add_device_to_group",
        description="Add a Device to a Device Group in 1Password Device Trust (Kolide K2)",
        method="POST",
        path="/device_groups/{device_group_id}/memberships",
        params=[
            Param("device_id", "The ID of the device to add", required=True),
        ],
    ),
    EndpointSpec(
        name="remove_device_from_group",
        description="Remove a Device from a Device Group in 1Password Device Trust (Kolide K2)",
        method="DELETE",
        path="/device_groups/{device_group_id}/memberships/{membership_id}",
    ),

    # --- Issues ---
    EndpointSpec(
        name="list_issues",
        description="Fetch a list of Device Trust Issues from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/issues",
        paginated=True,
        searchable_fields=_ISSUE_FIELDS,
        search_examples=[
            'title~"firewall"',
            'exempted:false AND detected_at>"2025-01-01T00:00:00Z"',
            'device_id:"12345"',
        ],
    ),
    EndpointSpec(
        name="get_issue",
        description="Fetch information for a specific Device Trust Issue from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/issues/{issue_id}",
    ),

    # --- People ---
    EndpointSpec(
        name="list_people",
        description="Fetch a list of People from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/people",
        paginated=True,
        searchable_fields=_PEOPLE_FIELDS,
        search_examples=_PEOPLE_EXAMPLES,
    ),
    EndpointSpec(
        name="get_person",
        description="Fetch information for a specific Person from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/people/{person_id}",
    ),
    EndpointSpec(
        name="list_person_devices",
        description="Fetch a list of registered Devices for a Person from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/people/{person_id}/registered_devices",
        paginated=True,
        searchable_fields=_DEVICE_FIELDS,
        search_examples=['name~"MacBook"', 'serial:"ABC123"', 'device_type:"Mac"'],
    ),
    EndpointSpec(
        name="list_person_issues",
        description="Fetch a list of open Device Trust Issues for a Person from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/people/{person_id}/open_issues",
        paginated=True,
        searchable_fields=_ISSUE_FIELDS,
        search_examples=_ISSUE_EXAMPLES,
    ),
    EndpointSpec(
        name="list_person_groups_for_person",
        description="Fetch a list of Person groups that a Person belongs to from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/people/{person_id}/person_groups",
        paginated=True,
        searchable_fields=["name"],
        search_examples=['name~"engineering"', 'name:"Security Team"'],
    ),
    EndpointSpec(
        name="list_deprovisioned_people",
        description="Fetch a list of people that have been deprovisioned from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/deprovisioned_people",
        paginated=True,
        searchable_fields=_PEOPLE_FIELDS,
        search_examples=['email~"@example.com"', 'name~"John"'],
    ),

    # --- Person Groups ---
    EndpointSpec(
        name="list_person_groups",
        description="Fetch a list of Person groups from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/person_groups",
        paginated=True,
        searchable_fields=["name"],
        search_examples=['name~"engineering"', 'name:"Security Team"'],
    ),
    EndpointSpec(
        name="get_person_group",
        description="Fetch information for a specific Person group from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/person_groups/{person_group_id}",
    ),
    EndpointSpec(
        name="list_person_group_people",
        description="Fetch a list of People in a Person group from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/person_groups/{person_group_id}/people",
        paginated=True,
        searchable_fields=_PEOPLE_FIELDS,
        search_examples=['email~"@example.com"', 'name~"John"'],
    ),

    # --- Checks ---
    EndpointSpec(
        name="list_checks",
        description="Fetch a list of Device Trust Checks (security/compliance checks) from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/checks",
        paginated=True,
        searchable_fields=[
            "name", "check_description", "check_tag_name",
            "check_tag_description", "check_tag_id", "slug", "type",
        ],
        search_examples=['name~"encryption"', 'type:"blocker"', 'check_tag_name~"macOS"'],
    ),
    EndpointSpec(
        name="get_check",
        description="Fetch information for a specific Device Trust Check from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/checks/{check_id}",
    ),
    EndpointSpec(
        name="get_check_results",
        description="Fetch a list of Device Trust Check results for a specific Check from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/checks/{check_id}/results",
        paginated=True,
        searchable_fields=_CHECK_RESULT_FIELDS,
        search_examples=_CHECK_RESULT_EXAMPLES,
    ),
    EndpointSpec(
        name="get_check_configuration",
        description="Fetch the configuration for a specific Device Trust Check from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/checks/{check_id}/configurations",
    ),
    EndpointSpec(
        name="update_check_configuration",
        description="Update the configuration for a Device Trust Check in 1Password Device Trust (Kolide K2)",
        method="PATCH",
        path="/checks/{check_id}/configurations",
        body_param="configuration",
        params=[
            Param("configuration", "The configuration to update", type="object", required=True),
        ],
    ),
    EndpointSpec(
        name="create_external_check_run",
        description=(
            "Create a new External check run for a Device Trust Check in 1Password "
            "Device Trust (Kolide K2). Pass exactly one of device_id, person_id, or "
            "person_email, and provide check_data per the API."
        ),
        method="POST",
        path="/checks/{check_id}/runs",
        params=[
            Param(
                "device_id",
                "The ID of the device. Use exactly one of device_id, person_id, or person_email.",
                type="integer",
            ),
            Param(
                "person_id",
                "The ID of the person. Use exactly one of device_id, person_id, or person_email.",
                type="integer",
            ),
            Param(
                "person_email",
                "The email of the person. Use exactly one of device_id, person_id, or person_email. "
                "None of the three is marked required at the schema level so the LLM can choose; "
                "the Kolide API enforces that exactly one is provided.",
                type="string",
            ),
            Param(
                "check_data",
                "JSON string for the check result; must include KOLIDE_CHECK_STATUS "
                "(FAIL, PASS, UNKNOWN, INAPPLICABLE, or ERROR). Optional extra metadata allowed.",
                required=True,
            ),
        ],
    ),

    # --- Live Query Campaigns ---
    EndpointSpec(
        name="list_live_query_campaigns",
        description="Fetch a list of Live query campaigns from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/live_query_campaigns",
        paginated=True,
        searchable_fields=["created_at", "name", "published", "tables_used"],
        search_examples=['name~"disk"', 'published:true', 'created_at>"2025-01-01T00:00:00Z"'],
    ),
    EndpointSpec(
        name="get_live_query_campaign",
        description="Fetch information for a specific Live query campaign from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/live_query_campaigns/{campaign_id}",
    ),
    EndpointSpec(
        name="create_live_query_campaign",
        description="Create a new Live query campaign to run an osquery query on devices in 1Password Device Trust (Kolide K2)",
        method="POST",
        path="/live_query_campaigns",
        params=[
            Param("sql", "The osquery SQL query to run", required=True),
            Param("name", "Optional name for the campaign"),
            Param("description", "Optional description"),
            Param("device_ids", "Optional list of device IDs to target",
                  type="array", items_type="string"),
            Param("device_group_ids", "Optional list of device group IDs to target",
                  type="array", items_type="string"),
            Param("target_macs", "Target all macOS devices"),
            Param("target_windows_devices", "Target all Windows devices"),
            Param("target_linux_devices", "Target all Linux devices"),
            Param("target_all_devices", "Target all devices regardless of platform"),
        ],
    ),
    EndpointSpec(
        name="update_live_query_campaign",
        description="Update an existing Live query campaign in 1Password Device Trust (Kolide K2)",
        method="PATCH",
        path="/live_query_campaigns/{campaign_id}",
        params=[
            Param("name", "New name for the campaign"),
            Param("description", "New description"),
        ],
    ),
    EndpointSpec(
        name="delete_live_query_campaign",
        description="Delete a Live query campaign from 1Password Device Trust (Kolide K2)",
        method="DELETE",
        path="/live_query_campaigns/{campaign_id}",
    ),
    EndpointSpec(
        name="get_live_query_results",
        description="Fetch results for a Live query campaign from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/live_query_campaigns/{campaign_id}/query_results",
        paginated=True,
        searchable_fields=["error_message", "warning_message"],
        search_examples=['error_message~"timeout"', 'warning_message~"deprecated"'],
    ),

    # --- Exemption Requests ---
    EndpointSpec(
        name="list_exemption_requests",
        description="Fetch a list of Device Trust Exemption requests from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/exemption_requests",
        paginated=True,
        searchable_fields=["status", "requested_at", "requester_message"],
        search_examples=[
            'status:"pending"', 'requested_at>"2025-01-01T00:00:00Z"',
            'requester_message~"update"',
        ],
    ),
    EndpointSpec(
        name="get_exemption_request",
        description="Fetch information for a specific Device Trust Exemption request from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/exemption_requests/{request_id}",
    ),
    EndpointSpec(
        name="update_exemption_request",
        description="Update a Device Trust Exemption request (approve/deny) in 1Password Device Trust (Kolide K2)",
        method="PATCH",
        path="/exemption_requests/{request_id}",
        params=[
            Param("status", "New status for the request"),
            Param("reviewer_note", "Note from the reviewer"),
        ],
    ),

    # --- Registration Requests ---
    EndpointSpec(
        name="list_registration_requests",
        description="Fetch a list of Device Registration requests from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/registration_requests",
        paginated=True,
        searchable_fields=["status", "requested_at", "requester_message"],
        search_examples=['status:"pending"', 'requested_at>"2025-01-01T00:00:00Z"'],
    ),
    EndpointSpec(
        name="get_registration_request",
        description="Fetch information for a specific Device Registration request from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/registration_requests/{request_id}",
    ),
    EndpointSpec(
        name="update_registration_request",
        description="Update a Device Registration request in 1Password Device Trust (Kolide K2)",
        method="PATCH",
        path="/registration_requests/{request_id}",
        params=[
            Param("status", "New status for the request"),
        ],
    ),

    # --- Packages ---
    EndpointSpec(
        name="list_packages",
        description="Fetch a list of software Packages from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/packages",
        paginated=True,
    ),
    EndpointSpec(
        name="get_package",
        description="Fetch information for a specific software Package from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/packages/{package_id}",
    ),

    # --- Admin Users ---
    EndpointSpec(
        name="list_admin_users",
        description="Fetch a list of Admin users from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/admin_users",
        paginated=True,
        searchable_fields=["first_name", "last_name", "email", "created_at"],
        search_examples=[
            'email~"@example.com"', 'last_name:"Smith"',
            'created_at>"2025-01-01T00:00:00Z"',
        ],
    ),
    EndpointSpec(
        name="get_admin_user",
        description="Fetch information for a specific Admin user from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/admin_users/{admin_user_id}",
    ),

    # --- Reporting Tables ---
    EndpointSpec(
        name="list_reporting_tables",
        description="Fetch a list of Reporting tables available for queries from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/reporting/tables",
        paginated=True,
    ),
    EndpointSpec(
        name="get_reporting_table",
        description="Fetch information for a specific Reporting table from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/reporting/tables/{table_name}",
    ),
    EndpointSpec(
        name="get_table_records",
        description="Fetch records from a Reporting table from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/reporting/tables/{table_name}/table_records",
        paginated=True,
    ),

    # --- Report Queries ---
    EndpointSpec(
        name="list_report_queries",
        description="Fetch a list of saved Report queries from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/reporting/queries",
        paginated=True,
    ),
    EndpointSpec(
        name="get_report_query",
        description="Fetch information for a specific Report query from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/reporting/queries/{query_id}",
    ),
    EndpointSpec(
        name="get_report_query_results",
        description="Fetch results for a Report query from 1Password Device Trust (Kolide K2)",
        method="GET",
        path="/reporting/queries/{query_id}/results",
        paginated=True,
    ),
]

_SUPPORTED_VERSIONS_SET = frozenset(SUPPORTED_KOLIDE_API_VERSIONS)

for _spec in ENDPOINTS:
    if _spec.api_versions is None:
        continue
    _unknown = set(_spec.api_versions) - _SUPPORTED_VERSIONS_SET
    if _unknown:
        raise ValueError(
            f"Endpoint {_spec.name!r} api_versions contains unsupported strings: "
            f"{sorted(_unknown)!r}. Supported: {sorted(_SUPPORTED_VERSIONS_SET)!r}"
        )

ENDPOINT_MAP: dict[str, EndpointSpec] = {
    f"kolide_{spec.name}": spec for spec in ENDPOINTS
}


# ===== Tool Building =====


def get_path_params(path: str) -> list[str]:
    """Extract parameter names from ``{placeholder}`` segments in a URL path."""
    return _PATH_PARAM_RE.findall(path)


def _build_query_description(
    searchable_fields: list[str],
    examples: list[str] | None,
) -> str:
    parts = [
        "Search query to filter results. Syntax: field_name<operator>value.",
        "Operators: ':' (exact match), '~' (substring match), '<' / '>' (datetime comparison).",
        "Quote values containing spaces with double quotes.",
        "Combine clauses with ' AND ' or ' OR '.",
        f"Searchable fields: {', '.join(searchable_fields)}.",
    ]
    if examples:
        parts.append(f"Examples: {', '.join(repr(e) for e in examples)}.")
    return " ".join(parts)


def build_tool(spec: EndpointSpec) -> Tool:
    """Generate an MCP ``Tool`` from a declarative ``EndpointSpec``."""
    properties: dict[str, Any] = {}
    required: list[str] = []

    # Path params -- always required strings
    path_param_names = get_path_params(spec.path)
    explicit_descs = {p.name: p.description for p in spec.params}
    for pname in path_param_names:
        desc = explicit_descs.get(
            pname,
            PATH_PARAM_DESCRIPTIONS.get(pname, f"The {pname.replace('_', ' ')}"),
        )
        properties[pname] = {"type": "string", "description": desc}
        required.append(pname)

    # Pagination
    if spec.paginated:
        properties["cursor"] = {
            "type": "string",
            "description": "Cursor for pagination",
        }
        properties["per_page"] = {
            "type": ["integer", "string"],
            "description": "Number of records per page (1-100)",
            "minimum": 1,
            "maximum": 100,
        }
        properties["fetch_all"] = {
            "type": ["boolean", "string"],
            "description": (
                "Set to true to automatically follow all pagination cursors and "
                "return the complete result set in a single response. Capped at "
                "10,000 records or 50 pages. When using fetch_all, cursor is ignored."
            ),
        }
        properties["fields"] = {
            "type": ["array", "string"],
            "items": {"type": "string"},
            "description": (
                "List of field names to include in each record. "
                "When specified, only these fields are returned per record, "
                "significantly reducing response size for large datasets. "
                "Pass as an array or a comma-separated string. "
                "Example: [\"device_id\", \"device_name\", \"name\"]"
            ),
        }
        properties["enrich_device_owner"] = {
            "type": ["boolean", "string"],
            "description": (
                "Set to true to enrich each record that has a device_id or "
                "device_information field with the device owner's name and email. "
                "Adds owner_name and owner_email fields to matching records."
            ),
        }

    # Search query with per-endpoint documentation
    if spec.searchable_fields:
        properties["query"] = {
            "type": "string",
            "description": _build_query_description(
                spec.searchable_fields, spec.search_examples,
            ),
        }

    # Extra (body / non-path) params
    path_param_set = set(path_param_names)
    for param in spec.params:
        if param.name in path_param_set:
            continue
        prop: dict[str, Any] = {
            "type": param.type,
            "description": param.description,
        }
        if param.type == "array" and param.items_type:
            prop["items"] = {"type": param.items_type}
        properties[param.name] = prop
        if param.required:
            required.append(param.name)

    # Append search hints to the description
    description = spec.description
    if spec.searchable_fields:
        description += ". Use the query parameter to filter results by searchable fields"
    elif spec.paginated:
        description += ". This endpoint does not support search queries"
    if spec.api_versions is not None:
        vers = ", ".join(sorted(spec.api_versions))
        description += f" (Kolide API {vers} only)"

    return Tool(
        name=f"kolide_{spec.name}",
        description=description,
        inputSchema={
            "type": "object",
            "properties": properties,
            "required": required,
        },
    )


def endpoint_available_for_api_version(spec: EndpointSpec, api_version: str) -> bool:
    """Return whether *spec* should be exposed for *api_version*."""
    if spec.api_versions is None:
        return True
    return api_version in spec.api_versions


def iter_endpoints_for_api_version(api_version: str) -> Iterator[EndpointSpec]:
    """Yield endpoint specs that apply to *api_version*."""
    for spec in ENDPOINTS:
        if endpoint_available_for_api_version(spec, api_version):
            yield spec


def build_all_tools(api_version: str | None = None) -> list[Tool]:
    """Build MCP ``Tool`` objects for endpoints valid at *api_version*.

    When *api_version* is ``None`` the currently configured Kolide API version
    (from ``KOLIDE_API_VERSION``) is used. The argument is kept for callers that
    need to build the tool list for a specific version (e.g. tests).
    """
    if api_version is None:
        from .api_version import get_kolide_api_version

        api_version = get_kolide_api_version()
    return [build_tool(spec) for spec in iter_endpoints_for_api_version(api_version)]
