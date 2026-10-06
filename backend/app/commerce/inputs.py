"""Strict closed input parsing is deliberately called only after authorization."""

import re
from datetime import UTC, datetime
from uuid import UUID

from app.commerce.errors import fail


def fields(body, required):
    if not isinstance(body, dict) or set(body) != set(required):
        fail("INVALID_REQUEST", 400)
    return body


def integer(value, low=1, high=100000000):
    if type(value) is not int or not low <= value <= high:
        fail("INVALID_REQUEST", 400)
    return value


def string(value, low=1, high=200):
    if not isinstance(value, str):
        fail("INVALID_REQUEST", 400)
    value = value.strip()
    if not low <= len(value) <= high:
        fail("INVALID_REQUEST", 400)
    return value


def identifier(value):
    if not isinstance(value, str):
        fail("INVALID_REQUEST", 400)
    try:
        result = UUID(value)
    except ValueError:
        fail("INVALID_REQUEST", 400)
    if str(result) != value:
        fail("INVALID_REQUEST", 400)
    return result


def boolean(value):
    if type(value) is not bool:
        fail("INVALID_REQUEST", 400)
    return value


def options(value):
    if not isinstance(value, dict) or len(value) > 10:
        fail("INVALID_REQUEST", 400)
    result = {string(k, 1, 80): string(v, 1, 80) for k, v in value.items()}
    if len(result) != len(value):
        fail("INVALID_REQUEST", 400)
    return result


def address(value):
    fields(
        value,
        [
            "recipient_name",
            "phone",
            "country_code",
            "region",
            "city",
            "postal_code",
            "address_line",
        ],
    )
    result = {
        k: string(
            v,
            1,
            {
                "recipient_name": 100,
                "phone": 32,
                "country_code": 2,
                "region": 100,
                "city": 100,
                "postal_code": 20,
                "address_line": 300,
            }[k],
        )
        for k, v in value.items()
    }
    if result["country_code"] != "CN":
        fail("INVALID_REQUEST", 400)
    return result


def timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)", value
    ):
        fail("INVALID_REQUEST", 400)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail("INVALID_REQUEST", 400)
    if result.tzinfo is None:
        fail("INVALID_REQUEST", 400)
    return result.astimezone(UTC)


def selection(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 50:
        fail("INVALID_REQUEST", 400)
    result = []
    for entry in value:
        fields(entry, ["order_line_id", "quantity"])
        result.append((identifier(entry["order_line_id"]), integer(entry["quantity"], 1, 99)))
    if len({v[0] for v in result}) != len(result):
        fail("INVALID_REQUEST", 400)
    return result
