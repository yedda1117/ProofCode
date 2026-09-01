import unittest

from proofcode.validation import classify_validation


class ValidationClassificationTests(unittest.TestCase):
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
