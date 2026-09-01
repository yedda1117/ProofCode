from pathlib import Path


AUTH_SOURCE = '''def authenticate(token: str | None) -> bool:
    """Return whether a request token should be accepted."""
    return token is not None
'''


workspace = Path(__file__).parent / "workspace"
(workspace / "auth.py").write_text(AUTH_SOURCE, encoding="utf-8")
print("Demo workspace reset: auth.py contains the intentional empty-token bug.")
