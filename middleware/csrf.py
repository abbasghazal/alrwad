import os

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        enabled = os.getenv("CSRF_PROTECTION", "false").lower() == "true"
        unsafe_method = request.method in {"POST", "PUT", "PATCH", "DELETE"}
        uses_cookie_auth = "session" in request.cookies or "refresh_token" in request.cookies
        if enabled and unsafe_method and uses_cookie_auth:
            csrf_cookie = request.cookies.get("csrf_token")
            csrf_header = request.headers.get("x-csrf-token")
            if not csrf_cookie or csrf_cookie != csrf_header:
                raise HTTPException(status_code=403, detail="CSRF token is missing or invalid")
        return await call_next(request)
