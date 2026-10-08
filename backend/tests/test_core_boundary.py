import base64
import json
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.errors import ApiError
from app.core.config import Settings
from app.core.security import (
    PASSWORD_HASHER,
    bearer_token,
    new_token,
    password_matches,
    token_digest,
)
from app.main import create_app
from app.services.core_access import login_body


def no_database():
    raise AssertionError("This boundary must not touch the database")


@pytest.mark.parametrize(
    "path",
    [
        "/auth/me?role=ADMIN",
        "/auth/logout",
        "/inquiries?limit=wrong",
        "/inquiries/not-a-uuid",
        "/inquiries/not-a-uuid/order",
    ],
)
@pytest.mark.parametrize("header", [None, "Basic invalid", "Bearer malformed"])
def test_unauthenticated_requests_precede_schema_validation_and_database(path, header):
    application = create_app(Settings(_env_file=None), session_factory=no_database)
    with TestClient(application) as client:
        response = client.request(
            "POST" if path == "/auth/logout" else "GET",
            "/api/v1" + path,
            headers={"Authorization": header} if header else {},
            content=b"invalid JSON",
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_health_and_openapi_do_not_connect_and_only_authorized_stage_4_routes_exist():
    application = create_app(Settings(_env_file=None), session_factory=no_database)
    with TestClient(application) as client:
        assert client.get("/health").json()["status"] == "ok"
        schema = client.get("/openapi.json").json()
        future = client.post("/api/v1/inquiries/invalid/approve")
    assert {
        path for path in schema["paths"] if path.startswith("/api/v1/") or path == "/health"
    } == {
        "/health",
        "/api/v1/auth/login",
        "/api/v1/auth/me",
        "/api/v1/auth/logout",
        "/api/v1/inquiries",
        "/api/v1/inquiries/{id}",
        "/api/v1/inquiries/{id}/order",
        "/api/v1/inquiries/{id}/resolve-context",
        "/api/v1/inquiries/{id}/runs/{run_id}",
        "/api/v1/inquiries/{id}/contexts/{context_id}",
    }
    assert schema["components"]["securitySchemes"]["BearerAuth"]["scheme"] == "bearer"
    assert schema["paths"]["/api/v1/auth/me"]["get"]["security"] == [{"BearerAuth": []}]
    login_schema = schema["paths"]["/api/v1/auth/login"]["post"]["requestBody"]
    assert login_schema["content"]["application/json"]["schema"]["additionalProperties"] is False
    assert future.status_code == 404
    assert future.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.parametrize("supplied", ["req-valid_12.test", "", "contains space", "a" * 101])
def test_request_id_is_validated_and_echoed(supplied):
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.get("/api/v1/auth/me", headers={"X-Request-Id": supplied})
    request_id = response.headers["x-request-id"]
    assert response.json()["error"]["request_id"] == request_id
    if supplied == "req-valid_12.test":
        assert request_id == supplied
    else:
        assert UUID(request_id)


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "null",
        "https://a.test/path",
        "https://a.test?q=1",
        "https://name:secret@a.test",
        "https://a.test/#part",
    ],
)
def test_cors_configuration_rejects_non_origins(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_allowed_origins=[origin])


def test_explicit_cors_preflight_and_unknown_origin_never_reach_database():
    application = create_app(
        Settings(_env_file=None, cors_allowed_origins=["http://localhost:5173"]),
        session_factory=no_database,
    )
    with TestClient(application) as client:
        allowed = client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": (
                    "authorization,content-type,x-request-id,idempotency-key"
                ),
            },
        )
        denied = client.post(
            "/api/v1/auth/login",
            headers={"Origin": "https://unknown.test"},
            json={"username": "agent.a", "password": new_token()},
        )
        preflight = client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://unknown.test",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert allowed.status_code == 200
    assert "idempotency-key" in allowed.headers["access-control-allow-headers"].lower()
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-credentials" not in allowed.headers
    for response in (denied, preflight):
        assert response.status_code == 403
        assert "access-control-allow-origin" not in response.headers
        assert response.headers["cache-control"] == "no-store"


