"""
Security middleware for VenueFlow API.

Adds HTTP security headers to every response:
- Content-Security-Policy: blocks XSS, clickjacking, data injection
- Strict-Transport-Security: enforces HTTPS
- X-Content-Type-Options: prevents MIME sniffing
- X-Frame-Options: blocks framing
- Referrer-Policy: limits referrer leakage
- Permissions-Policy: disables unused browser APIs

Also adds request ID tracing for Cloud Logging correlation.
"""



import uuid
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to every HTTP response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()

        # Attach request ID for log correlation
        request.state.request_id = request_id

        response: Response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        # ── Security headers ──────────────────────────────────────────────
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )
        response.headers["Permissions-Policy"] = (
            "geolocation=(self), camera=(), microphone=(), payment=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "   # inline scripts for PWA
            "style-src 'self' 'unsafe-inline'; "
            "connect-src 'self' wss:; "             # WebSocket connections
            "img-src 'self' data: https://maps.googleapis.com; "
            "font-src 'self'; "
            "frame-ancestors 'none';"
        )

        # ── Structured Cloud Logging ──────────────────────────────────────
        logger.info(
            "request completed",
            extra={
                "httpRequest": {
                    "requestMethod": request.method,
                    "requestUrl": str(request.url),
                    "status": response.status_code,
                    "latency": f"{duration_ms}ms",
                    "userAgent": request.headers.get("user-agent", ""),
                    "remoteIp": request.client.host if request.client else "",
                },
                "requestId": request_id,
            },
        )

        return response


class RateLimitHeaderMiddleware(BaseHTTPMiddleware):
    """Adds rate limit info headers so clients can self-throttle."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        # slowapi sets X-RateLimit-* headers; we ensure they're always present
        if "X-RateLimit-Limit" not in response.headers:
            response.headers["X-RateLimit-Limit"] = "60"
        return response
