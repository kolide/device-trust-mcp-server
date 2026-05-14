# 1Password Device Trust (Kolide K2) MCP Server

An MCP (Model Context Protocol) server that exposes the 1Password Device Trust API (formerly Kolide K2) as tools for AI agents. Uses Streamable HTTP transport for communication.

## Features

- Full coverage of 1Password Device Trust (Kolide K2) API endpoints (57 endpoint tools + 3 composite analytical tools)
- **Auto-pagination** (`fetch_all`) to retrieve complete datasets in a single tool call
- **Field projection** (`fields`) to return only the columns you need, reducing response size
- **Device owner enrichment** (`enrich_device_owner`) to automatically resolve device IDs to owner names/emails
- **Composite analytical tools** for common aggregation tasks (resolution time stats, grouped counts)
- **Dynamic reporting table validation** — table names are fetched from the API at startup and refreshable on demand
- **MCP Resources** providing search syntax docs, reporting table guides, and workflow references
- **Bearer token authentication** on all MCP endpoints
- **Structured JSON audit logging** of every tool invocation
- Binds to localhost only by default; configurable CORS allowlist
- Streamable HTTP transport for easy integration with AI tools
- API key and Kolide API version (`KOLIDE_API_VERSION`) read fresh on each request (supports `.env` updates without restart)

## Maintaining API parity

The server does **not** load OpenAPI at runtime. Tools are defined in `src/kolide_mcp/endpoints.py` (`ENDPOINTS`), and the HTTP client sends `x-kolide-api-version` from `get_kolide_api_version()` in `src/kolide_mcp/api_version.py` (overridable via **`KOLIDE_API_VERSION`** in your environment or `.env`).

**Workflow when the Kolide API changes:**

1. **`openapi/`** — Treat `openapi/openapi*.json` as the canonical REST contract snapshot. There is one file per supported version (e.g. `openapi2026-04-07.json`); CI checks `ENDPOINTS` against **all** of them.
2. **Implementation** — For any real API delta reflected in those JSON files, update `ENDPOINTS` (and `composite_tools.py` / `resources.py` if needed). Set **`KOLIDE_API_VERSION`** in `.env` to the version line you run against.
3. **Verification** — CI runs drift checks so `ENDPOINTS` stays aligned with the pinned OpenAPI file (path templates are compared with parameter names ignored). To run the same tests locally after `uv sync`:

   ```bash
   uv run python -m unittest discover -s tests -v
   ```

If the pinned OpenAPI file gains operations you do not want as MCP tools yet, add the normalized ``(METHOD, path)`` pair to ``OPENAPI_OPERATIONS_WITHOUT_MCP_TOOL`` in `tests/test_openapi_drift.py` and document why.

**Endpoints that exist only on some API versions**

Kolide may expose routes on one dated API line but not another. In `EndpointSpec`, set **`api_versions`** to a `frozenset` of version strings (must be a subset of `SUPPORTED_KOLIDE_API_VERSIONS` in `api_version.py`):

- **`api_versions=None`** (default) — tool is listed and callable for every supported version, as long as that version’s OpenAPI snapshot includes the operation.
- **`api_versions=frozenset({"2026-04-07"})`** — tool appears in `list_tools` and works only when `KOLIDE_API_VERSION` is `2026-04-07`; other versions skip it in drift checks and get a clear error if invoked anyway.

After adding a new version line to the server, extend `SUPPORTED_KOLIDE_API_VERSIONS`, add `openapi<version>.json`, and adjust `api_versions` on affected specs.

## Installation

### Using uv (recommended)

```bash
cd /path/to/k2_api_mcp
uv sync
```

### Using pip

```bash
cd /path/to/k2_api_mcp
pip install -e .
```

## Configuration

### Environment Variables

Copy the example and fill in your values:

```bash
cp .env.example .env
```

**Required variables:**

| Variable | Description |
|---|---|
| `KOLIDE_API_KEY` | Your Kolide API key (Dashboard > Settings > API Keys) |
| `MCP_AUTH_TOKEN` | Bearer token for MCP endpoint access. Generate one with: `python -c "import secrets; print(secrets.token_hex(32))"` |

**Optional variables:**

