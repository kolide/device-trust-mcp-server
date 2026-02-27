"""1Password Device Trust (Kolide K2) MCP Server with Streamable HTTP transport."""

import json
import os
from typing import Any

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Resource, TextContent, Tool

from .client import KolideClient, KolideAPIError
from .composite_tools import COMPOSITE_HANDLERS, COMPOSITE_TOOLS
from .endpoints import (
    ENDPOINT_MAP,
    EndpointSpec,
    build_all_tools,
    get_path_params,
)
from .resources import RESOURCES, get_resource_content

server = Server("kolide-1password-device-trust")
client = KolideClient()

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
    """Enrich records in-place with owner_name and owner_email fields.

    Fetches device and person data concurrently in two batched rounds
    instead of issuing sequential calls per record.
    """
    import asyncio

    unique_device_ids = {
        did for r in records if (did := _extract_device_id(r))
    }
    if not unique_device_ids:
        return

    semaphore = asyncio.Semaphore(10)

    async def _fetch_device(dev_id: str) -> tuple[str, dict[str, Any] | None]:
        async with semaphore:
            try:
                return (dev_id, await client.request("GET", f"/devices/{dev_id}"))
            except KolideAPIError:
                return (dev_id, None)

    device_results = await asyncio.gather(
        *[_fetch_device(did) for did in unique_device_ids]
    )

    person_to_devices: dict[str, list[str]] = {}
    for dev_id, device in device_results:
        if device is None:
            continue
        person_id = device.get("registered_owner_info", {}).get("identifier")
        if person_id:
            person_to_devices.setdefault(str(person_id), []).append(dev_id)

    async def _fetch_person(person_id: str) -> tuple[str, dict[str, Any] | None]:
        async with semaphore:
            try:
                return (person_id, await client.request("GET", f"/people/{person_id}"))
            except KolideAPIError:
                return (person_id, None)

    person_results = await asyncio.gather(
        *[_fetch_person(pid) for pid in person_to_devices]
    )

    owner_cache: dict[str, dict[str, str]] = {}
    for person_id, person in person_results:
        if person is None:
            continue
        owner_info = {
            "owner_name": person.get("name", ""),
            "owner_email": person.get("email", ""),
        }
        for dev_id in person_to_devices[person_id]:
            owner_cache[dev_id] = owner_info

    for record in records:
        dev_id = _extract_device_id(record)
        if dev_id and dev_id in owner_cache:
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
                await _enrich_device_owners(result["data"])
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
        """ASGI app that handles OPTIONS and delegates to session manager."""
        if scope["type"] == "http":
            method = scope.get("method", "")
            if method == "OPTIONS":
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
        await session_manager.handle_request(scope, receive, send)

    debug = os.getenv("MCP_DEBUG", "false").lower() == "true"

    app = Starlette(
        debug=debug,
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
