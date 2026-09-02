def extract_bearer_token(header: str | None) -> str | None:
    """Extract a token from an HTTP Authorization header."""
    if not header:
        return None
    return header.removeprefix("Bearer ").strip()


def authenticate(token: str | None) -> bool:
    """Return whether an extracted token should be accepted."""
    return bool(token and token.strip())
