import pytest

from src.session_security import SessionTokenCodec, SessionTokenError


def test_signed_session_keeps_an_absolute_expiry_and_scoped_hmac():
    now = 1_800_000_000
    codec = SessionTokenCodec(
        signing_keys={"key-a": b"a" * 32},
        current_key_id="key-a",
        clock=lambda: now,
    )

    token, claims = codec.issue()

    assert claims.expires_at == now + 24 * 60 * 60
    assert codec.verify(token) == claims
    assert len(codec.session_hmac(claims)) == 64
    assert codec.key_hmac(claims, "A" * 43) != codec.key_hmac(claims, "B" * 43)


def test_expired_or_tampered_cookie_is_rejected_at_absolute_boundary():
    now = 1_800_000_000
    codec = SessionTokenCodec(
        signing_keys={"key-a": b"a" * 32},
        current_key_id="key-a",
        clock=lambda: now,
    )
    token, claims = codec.issue()

    parts = token.split(".")
    parts[-1] = ("A" if parts[-1][0] != "A" else "B") + parts[-1][1:]
    with pytest.raises(SessionTokenError):
        codec.verify(".".join(parts))

    expired_codec = SessionTokenCodec(
        signing_keys={"key-a": b"a" * 32},
        current_key_id="key-a",
        clock=lambda: claims.expires_at,
    )
    with pytest.raises(SessionTokenError):
        expired_codec.verify(token)


def test_rotated_codec_accepts_previous_key_without_extending_session_expiry():
    now = 1_800_000_000
    original = SessionTokenCodec(
        signing_keys={"key-a": b"a" * 32},
        current_key_id="key-a",
        clock=lambda: now,
    )
    token, claims = original.issue()
    rotated = SessionTokenCodec(
        signing_keys={"key-a": b"a" * 32, "key-b": b"b" * 32},
        current_key_id="key-b",
        clock=lambda: now + 3600,
    )

    assert rotated.verify(token) == claims
    assert rotated.issue()[1].expires_at == now + 3600 + 24 * 60 * 60