| Variable | Default | Description |
|---|---|---|
| `KOLIDE_API_URL` | `https://api.kolide.com` | Kolide API base URL (unusual to override). |
| `KOLIDE_API_VERSION` | `2026-04-07` | **Set in `.env`** to pin the dated Kolide API line. Must be `2023-05-26` or `2026-04-07`. Sent as `X-Kolide-Api-Version` on every upstream request. Use `2023-05-26` only if you depend on the older API contract. |
| `MCP_HOST` | `127.0.0.1` | Bind address. Only change if you need remote access. |
| `MCP_PORT` | `8000` | Listen port |
| `MCP_CORS_ALLOWED_ORIGINS` | `http://localhost,http://127.0.0.1` | Comma-separated origins for browser-based MCP clients |
| `MCP_MAX_ENRICH_RECORDS` | `500` | Max records enriched per `enrich_device_owner` call |
| `MCP_LOG_FILE` | *(unset)* | File path for structured audit logs (in addition to stdout) |
| `MCP_DEBUG` | `false` | Starlette debug mode (development only) |

The Kolide API key and API version header are read fresh on each tool call (using your `.env` if present), so you can change `KOLIDE_API_KEY` or `KOLIDE_API_VERSION` without restarting the server.

## Running the Server

### Using uv

```bash
uv run kolide-mcp
```

### Using Python directly

```bash
python -m kolide_mcp.server
```

The server will start and display:
```
Starting 1Password Device Trust MCP server on 127.0.0.1:8000
MCP endpoint: http://127.0.0.1:8000/mcp
Health check: http://127.0.0.1:8000/health
```

> **Note:** The server refuses to start if `MCP_AUTH_TOKEN` is not set.

## Connecting AI Tools

> **Tip:** Drop-in example configs live in `.cursor.example/`,
> `.claude.example/`, and `.vscode.example/` at the repo root. Copy the one
> you need into place (e.g. `cp -r .cursor.example .cursor`) instead of
> writing the JSON by hand, then replace `your-mcp-auth-token-here` with
> your `MCP_AUTH_TOKEN`.

### Cursor

Add to `.cursor/mcp.json` in your project or global config:

```json
{
  "mcpServers": {
    "kolide": {
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_AUTH_TOKEN"
      }
    }
  }
}
```

### Claude Desktop

Claude Desktop's `claude_desktop_config.json` only supports stdio (subprocess) servers — it does not connect to remote HTTP URLs configured in the JSON file. To bridge the gap, use [`mcp-remote`](https://www.npmjs.com/package/mcp-remote), which wraps the HTTP server as a stdio process that Claude Desktop can manage.

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kolide": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "http://localhost:8000/mcp",
        "--header", "Authorization: Bearer YOUR_MCP_AUTH_TOKEN"
      ]
    }
  }
}
```

### VS Code (Copilot Chat)

Requires VS Code 1.99+ with MCP support. Add to `.vscode/mcp.json` in your project, then open the Copilot Chat panel in **Agent** mode:

```json
{
  "servers": {
    "kolide": {
      "type": "http",
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_AUTH_TOKEN"
      }
    }
  }
}
```

### Other MCP Clients

Connect to the MCP endpoint at `http://localhost:8000/mcp` with an `Authorization: Bearer <token>` header. The server uses the Streamable HTTP transport. Clients that only support stdio can use `mcp-remote` as shown in the Claude Desktop example above.

Replace `YOUR_MCP_AUTH_TOKEN` in all examples with the same value you set in `MCP_AUTH_TOKEN`.

## Enhanced Parameters for List Tools

All paginated list tools support these additional parameters that significantly reduce the number of tool calls needed for analytical queries.

### `fetch_all` (boolean)

Automatically follow all pagination cursors and return the complete result set in a single response. Capped at 10,000 records or 50 pages.

```json
{
  "table_name": "device_chrome_extensions",
  "fetch_all": true
}
```

### `fields` (string array)

Return only specified fields in each record, reducing response size dramatically for tables with large payloads.

```json
{
  "table_name": "device_chrome_extensions",
  "fetch_all": true,
  "fields": ["device_id", "device_name", "name", "identifier"]
}
```

### `enrich_device_owner` (boolean)

Automatically resolve `device_id` or `device_information` fields to the registered owner's name and email. Injects `owner_name` and `owner_email` into each record.

```json
{
  "query": "check_id:\"27680\"",
  "fetch_all": true,
  "enrich_device_owner": true
}
```

## Available Tools

The server exposes 60 tools: 57 endpoint tools covering all API functionality, plus 3 composite/utility tools.

### Composite & Utility Tools

- `kolide_issue_resolution_stats` - Compute resolution time statistics (avg, median, min, max, p90) for issues of a specific check. Automatically fetches all pages.
- `kolide_count_table_records_by_field` - Count records in a reporting table grouped by a field. Returns ranked results. Useful for "which device has the most extensions?" style questions.
- `kolide_refresh_reporting_tables` - Refresh the cached list of valid reporting table names from the API. Use if a table name is unexpectedly rejected.

