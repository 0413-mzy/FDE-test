import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings


def test_production_demo_requires_origin_and_distinct_passwords():
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_env="production", commerce_public_demo=True)


def test_disabled_info_contains_no_credentials():
    from app.commerce.public_demo import install_public_demo

    app = FastAPI()
    install_public_demo(app, Settings(_env_file=None))
    assert TestClient(app).get("/api/commerce/v1/demo-info").json() == {
        "enabled": False,
        "accounts": [],
        "password": None,
    }


def public_settings(**kw):
    return Settings(
        _env_file=None,
        app_env="production",
        commerce_public_demo=True,
        commerce_public_origin="https://demo.example.test",
        commerce_demo_password="public-fictional-password",
        commerce_operator_password="private-operator-secret-12345",
        **kw,
    )


def test_public_guards_body_rate_and_credentials(tmp_path):
    from app.commerce.public_demo import MAX_BODY, install_public_demo

    app = FastAPI()
    calls = []

    @app.post("/api/commerce/v1/auth/register")
    def register():
        calls.append(True)
        return {"ok": True}

    @app.post("/api/commerce/v1/auth/login")
    async def login(request: __import__("fastapi").Request):
        return {"bytes": len(await request.body())}

    (tmp_path / "index.html").write_text("<html>demo</html>")
    (tmp_path / ".secret").write_text("private")
    (tmp_path / "alias.txt").symlink_to(tmp_path / ".secret")
    install_public_demo(app, public_settings(commerce_static_dir=tmp_path))
    client = TestClient(app)
    info = client.get("/api/commerce/v1/demo-info")
    assert info.json()["accounts"] == [
        "customer.a",
        "customer.b",
        "owner.a",
        "owner.b",
        "staff.a",
        "demo",
        "dual.a",
    ]
    assert "private-operator" not in info.text and "platform" not in info.text
    assert client.post("/api/commerce/v1/auth/register").status_code == 403
    assert calls == []
    assert (
        client.post("/api/commerce/v1/auth/login", content=b"x" * (MAX_BODY + 1)).status_code == 413
    )
    assert client.post("/api/commerce/v1/auth/login", content=b"abc").json() == {"bytes": 3}
    for _ in range(28):
        client.post("/api/commerce/v1/auth/login", content=b"abc")
    rejected = client.post("/api/commerce/v1/auth/login")
    assert rejected.status_code == 429 and rejected.headers["retry-after"] == "60"
    for path in ["/api/unknown", "/.secret", "/assets/missing.js", "/alias.txt", "/%2e%2e/secret"]:
        assert client.get(path).status_code == 404
    assert client.get("/customer").status_code == 200
    assert client.get("/ready").status_code == 503
    assert info.headers["x-content-type-options"] == "nosniff"


def test_cloud_url_normalization(monkeypatch):
    from app.db import connection

    captured = []
    monkeypatch.setattr(connection, "create_engine", lambda url, **kw: captured.append(url))
    connection.product_engine("postgres://u:p@host/db?sslmode=require")
    assert captured[0].drivername == "postgresql+psycopg"
    assert captured[0].query["sslmode"] == "require"
    with pytest.raises(ValueError):
        connection.product_engine("postgresql+pg8000://u:p@host/db")


def test_loopback_exception_requires_explicit_acceptance_flag():
    for origin in ["http://127.0.0.1:8000", "http://external.example.test"]:
        with pytest.raises(ValueError):
            Settings(
                _env_file=None,
                app_env="production",
                commerce_public_demo=True,
                commerce_public_origin=origin,
                commerce_demo_password="public-password-123",
                commerce_operator_password="private-operator-password-123",
            )
    accepted = Settings(
        _env_file=None,
        app_env="production",
        commerce_public_demo=True,
        commerce_public_demo_local_acceptance=True,
        commerce_public_origin="http://127.0.0.1:8000",
        commerce_demo_password="public-password-123",
        commerce_operator_password="private-operator-password-123",
    )
    assert accepted.cors_allowed_origins == ["http://127.0.0.1:8000"]
    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            app_env="production",
            commerce_public_demo=True,
            commerce_public_demo_local_acceptance=True,
            commerce_public_origin="http://external.example.test",
            commerce_demo_password="public-password-123",
            commerce_operator_password="private-operator-password-123",
        )


def test_disconnect_releases_login_capacity(monkeypatch):
    from starlette.requests import ClientDisconnect, Request

    from app.commerce.public_demo import install_public_demo

    app = FastAPI()

    @app.post("/api/commerce/v1/auth/login")
    def login():
        return {"ok": True}

    install_public_demo(app, public_settings())
    original = Request.stream

    async def disconnected(self):
        raise ClientDisconnect()
        yield b""

    monkeypatch.setattr(Request, "stream", disconnected)
    client = TestClient(app)
    for _ in range(3):
        assert client.post("/api/commerce/v1/auth/login").status_code == 400
    monkeypatch.setattr(Request, "stream", original)
    response = client.post("/api/commerce/v1/auth/login", content=b"{}")
    assert response.status_code == 200
    assert "img-src 'self' data: blob:" in response.headers["content-security-policy"]


def test_business_write_traffic_does_not_consume_login_ip_budget():
    from app.commerce.public_demo import install_public_demo

    app = FastAPI()

    @app.post("/api/commerce/v1/customer/cart")
    def business_write():
        return {"ok": True}

    @app.post("/api/commerce/v1/auth/login")
    def login():
        return {"ok": True}

    install_public_demo(app, public_settings())
    client = TestClient(app)
    headers = {"Authorization": "Bearer visitor-token"}
    for _ in range(30):
        assert client.post("/api/commerce/v1/customer/cart", headers=headers).status_code == 200
    assert client.post("/api/commerce/v1/auth/login").status_code == 200
    for _ in range(29):
        assert client.post("/api/commerce/v1/auth/login").status_code == 200
    assert client.post("/api/commerce/v1/auth/login").status_code == 429
    assert client.post("/api/commerce/v1/customer/cart", headers=headers).status_code == 200
