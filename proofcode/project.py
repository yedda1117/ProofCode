from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from proofcode.validation import classify_validation, validation_scope


@dataclass(frozen=True)
class ValidationPolicy:
    required_commands: tuple[tuple[str, ...], ...] = ()
    suggested_commands: tuple[tuple[str, ...], ...] = ()
    source: str = "none"
    warning: str | None = None

    def prompt_line(self) -> str:
        if self.required_commands:
            commands = " && ".join(" ".join(command) for command in self.required_commands)
            return f"required ({self.source}): {commands}"
        if self.suggested_commands:
            commands = " | ".join(" ".join(command) for command in self.suggested_commands)
            return f"suggested ({self.source}): {commands}"
        if self.warning:
            return f"none; warning={self.warning}"
        return "none discovered"


def discover_validation_policy(root: Path) -> ValidationPolicy:
    configured = root / ".proofcode.json"
    if configured.is_file():
        try:
            payload = json.loads(configured.read_text(encoding="utf-8"))
            commands = payload.get("validation", {}).get("required_commands", [])
            required = _validated_commands(commands)
            if not required:
                raise ValueError("validation.required_commands must not be empty")
            return ValidationPolicy(
                required_commands=required,
                source=".proofcode.json",
            )
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            return ValidationPolicy(
                source=".proofcode.json",
                warning=f"invalid validation policy: {exc}",
            )

    suggestions: list[tuple[str, ...]] = []
    package_json = root / "package.json"
    if package_json.is_file():
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
            scripts = payload.get("scripts", {})
            if isinstance(scripts, dict) and "test" in scripts:
                suggestions.append(("npm", "test"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
    if (root / "Cargo.toml").is_file():
        suggestions.append(("cargo", "test"))
    if (root / "go.mod").is_file():
        suggestions.append(("go", "test", "./..."))
    if (root / "pom.xml").is_file():
        suggestions.append(("mvn", "test"))
    if (root / "gradlew").is_file() or (root / "gradlew.bat").is_file():
        executable = "gradlew.bat" if (root / "gradlew.bat").is_file() else "./gradlew"
        suggestions.append((executable, "test"))

    pyproject = root / "pyproject.toml"
    pytest_configured = any(
        path.is_file()
        for path in (root / "pytest.ini", root / "conftest.py", root / "tox.ini")
    )
    if pyproject.is_file():
        try:
            text = pyproject.read_text(encoding="utf-8").casefold()
            pytest_configured = pytest_configured or "pytest" in text
        except (OSError, UnicodeError):
            pass
    if pytest_configured:
        suggestions.append(("python", "-m", "pytest"))
    elif (root / "tests").is_dir():
        suggestions.append(("python", "-m", "unittest", "discover", "-v"))

    unique = tuple(dict.fromkeys(suggestions))
    return ValidationPolicy(
        suggested_commands=unique,
        source="project discovery" if unique else "none",
    )


def _validated_commands(value: object) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, list):
        raise TypeError("required_commands must be an array")
    commands: list[tuple[str, ...]] = []
    for position, command in enumerate(value, start=1):
        if not isinstance(command, list) or not command or not all(
            isinstance(item, str) and item for item in command
        ):
            raise TypeError(f"required command {position} must be a non-empty argv array")
        if classify_validation(command) is None or validation_scope(command) != "project":
            raise ValueError(
                f"required command {position} must be recognized project-wide validation"
            )
        commands.append(tuple(command))
    return tuple(commands)
