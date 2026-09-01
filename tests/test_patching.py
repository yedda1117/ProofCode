import unittest

from proofcode.errors import ToolError
from proofcode.patching import apply_unified_hunks


class UnifiedPatchTests(unittest.TestCase):
    def test_applies_multiple_hunks(self) -> None:
        content = "one\ntwo\nthree\nfour\nfive\n"
        patch = "@@ -1,2 +1,2 @@\n one\n-two\n+second\n@@ -4,2 +4,2 @@\n four\n-five\n+fifth"

        result = apply_unified_hunks(content, patch)

        self.assertEqual(result, "one\nsecond\nthree\nfour\nfifth\n")

    def test_rejects_file_headers(self) -> None:
        with self.assertRaises(ToolError):
            apply_unified_hunks("old\n", "--- a.txt\n+++ a.txt\n@@ -1 +1 @@\n-old\n+new")


if __name__ == "__main__":
    unittest.main()
