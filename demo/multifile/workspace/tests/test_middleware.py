import unittest

from middleware import authorize


class MiddlewareTests(unittest.TestCase):
    def test_accepts_valid_bearer_header(self) -> None:
        self.assertTrue(authorize({"Authorization": "Bearer valid-token"}))

    def test_rejects_other_authorization_scheme(self) -> None:
        self.assertFalse(authorize({"Authorization": "Basic credentials"}))

    def test_rejects_missing_authorization_header(self) -> None:
        self.assertFalse(authorize({}))


if __name__ == "__main__":
    unittest.main()
