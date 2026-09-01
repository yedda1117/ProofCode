from __future__ import annotations

from pathlib import Path


TEST_RUNNERS = {"pytest", "py.test", "nose2", "tox", "jest", "vitest", "rspec"}
SCRIPT_RUNNERS = {"npm", "npm.cmd", "pnpm", "pnpm.cmd", "yarn", "yarn.cmd", "bun"}


def classify_validation(argv: list[str]) -> str | None:
    if not argv:
        return None
    executable = Path(argv[0]).name.lower()
    arguments = [argument.lower() for argument in argv[1:]]
    if any(argument in {"-h", "--help", "--version"} for argument in arguments):
        return None
    if "--collect-only" in arguments:
        return None

    if executable in TEST_RUNNERS:
        return "test"
    if executable in {"python", "python.exe", "python3", "py", "py.exe"}:
        return _classify_python(arguments)
    if executable in SCRIPT_RUNNERS:
        return _classify_script_runner(arguments)
    if executable == "go" and arguments:
        if arguments[0] == "test":
            return "test"
        if arguments[0] in {"build", "vet"}:
            return "check"
    if executable == "cargo" and arguments:
        if arguments[0] == "test":
            return "check" if "--no-run" in arguments else "test"
        if arguments[0] in {"build", "check", "clippy"}:
            return "check"
    if executable in {"dotnet", "mvn", "mvnw", "mvnw.cmd", "gradle", "gradlew", "gradlew.bat"}:
        return _classify_build_tool(executable, arguments)
    if executable in {"make", "make.exe"} and arguments:
        if any(argument in {"test", "tests", "check"} for argument in arguments):
            return "test"
        if any(argument in {"build", "all", "compile"} for argument in arguments):
            return "check"
    return None


def _classify_python(arguments: list[str]) -> str | None:
    if len(arguments) >= 2 and arguments[0] == "-m":
        module = arguments[1]
        if module in {"unittest", "pytest", "nose2", "tox"}:
            return "test"
        if module in {"compileall", "py_compile", "mypy", "ruff"}:
            return "check"
    if len(arguments) >= 2 and arguments[0].endswith("manage.py") and arguments[1] == "test":
        return "test"
    if arguments:
        script = arguments[0].replace("\\", "/")
        name = Path(script).name
        if (
            script.startswith("tests/")
            or "/tests/" in script
            or name.startswith("test_")
            or name.endswith("_test.py")
        ):
            return "test"
    return None


def _classify_script_runner(arguments: list[str]) -> str | None:
    commands = [argument for argument in arguments if not argument.startswith("-")]
    if "run" in commands:
        commands.remove("run")
    if any(command in {"test", "test:unit", "test:integration"} for command in commands):
        return "test"
    if any(command in {"build", "check", "lint", "typecheck"} for command in commands):
        return "check"
    return None


def _classify_build_tool(executable: str, arguments: list[str]) -> str | None:
    if executable == "dotnet":
        if "test" in arguments:
            return "test"
        if any(command in arguments for command in {"build", "format"}):
            return "check"
    if executable in {"mvn", "mvnw", "mvnw.cmd"}:
        if any(command in arguments for command in {"test", "verify"}):
            return "test"
        if any(command in arguments for command in {"compile", "package"}):
            return "check"
    if executable in {"gradle", "gradlew", "gradlew.bat"}:
        if any("test" in command.lower() for command in arguments):
            return "test"
        if any(command in arguments for command in {"build", "check", "assemble"}):
            return "check"
    return None
