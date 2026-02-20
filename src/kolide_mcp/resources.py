"""MCP Resources providing reference documentation for the Kolide MCP server."""

from mcp.types import Resource

from .endpoints import ENDPOINTS


def _build_search_syntax_doc() -> str:
    """Generate markdown documentation for the search query syntax."""
    lines = [
        "# Kolide Search Query Syntax",
        "",
        "## Operators",
        "",
        "| Operator | Meaning | Example |",
        "|----------|---------|---------|",
        '| `:` | Exact match | `status:"fail"` |',
        '| `~` | Substring match | `name~"MacBook"` |',
        '| `>` | Greater than (datetime) | `detected_at>"2025-01-01T00:00:00Z"` |',
        '| `<` | Less than (datetime) | `resolved_at<"2025-06-01T00:00:00Z"` |',
        "",
        "## Combining Clauses",
        "",
        "Use `AND` or `OR` to combine multiple conditions:",
        "",
        '- `device_type:"Mac" AND registered_at>"2025-01-01T00:00:00Z"`',
        '- `status:"fail" OR status:"error"`',
        "",
        "Quote values containing spaces with double quotes.",
        "",
        "## Searchable Fields by Endpoint",
        "",
    ]

    for spec in ENDPOINTS:
        if spec.searchable_fields:
            lines.append(f"### kolide_{spec.name}")
            lines.append("")
            lines.append(f"Fields: `{'`, `'.join(spec.searchable_fields)}`")
            if spec.search_examples:
                lines.append("")
                lines.append(f"Examples: {', '.join(f'`{e}`' for e in spec.search_examples)}")
            lines.append("")

    return "\n".join(lines)


def _build_reporting_tables_doc() -> str:
    """Generate documentation about known reporting tables."""
    return (
        "# Kolide Reporting Tables\n"
        "\n"
        "Reporting tables contain device inventory and telemetry data collected by the Kolide agent.\n"
        "Use `kolide_list_reporting_tables` to get the full current list.\n"
        "Use `kolide_get_reporting_table` with a table name to see its columns.\n"
        "\n"
        "## Common Tables\n"
        "\n"
        "### Device Software & Extensions\n"
        "- **device_chrome_extensions** - Chrome, Brave, Edge, and Chromium browser extensions\n"
        "- **mac_safari_extensions** - Safari browser extensions\n"
        "- **device_vscode_extensions** - VS Code extensions\n"
        "\n"
        "### macOS Specific\n"
        "- **mac_kernel_extensions** - macOS kernel extensions\n"
        "- **mac_system_extensions** - macOS system extensions\n"
        "\n"
        "## Efficient Querying Tips\n"
        "\n"
        "- Use `kolide_count_table_records_by_field` to group and count records without\n"
        "  fetching full payloads (e.g. count extensions per device).\n"
        "- Use the `fields` parameter on `kolide_get_table_records` to select only the\n"
        "  columns you need, reducing response size dramatically.\n"
        "- Use `fetch_all: true` to get all records in a single tool call instead of\n"
        "  manually paginating.\n"
        "- Use `enrich_device_owner: true` to automatically resolve device IDs to\n"
        "  their registered owner name and email.\n"
    )


def _build_workflows_doc() -> str:
    """Generate documentation about common multi-step workflows."""
    return (
        "# Common Kolide MCP Workflows\n"
        "\n"
        "## Find Which User Has the Most Browser Extensions\n"
        "\n"
        "**Quick way:** Call `kolide_count_table_records_by_field` with:\n"
        "- `table_name: \"device_chrome_extensions\"`\n"
        "- `group_by: \"device_id\"`\n"
        "- `label_field: \"device_name\"`\n"
        "\n"
        "Then call `kolide_get_device` with the top device_id to find the owner,\n"
        "followed by `kolide_get_person` with the registered_owner_info identifier.\n"
        "\n"
        "**Full data way:** Call `kolide_get_table_records` with:\n"
        "- `table_name: \"device_chrome_extensions\"`\n"
        "- `fetch_all: true`\n"
        "- `fields: [\"device_id\", \"device_name\", \"name\", \"identifier\"]`\n"
        "- `enrich_device_owner: true`\n"
        "\n"
        "## Compute Average Issue Resolution Time for a Check\n"
        "\n"
        "**Quick way:** Call `kolide_issue_resolution_stats` with the `check_id`.\n"
        "This automatically fetches all issues and computes avg/median/min/max/p90.\n"
        "\n"
        "**Manual way:**\n"
        "1. Call `kolide_list_issues` with `query: 'check_id:\"27680\"'` and `fetch_all: true`\n"
        "2. Filter to resolved issues (resolved_at is not null)\n"
        "3. Compute deltas between detected_at and resolved_at\n"
        "\n"
        "## Audit Browser Extensions for Security Concerns\n"
        "\n"
        "1. Call `kolide_get_table_records` with:\n"
        "   - `table_name: \"device_chrome_extensions\"`\n"
        "   - `fetch_all: true`\n"
        "   - `fields: [\"device_id\", \"device_name\", \"name\", \"identifier\", \"enabled\", \"from_webstore\", \"version\"]`\n"
        "2. Review results for known compromised extension IDs, sideloaded extensions\n"
        "   (from_webstore is false), and suspicious extension names.\n"
        "\n"
        "## Find a Specific Check by Name\n"
        "\n"
        "Call `kolide_list_checks` with `query: 'name~\"up to date\"'` to search\n"
        "by partial name match.\n"
        "\n"
        "## List All Open Issues for a Person\n"
        "\n"
        "1. Call `kolide_list_people` with `query: 'email~\"user@example.com\"'` to find the person ID.\n"
        "2. Call `kolide_list_person_issues` with the person_id.\n"
        "\n"
        "## Find Devices Failing a Specific Check\n"
        "\n"
        "Call `kolide_get_check_results` with the check_id and `query: 'status:\"fail\"'`.\n"
    )


_RESOURCE_CONTENT = {
    "kolide://docs/search-syntax": _build_search_syntax_doc,
    "kolide://docs/reporting-tables": _build_reporting_tables_doc,
    "kolide://docs/workflows": _build_workflows_doc,
}


RESOURCES: list[Resource] = [
    Resource(
        uri="kolide://docs/search-syntax",
        name="Kolide Search Syntax Reference",
        description=(
            "Complete reference for the search query syntax used by list/filter tools, "
            "including operators, field names per endpoint, and examples."
        ),
        mimeType="text/markdown",
    ),
    Resource(
        uri="kolide://docs/reporting-tables",
        name="Kolide Reporting Tables Guide",
        description=(
            "Overview of available reporting tables (device extensions, system info, etc.) "
            "with tips for efficient querying."
        ),
        mimeType="text/markdown",
    ),
    Resource(
        uri="kolide://docs/workflows",
        name="Common Kolide Workflows",
        description=(
            "Step-by-step guides for common tasks: finding extension counts per user, "
            "computing issue resolution stats, auditing extensions for security, and more."
        ),
        mimeType="text/markdown",
    ),
]


def get_resource_content(uri: str) -> str:
    """Get the content for a resource by URI."""
    builder = _RESOURCE_CONTENT.get(uri)
    if builder:
        return builder()
    raise ValueError(f"Unknown resource: {uri}")
