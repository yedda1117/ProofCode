import unittest

from auth import authenticate


class AuthTests(unittest.TestCase):
    def test_non_empty_token_is_accepted(self) -> None:
        self.assertTrue(authenticate("valid-token"))

    def test_empty_token_is_rejected(self) -> None:
        self.assertFalse(authenticate(""))


if __name__ == "__main__":
    unittest.main()
