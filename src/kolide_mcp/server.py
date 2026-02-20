"""1Password Device Trust (Kolide K2) MCP Server with Streamable HTTP transport."""

import json
import os
from typing import Any

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool

from .client import KolideClient, KolideAPIError
from .endpoints import (
    ENDPOINT_MAP,
    EndpointSpec,
    build_all_tools,
    get_path_params,
)

server = Server("kolide-1password-device-trust")
client = KolideClient()

TOOLS = build_all_tools()


def _format_result(result: Any) -> str:
    """Format API result as JSON string."""
    return json.dumps(result, indent=2, default=str)


async def _dispatch(spec: EndpointSpec, args: dict[str, Any]) -> Any:
    """Execute an API call derived from an EndpointSpec and the tool arguments."""
    # Resolve path parameters
    path = spec.path
    for pname in get_path_params(spec.path):
        path = path.replace(f"{{{pname}}}", str(args[pname]))

    # Query-string params for paginated list endpoints
    params: dict[str, Any] | None = None
    if spec.paginated:
        params = {
            "cursor": args.get("cursor"),
            "per_page": args.get("per_page"),
        }
        if spec.searchable_fields:
            params["query"] = args.get("query")

    # Request body for write operations
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

    return await client.request(spec.method, path, params=params, json_data=json_data)


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools."""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    try:
        spec = ENDPOINT_MAP.get(name)
        if not spec:
            raise ValueError(f"Unknown tool: {name}")
        result = await _dispatch(spec, arguments)
        return [TextContent(type="text", text=_format_result(result))]
    except KolideAPIError as e:
        return [TextContent(type="text", text=f"Error: {e.message} (status: {e.status_code})")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


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
