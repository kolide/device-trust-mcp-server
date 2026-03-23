"""1Password Device Trust (Kolide K2) MCP Server with Streamable HTTP transport."""

import contextvars
import json
import logging
import os
from typing import Any

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Resource, TextContent, Tool

from .client import KolideClient, KolideAPIError
from .composite_tools import COMPOSITE_HANDLERS, COMPOSITE_TOOLS
from .config import ServerConfig
from .logging_config import setup_logging
from .endpoints import (
    ENDPOINT_MAP,
    EndpointSpec,
    build_all_tools,
    get_path_params,
)
from .resources import RESOURCES, get_resource_content

server = Server("kolide-1password-device-trust")
client = KolideClient()
config = ServerConfig()
logger = logging.getLogger("kolide_mcp")

# Carries the source IP of the current HTTP request into the MCP tool handler.
_request_ip: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_ip", default="unknown"
)

MAX_FETCH_ALL = 10_000
MAX_FETCH_ALL_PAGES = 50

TOOLS = build_all_tools() + COMPOSITE_TOOLS


def _format_result(result: Any) -> str:
    """Format API result as JSON string."""
    return json.dumps(result, indent=2, default=str)


async def _dispatch(spec: EndpointSpec, args: dict[str, Any]) -> Any:
    """Execute an API call derived from an EndpointSpec and the tool arguments."""
    path = spec.path
    for pname in get_path_params(spec.path):
        path = path.replace(f"{{{pname}}}", str(args[pname]))

    params: dict[str, Any] | None = None
    if spec.paginated:
        params = {
            "cursor": args.get("cursor"),
            "per_page": args.get("per_page"),
        }
        if spec.searchable_fields:
            params["query"] = args.get("query")

    json_data: Any = None
    if spec.method in ("POST", "PATCH", "PUT"):
        if spec.body_param:
            json_data = args.get(spec.body_param)
        else:
            path_param_set = set(get_path_params(spec.path))
            body: dict[str, Any] = {}
            for param in spec.params:
                if param.name not in path_param_set:
                    val = args.get(param.name)
                    if val is not None:
                        body[param.name] = val
            json_data = body if body else None

    result = await client.request(spec.method, path, params=params, json_data=json_data)

    if args.get("fetch_all") and spec.paginated and isinstance(result, dict):
        all_data = list(result.get("data", []))
        pages = 1
        while (
            result.get("pagination", {}).get("next_cursor")
            and len(all_data) < MAX_FETCH_ALL
            and pages < MAX_FETCH_ALL_PAGES
        ):
            params["cursor"] = result["pagination"]["next_cursor"]
            result = await client.request(spec.method, path, params=params)
            all_data.extend(result.get("data", []))
            pages += 1
        result = {
            "data": all_data,
            "total_count": len(all_data),
            "pages_fetched": pages,
            "truncated": len(all_data) >= MAX_FETCH_ALL or pages >= MAX_FETCH_ALL_PAGES,
        }

    return result


def _extract_device_id(record: dict[str, Any]) -> str | None:
    """Extract device_id from a record, handling both flat and nested formats."""
    dev_id = record.get("device_id")
    if dev_id is not None:
        return str(dev_id)
    dev_info = record.get("device_information")
    if isinstance(dev_info, dict):
        ident = dev_info.get("identifier")
        if ident is not None:
            return str(ident)
    return None


async def _enrich_device_owners(records: list[dict[str, Any]]) -> None:
    """Enrich records in-place with owner_name and owner_email fields."""
    owner_cache: dict[str, dict[str, str]] = {}

    for record in records:
        dev_id = _extract_device_id(record)
        if not dev_id:
            continue

        if dev_id not in owner_cache:
            try:
                device = await client.request("GET", f"/devices/{dev_id}")
                person_id = device.get("registered_owner_info", {}).get("identifier")
                if person_id:
                    person = await client.request("GET", f"/people/{person_id}")
                    owner_cache[dev_id] = {
                        "owner_name": person.get("name", ""),
                        "owner_email": person.get("email", ""),
                    }
                else:
                    owner_cache[dev_id] = {}
            except KolideAPIError:
                owner_cache[dev_id] = {}

        if owner_cache[dev_id]:
            record.update(owner_cache[dev_id])


def _apply_field_projection(result: dict[str, Any], fields: list[str]) -> None:
    """Filter records in-place to only include requested fields."""
    field_set = set(fields)
    result["data"] = [
        {k: v for k, v in item.items() if k in field_set}
        for item in result["data"]
    ]


