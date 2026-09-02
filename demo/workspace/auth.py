def authenticate(token: str | None) -> bool:
    """Return whether a request token should be accepted."""
    return bool(token)
