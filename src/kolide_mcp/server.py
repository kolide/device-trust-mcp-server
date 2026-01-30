"""1Password Device Trust (Kolide K2) MCP Server with Streamable HTTP transport."""

import json
import os
from typing import Any

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool

from .client import KolideClient, KolideAPIError

# Initialize server and client
server = Server("kolide-1password-device-trust")
client = KolideClient()


def _format_result(result: Any) -> str:
    """Format API result as JSON string."""
    return json.dumps(result, indent=2, default=str)


# ===== Tool Definitions =====

TOOLS = [
    # Organization
    Tool(
        name="kolide_whoami",
        description="Fetch information about the organization from 1Password Device Trust (Kolide K2)",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    # Audit Logs
    Tool(
        name="kolide_list_audit_logs",
        description="Fetch a list of Audit logs from 1Password Device Trust (Kolide K2). Use query parameter to filter results.",
        inputSchema={
            "type": "object",
            "properties": {
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": [],
        },
    ),
    Tool(
        name="kolide_get_audit_log",
        description="Fetch information for a specific Audit log from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "audit_log_id": {"type": "string", "description": "The ID of the audit log"},
            },
            "required": ["audit_log_id"],
        },
    ),
    # Auth Logs
    Tool(
        name="kolide_list_auth_logs",
        description="Fetch a list of Auth log sessions from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": [],
        },
    ),
    Tool(
        name="kolide_get_auth_log",
        description="Fetch information for a specific Auth log session from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "auth_log_id": {"type": "string", "description": "The ID of the auth log"},
            },
            "required": ["auth_log_id"],
        },
    ),
    # Devices
    Tool(
        name="kolide_list_devices",
        description="Fetch a list of Devices from 1Password Device Trust (Kolide K2). Use query parameter to filter by name, serial, etc.",
        inputSchema={
            "type": "object",
            "properties": {
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": [],
        },
    ),
    Tool(
        name="kolide_get_device",
        description="Fetch information for a specific Device from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "The ID of the device"},
            },
            "required": ["device_id"],
        },
    ),
    Tool(
        name="kolide_delete_device",
        description="Delete a specific Device from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "The ID of the device to delete"},
            },
            "required": ["device_id"],
        },
    ),
    Tool(
        name="kolide_get_device_open_issues",
        description="Fetch a list of open Device Trust Issues for a Device from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "The ID of the device"},
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": ["device_id"],
        },
    ),
    Tool(
        name="kolide_update_device_authentication_mode",
        description="Update a Device's authentication mode in 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "The ID of the device"},
                "authentication_mode": {"type": "string", "description": "The new authentication mode"},
            },
            "required": ["device_id", "authentication_mode"],
        },
    ),
    Tool(
        name="kolide_delete_device_registration",
        description="Delete a device registration from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "The ID of the device"},
            },
            "required": ["device_id"],
        },
    ),
    Tool(
        name="kolide_create_check_refresh",
        description="Create a new Check refresh for a device to re-run Device Trust checks in 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "The ID of the device"},
                "check_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional list of specific check IDs to refresh"},
            },
            "required": ["device_id"],
        },
    ),
    Tool(
        name="kolide_get_device_check_results",
        description="Fetch a list of Device Trust Check results for a Device from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "The ID of the device"},
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": ["device_id"],
        },
    ),
    # Device Groups
    Tool(
        name="kolide_list_device_groups",
        description="Fetch a list of Device groups from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": [],
        },
    ),
    Tool(
        name="kolide_get_device_group",
        description="Fetch information for a specific Device group from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "device_group_id": {"type": "string", "description": "The ID of the device group"},
            },
            "required": ["device_group_id"],
        },
    ),
    Tool(
        name="kolide_list_device_group_devices",
        description="Fetch a list of Devices in a Device group from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "device_group_id": {"type": "string", "description": "The ID of the device group"},
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": ["device_group_id"],
        },
    ),
    Tool(
        name="kolide_add_device_to_group",
        description="Add a Device to a Device Group in 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "device_group_id": {"type": "string", "description": "The ID of the device group"},
                "device_id": {"type": "string", "description": "The ID of the device to add"},
            },
            "required": ["device_group_id", "device_id"],
        },
    ),
    Tool(
        name="kolide_remove_device_from_group",
        description="Remove a Device from a Device Group in 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "device_group_id": {"type": "string", "description": "The ID of the device group"},
                "membership_id": {"type": "string", "description": "The ID of the membership to remove"},
            },
            "required": ["device_group_id", "membership_id"],
        },
    ),
    # Issues
    Tool(
        name="kolide_list_issues",
        description="Fetch a list of Device Trust Issues from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": [],
        },
    ),
    Tool(
        name="kolide_get_issue",
        description="Fetch information for a specific Device Trust Issue from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_id": {"type": "string", "description": "The ID of the issue"},
            },
            "required": ["issue_id"],
        },
    ),
    # People
    Tool(
        name="kolide_list_people",
        description="Fetch a list of People from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": [],
        },
    ),
    Tool(
        name="kolide_get_person",
        description="Fetch information for a specific Person from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "person_id": {"type": "string", "description": "The ID of the person"},
            },
            "required": ["person_id"],
        },
    ),
    Tool(
        name="kolide_list_person_devices",
        description="Fetch a list of registered Devices for a Person from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "person_id": {"type": "string", "description": "The ID of the person"},
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": ["person_id"],
        },
    ),
    Tool(
        name="kolide_list_person_issues",
        description="Fetch a list of open Device Trust Issues for a Person from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "person_id": {"type": "string", "description": "The ID of the person"},
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": ["person_id"],
        },
    ),
    Tool(
        name="kolide_list_person_groups_for_person",
        description="Fetch a list of Person groups that a Person belongs to from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "person_id": {"type": "string", "description": "The ID of the person"},
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": ["person_id"],
        },
    ),
    Tool(
        name="kolide_list_deprovisioned_people",
        description="Fetch a list of people that have been deprovisioned from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": [],
        },
    ),
    # Person Groups
    Tool(
        name="kolide_list_person_groups",
        description="Fetch a list of Person groups from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": [],
        },
    ),
    Tool(
        name="kolide_get_person_group",
        description="Fetch information for a specific Person group from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "person_group_id": {"type": "string", "description": "The ID of the person group"},
            },
            "required": ["person_group_id"],
        },
    ),
    Tool(
        name="kolide_list_person_group_people",
        description="Fetch a list of People in a Person group from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "person_group_id": {"type": "string", "description": "The ID of the person group"},
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": ["person_group_id"],
        },
    ),
    # Checks
    Tool(
        name="kolide_list_checks",
        description="Fetch a list of Device Trust Checks (security/compliance checks) from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": [],
        },
    ),
    Tool(
        name="kolide_get_check",
        description="Fetch information for a specific Device Trust Check from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "check_id": {"type": "string", "description": "The ID of the check"},
            },
            "required": ["check_id"],
        },
    ),
    Tool(
        name="kolide_get_check_results",
        description="Fetch a list of Device Trust Check results for a specific Check from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "check_id": {"type": "string", "description": "The ID of the check"},
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": ["check_id"],
        },
    ),
    Tool(
        name="kolide_get_check_configuration",
        description="Fetch the configuration for a specific Device Trust Check from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "check_id": {"type": "string", "description": "The ID of the check"},
            },
            "required": ["check_id"],
        },
    ),
    Tool(
        name="kolide_update_check_configuration",
        description="Update the configuration for a Device Trust Check in 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "check_id": {"type": "string", "description": "The ID of the check"},
                "configuration": {"type": "object", "description": "The configuration to update"},
            },
            "required": ["check_id", "configuration"],
        },
    ),
    # Live Query Campaigns
    Tool(
        name="kolide_list_live_query_campaigns",
        description="Fetch a list of Live query campaigns from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": [],
        },
    ),
    Tool(
        name="kolide_get_live_query_campaign",
        description="Fetch information for a specific Live query campaign from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "The ID of the campaign"},
            },
            "required": ["campaign_id"],
        },
    ),
    Tool(
        name="kolide_create_live_query_campaign",
        description="Create a new Live query campaign to run an osquery query on devices in 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The osquery SQL query to run"},
                "name": {"type": "string", "description": "Optional name for the campaign"},
                "description": {"type": "string", "description": "Optional description"},
                "device_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional list of device IDs to target"},
                "device_group_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional list of device group IDs to target"},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="kolide_update_live_query_campaign",
        description="Update an existing Live query campaign in 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "The ID of the campaign"},
                "name": {"type": "string", "description": "New name for the campaign"},
                "description": {"type": "string", "description": "New description"},
            },
            "required": ["campaign_id"],
        },
    ),
    Tool(
        name="kolide_delete_live_query_campaign",
        description="Delete a Live query campaign from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "The ID of the campaign to delete"},
            },
            "required": ["campaign_id"],
        },
    ),
    Tool(
        name="kolide_get_live_query_results",
        description="Fetch results for a Live query campaign from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "The ID of the campaign"},
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": ["campaign_id"],
        },
    ),
    # Exemption Requests
    Tool(
        name="kolide_list_exemption_requests",
        description="Fetch a list of Device Trust Exemption requests from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": [],
        },
    ),
    Tool(
        name="kolide_get_exemption_request",
        description="Fetch information for a specific Device Trust Exemption request from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "description": "The ID of the exemption request"},
            },
            "required": ["request_id"],
        },
    ),
    Tool(
        name="kolide_update_exemption_request",
        description="Update a Device Trust Exemption request (approve/deny) in 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "description": "The ID of the exemption request"},
                "status": {"type": "string", "description": "New status for the request"},
                "reviewer_note": {"type": "string", "description": "Note from the reviewer"},
            },
            "required": ["request_id"],
        },
    ),
    # Registration Requests
    Tool(
        name="kolide_list_registration_requests",
        description="Fetch a list of Device Registration requests from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": [],
        },
    ),
    Tool(
        name="kolide_get_registration_request",
        description="Fetch information for a specific Device Registration request from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "description": "The ID of the registration request"},
            },
            "required": ["request_id"],
        },
    ),
    Tool(
        name="kolide_update_registration_request",
        description="Update a Device Registration request in 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "description": "The ID of the registration request"},
                "status": {"type": "string", "description": "New status for the request"},
            },
            "required": ["request_id"],
        },
    ),
    # Packages
    Tool(
        name="kolide_list_packages",
        description="Fetch a list of software Packages from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": [],
        },
    ),
    Tool(
        name="kolide_get_package",
        description="Fetch information for a specific software Package from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "package_id": {"type": "string", "description": "The ID of the package"},
            },
            "required": ["package_id"],
        },
    ),
    # Admin Users
    Tool(
        name="kolide_list_admin_users",
        description="Fetch a list of Admin users from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": [],
        },
    ),
    Tool(
        name="kolide_get_admin_user",
        description="Fetch information for a specific Admin user from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "admin_user_id": {"type": "string", "description": "The ID of the admin user"},
            },
            "required": ["admin_user_id"],
        },
    ),
    # Reporting Tables
    Tool(
        name="kolide_list_reporting_tables",
        description="Fetch a list of Reporting tables available for queries from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": [],
        },
    ),
    Tool(
        name="kolide_get_reporting_table",
        description="Fetch information for a specific Reporting table from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "The name of the reporting table"},
            },
            "required": ["table_name"],
        },
    ),
    Tool(
        name="kolide_get_table_records",
        description="Fetch records from a Reporting table from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "The name of the reporting table"},
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": ["table_name"],
        },
    ),
    # Report Queries
    Tool(
        name="kolide_list_report_queries",
        description="Fetch a list of saved Report queries from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
                "query": {"type": "string", "description": "Query to filter results"},
            },
            "required": [],
        },
    ),
    Tool(
        name="kolide_get_report_query",
        description="Fetch information for a specific Report query from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "query_id": {"type": "string", "description": "The ID of the report query"},
            },
            "required": ["query_id"],
        },
    ),
    Tool(
        name="kolide_get_report_query_results",
        description="Fetch results for a Report query from 1Password Device Trust (Kolide K2)",
        inputSchema={
            "type": "object",
            "properties": {
                "query_id": {"type": "string", "description": "The ID of the report query"},
                "cursor": {"type": "string", "description": "Cursor for pagination"},
                "per_page": {"type": "integer", "description": "Number of records per page (1-100)", "minimum": 1, "maximum": 100},
            },
            "required": ["query_id"],
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools."""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    try:
        result = await _dispatch_tool(name, arguments)
        return [TextContent(type="text", text=_format_result(result))]
    except KolideAPIError as e:
        return [TextContent(type="text", text=f"Error: {e.message} (status: {e.status_code})")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def _dispatch_tool(name: str, args: dict[str, Any]) -> Any:
    """Dispatch tool call to appropriate client method."""
    # Organization
    if name == "kolide_whoami":
        return await client.whoami()

    # Audit Logs
    elif name == "kolide_list_audit_logs":
        return await client.list_audit_logs(
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_get_audit_log":
        return await client.get_audit_log(args["audit_log_id"])

    # Auth Logs
    elif name == "kolide_list_auth_logs":
        return await client.list_auth_logs(
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_get_auth_log":
        return await client.get_auth_log(args["auth_log_id"])

    # Devices
    elif name == "kolide_list_devices":
        return await client.list_devices(
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_get_device":
        return await client.get_device(args["device_id"])
    elif name == "kolide_delete_device":
        return await client.delete_device(args["device_id"])
    elif name == "kolide_get_device_open_issues":
        return await client.get_device_open_issues(
            device_id=args["device_id"],
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_update_device_authentication_mode":
        return await client.update_device_authentication_mode(
            device_id=args["device_id"],
            authentication_mode=args["authentication_mode"],
        )
    elif name == "kolide_delete_device_registration":
        return await client.delete_device_registration(args["device_id"])
    elif name == "kolide_create_check_refresh":
        return await client.create_check_refresh(
            device_id=args["device_id"],
            check_ids=args.get("check_ids"),
        )
    elif name == "kolide_get_device_check_results":
        return await client.get_device_check_results(
            device_id=args["device_id"],
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )

    # Device Groups
    elif name == "kolide_list_device_groups":
        return await client.list_device_groups(
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_get_device_group":
        return await client.get_device_group(args["device_group_id"])
    elif name == "kolide_list_device_group_devices":
        return await client.list_device_group_devices(
            device_group_id=args["device_group_id"],
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_add_device_to_group":
        return await client.add_device_to_group(
            device_group_id=args["device_group_id"],
            device_id=args["device_id"],
        )
    elif name == "kolide_remove_device_from_group":
        return await client.remove_device_from_group(
            device_group_id=args["device_group_id"],
            membership_id=args["membership_id"],
        )

    # Issues
    elif name == "kolide_list_issues":
        return await client.list_issues(
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_get_issue":
        return await client.get_issue(args["issue_id"])

    # People
    elif name == "kolide_list_people":
        return await client.list_people(
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_get_person":
        return await client.get_person(args["person_id"])
    elif name == "kolide_list_person_devices":
        return await client.list_person_devices(
            person_id=args["person_id"],
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_list_person_issues":
        return await client.list_person_issues(
            person_id=args["person_id"],
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_list_person_groups_for_person":
        return await client.list_person_groups_for_person(
            person_id=args["person_id"],
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_list_deprovisioned_people":
        return await client.list_deprovisioned_people(
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )

    # Person Groups
    elif name == "kolide_list_person_groups":
        return await client.list_person_groups(
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_get_person_group":
        return await client.get_person_group(args["person_group_id"])
    elif name == "kolide_list_person_group_people":
        return await client.list_person_group_people(
            person_group_id=args["person_group_id"],
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )

    # Checks
    elif name == "kolide_list_checks":
        return await client.list_checks(
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_get_check":
        return await client.get_check(args["check_id"])
    elif name == "kolide_get_check_results":
        return await client.get_check_results(
            check_id=args["check_id"],
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_get_check_configuration":
        return await client.get_check_configuration(args["check_id"])
    elif name == "kolide_update_check_configuration":
        return await client.update_check_configuration(
            check_id=args["check_id"],
            configuration=args["configuration"],
        )

    # Live Query Campaigns
    elif name == "kolide_list_live_query_campaigns":
        return await client.list_live_query_campaigns(
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_get_live_query_campaign":
        return await client.get_live_query_campaign(args["campaign_id"])
    elif name == "kolide_create_live_query_campaign":
        return await client.create_live_query_campaign(
            query=args["query"],
            name=args.get("name"),
            description=args.get("description"),
            device_ids=args.get("device_ids"),
            device_group_ids=args.get("device_group_ids"),
        )
    elif name == "kolide_update_live_query_campaign":
        return await client.update_live_query_campaign(
            campaign_id=args["campaign_id"],
            name=args.get("name"),
            description=args.get("description"),
        )
    elif name == "kolide_delete_live_query_campaign":
        return await client.delete_live_query_campaign(args["campaign_id"])
    elif name == "kolide_get_live_query_results":
        return await client.get_live_query_results(
            campaign_id=args["campaign_id"],
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )

    # Exemption Requests
    elif name == "kolide_list_exemption_requests":
        return await client.list_exemption_requests(
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_get_exemption_request":
        return await client.get_exemption_request(args["request_id"])
    elif name == "kolide_update_exemption_request":
        return await client.update_exemption_request(
            request_id=args["request_id"],
            status=args.get("status"),
            reviewer_note=args.get("reviewer_note"),
        )

    # Registration Requests
    elif name == "kolide_list_registration_requests":
        return await client.list_registration_requests(
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_get_registration_request":
        return await client.get_registration_request(args["request_id"])
    elif name == "kolide_update_registration_request":
        return await client.update_registration_request(
            request_id=args["request_id"],
            status=args.get("status"),
        )

    # Packages
    elif name == "kolide_list_packages":
        return await client.list_packages(
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_get_package":
        return await client.get_package(args["package_id"])

    # Admin Users
    elif name == "kolide_list_admin_users":
        return await client.list_admin_users(
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_get_admin_user":
        return await client.get_admin_user(args["admin_user_id"])

    # Reporting Tables
    elif name == "kolide_list_reporting_tables":
        return await client.list_reporting_tables(
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_get_reporting_table":
        return await client.get_reporting_table(args["table_name"])
    elif name == "kolide_get_table_records":
        return await client.get_table_records(
            table_name=args["table_name"],
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )

    # Report Queries
    elif name == "kolide_list_report_queries":
        return await client.list_report_queries(
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
            query=args.get("query"),
        )
    elif name == "kolide_get_report_query":
        return await client.get_report_query(args["query_id"])
    elif name == "kolide_get_report_query_results":
        return await client.get_report_query_results(
            query_id=args["query_id"],
            cursor=args.get("cursor"),
            per_page=args.get("per_page"),
        )

    else:
        raise ValueError(f"Unknown tool: {name}")


def create_app():
    """Create the Starlette application with Streamable HTTP transport."""
    from contextlib import asynccontextmanager
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response

    # Create session manager - handles all the transport complexity
    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=True,
        stateless=True,  # Each request is independent
    )

    @asynccontextmanager
    async def lifespan(app):
        """Lifespan context manager to start/stop the session manager."""
        async with session_manager.run():
            yield

    async def health_check(request: Request):
        return JSONResponse({"status": "ok"})

    # Create an ASGI app wrapper that handles OPTIONS and delegates to session manager
    async def mcp_asgi_app(scope, receive, send):
        """ASGI app that handles OPTIONS and delegates to session manager."""
        if scope["type"] == "http":
            method = scope.get("method", "")
            if method == "OPTIONS":
                # Send CORS preflight response
                response = Response(
                    status_code=204,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type, mcp-session-id, last-event-id",
                    }
                )
                await response(scope, receive, send)
                return
        # Delegate all other requests to session manager
        await session_manager.handle_request(scope, receive, send)

    app = Starlette(
        debug=True,
        lifespan=lifespan,
        routes=[
            Route("/health", health_check, methods=["GET"]),
            Mount("/mcp", app=mcp_asgi_app),
            Mount("/sse", app=mcp_asgi_app),
        ],
    )

    return app


def main():
    """Run the MCP server with Streamable HTTP transport."""
    import uvicorn

    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8000"))

    print(f"Starting 1Password Device Trust MCP server on {host}:{port}")
    print(f"MCP endpoint: http://{host}:{port}/mcp")
    print(f"Health check: http://{host}:{port}/health")

    app = create_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
