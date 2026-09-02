from auth import authenticate


def authorize(headers: dict[str, str]) -> bool:
    """Authorize one request from its HTTP headers."""
    return authenticate(headers.get("Authorization"))