### Organization
- `kolide_whoami` - Get organization information

### Devices
- `kolide_list_devices` - List all devices
- `kolide_get_device` - Get device details
- `kolide_delete_device` - Delete a device
- `kolide_get_device_open_issues` - Get open issues for a device
- `kolide_update_device_authentication_mode` - Update device auth mode
- `kolide_delete_device_registration` - Delete device registration
- `kolide_create_check_refresh` - Trigger check refresh on device
- `kolide_get_device_check_results` - Get check results for device

### Device Groups
- `kolide_list_device_groups` - List device groups
- `kolide_get_device_group` - Get device group details
- `kolide_list_device_group_devices` - List devices in a group
- `kolide_add_device_to_group` - Add device to group
- `kolide_remove_device_from_group` - Remove device from group

### People
- `kolide_list_people` - List all people
- `kolide_get_person` - Get person details
- `kolide_list_person_devices` - List devices for a person
- `kolide_list_person_issues` - List open issues for a person
- `kolide_list_person_groups_for_person` - List groups a person belongs to
- `kolide_list_deprovisioned_people` - List deprovisioned people

### Person Groups
- `kolide_list_person_groups` - List person groups
- `kolide_get_person_group` - Get person group details
- `kolide_list_person_group_people` - List people in a group

### Issues
- `kolide_list_issues` - List all issues
- `kolide_get_issue` - Get issue details

### Checks
- `kolide_list_checks` - List security checks
- `kolide_get_check` - Get check details
- `kolide_get_check_results` - Get results for a check
- `kolide_get_check_configuration` - Get check configuration
- `kolide_update_check_configuration` - Update check configuration

### Live Query Campaigns
- `kolide_list_live_query_campaigns` - List live query campaigns
- `kolide_get_live_query_campaign` - Get campaign details
- `kolide_create_live_query_campaign` - Create new osquery campaign
- `kolide_update_live_query_campaign` - Update campaign
- `kolide_delete_live_query_campaign` - Delete campaign
- `kolide_get_live_query_results` - Get campaign results

### Exemption Requests
- `kolide_list_exemption_requests` - List exemption requests
- `kolide_get_exemption_request` - Get request details
- `kolide_update_exemption_request` - Approve/deny request

### Registration Requests
- `kolide_list_registration_requests` - List registration requests
- `kolide_get_registration_request` - Get request details
- `kolide_update_registration_request` - Update request

### Packages
- `kolide_list_packages` - List software packages
- `kolide_get_package` - Get package details

### Admin Users
- `kolide_list_admin_users` - List admin users
- `kolide_get_admin_user` - Get admin user details

### Audit Logs
- `kolide_list_audit_logs` - List audit logs
- `kolide_get_audit_log` - Get audit log details

### Auth Logs
- `kolide_list_auth_logs` - List auth log sessions
- `kolide_get_auth_log` - Get auth log details

### Reporting
- `kolide_list_reporting_tables` - List available reporting tables
- `kolide_get_reporting_table` - Get table schema
- `kolide_get_table_records` - Fetch records from a table
- `kolide_list_report_queries` - List saved report queries
- `kolide_get_report_query` - Get query details
- `kolide_get_report_query_results` - Execute and get query results

## MCP Resources

The server exposes three reference documentation resources that AI agents can read for context:

| Resource URI | Description |
|---|---|
| `kolide://docs/search-syntax` | Full search query syntax with operators, field names per endpoint, and examples |
| `kolide://docs/reporting-tables` | Overview of reporting tables with efficient querying tips |
| `kolide://docs/workflows` | Step-by-step guides for common analytical tasks |

## Query Parameter

Many list tools support a `query` parameter for filtering. The query syntax uses:
- `:` for exact matches (e.g., `status:"fail"`)
- `~` for substring matches (e.g., `name~"MacBook"`)
- `>` / `<` for datetime comparisons (e.g., `detected_at>"2025-01-01T00:00:00Z"`)
- `AND` / `OR` to combine clauses

Each tool's description includes the searchable fields and examples for that endpoint.

## Pagination

List tools return paginated results. Use the `cursor` from the response to fetch the next page, or set `fetch_all: true` to retrieve all pages automatically:

```json
{
  "cursor": "next_page_cursor",
  "per_page": 25
}
```

## Health Check

The server provides a health endpoint at `http://localhost:8000/health` that returns:
```json
{"status": "ok"}
```

## License

MIT