def test_database_failure_does_not_disclose_exception_or_configuration(caplog):
    sensitive = new_token()

    def failed_database():
        raise RuntimeError("connection password=" + sensitive)

    application = create_app(Settings(_env_file=None), session_factory=failed_database)
    with TestClient(application) as client:
        response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + new_token()})
        assert client.get("/health").status_code == 200
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert sensitive not in response.text + caplog.text
    assert "INTERNAL_ERROR" in caplog.text
    assert response.headers["x-request-id"] in caplog.text


def test_password_and_token_material():
    secret = new_token() + " "
    hashed = PASSWORD_HASHER.hash(secret)
    assert password_matches(hashed, secret)
    assert not password_matches(hashed, secret.strip())
    assert not password_matches(None, secret)
    assert not password_matches("invalid stored hash", secret)
    tokens = [new_token() for _ in range(10)]
    assert len(set(tokens)) == 10
    for token in tokens:
        assert len(base64.urlsafe_b64decode(token + "=")) == 32
        assert len(token_digest(token)) == 64 and token_digest(token) != token
        assert bearer_token("bEaReR " + token) == token
        assert bearer_token("Bearer " + token + " extra") is None


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b"[]",
        b"null",
        b'{"username":"agent.a","password":"x","role":"ADMIN"}',
        b'{"username":"agent.a","username":"admin","password":"x"}',
        b'{"username":"agent.a","password":12}',
        b'{"username":"a","password":"x"}',
    ],
)
def test_login_schema_closed_and_errors_do_not_echo_inputs(body):
    with pytest.raises(ApiError) as result:
        login_body(body, "application/json")
    assert result.value.status == 422
    assert "input" not in result.value.details


def test_login_password_is_not_trimmed_or_echoed_in_validation_error():
    secret = new_token()
    data = login_body(
        json.dumps({"username": "agent.a", "password": " " + secret + " "}).encode(),
        "application/json; charset=utf-8",
    )
    assert data.password == " " + secret + " " and secret not in repr(data)
    with pytest.raises(ApiError) as result:
        login_body(
            json.dumps({"username": "agent.a", "password": secret * 4}).encode(), "application/json"
        )
    assert result.value.details == {"field_errors": ["password"]}
    assert secret not in json.dumps(result.value.payload("req-test"))


