"""Isolated local commerce demos. Never resets or removes an existing schema."""

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = [
    "purchase",
    "partial-return",
    "full-refund",
    "shipped-partial-refund",
    "return-no-restock",
    "reject-withdraw",
    "exceptions",
    "onboarding",
]


def configuration(env):
    if env.get("APP_ENV") not in {"development", "test"}:
        raise ValueError("APP_ENV must explicitly be development or test")
    raw = env.get("TEST_DATABASE_URL")
    if not raw:
        raise ValueError("An explicit isolated TEST_DATABASE_URL is required")
    url = make_url(raw)
    if url.drivername != "postgresql+psycopg" or "options" in url.query:
        raise ValueError("Use a PostgreSQL psycopg test URL without search_path/options")
    return {
        "url": url,
        "schema": "commerce_demo_" + uuid4().hex,
        "password": secrets.token_urlsafe(32),
    }


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(api, path, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        api + "/api/commerce/v1" + path,
        headers=headers,
        data=json.dumps(body).encode() if body is not None else None,
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return None if response.status == 204 else json.load(response)


def ready(process, url):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Child service exited; see its protected log")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.1)
    raise RuntimeError("Child service readiness timed out")


def stop(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def http_boundaries(api, password):
    base = api + "/api/commerce/v1"

    def rejected(path, expected, token=None, raw=None):
        headers = {"Content-Type": "application/json", "Idempotency-Key": str(uuid4())}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(base + path, headers=headers, data=raw)
        try:
            urllib.request.urlopen(req, timeout=10).close()
        except urllib.error.HTTPError as error:
            if error.code != expected:
                raise RuntimeError("Unexpected HTTP boundary status") from None
            payload = json.load(error)
            if set(payload["error"]) != {"code", "message", "request_id", "details"}:
                raise RuntimeError("Nonclosed HTTP error") from None
            return
        raise RuntimeError("HTTP boundary unexpectedly accepted request")

    for path in ["/customer/cart", "/customer/orders"]:
        rejected(path, 401)
    rejected("/catalog/products?limit=2&limit=3", 400)
    token = request(api, "/auth/login", body={"username": "customer.a", "password": password})[
        "token"
    ]
    try:
        rejected("/customer/cart/lines", 400, token, b'{"quantity":1,"quantity":2}')
        if (
            request(api, "/customer/cart", token)["lines"]
            or request(api, "/customer/orders", token)["items"]
        ):
            raise RuntimeError("Rejected input changed fresh business records")
    finally:
        request(api, "/auth/logout", token, {})
    return [
        "P01 unauthenticated cart/order 401",
        "P08 duplicate query/JSON 400 without business changes",
    ]


def snapshot(api, password, username="customer.a"):
    token = request(api, "/auth/login", body={"username": username, "password": password})["token"]
    try:
        result = []
        offset = 0
        while True:
            page = request(api, f"/customer/orders?limit=20&offset={offset}", token)
            for order in page["items"]:
                result.append(request(api, "/customer/orders/" + order["id"], token))
            if not page["has_more"]:
                return result
            offset += 20
    finally:
        request(api, "/auth/logout", token, {})


def run_scenario(name, evidence, interactive=False):
    config = configuration(os.environ)
    directory = Path(tempfile.mkdtemp(prefix="fde-commerce-demo-"))
    directory.chmod(0o700)
    password_file = directory / "password"
    password_file.write_text(config["password"])
    password_file.chmod(0o600)
    engine = create_engine(config["url"], hide_parameters=True)
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{config["schema"]}"'))
    finally:
        engine.dispose()
    url = config["url"].update_query_dict(
        {"options": f"-c search_path={config['schema']} -c timezone=UTC"}
    )
    api_port, ui_port = free_port(), free_port()
    api = f"http://127.0.0.1:{api_port}"
    ui = f"http://127.0.0.1:{ui_port}"
    mailbox = directory / "mailbox"
    mailbox.mkdir(mode=0o700)
    env = dict(
        os.environ,
        APP_ENV="development",
        DATABASE_URL=url.render_as_string(hide_password=False),
        DEMO_SEED_PASSWORD=config["password"],
        CORS_ALLOWED_ORIGINS=json.dumps([ui]),
        VITE_API_BASE_URL=api,
        COMMERCE_MAILBOX_DIR=str(mailbox),
    )
    # Private resume metadata; contains connection configuration and must never be committed.
    runtime = directory / "runtime.json"
    runtime.write_text(
        json.dumps(
            {
                "database_url": env["DATABASE_URL"],
                "schema": config["schema"],
                "api": api,
                "ui": ui,
                "password_file": str(password_file),
                "mailbox_dir": str(mailbox),
            }
        )
    )
    runtime.chmod(0o600)
    api_process = ui_process = None
    log_path = directory / "services.log"
    with log_path.open("w") as log:
        log_path.chmod(0o600)
        try:
            for module in [
                ("alembic", "upgrade", "head"),
                ("app.commerce.seed",),
                ("app.commerce.onboarding_seed",),
            ]:
                subprocess.run(
                    [sys.executable, "-m", *module],
                    cwd=ROOT / "backend",
                    env=env,
                    stdout=log,
                    stderr=log,
                    check=True,
                )

            def launch_api():
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(api_port),
                        "--no-access-log",
                    ],
                    cwd=ROOT / "backend",
                    env=env,
                    stdout=log,
                    stderr=log,
                )
                try:
                    ready(process, api + "/health")
                except BaseException:
                    stop(process)
                    raise
                return process

            api_process = launch_api()
            http_checks = http_boundaries(api, config["password"])
            ui_process = subprocess.Popen(
                [
                    "node",
                    str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(ui_port),
                    "--strictPort",
                ],
                cwd=ROOT / "frontend",
                env=env,
                stdout=log,
                stderr=log,
            )
            ready(ui_process, ui)
            if interactive:
                print(
                    json.dumps(
                        {
                            "ui": ui,
                            "api": api,
                            "password_file": str(password_file),
                            "mailbox_dir": str(mailbox),
                            "schema": config["schema"],
                            "note": "Local fictional demo; CtrlC stops services, data retained.",
                        }
                    ),
                    flush=True,
                )
                while api_process.poll() is None and ui_process.poll() is None:
                    time.sleep(0.5)
                raise RuntimeError("Demo service exited unexpectedly")
            script = (
                "commerce-browser-acceptance.cjs"
                if name == "purchase"
                else "commerce-onboarding-browser-acceptance.cjs"
                if name == "onboarding"
                else "commerce-step5-browser-acceptance.cjs"
                if name == "exceptions"
                else "commerce-step4-browser-acceptance.cjs"
            )
            scenario_dir = evidence / name
            scenario_dir.mkdir(parents=True, exist_ok=True)
            browser_env = dict(
                env,
                COMMERCE_UI_URL=ui,
                COMMERCE_PASSWORD_FILE=str(password_file),
                COMMERCE_SCENARIO=name,
                COMMERCE_SCREENSHOT_DIR=str(scenario_dir),
            )
            subprocess.run(["node", str(ROOT / "scripts" / script)], env=browser_env, check=True)
            username = "customer.b" if name == "onboarding" else "customer.a"
            before = snapshot(api, config["password"], username)
            if not before:
                raise RuntimeError("Browser scenario left no persistent customer orders")
            stop(api_process)
            api_process = launch_api()
            after = snapshot(api, config["password"], username)
            if before != after:
                raise RuntimeError("Business records changed across API restart")
            return {
                "scenario": name,
                "schema": config["schema"],
                "status": "PASSED",
                "restart_orders": len(after),
                "http_checks": http_checks,
                "screenshots": str(scenario_dir),
            }
        finally:
            stop(ui_process)
            stop(api_process)


