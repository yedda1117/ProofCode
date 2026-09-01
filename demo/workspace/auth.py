def authenticate(token: str | None) -> bool:
    """Return whether a request token should be accepted."""
    return token is not None