def test_commerce_additive_endpoint_inventory_is_separate_and_closed():
    with TestClient(create_app(Settings(_env_file=None), session_factory=no_database)) as client:
        schema = client.get("/openapi.json").json()
    paths = {
        path.removeprefix("/api/commerce/v1")
        for path in schema["paths"]
        if path.startswith("/api/commerce/v1")
    }
    assert paths == {
        "/merchant/shops/{shop}/conversations/{conversation}/ai-assistance",
        "/auth/register",
        "/auth/verify-email",
        "/auth/verification-request",
        "/auth/password-reset/request",
        "/auth/password-reset/confirm",
        "/account/profile",
        "/account/email",
        "/account/password",
        "/customer/addresses",
        "/customer/addresses/{id}/edit",
        "/customer/addresses/{id}/delete",
        "/customer/merchant-applications",
        "/customer/merchant-applications/{id}/withdraw",
        "/review/merchant-applications",
        "/review/merchant-applications/{id}/decision",
        "/auth/login",
        "/auth/me",
        "/auth/logout",
        "/catalog/products",
        "/catalog/products/{product}",
        "/merchant/shops",
        "/merchant/shops/{shop}/products",
        "/merchant/shops/{shop}/products/{product}",
        "/merchant/shops/{shop}/products/{product}/edit",
        "/merchant/shops/{shop}/products/{product}/publish",
        "/merchant/shops/{shop}/products/{product}/archive",
        "/merchant/shops/{shop}/products/{product}/skus",
        "/merchant/shops/{shop}/products/{product}/skus/{sku}/edit",
        "/merchant/shops/{shop}/inventory/{sku}",
        "/merchant/shops/{shop}/inventory/{sku}/adjust",
        "/customer/cart",
        "/customer/cart/lines",
        "/customer/cart/lines/{sku}",
        "/customer/checkouts",
        "/customer/checkouts/{checkout}",
        "/customer/orders",
        "/customer/orders/{order}",
        "/customer/orders/{order}/address",
        "/customer/orders/{order}/cancel",
        "/customer/orders/{order}/payments",
        "/customer/orders/{order}/confirm-receipt",
        "/merchant/shops/{shop}/orders",
        "/merchant/shops/{shop}/orders/{order}",
        "/merchant/shops/{shop}/orders/{order}/shipments",
        "/customer/orders/{order}/shipments/{shipment}",
        "/merchant/shops/{shop}/orders/{order}/shipments/{shipment}",
        "/customer/conversations",
        "/merchant/shops/{shop}/conversations",
        "/customer/conversations/{conversation}/messages",
        "/merchant/shops/{shop}/conversations/{conversation}/messages",
        "/customer/orders/{order}/after-sales",
        "/customer/orders/{order}/after-sales/{case}",
        "/merchant/shops/{shop}/orders/{order}/after-sales/{case}",
        "/customer/orders/{order}/after-sales/{case}/withdraw",
        "/customer/orders/{order}/after-sales/{case}/return",
        "/merchant/shops/{shop}/orders/{order}/after-sales/{case}/decision",
        "/merchant/shops/{shop}/orders/{order}/after-sales/{case}/receive-return",
        "/merchant/shops/{shop}/orders/{order}/after-sales/{case}/refunds",
        "/demo/refunds/{attempt}/result",
        "/demo/pending",
        "/demo/payments/{attempt}/result",
        "/demo/shipments",
        "/demo/shipments/{shipment}",
        "/demo/shipments/{shipment}/events",
        "/demo/orders/expire",
        "/customer/disputes",
        "/customer/disputes/{id}/evidence",
        "/customer/disputes/{id}/withdraw",
        "/customer/favorites",
        "/customer/orders/{order_id}/lines/{line_id}/review",
        "/customer/orders/{order}/after-sales/{case}/dispute",
        "/customer/orders/{order}/after-sales/{case}/dispute-eligibility",
        "/customer/reports",
        "/customer/reviews/{review_id}/edit",
        "/merchant/shops/{shop_id}/products/{product_id}/experience",
        "/merchant/shops/{shop_id}/products/{product_id}/experience/images",
        "/merchant/shops/{shop_id}/products/{product_id}/experience/images/{image_id}/delete",
        "/merchant/shops/{shop_id}/reviews",
        "/merchant/shops/{shop_id}/reviews/{review_id}/reply",
        "/merchant/shops/{shop}/analytics",
        "/merchant/shops/{shop}/disputes",
        "/merchant/shops/{shop}/disputes/{id}/evidence",
        "/platform/access",
        "/platform/data/access",
        "/platform/data/resources",
        "/platform/data/resources/{resource}",
        "/platform/data/resources/{resource}/{record_id}",
        "/platform/data/history",
        "/platform/accounts",
        "/platform/analytics",
        "/platform/categories",
        "/platform/categories/{id}/edit",
        "/platform/disputes",
        "/platform/disputes/{id}/decision",
        "/platform/disputes/{id}/refunds",
        "/platform/moderation",
        "/platform/products",
        "/platform/reports",
        "/platform/reports/{id}/decision",
        "/platform/reviews",
        "/platform/shops",
        "/shopping/categories",
        "/shopping/images/{image_id}",
        "/shopping/products",
        "/shopping/products/{product_id}",
        "/shopping/products/{product_id}/reviews",
        "/shopping/shops",
        "/platform/actions",
        "/platform/disputes/{id}/context",
        "/demo-info",
    }
    assert schema["paths"]["/api/commerce/v1/auth/me"]["get"]["security"] == [
        {"CommerceBearer": []}
    ]
    assert schema["components"]["securitySchemes"]["CommerceBearer"]["scheme"] == "bearer"
    for path, methods in schema["paths"].items():
        if not path.startswith("/api/commerce/v1"):
            continue
        for method in methods.values():
            for name in __import__("re").findall(r"{(\w+)}", path):
                assert any(p["name"] == name and p["in"] == "path" for p in method["parameters"])
