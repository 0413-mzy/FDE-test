"""Explicit real-HTTP acceptance of a fictional public demo, never a real-money site."""

import argparse
import base64
import json
import os
import re
import struct
import urllib.error
import urllib.request
import zlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def request(base, path, token=None, body=None, status=200):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        headers["Idempotency-Key"] = str(uuid4())
    req = urllib.request.Request(
        base + path,
        headers=headers,
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        response = urllib.request.urlopen(req, timeout=45)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        if response.status not in (status if isinstance(status, tuple) else (status,)):
            raise RuntimeError(
                "Unexpected HTTP status " + str(response.status) + " at " + path.split("?")[0]
            )
        data = response.read()
        return json.loads(data) if "json" in response.headers.get("Content-Type", "") else data


def run(base):
    api = "/api/commerce/v1"
    assert request(base, "/health")["status"] == "ok"
    assert request(base, "/ready")["status"] == "ready"
    info = request(base, api + "/demo-info")
    assert info["enabled"] and "platform" not in info["accounts"]
    assert "reviewer" not in info["accounts"] and len(info["password"]) >= 12
    page = request(base, "/").decode()
    assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', page)
    assert len(assets) >= 2
    for asset in assets:
        assert request(base, asset)
    request(base, "/.env", status=404)
    request(base, "/app/main.py", status=404)
    request(base, "/api/v1/orders", status=404)
    request(base, api + "/demo/pending", status=401)
    for path in ["/auth/register", "/account/password", "/account/email", "/account/profile"]:
        result = request(base, api + path, body={}, status=403)
        assert result["error"]["code"] == "PUBLIC_DEMO_DISABLED"
    sessions = []

    def login(name):
        data = request(
            base,
            api + "/auth/login",
            body={"username": name, "password": info["password"]},
        )
        sessions.append(data["token"])
        return data["token"]

    customer, other, owner, outsider, demo = [
        login(name) for name in ["customer.a", "customer.b", "owner.a", "owner.b", "demo"]
    ]
    try:
        request(
            base,
            api + "/auth/login",
            body={"username": "platform", "password": info["password"]},
            status=401,
        )
        request(base, api + "/platform/accounts", customer, status=403)
        request(base, api + "/demo/pending", customer, status=403)
        products = request(base, api + "/shopping/products", customer)["items"]
        product = next(p for p in products if p["title"] == "Fictional Product A")
        shop, sku = product["shop_id"], product["skus"][0]
        experience_path = f"/merchant/shops/{shop}/products/{product['id']}/experience"
        experience = request(base, api + experience_path, owner)

        def chunk(kind, value):
            return (
                struct.pack("!I", len(value))
                + kind
                + value
                + struct.pack("!I", zlib.crc32(kind + value) & 0xFFFFFFFF)
            )

        png = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack("!IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00\xff"))
            + chunk(b"IEND", b"")
        )
        uploaded = request(
            base,
            api + experience_path + "/images",
            owner,
            {
                "expected_version": experience["version"],
                "data_base64": base64.b64encode(png).decode(),
                "alt": "公开演示验收：虚构商品图片",
            },
            201,
        )
        image_url = uploaded["images"][-1]["url"]
        assert request(base, image_url).startswith(b"\x89PNG")
        cart = request(base, api + "/customer/cart", customer)
        request(
            base,
            api + "/customer/cart/lines",
            customer,
            {
                "expected_version": cart["version"],
                "sku_id": sku["id"],
                "quantity": 1,
                "seen_price_version": sku["price_version"],
            },
            (200, 201),
        )
        cart = request(base, api + "/customer/cart", customer)
        checkout = request(
            base,
            api + "/customer/checkouts",
            customer,
            {
                "expected_version": cart["version"],
                "address": {
                    "recipient_name": "虚构演示买家",
                    "phone": "13800000000",
                    "country_code": "CN",
                    "region": "上海",
                    "city": "上海",
                    "postal_code": "200000",
                    "address_line": "虚构演示地址，不是实际配送地点",
                },
            },
            201,
        )
        order = next(o for o in checkout["orders"] if o["shop_id"] == shop)
        oid = order["id"]
        order_path = api + "/customer/orders/" + oid
        request(base, order_path, other, status=404)
        request(base, api + f"/merchant/shops/{shop}/orders/{oid}", outsider, status=404)
        payment = request(
            base, order_path + "/payments", customer, {"expected_version": order["version"]}, 201
        )
        request(
            base,
            api + f"/demo/payments/{payment['id']}/result",
            demo,
            {
                "expected_version": payment["version"],
                "result": "SUCCEEDED",
                "event_id": str(uuid4()),
            },
        )
        order = request(base, order_path, customer)
        shipment = request(
            base,
            api + f"/merchant/shops/{shop}/orders/{oid}/shipments",
            owner,
            {
                "expected_version": order["version"],
                "lines": [{"order_line_id": order["lines"][0]["id"], "quantity": 1}],
            },
            201,
        )
        for kind in ("COLLECTED", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED"):
            result = request(
                base,
                api + f"/demo/shipments/{shipment['id']}/events",
                demo,
                {
                    "expected_version": shipment["version"],
                    "event_id": str(uuid4()),
                    "kind": kind,
                    "description": "公开演示验收：手动模拟物流 " + kind,
                    "occurred_at": datetime.now(UTC).isoformat(),
                },
            )
            shipment.update(result)
        order = request(base, order_path, customer)
        completed = request(
            base,
            order_path + "/confirm-receipt",
            customer,
            {"expected_version": order["version"]},
        )
        assert completed["status"] == "COMPLETED"
        assert completed["financial_status"] == "PAID" and completed["total_minor"] == 1000
        return {"base_url": base, "order_id": oid, "image_url": image_url}
    finally:
        for token in sessions:
            request(base, api + "/auth/logout", token, {}, 204)


def persisted(receipt):
    base = receipt["base_url"]
    info = request(base, "/api/commerce/v1/demo-info")
    identity = request(
        base,
        "/api/commerce/v1/auth/login",
        body={"username": "customer.a", "password": info["password"]},
    )
    token = identity["token"]
    try:
        order = request(base, "/api/commerce/v1/customer/orders/" + receipt["order_id"], token)
        assert order["status"] == "COMPLETED"
        assert order["financial_status"] == "PAID" and order["total_minor"] == 1000
        assert request(base, receipt["image_url"]).startswith(b"\x89PNG")
    finally:
        request(base, "/api/commerce/v1/auth/logout", token, {}, 204)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url")
    parser.add_argument("--receipt-file", type=Path, required=True)
    parser.add_argument("--check-persisted", action="store_true")
    args = parser.parse_args()
    if args.check_persisted:
        persisted(json.loads(args.receipt_file.read_text()))
        print("PASS: completed order and uploaded image persisted after service restart.")
    else:
        if not args.base_url:
            parser.error("--base-url is required")
        receipt = run(args.base_url.rstrip("/"))
        fd = os.open(args.receipt_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as output:
            json.dump(receipt, output)
        print(
            "PASS: production static app; simulated purchase/payment/shipment/receipt; "
            "image and permissions."
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        detail = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        raise SystemExit("Public demo acceptance failed: " + detail) from None
