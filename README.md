# 1Password Device Trust (Kolide K2) MCP Server

An MCP (Model Context Protocol) server that exposes the 1Password Device Trust API (formerly Kolide K2) as tools for AI agents. Uses SSE (Server-Sent Events) transport for communication.

## Features

- Full coverage of 1Password Device Trust (Kolide K2) API endpoints (59 endpoints exposed as MCP tools)
- SSE transport for easy integration with AI tools
- API key loaded fresh on each request (supports `.env` file updates without restart)
- Pagination support via cursor-based navigation

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

Create a `.env` file in the project directory (or set environment variables):

```bash
# Required: Your Kolide API key
KOLIDE_API_KEY=your-api-key-here

# Optional: Server configuration
MCP_HOST=0.0.0.0  # Default: 0.0.0.0
MCP_PORT=8000     # Default: 8000
```

The API key is read fresh on each tool call, so you can update it in the `.env` file without restarting the server.

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
Starting Kolide MCP server on 0.0.0.0:8000
SSE endpoint: http://0.0.0.0:8000/sse
Messages endpoint: http://0.0.0.0:8000/messages/
```

## Connecting AI Tools

### Cursor

Add to `.cursor/mcp.json` in your project or global config:

```json
{
  "mcpServers": {
    "kolide": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kolide": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Other MCP Clients

Connect to the MCP endpoint at `http://localhost:8000/mcp`. The server uses the Streamable HTTP transport which accepts both GET and POST requests.

## Available Tools

The server exposes 56 tools covering all 1Password Device Trust (Kolide K2) API functionality:

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

## Query Parameter

Many list tools support a `query` parameter for filtering. The query syntax uses:
- `:` for exact matches (e.g., `status:failing`)
- `~` for partial string matches (e.g., `name~macbook`)
- `:[...]` for array matches (e.g., `status:["open","resolved"]`)

## Pagination

List tools return paginated results. Use the `cursor` from the response to fetch the next page:

```json
{
  "cursor": "next_page_cursor",
  "per_page": 25,
  ...
}
```

## Health Check

The server provides a health endpoint at `http://localhost:8000/health` that returns:
```json
{"status": "ok"}
```

## License

MIT
