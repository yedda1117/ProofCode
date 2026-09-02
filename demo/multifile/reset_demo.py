from pathlib import Path


AUTH_SOURCE = '''def extract_bearer_token(header: str | None) -> str | None:
    """Extract a token from an HTTP Authorization header."""
    if not header:
        return None
    return header.removeprefix("Bearer ").strip()


def authenticate(token: str | None) -> bool:
    """Return whether an extracted token should be accepted."""
    return bool(token and token.strip())
'''


MIDDLEWARE_SOURCE = '''from auth import authenticate


def authorize(headers: dict[str, str]) -> bool:
    """Authorize one request from its HTTP headers."""
    return authenticate(headers.get("Authorization"))
'''


workspace = Path(__file__).parent / "workspace"
workspace.joinpath("auth.py").write_text(AUTH_SOURCE, encoding="utf-8")
workspace.joinpath("middleware.py").write_text(MIDDLEWARE_SOURCE, encoding="utf-8")
print("Multi-file demo reset: parser and middleware contain intentional integration bugs.")
