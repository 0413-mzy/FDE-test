"""Merchant-only conversation assistance endpoints."""

from uuid import uuid4

import anyio
from fastapi import APIRouter, Request
from sqlalchemy.exc import DBAPIError
from starlette.responses import JSONResponse

from app.commerce.ai_service import assistance, authority
from app.commerce.errors import CommerceError, fail
from app.commerce.router import bounded_body

router = APIRouter(prefix="/api/commerce/v1", tags=["conversation assistance"])
PATH = "/merchant/shops/{shop}/conversations/{conversation}/ai-assistance"


def endpoint(request: Request, shop: str, conversation: str):
    request.state.request_id = str(uuid4())
    replay = False
    try:
        origin = request.headers.get("origin")
        if origin is not None and origin not in request.app.state.settings.cors_allowed_origins:
            fail("CAPABILITY_REQUIRED", 403)
        # Resolve authority before reading input.
        with request.app.state.session_factory() as db, db.begin():
            authority(db, request)
        raw = anyio.from_thread.run(bounded_body, request) if request.method == "POST" else b""
        result, replay = assistance(request, request.method == "POST", raw)
        status = 200
    except CommerceError as error:
        result, status = error.payload(request.state.request_id), error.status
    except DBAPIError:
        result, status = CommerceError(409, "OPERATION_BUSY").payload(request.state.request_id), 409
    except Exception:
        result, status = CommerceError(500, "INTERNAL_ERROR").payload(request.state.request_id), 500
    response = JSONResponse(
        result,
        status_code=status,
        headers={"Cache-Control": "no-store", "X-Request-Id": request.state.request_id},
    )
    if replay:
        response.headers["Idempotent-Replay"] = "true"
    return response


for method in ("GET", "POST"):
    router.add_api_route(
        PATH,
        endpoint,
        methods=[method],
        name="merchant.conversation.ai-assistance." + method.lower(),
        openapi_extra={"security": [{"CommerceBearer": []}]},
    )
