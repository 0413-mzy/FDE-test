"""Explicit production demo entrypoint; no reload, credentials or destructive resets."""

import os
import subprocess
import sys
from pathlib import Path


def runtime_port(environment):
    raw = environment.get("PORT", "8000")
    if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal():
        raise ValueError("PORT must be a valid TCP port")
    port = int(raw)
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be a valid TCP port")
    return port


def prepare():
    from app.commerce.public_demo_seed import bootstrap_public_demo
    from app.core.config import Settings

    settings = Settings()
    if settings.app_env != "production" or not settings.commerce_public_demo:
        raise ValueError("Explicit production public demo configuration is required")
    folder = settings.commerce_static_dir
    if folder is None or not (Path(folder) / "index.html").is_file():
        raise ValueError("Built frontend is required")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    bootstrap_public_demo(settings)


def start(prepare_fn, execute_fn, environment):
    port = runtime_port(environment)
    prepare_fn()
    execute_fn(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
            "--workers",
            "1",
            "--no-access-log",
            "--no-proxy-headers",
        ]
    )


def main():
    try:
        start(prepare, lambda argv: os.execv(sys.executable, argv), os.environ)
    except Exception as error:
        # Database URLs, validation values and subprocess details can contain secrets.
        raise SystemExit("Public demo startup failed: " + type(error).__name__) from None


if __name__ == "__main__":
    main()
