
import secrets
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import httpx
from jose import JWTError, jwt

from app.core.config import settings

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
# F-03 (audit_dependencies): migrated off passlib. passlib has been
# effectively unmaintained since 2020-10 and the bcrypt-4.x adapter logged
# `(trapped) error reading bcrypt version` on every startup. Native bcrypt is
# a much smaller surface, has a stable maintainer, and ships its own
# Rust-backed implementation. Hash format ($2b$…) is identical to what
# passlib emitted, so existing rows in the `users` table verify without a
# migration. bcrypt limits inputs to 72 bytes (a documented trade-off) —
# anything longer is truncated by the library, same as before.

# Reasonable cost factor. 12 ~= 250 ms on a modern CPU — slow enough to make
# brute force expensive, fast enough not to harm UX. Configurable later via
# settings if benchmarks demand it.
_BCRYPT_ROUNDS = 12


def hash_password(plain: str) -> str:
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    # checkpw is constant-time and accepts any $2a/$2b/$2y hash, so we stay
    # compatible with rows that passlib wrote before the migration.
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # Malformed hash in DB (e.g. legacy plaintext from before the auth
        # rewrite) — treat as "no match" rather than crashing the login.
        return False


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------
def _now() -> datetime:
    return datetime.now(UTC)


def create_access_token(
    subject: str,
    extra_claims: dict[str, Any] | None = None,
    *,
    token_type: str = "access",
    expires_minutes: int | None = None,
) -> str:
    """
    Create an access token.

    audit_security H (JWT type confusion): `extra_claims` is merged **before**
    the structural claims (`sub`, `iat`, `type`, `exp`) so callers can't
    accidentally overwrite them — that bug previously broke candidate and
    admin auth (their `type` got clobbered by the recruiter-flavoured default).
    The new `token_type` kwarg makes the intent explicit at the call site.

    audit_security H (always set exp): an `exp` is now set in every environment.
    Dev tokens get a long but bounded lifetime (cookie max-age is still big in
    dev — see `access_token_cookie_max_age`) so a leaked dev token can no
    longer be valid for years.
    """
    payload: dict[str, Any] = {
        **(extra_claims or {}),
        "sub": subject,
        "iat": _now(),
        "type": token_type,
    }
    if expires_minutes is None:
        expires_minutes = (
            settings.access_token_expire_minutes if settings.is_production else 60 * 24
        )
    payload["exp"] = _now() + timedelta(minutes=expires_minutes)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def access_token_cookie_max_age() -> int:
    """Cookie max-age in seconds, mirroring create_access_token() lifetime."""
    if settings.is_production:
        return settings.access_token_expire_minutes * 60
    # Non-prod: ~10 years, effectively non-expiring for local/dev/test.
    return 60 * 60 * 24 * 365 * 10


def create_refresh_token() -> tuple[str, str]:
    """
    Generate a cryptographically secure refresh token.

    Returns:
        (raw_token, token_hash) — store the hash in the DB, send raw to client.
    """
    raw = secrets.token_urlsafe(64)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, token_hash


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def decode_access_token(token: str, *, expected_type: str = "access") -> dict[str, Any]:
    """
    Decode and validate a JWT access token.

    audit_security H: callers must pass `expected_type` to validate against the
    identity they expect (`access` for HR, `candidate`, `admin`). The previous
    implementation hard-coded `access`, which is why candidate and admin
    tokens — created with `extra_claims={"type":"candidate"|"admin"}` — would
    fail validation on the only available `decode_access_token` helper.

    Raises:
        JWTError: if the token is invalid, expired, or the type does not match.
    """
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("type") != expected_type:
        raise JWTError("Token type mismatch")
    return payload


def generate_public_token() -> str:
    """Generate a unique opaque public tracking token for candidates."""
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Google OAuth
# ---------------------------------------------------------------------------
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


def get_google_auth_url(state: str) -> str:
    """Return the Google OAuth2 authorization URL."""
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{GOOGLE_AUTH_URL}?{query}"


async def exchange_google_code(code: str) -> dict[str, Any]:
    """Exchange an OAuth2 authorization code for tokens + user info."""
    async with httpx.AsyncClient() as client:
        # Exchange code for tokens
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()

        # Fetch user info
        user_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        user_resp.raise_for_status()
        return user_resp.json()
