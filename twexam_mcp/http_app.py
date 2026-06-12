# twexam_mcp/http_app.py
"""Authenticated HTTP entry point for remote (phone) use.

The streamable-http MCP app is wrapped with a bearer-token gate so that exposing
it through a Cloudflare Tunnel doesn't hand the server to anyone who guesses the
URL. Set TWEXAM_TOKEN to the shared secret the phone connector will send as
``Authorization: Bearer <token>``.
"""
from __future__ import annotations
import os

from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from twexam_mcp.server import mcp


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Reject any request whose Authorization header != 'Bearer <token>'.

    /health is left open so a tunnel / uptime check needs no secret.
    """

    def __init__(self, app, token: str):
        super().__init__(app)
        self._token = token

    async def dispatch(self, request, call_next):
        if request.url.path == "/health":
            return JSONResponse({"status": "ok"})
        if request.headers.get("authorization", "") != f"Bearer {self._token}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


def build_app():
    """Build the auth-gated ASGI app. Raises if no token is configured."""
    token = os.environ.get("TWEXAM_TOKEN")
    if not token:
        raise RuntimeError(
            "TWEXAM_TOKEN is not set — refusing to start an unauthenticated "
            "public server. Set it to a long random secret (the phone password)."
        )
    app = mcp.streamable_http_app()
    app.add_middleware(BearerAuthMiddleware, token=token)
    return app


def serve() -> None:
    """Run the authenticated server with uvicorn (called by server.main http branch)."""
    import uvicorn
    host = os.environ.get("TWEXAM_HOST", "127.0.0.1")
    port = int(os.environ.get("TWEXAM_PORT", "8000"))
    uvicorn.run(build_app(), host=host, port=port)
