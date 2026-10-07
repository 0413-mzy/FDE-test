"""Public deployment never starts on invalid config or failed initialization."""

import pytest

from app.commerce.public_demo_start import runtime_port, start


def test_port_rejects_invalid_values():
    assert runtime_port({}) == 8000
    assert runtime_port({"PORT": "10000"}) == 10000
    for value in ["-1", "0", "65536", "x", "8000;whoami"]:
        with pytest.raises(ValueError):
            runtime_port({"PORT": value})


def test_failed_preparation_never_executes_server():
    calls = []

    def prepare():
        raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError):
        start(prepare, lambda argv: calls.append(argv), {})
    assert calls == []


def test_success_starts_one_worker_without_reload_or_access_logs():
    calls = []
    start(lambda: calls.append("ready"), lambda argv: calls.append(argv), {"PORT": "10000"})
    assert calls[0] == "ready"
    args = calls[1]
    assert args[args.index("--port") + 1] == "10000"
    assert args[args.index("--workers") + 1] == "1"
    assert "--reload" not in args
    assert "--no-access-log" in args and "--no-proxy-headers" in args
