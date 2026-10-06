"""HTTP bridge; authentication precedes manual request-schema validation."""

import logging
from collections.abc import Callable

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, Response

from app.api.contracts import InquiryList, InquiryView, LoginInput, LoginView, UserView
from app.api.errors import ApiError
from app.core.security import bearer_token
from app.services.core_access import CoreAccess

router = APIRouter(prefix="/api/v1")
SECURITY = {"security": [{"BearerAuth": []}]}
logger = logging.getLogger(__name__)


async def invoke(request: Request, action: Callable, *, login: bool = False) -> Response:
    headers = request.headers.getlist("authorization")
    authorization = headers[0] if len(headers) == 1 else None
    if not login and bearer_token(authorization) is None:
        raise ApiError(401, "UNAUTHENTICATED")
    body = await request.body()
    query = list(request.query_params.multi_items())

    def transaction():
        try:
            with request.app.state.session_factory() as session, session.begin():
                service = CoreAccess(session, request.app.state.clock, request.state.request_id)
                try:
                    result = action(service, authorization, body, query)
                except ApiError as exc:
                    # Persist safe login/access-denied audits; unexpected failures roll back.
                    result = exc
        except Exception:
            # Database errors may contain parameters/config; do not log or disclose them.
            logger.warning("INTERNAL_ERROR request_id=%s", request.state.request_id)
            raise ApiError(500, "INTERNAL_ERROR") from None
        if isinstance(result, ApiError):
            raise result
        return result

    result = await run_in_threadpool(transaction)
    if result is None:
        return Response(status_code=204)
    return JSONResponse(result.model_dump(mode="json"))


@router.post(
    "/auth/login",
    response_model=LoginView,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": LoginInput.model_json_schema()}},
        }
    },
)
async def login(request: Request):
    return await invoke(
        request,
        lambda service, _, body, query: service.login(
            body, request.headers.get("content-type", ""), query
        ),
        login=True,
    )


@router.get("/auth/me", response_model=UserView, openapi_extra=SECURITY)
async def me(request: Request):
    return await invoke(
        request, lambda service, header, body, query: service.me(header, body, query)
    )


@router.post("/auth/logout", status_code=204, openapi_extra=SECURITY)
async def logout(request: Request):
    return await invoke(
        request, lambda service, header, body, query: service.logout(header, body, query)
    )


@router.get(
    "/inquiries",
    response_model=InquiryList,
    openapi_extra={
        **SECURITY,
        "parameters": [
            {
                "name": "limit",
                "in": "query",
                "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
            {
                "name": "offset",
                "in": "query",
                "schema": {"type": "integer", "minimum": 0, "default": 0},
            },
        ],
    },
)
async def inquiries(request: Request):
    return await invoke(
        request, lambda service, header, body, query: service.list_inquiries(header, body, query)
    )


PATH_ID = {
    "name": "id",
    "in": "path",
    "required": True,
    "schema": {"type": "string", "format": "uuid"},
}


@router.get(
    "/inquiries/{id}",
    response_model=InquiryView,
    openapi_extra={**SECURITY, "parameters": [PATH_ID]},
)
async def inquiry(request: Request):
    return await invoke(
        request,
        lambda service, header, body, query: service.read_inquiry(
            header, request.path_params["id"], body, query
        ),
    )


@router.get(
    "/inquiries/{id}/order",
    openapi_extra={**SECURITY, "parameters": [PATH_ID]},
    responses={409: {"description": "CONTEXT_REQUIRED (Stage 4 reads the current snapshot)"}},
)
async def order(request: Request):
    from app.api.resolution import read

    return await read(request, order=True)
