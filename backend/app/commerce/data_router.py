"""GET-only inspection routes; database transactions cannot write."""

from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from starlette.responses import JSONResponse

from app.commerce import data_center as data
from app.commerce.errors import CommerceError, fail
from app.commerce.service import Commerce

router = APIRouter(prefix="/api/commerce/v1/platform/data", tags=["private data center"])


def read(request, kind, name=None, rid=None):
    request.state.request_id = str(uuid4())
    headers = {"Cache-Control": "no-store", "X-Request-Id": request.state.request_id}
    try:
        with request.app.state.session_factory() as db, db.begin():
            db.execute(text("SET TRANSACTION READ ONLY"))
            db.execute(text("SET LOCAL statement_timeout='3000ms'"))
            svc = Commerce(db, request.app.state.clock, request)
            data.private_authorize(svc)
            params = dict(request.query_params)
            if kind in ("access", "resources"):
                if params:
                    fail("INVALID_REQUEST", 400)
                result = (
                    {
                        "platform_enabled": True,
                        "read_only": True,
                        "environment": request.app.state.settings.app_env,
                        "public_demo": request.app.state.settings.commerce_public_demo,
                    }
                    if kind == "access"
                    else data.directory(db)
                )
            elif kind == "history":
                result = data.history(db, params)
            elif kind == "list":
                result = data.listing(db, name, params)
            else:
                result = data.detail(db, name, rid, params)
        return JSONResponse(jsonable_encoder(result), headers=headers)
    except CommerceError as error:
        return JSONResponse(
            error.payload(request.state.request_id),
            status_code=error.status,
            headers=headers,
        )
    except DBAPIError:
        return JSONResponse(
            CommerceError(503, "DATA_READ_UNAVAILABLE").payload(request.state.request_id),
            status_code=503,
            headers=headers,
        )

    except Exception:
        return JSONResponse(
            CommerceError(500, "INTERNAL_ERROR").payload(request.state.request_id),
            status_code=500,
            headers=headers,
        )


@router.get("/access")
def access(request: Request):
    return read(request, "access")


@router.get("/resources")
def resources(request: Request):
    return read(request, "resources")


@router.get("/history")
def history(request: Request):
    return read(request, "history")


@router.get("/resources/{resource}")
def records(resource: str, request: Request):
    return read(request, "list", resource)


@router.get("/resources/{resource}/{record_id}")
def record(resource: str, record_id: str, request: Request):
    return read(request, "detail", resource, record_id)
