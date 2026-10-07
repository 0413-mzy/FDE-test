"""Privileged local simulated mail; no HTTP viewer and no ordinary token logging."""

import argparse
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from uuid import uuid4


def directory(settings):
    if settings.app_env not in {"development", "test"} or settings.commerce_mailbox_dir is None:
        raise OSError("Local simulated mailbox is unavailable")
    folder = Path(settings.commerce_mailbox_dir)
    if folder.is_symlink():
        raise OSError("Unsafe mailbox directory")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    return folder


def check_delivery(settings):
    """Uniform write preflight for known and unknown recipients before acceptance."""
    folder = directory(settings)
    probe = folder / (".probe-" + uuid4().hex)
    fd = os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(b"simulation")
            output.flush()
            os.fsync(output.fileno())
    finally:
        probe.unlink(missing_ok=True)


def fingerprint(settings, value):
    """Persistent private HMAC prevents idempotency fingerprints becoming password oracles."""
    folder = directory(settings)
    path = folder / ".fingerprint-key"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "wb") as output:
            output.write(secrets.token_bytes(32))
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise OSError("Unsafe fingerprint key")
    key = path.read_bytes()
    if len(key) != 32:
        raise OSError("Invalid fingerprint key")
    value = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hmac.new(key, value, hashlib.sha256).hexdigest()


def deliver(settings, letter):
    folder = directory(settings)
    path = folder / (uuid4().hex + ".json")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump({"simulation": True, **letter}, output)


def main():
    parser = argparse.ArgumentParser(description="Privileged local simulated mailbox reader")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--email")
    args = parser.parse_args()
    for path in sorted(args.directory.glob("*.json")):
        if path.is_symlink() or path.stat().st_mode & 0o077:
            raise SystemExit("Unsafe mailbox permissions")
        letter = json.loads(path.read_text())
        if args.email is None or letter["email"] == args.email.lower():
            print(json.dumps(letter))


if __name__ == "__main__":
    main()
