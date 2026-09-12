"""Small HTTP boundary for the single-operator demo; no external calls."""

from __future__ import annotations

import secrets
from ipaddress import ip_address

from starlette.responses import JSONResponse

MAX_REQUEST_BYTES = 16_384

# Every path that costs something to answer: case data, model quota, or the CPU
# of a propagation. Listed in one place because an endpoint added outside it is
# unauthenticated, unbounded and cross-origin by omission rather than by
# decision -- which is how /ingest and /interop were briefly served.
PROTECTED_PREFIXES = ("/cases", "/runs", "/context", "/ingest", "/interop")


class APIGuard:
    """Protect case data/model quota and bound JSON bodies before parsing."""

    def __init__(self, app, token: str, origins: list[str], require_remote_token: bool):
        self.app = app
        self.token = token
        self.origins = set(origins)
        self.require_remote_token = require_remote_token

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        is_api = any(
            path == prefix or path.startswith(prefix + "/")
            for prefix in PROTECTED_PREFIXES
        )
        if scope["type"] != "http" or not is_api or scope.get("method") == "OPTIONS":
            return await self.app(scope, receive, send)

        async def refuse(status, code, message):
            await JSONResponse({"detail": {"error": code, "message": message}}, status_code=status)(scope, receive, send)

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        host = headers.get("host", "")
        origin = headers.get("origin")
        same_origin = f"{scope.get('scheme', 'http')}://{host}"
        if origin and origin != same_origin and origin not in self.origins:
            return await refuse(403, "ORIGIN_DENIED", "This browser origin is not permitted.")
        if self.token:
            supplied = headers.get("authorization", "")
            if not secrets.compare_digest(supplied.encode(), f"Bearer {self.token}".encode()):
                return await refuse(401, "ACCESS_REQUIRED", "Enter the operator access token.")
        elif self.require_remote_token:
            try:
                local_client = ip_address((scope.get("client") or ("",))[0]).is_loopback
            except ValueError:
                local_client = False
            if not local_client:
                return await refuse(503, "ACCESS_NOT_CONFIGURED", "Set DESK_ACCESS_TOKEN before exposing this API remotely.")

        # Read only the small request body, never buffer responses/trajectory bundles.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > MAX_REQUEST_BYTES:
                return await refuse(413, "REQUEST_TOO_LARGE", "Request exceeds the 16 KiB limit.")
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)