def provenance():
    files = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
    ).split(b"\0")
    digest = hashlib.sha256()
    for relative in sorted(set(files)):
        if not relative:
            continue
        path = ROOT / os.fsdecode(relative)
        if path.is_file():
            digest.update(relative + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return {
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
        "source_tree_sha256": digest.hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS + ["all", "interactive"], default="all")
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()
    results = []
    evidence = args.evidence_dir or Path(tempfile.mkdtemp(prefix="fde-commerce-evidence-"))
    evidence.mkdir(parents=True, exist_ok=True)
    source = provenance()
    try:
        configuration(os.environ)  # Reject unsafe configuration before starting anything.
        if args.scenario == "interactive":
            run_scenario("interactive", evidence, interactive=True)
            return
        for name in SCENARIOS if args.scenario == "all" else [args.scenario]:
            results.append(run_scenario(name, evidence))
            print(f"PASS {name}: browser and API restart", flush=True)
        (evidence / "results.json").write_text(
            json.dumps(source | {"status": "PASSED", "results": results}, indent=2)
        )
        print("Evidence: " + str(evidence / "results.json"))
    except KeyboardInterrupt:
        (evidence / "results.json").write_text(
            json.dumps(source | {"status": "INTERRUPTED", "results": results}, indent=2)
        )
        print("Stopped own demo services; generated schema retained.")
        if args.scenario != "interactive":
            raise SystemExit(130) from None
    except Exception as error:  # noqa: BLE001 -- CLI redacts untrusted exception payloads.
        # No exception strings: database URLs, passwords or tokens may occur in third-party errors.
        (evidence / "results.json").write_text(
            json.dumps(
                source
                | {
                    "results": results,
                    "status": "FAILED",
                    "error_type": type(error).__name__,
                },
                indent=2,
            )
        )
        print(
            "FAILED "
            + type(error).__name__
            + "; see protected local service log. No existing data reset.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
