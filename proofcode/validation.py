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


def validation_scope(argv: list[str]) -> str | None:
    """Classify recognized validation as project-wide or explicitly focused.

    This is deliberately a syntactic, conservative policy.  It does not claim
    that a project-wide suite is complete or semantically covers every change.
    """
    kind = classify_validation(argv)
    if kind is None:
        return None
    executable = Path(argv[0]).name.lower()
    arguments = [argument.lower() for argument in argv[1:]]

    if executable in TEST_RUNNERS:
        return "focused" if _has_test_selector(arguments) else "project"
    if executable in {"python", "python.exe", "python3", "py", "py.exe"}:
        if len(arguments) >= 2 and arguments[0] == "-m":
            module = arguments[1]
            remaining = arguments[2:]
            if module == "unittest":
                return "project" if not remaining or remaining[0] == "discover" else "focused"
            if module in {"pytest", "nose2", "tox"}:
                return "focused" if _has_test_selector(remaining) else "project"
            if module == "py_compile":
                return "focused"
            if module == "compileall":
                targets = [argument for argument in remaining if not argument.startswith("-")]
                return "project" if not targets or targets == ["."] else "focused"
            if module in {"mypy", "ruff"}:
                targets = [
                    argument
                    for argument in remaining
                    if not argument.startswith("-") and argument != "check"
                ]
                return "project" if not targets or targets == ["."] else "focused"
        if arguments and classify_validation(argv) == "test":
            return "focused"
    if executable in SCRIPT_RUNNERS:
        commands = [argument for argument in arguments if argument != "run"]
        command_names = (
            {"test", "test:unit", "test:integration"}
            if kind == "test"
            else {"build", "check", "lint", "typecheck"}
        )
        command_index = next(
            (
                index
                for index, argument in enumerate(commands)
                if argument in command_names
            ),
            None,
        )
        remaining = commands[command_index + 1 :] if command_index is not None else []
        return "focused" if _has_test_selector(remaining) else "project"
    if executable == "go" and arguments and arguments[0] == "test":
        packages = [argument for argument in arguments[1:] if not argument.startswith("-")]
        return "project" if packages == ["./..."] else "focused"
    if executable == "cargo" and arguments and arguments[0] == "test":
        remaining = arguments[1:]
        focused_flags = {"--test", "--package", "-p", "--bin", "--example"}
        if any(argument in focused_flags for argument in remaining):
            return "focused"
        return "focused" if _has_test_selector(remaining) else "project"
    # Build, lint and type-check commands are treated as project checks unless
    # their ecosystem-specific classifier says they are not validation at all.
    return "project"


def normalized_validation_argv(argv: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if not argv:
        return ()
    executable = Path(argv[0]).name.lower()
    if executable in {"python.exe", "python3", "py", "py.exe"}:
        executable = "python"
    elif executable.endswith(".cmd") and executable[:-4] in {
        "npm",
        "pnpm",
        "yarn",
        "mvnw",
    }:
        executable = executable[:-4]
    return (executable, *(argument.lower() for argument in argv[1:]))


def _has_test_selector(arguments: list[str]) -> bool:
    selector_flags = {
        "-k",
        "-m",
        "--ignore",
        "--ignore-glob",
        "--deselect",
        "--testnamepattern",
        "--testpathpattern",
    }
    selector_prefixes = (
        "-k=",
        "-m=",
        "--ignore=",
        "--ignore-glob=",
        "--deselect=",
        "--testnamepattern=",
        "--testpathpattern=",
    )
    options_with_values = {"--maxfail", "--tb", "--junitxml", "--rootdir", "-c"}
    skip_next = False
    for argument in arguments:
        if skip_next:
            skip_next = False
            continue
        if argument in selector_flags or argument.startswith(selector_prefixes):
            return True
        if argument in options_with_values:
            skip_next = True
            continue
        if argument.startswith("-"):
            continue
        return True
    return False


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
