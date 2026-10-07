"""Explicit, single-process public demo boundary; never grants domain authority."""

import hashlib
import time
from collections import defaultdict, deque
from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Request
from sqlalchemy import text
from starlette.requests import ClientDisconnect
from starlette.responses import FileResponse, JSONResponse

from app.commerce.errors import CommerceError

VISITOR_ACCOUNTS = ["customer.a", "customer.b", "owner.a", "owner.b", "staff.a", "demo", "dual.a"]
MAX_BODY = 4 * 1024 * 1024 + 65536


def install_public_demo(application, settings):
    enabled = settings.app_env == "production" and settings.commerce_public_demo

    @application.get("/api/commerce/v1/demo-info")
    def demo_info():
        return {
            "enabled": enabled,
            "accounts": VISITOR_ACCOUNTS if enabled else [],
            "password": settings.commerce_demo_password.get_secret_value() if enabled else None,
        }

    @application.get("/ready")
    def readiness():
        try:
            config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
            heads = set(ScriptDirectory.from_config(config).get_heads())
            with application.state.session_factory() as db:
                versions = set(db.scalars(text("SELECT version_num FROM alembic_version")))
                db.execute(text("SELECT 1"))
            if versions != heads:
                raise ValueError("Migration mismatch")
        except Exception:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {"status": "ready"}

    if not enabled:
        return
    counters = defaultdict(deque)
    login_active = 0

    def error(code, status):
        response = JSONResponse(
            CommerceError(status, code).payload(str(uuid4())), status_code=status
        )
        if status == 429:
            response.headers["Retry-After"] = "60"
        return response

    @application.middleware("http")
    async def demo_boundary(request: Request, call_next):
        nonlocal login_active
        path = request.url.path
        write = request.method not in {"GET", "HEAD", "OPTIONS"}
        login = path == "/api/commerce/v1/auth/login" and write
        blocked = write and (
            path.startswith("/api/commerce/v1/auth/")
            and path not in {"/api/commerce/v1/auth/login", "/api/commerce/v1/auth/logout"}
            or path
            in {
                "/api/commerce/v1/account/profile",
                "/api/commerce/v1/account/email",
                "/api/commerce/v1/account/password",
            }
            or path.startswith("/api/commerce/v1/customer/merchant-applications")
        )
        response = None
        acquired = False
        try:
            if blocked:
                response = error("PUBLIC_DEMO_DISABLED", 403)
            elif write:
                now = time.monotonic()
                for key in list(counters):
                    while counters[key] and counters[key][0] <= now - 60:
                        counters[key].popleft()
                    if not counters[key]:
                        del counters[key]
                token = hashlib.sha256(
                    request.headers.get("authorization", "").encode()
                ).hexdigest()
                ip = request.client.host if request.client else "unknown"
                keys = [
                    ("global", "login" if login else "write", 30 if login else 180),
                    ("ip-login" if login else "ip-write", ip, 30 if login else 90),
                    ("token", token, 90),
                ]
                if (
                    len(counters) > 4096
                    or any(len(counters[(kind, key)]) >= limit for kind, key, limit in keys)
                    or login
                    and login_active >= 2
                ):
                    response = error("RATE_LIMITED", 429)
                else:
                    for kind, key, _ in keys:
                        counters[(kind, key)].append(now)
                    if login:
                        login_active += 1
                        acquired = True
                    size = 0
                    chunks = []
                    async for chunk in request.stream():
                        size += len(chunk)
                        if size > MAX_BODY:
                            response = error("REQUEST_TOO_LARGE", 413)
                            break
                        chunks.append(chunk)
                    if response is None:
                        request._body = b"".join(chunks)
            response = response or await call_next(request)
        except (ClientDisconnect, OSError):
            response = error("INVALID_REQUEST", 400)
        finally:
            if acquired:
                login_active -= 1
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                "Strict-Transport-Security": "max-age=31536000",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; "
                "object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
            }
        )
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    if settings.commerce_static_dir is not None:
        root = settings.commerce_static_dir.resolve()
        index = (root / "index.html").resolve()
        if not root.is_dir() or not index.is_file() or not index.is_relative_to(root):
            raise ValueError("Public demo static directory must contain index.html")

        @application.get("/{asset_path:path}", include_in_schema=False)
        def frontend(asset_path: str):
            parts = Path(asset_path).parts
            if asset_path.startswith(("api/", "ready", "health")) or any(
                p.startswith(".") for p in parts
            ):
                return error("NOT_FOUND", 404)
            candidate = (root / asset_path).resolve()
            if not candidate.is_relative_to(root) or any(
                part.startswith(".") for part in candidate.relative_to(root).parts
            ):
                return error("NOT_FOUND", 404)
            if candidate.is_file():
                return FileResponse(candidate)
            if Path(asset_path).suffix or asset_path.startswith("assets/"):
                return error("NOT_FOUND", 404)
            return FileResponse(index)
