"""Signed anonymous-session cookies and scoped HMAC identifiers."""

from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import hmac
import re
import secrets
import time
from collections.abc import Callable


SESSION_TTL_SECONDS = 24 * 60 * 60
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")


class SessionTokenError(ValueError):
    """The anonymous session cookie is invalid or expired."""


class SessionTokenExpired(SessionTokenError):
    """The signed cookie was valid but its absolute expiry has passed."""


@dataclass(frozen=True)
class SessionClaims:
    key_id: str
    session_id: str
    expires_at: int


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class SessionTokenCodec:
    def __init__(
        self,
        *,
        signing_keys: dict[str, bytes],
        current_key_id: str,
        clock: Callable[[], float] = time.time,
        ttl_seconds: int = SESSION_TTL_SECONDS,
    ) -> None:
        if not signing_keys or current_key_id not in signing_keys:
            raise ValueError("current session signing key is not configured")
        if any(
            not _KEY_ID_RE.fullmatch(key_id) or len(secret) < 32
            for key_id, secret in signing_keys.items()
        ):
            raise ValueError("session signing keys must have valid IDs and 32+ bytes")
        if ttl_seconds <= 0 or ttl_seconds > SESSION_TTL_SECONDS:
            raise ValueError("session TTL must be between 1 second and 24 hours")
        self.signing_keys = dict(signing_keys)
        self.current_key_id = current_key_id
        self.clock = clock
        self.ttl_seconds = ttl_seconds

    def issue(self) -> tuple[str, SessionClaims]:
        claims = SessionClaims(
            key_id=self.current_key_id,
            session_id=secrets.token_urlsafe(32),
            expires_at=int(self.clock()) + self.ttl_seconds,
        )
        return self._encode(claims), claims

    def _encode(self, claims: SessionClaims) -> str:
        payload = f"{claims.key_id}.{claims.session_id}.{claims.expires_at}"
        signature = hmac.new(
            self.signing_keys[claims.key_id], payload.encode("ascii"), hashlib.sha256
        ).digest()
        return f"{payload}.{_b64url(signature)}"

    def verify(self, token: str) -> SessionClaims:
        if not isinstance(token, str) or len(token) > 256:
            raise SessionTokenError("invalid session cookie")
        parts = token.split(".")
        if len(parts) != 4:
            raise SessionTokenError("invalid session cookie")
        key_id, session_id, expires_raw, signature_raw = parts
        secret = self.signing_keys.get(key_id)
        if (
            secret is None
            or not _SESSION_ID_RE.fullmatch(session_id)
            or not expires_raw.isdecimal()
            or not signature_raw
        ):
            raise SessionTokenError("invalid session cookie")
        try:
            signature = _unb64url(signature_raw)
        except (ValueError, base64.binascii.Error) as exc:
            raise SessionTokenError("invalid session cookie") from exc
        payload = f"{key_id}.{session_id}.{expires_raw}"
        expected = hmac.new(secret, payload.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise SessionTokenError("invalid session cookie")
        expires_at = int(expires_raw)
        if int(self.clock()) >= expires_at:
            raise SessionTokenExpired("session cookie expired")
        return SessionClaims(key_id, session_id, expires_at)

    def session_hmac(self, claims: SessionClaims) -> str:
        return hmac.new(
            self.signing_keys[claims.key_id],
            b"rag-portfolio:session:" + claims.session_id.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()

    def key_hmac(self, claims: SessionClaims, raw_key: str) -> str:
        scoped_key = (
            b"rag-portfolio:idempotency:"
            + claims.session_id.encode("ascii")
            + b":"
            + raw_key.encode("ascii")
        )
        return hmac.new(
            self.signing_keys[claims.key_id], scoped_key, hashlib.sha256
        ).hexdigest()
