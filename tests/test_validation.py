import unittest

from proofcode.validation import classify_validation, validation_scope


class ValidationClassificationTests(unittest.TestCase):
    def test_distinguishes_project_and_focused_tests(self) -> None:
        self.assertEqual(validation_scope(["pytest", "-q"]), "project")
        self.assertEqual(validation_scope(["pytest", "tests/test_math.py"]), "focused")
        self.assertEqual(validation_scope(["pytest", "-k", "math"]), "focused")
        self.assertEqual(validation_scope(["npm", "test"]), "project")
        self.assertEqual(validation_scope(["npm", "test", "--", "test_math"]), "focused")
        self.assertEqual(validation_scope(["go", "test", "./..."]), "project")
        self.assertEqual(validation_scope(["go", "test", "./auth"]), "focused")
        self.assertEqual(validation_scope(["cargo", "test"]), "project")
        self.assertEqual(validation_scope(["cargo", "test", "auth_test"]), "focused")
        self.assertEqual(validation_scope(["python", "-m", "compileall", "."]), "project")
        self.assertEqual(
            validation_scope(["python", "-m", "py_compile", "auth.py"]), "focused"
        )
        self.assertEqual(validation_scope(["python", "-m", "ruff", "check", "."]), "project")
        self.assertEqual(
            validation_scope(["python", "-m", "ruff", "check", "auth.py"]), "focused"
        )
        self.assertEqual(validation_scope(["npm", "run", "lint"]), "project")
        self.assertEqual(
            validation_scope(["npm", "run", "lint", "--", "auth.js"]), "focused"
        )
        self.assertEqual(
            validation_scope(["python", "-m", "unittest", "discover"]), "project"
        )
        self.assertEqual(
            validation_scope(["python", "-m", "unittest", "tests.test_math"]), "focused"
        )

    def test_recognizes_common_test_commands(self) -> None:
        commands = [
            ["python", "-m", "unittest", "discover"],
            ["python", "-m", "pytest", "tests/test_agent.py"],
            ["pytest", "-q"],
            ["npm", "test"],
            ["cargo", "test"],
            ["go", "test", "./..."],
            ["dotnet", "test"],
            ["mvn", "verify"],
            ["gradlew.bat", "test"],
        ]

        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(classify_validation(command), "test")

    def test_recognizes_build_and_static_checks(self) -> None:
        commands = [
            ["python", "-m", "compileall", "."],
            ["python", "-m", "ruff", "check", "."],
            ["npm", "run", "build"],
            ["cargo", "check"],
            ["go", "vet", "./..."],
            ["dotnet", "build"],
        ]

        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(classify_validation(command), "check")

    def test_rejects_successful_but_unrelated_commands(self) -> None:
        commands = [
            ["python", "-c", "print('ok')"],
            ["echo", "test"],
            ["git", "status"],
            ["pytest", "--help"],
            ["pytest", "--collect-only"],
        ]

        for command in commands:
            with self.subTest(command=command):
                self.assertIsNone(classify_validation(command))

    def test_treats_test_compilation_without_execution_as_check(self) -> None:
        self.assertEqual(classify_validation(["cargo", "test", "--no-run"]), "check")


if __name__ == "__main__":
    unittest.main()
