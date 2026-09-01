import unittest

from evaluation.context_replay import run_replay


class ContextReplayTests(unittest.TestCase):
    def test_layered_context_reduces_accumulated_prompt_size_without_losing_evidence(self) -> None:
        result = run_replay()

        self.assertLess(result.layered_total_chars, result.linear_total_chars)
        self.assertLess(result.layered_peak_chars, result.linear_peak_chars)
        self.assertLess(result.truncated_visible_evidence_chars, result.raw_evidence_chars)
        self.assertEqual(result.recovered_evidence_chars, result.raw_evidence_chars)


if __name__ == "__main__":
    unittest.main()
