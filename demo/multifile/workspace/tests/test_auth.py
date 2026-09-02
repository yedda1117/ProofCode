import unittest

from auth import authenticate, extract_bearer_token


class AuthTests(unittest.TestCase):
    def test_extracts_non_empty_bearer_token(self) -> None:
        self.assertEqual(extract_bearer_token("Bearer valid-token"), "valid-token")

    def test_rejects_non_bearer_scheme(self) -> None:
        self.assertIsNone(extract_bearer_token("Basic credentials"))

    def test_rejects_empty_bearer_value(self) -> None:
        self.assertIsNone(extract_bearer_token("Bearer   "))

    def test_scheme_is_case_sensitive(self) -> None:
        self.assertIsNone(extract_bearer_token("bearer valid-token"))

    def test_authenticate_accepts_only_non_empty_extracted_token(self) -> None:
        self.assertTrue(authenticate("valid-token"))
        self.assertFalse(authenticate(""))
        self.assertFalse(authenticate(None))


if __name__ == "__main__":
    unittest.main()
