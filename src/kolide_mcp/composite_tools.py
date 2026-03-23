"""Composite analytical tools that combine multiple API calls with aggregation."""

from collections import Counter
from datetime import datetime
from statistics import median
from typing import Any

# Known reporting table names as of Kolide API version 2023-05-26.
# When new tables are added to the API, append them here and update the version note.
# Alternative: replace this allowlist with re.fullmatch(r'[a-z][a-z0-9_]*', table_name)
# for a format-only check that permits any well-formed name without explicit enumeration.
KNOWN_REPORTING_TABLES: frozenset[str] = frozenset(
    {
        "device_chrome_extensions",
        "mac_safari_extensions",
        "device_vscode_extensions",
        "mac_kernel_extensions",
        "mac_system_extensions",
    }
)

from mcp.types import Tool

from .client import KolideClient

MAX_FETCH_ALL = 10_000
MAX_FETCH_ALL_PAGES = 50


async def _fetch_all_pages(
    client: KolideClient,
    path: str,
    query: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch all pages from a paginated endpoint."""
    params: dict[str, Any] = {"per_page": 100}
    if query:
        params["query"] = query

    result = await client.request("GET", path, params=params)
    all_data = list(result.get("data", []))
    pages = 1

    while (
        result.get("pagination", {}).get("next_cursor")
        and len(all_data) < MAX_FETCH_ALL
        and pages < MAX_FETCH_ALL_PAGES
    ):
        params["cursor"] = result["pagination"]["next_cursor"]
        result = await client.request("GET", path, params=params)
        all_data.extend(result.get("data", []))
        pages += 1

    return all_data


async def handle_issue_resolution_stats(
    client: KolideClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Compute resolution time statistics for issues of a specific check."""
    check_id = args["check_id"]
    query = args.get("query") or f'check_id:"{check_id}"'

    issues = await _fetch_all_pages(client, "/issues", query=query)

    resolved_days: list[float] = []
    open_count = 0

    for issue in issues:
        detected = issue.get("detected_at")
        resolved = issue.get("resolved_at")
        if detected and resolved:
            det = datetime.fromisoformat(detected.replace("Z", "+00:00"))
            res = datetime.fromisoformat(resolved.replace("Z", "+00:00"))
            delta_days = (res - det).total_seconds() / 86400.0
            if delta_days >= 0:
                resolved_days.append(delta_days)
        elif detected and not resolved:
            open_count += 1

    if not resolved_days:
        return {
            "check_id": check_id,
            "total_issues": len(issues),
            "resolved_count": 0,
            "open_count": open_count,
            "message": "No resolved issues found to compute statistics.",
        }

    sorted_days = sorted(resolved_days)
    avg = sum(sorted_days) / len(sorted_days)
    med = median(sorted_days)
    p90_idx = min(int(len(sorted_days) * 0.9), len(sorted_days) - 1)

    return {
        "check_id": check_id,
        "total_issues": len(issues),
        "resolved_count": len(resolved_days),
        "open_count": open_count,
        "average_days_to_resolve": round(avg, 1),
        "median_days_to_resolve": round(med, 1),
        "min_days_to_resolve": round(sorted_days[0], 1),
        "max_days_to_resolve": round(sorted_days[-1], 1),
        "p90_days_to_resolve": round(sorted_days[p90_idx], 1),
    }


async def handle_count_table_records_by_field(
    client: KolideClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Count reporting table records grouped by a specified field."""
    table_name = args["table_name"]
    group_by = args["group_by"]

    if table_name not in KNOWN_REPORTING_TABLES:
        return {
            "error": f"Unknown table: {table_name!r}.",
            "valid_tables": sorted(KNOWN_REPORTING_TABLES),
        }

    records = await _fetch_all_pages(
        client, f"/reporting/tables/{table_name}/table_records"
    )

    counter: Counter = Counter()
    group_labels: dict[str, str] = {}
    label_field = args.get("label_field")

    for rec in records:
        key = rec.get(group_by)
        if key is not None:
            key_str = str(key)
            counter[key_str] += 1
            if label_field and key_str not in group_labels:
                label = rec.get(label_field)
                if label is not None:
                    group_labels[key_str] = str(label)

    top_n = int(args.get("top_n", 20))
    ranked = counter.most_common(top_n)

    results = []
    for value, count in ranked:
        entry: dict[str, Any] = {group_by: value, "count": count}
        if label_field and value in group_labels:
            entry[label_field] = group_labels[value]
        results.append(entry)

    return {
        "table_name": table_name,
        "group_by": group_by,
        "total_records": len(records),
        "unique_values": len(counter),
        "top_results": results,
    }


COMPOSITE_TOOLS: list[Tool] = [
    Tool(
        name="kolide_issue_resolution_stats",
        description=(
            "Compute resolution time statistics (avg, median, min, max, p90) "
            "for Device Trust issues, typically filtered to a specific check. "
            "Automatically fetches all issue pages and calculates metrics. "
            'Use the query parameter to add extra filters (e.g. \'resolved_at>"2025-01-01T00:00:00Z"\').'
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "check_id": {
                    "type": "string",
                    "description": "The check ID to compute stats for. Used as the default query filter.",
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Optional search query to override the default check_id filter. "
                        "Uses the same syntax as list_issues."
                    ),
                },
            },
            "required": ["check_id"],
        },
    ),
    Tool(
        name="kolide_count_table_records_by_field",
        description=(
            "Count records in a Reporting table grouped by a specified field. "
            "Automatically fetches all pages and returns the top results ranked by count. "
            "Useful for questions like 'which device has the most extensions?' or "
            "'what is the most commonly installed extension?'"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": (
                        "The reporting table name (e.g. 'device_chrome_extensions', "
                        "'mac_safari_extensions', 'device_vscode_extensions')."
                    ),
                },
                "group_by": {
                    "type": "string",
                    "description": "The field name to group and count by (e.g. 'device_id', 'name', 'identifier').",
                },
                "label_field": {
                    "type": "string",
                    "description": (
                        "Optional field to include as a label for each group "
                        "(e.g. 'device_name' when grouping by 'device_id', "
                        "or 'name' when grouping by 'identifier')."
                    ),
                },
                "top_n": {
                    "type": ["integer", "string"],
                    "description": "Number of top results to return (default: 20).",
                },
            },
            "required": ["table_name", "group_by"],
        },
    ),
]

COMPOSITE_HANDLERS: dict[str, Any] = {
    "kolide_issue_resolution_stats": handle_issue_resolution_stats,
    "kolide_count_table_records_by_field": handle_count_table_records_by_field,
}
