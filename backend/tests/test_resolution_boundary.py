import pytest

from app.api.errors import ApiError
from app.services.resolution import resolve_input


@pytest.mark.parametrize(
    "body",
    [
        b"{}",
        b"[]",
        b'{"expected_lock_version":true}',
        b'{"expected_lock_version":1,"expected_lock_version":2}',
        b'{"expected_lock_version":1,"order_id":"foreign"}',
    ],
)
def test_closed_resolve_input(body):
    with pytest.raises(ApiError) as error:
        resolve_input(body, "application/json", [], ["key"])
    assert error.value.code == "INVALID_REQUEST"


def test_key_exact_and_positive_version():
    assert resolve_input(b'{"expected_lock_version":2}', "application/json", [], [" key "]) == (
        2,
        " key ",
    )


def test_resolve_openapi_has_closed_request_and_idempotency_header():
    from app.core.config import Settings
    from app.main import create_app

    route = create_app(Settings(_env_file=None)).openapi()["paths"][
        "/api/v1/inquiries/{id}/resolve-context"
    ]["post"]
    assert (
        route["requestBody"]["content"]["application/json"]["schema"]["additionalProperties"]
        is False
    )
    assert next(p for p in route["parameters"] if p["name"] == "Idempotency-Key")["required"]
