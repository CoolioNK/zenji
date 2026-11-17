"""Sicherheits-Header für den Produktivbetrieb hinter Cloudflare Pages."""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

CSP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "img-src 'self' data: https:; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "script-src 'self'; "
    "connect-src 'self' https://*.supabase.co wss://*.supabase.co; "
    "upgrade-insecure-requests"
)

_REFERRER_POLICY = "strict-origin-when-cross-origin"
_X_CONTENT_TYPE_OPTIONS = "nosniff"
_X_FRAME_OPTIONS = "DENY"
_PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=()"


class SecurityHeadersMiddleware:
    """Fügt sichere Standard-Header hinzu, ohne den App-Flow zu verändern."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {key.lower() for key, _ in headers}
                values = {
                    b"content-security-policy": CSP.encode("utf-8"),
                    b"referrer-policy": _REFERRER_POLICY.encode("ascii"),
                    b"x-content-type-options": _X_CONTENT_TYPE_OPTIONS.encode("ascii"),
                    b"x-frame-options": _X_FRAME_OPTIONS.encode("ascii"),
                    b"permissions-policy": _PERMISSIONS_POLICY.encode("ascii"),
                }
                for key, value in values.items():
                    if key not in present:
                        headers.append((key, value))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


__all__ = ["SecurityHeadersMiddleware"]