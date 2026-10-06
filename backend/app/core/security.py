"""Password verification and opaque session tokens; never authorization grants."""

import hashlib
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

PASSWORD_HASHER = PasswordHasher(
    memory_cost=65536, time_cost=3, parallelism=1, salt_len=16, hash_len=32
)
_DUMMY_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))


def password_matches(stored_hash: str | None, password: str) -> bool:
    try:
        verified = PASSWORD_HASHER.verify(stored_hash or _DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
    return stored_hash is not None and verified


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def bearer_token(header: str | None) -> str | None:
    match = re.fullmatch(r"(?i:Bearer) ([A-Za-z0-9_-]{43})", header or "")
    return match[1] if match else None
