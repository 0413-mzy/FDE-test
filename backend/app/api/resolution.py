"""HTTP orchestration commits reservation before any external await."""

import logging

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from app.api.contracts import ResolveInput, ResolveView
from app.api.errors import ApiError
from app.context.collector import Collection, collect
from app.core.security import bearer_token
from app.services.resolution import Reservation, ResolutionService

router = APIRouter(prefix="/api/v1")
logger = logging.getLogger(__name__)


def authorization(request):
    values = request.headers.getlist("authorization")
    header = values[0] if len(values) == 1 else None
    if bearer_token(header) is None:
        raise ApiError(401, "UNAUTHENTICATED")
    return header


async def transaction(request, action):
    def execute():
        try:
            with request.app.state.session_factory() as session, session.begin():
                service = ResolutionService(
                    session, request.app.state.clock, request.state.request_id
                )
                try:
                    return action(service)
                except ApiError as error:
                    return error
        except Exception:
            logger.warning("INTERNAL_ERROR request_id=%s", request.state.request_id)
            raise ApiError(500, "INTERNAL_ERROR") from None

    result = await run_in_threadpool(execute)
    if isinstance(result, ApiError):
        raise result
    return result


@router.post(
    "/inquiries/{id}/resolve-context",
    response_model=ResolveView,
    status_code=201,
    openapi_extra={
        "security": [{"BearerAuth": []}],
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": ResolveInput.model_json_schema()}},
        },
        "parameters": [
            {
                "name": "Idempotency-Key",
                "in": "header",
                "required": True,
                "schema": {"type": "string", "minLength": 1, "maxLength": 200},
            }
        ],
    },
    responses={200: {"model": ResolveView}, 202: {"model": ResolveView}},
)
async def resolve(request: Request):
    header = authorization(request)
    body = await request.body()
    result = await transaction(
        request,
        lambda service: service.start(
            header,
            request.path_params["id"],
            body,
            request.headers.get("content-type", ""),
            list(request.query_params.multi_items()),
            request.headers.getlist("idempotency-key"),
        ),
    )
    if not isinstance(result, Reservation):
        status, view = result
        return JSONResponse(
            view,
            status_code=status,
            headers={
                "Location": f"/api/v1/inquiries/{request.path_params['id']}/runs/{view['run_id']}"
            }
            if status == 202
            else {},
        )
    try:
        async with request.app.state.provider_factory() as providers:
            collection = (
                Collection([], "SOURCE_BINDING_MISMATCH")
                if providers.support_source_system != result.source_system
                else await collect(
                    providers,
                    result.external_inquiry_id,
                    result.external_order_id,
                    request.app.state.clock,
                    request.state.request_id,
                )
            )
    except Exception:
        logger.warning("INTERNAL_ERROR request_id=%s", request.state.request_id)
        raise ApiError(500, "INTERNAL_ERROR") from None
    view = await transaction(request, lambda service: service.finish(header, result, collection))
    return JSONResponse(view, status_code=201)


async def read(request, **options):
    header = authorization(request)
    body = await request.body()
    result = await transaction(
        request,
        lambda service: service.read(
            header,
            request.path_params["id"],
            body,
            list(request.query_params.multi_items()),
            **options,
        ),
    )
    return JSONResponse(result)


@router.get("/inquiries/{id}/runs/{run_id}", openapi_extra={"security": [{"BearerAuth": []}]})
async def run(request: Request):
    return await read(request, run_id=request.path_params["run_id"])


@router.get(
    "/inquiries/{id}/contexts/{context_id}", openapi_extra={"security": [{"BearerAuth": []}]}
)
async def context(request: Request):
    return await read(request, context_id=request.path_params["context_id"])
