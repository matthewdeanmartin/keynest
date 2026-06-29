"""Secret value generators and validators (stdlib ``secrets`` only)."""

from __future__ import annotations

import json
import secrets
import string
import uuid
from urllib.parse import urlparse

_PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}"


def generate_password(length: int = 24) -> str:
    """Generate a random password from a mixed alphabet."""
    if length < 1:
        raise ValueError("length must be >= 1")
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def generate_hex_token(num_bytes: int = 32) -> str:
    """Generate a random hex token from ``num_bytes`` of entropy."""
    return secrets.token_hex(num_bytes)


def generate_base64_token(num_bytes: int = 32) -> str:
    """Generate a URL-safe base64 token from ``num_bytes`` of entropy."""
    return secrets.token_urlsafe(num_bytes)


def generate_uuid() -> str:
    """Generate a random UUID4 string."""
    return str(uuid.uuid4())


def generate_api_token_placeholder(prefix: str = "sk") -> str:
    """Generate an API-token-shaped placeholder, e.g. ``sk_live_<random>``."""
    return f"{prefix}_live_{secrets.token_urlsafe(24)}"


# -- validators --------------------------------------------------------------


def validate_url(value: str) -> str | None:
    """Return ``None`` if ``value`` looks like a URL, else a warning string."""
    parsed = urlparse(value.strip())
    if not parsed.scheme:
        return "Missing URL scheme (e.g. https://)."
    if not parsed.netloc and not parsed.path:
        return "URL has no host or path."
    return None


def validate_json(value: str) -> str | None:
    """Return ``None`` if ``value`` is valid JSON, else a warning string."""
    try:
        json.loads(value)
    except (ValueError, TypeError) as exc:
        return f"Not valid JSON: {exc}"
    return None


def validate_pem(value: str) -> str | None:
    """Return ``None`` if ``value`` looks PEM-ish, else a warning string."""
    text = value.strip()
    if "-----BEGIN" in text and "-----END" in text:
        return None
    return "Does not contain PEM BEGIN/END markers."