def _coerce_bool(value: Any) -> bool:
    """Coerce a value to boolean, handling string representations."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)


def _coerce_field_list(value: Any) -> list[str]:
    """Coerce a value to a list of field names, handling CSV strings and JSON."""
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        import json as _json
        try:
            parsed = _json.loads(value)
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        except (ValueError, TypeError):
            pass
        return [f.strip() for f in value.split(",") if f.strip()]
    return []


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools."""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    logger.info(
        "tool_call",
        extra={
            "extra": {
                "tool": name,
                "arg_keys": sorted(arguments.keys()),
                "src": _request_ip.get(),
            }
        },
    )
    try:
        handler = COMPOSITE_HANDLERS.get(name)
        if handler:
            result = await handler(client, arguments)
            return [TextContent(type="text", text=_format_result(result))]

        spec = ENDPOINT_MAP.get(name)
        if not spec:
            raise ValueError(f"Unknown tool: {name}")

        fetch_all = _coerce_bool(arguments.get("fetch_all", False))
        enrich = _coerce_bool(arguments.get("enrich_device_owner", False))
        raw_fields = arguments.get("fields")
        projected_fields = _coerce_field_list(raw_fields) if raw_fields else None

        coerced_args = {**arguments, "fetch_all": fetch_all}
        result = await _dispatch(spec, coerced_args)

        if isinstance(result, dict) and "data" in result:
            if enrich:
                records = result["data"]
                cap = config.max_enrich_records
                await _enrich_device_owners(records[:cap])
                if len(records) > cap:
                    result["enrichment_truncated"] = True
                    result["enrichment_limit"] = cap
            if projected_fields:
                _apply_field_projection(result, projected_fields)

        return [TextContent(type="text", text=_format_result(result))]
    except KolideAPIError as e:
        return [TextContent(type="text", text=f"Error: {e.message} (status: {e.status_code})")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """List available reference documentation resources."""
    return RESOURCES


@server.read_resource()
async def handle_read_resource(uri) -> str:
    """Read a reference documentation resource."""
    return get_resource_content(str(uri))


def create_app():
    """Create the Starlette application with Streamable HTTP transport."""
    from contextlib import asynccontextmanager
    from starlette.applications import Starlette
    from starlette.middleware.cors import CORSMiddleware
    from starlette.routing import Route, Mount
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response

    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=True,
        stateless=True,
    )

    @asynccontextmanager
    async def lifespan(app):
        async with session_manager.run():
            try:
                yield
            finally:
                await client.close()

    async def health_check(request: Request):
        return JSONResponse({"status": "ok"})

    async def mcp_asgi_app(scope, receive, send):
        await session_manager.handle_request(scope, receive, send)

    app = Starlette(
        debug=config.debug,
        lifespan=lifespan,
        routes=[
            Route("/health", health_check, methods=["GET"]),
            Mount("/mcp", app=mcp_asgi_app),
            Mount("/sse", app=mcp_asgi_app),
        ],
    )

    # Restrict CORS to explicitly configured origins. Native MCP clients such as
    # Claude Desktop do not trigger CORS; this covers browser-based MCP clients.
    # Configure allowed origins via MCP_CORS_ALLOWED_ORIGINS (comma-separated).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_allowed_origins,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "mcp-session-id", "last-event-id"],
    )

    # Capture source IP per-request so the tool handler can include it in audit logs.
    from starlette.middleware.base import BaseHTTPMiddleware as _BaseHTTPMiddleware

    class RequestContextMiddleware(_BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            _request_ip.set(request.client.host if request.client else "unknown")
            return await call_next(request)

    app.add_middleware(RequestContextMiddleware)

    # Require a bearer token on all MCP endpoints. /health is exempt so
    # monitoring can run without credentials.
    if config.auth_token:
        from starlette.middleware.base import BaseHTTPMiddleware

        class BearerAuthMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                if request.url.path == "/health":
                    return await call_next(request)
                auth = request.headers.get("Authorization", "")
                if not auth.startswith("Bearer ") or auth[7:] != config.auth_token:
                    return JSONResponse({"error": "Unauthorized"}, status_code=401)
                return await call_next(request)

        app.add_middleware(BearerAuthMiddleware)

    return app


def main():
    """Run the MCP server with Streamable HTTP transport."""
    import sys
    import uvicorn

    setup_logging(config.log_file)

    if not config.auth_token:
        print(
            "ERROR: MCP_AUTH_TOKEN is not set. The MCP server requires an authentication token.\n"
            "Generate one with:  python -c \"import secrets; print(secrets.token_hex(32))\"\n"
            "Then set it in your .env file and your MCP client configuration.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Starting 1Password Device Trust MCP server on {config.host}:{config.port}")
    print(f"MCP endpoint: http://{config.host}:{config.port}/mcp")
    print(f"Health check: http://{config.host}:{config.port}/health")

    app = create_app()
    uvicorn.run(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
