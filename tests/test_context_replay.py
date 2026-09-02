import unittest

from evaluation.context_replay import run_replay
from evaluation.design_scenarios import run_design_scenarios


class ContextReplayTests(unittest.TestCase):
    def test_layered_context_reduces_accumulated_prompt_size_without_losing_evidence(self) -> None:
        result = run_replay()

        self.assertLess(result.layered_total_chars, result.linear_total_chars)
        self.assertLess(result.layered_peak_chars, result.linear_peak_chars)
        self.assertLess(result.truncated_visible_evidence_chars, result.raw_evidence_chars)
        self.assertEqual(result.recovered_evidence_chars, result.raw_evidence_chars)

    def test_design_scenarios_demonstrate_routing_and_revision_gate(self) -> None:
        result = run_design_scenarios()

        self.assertFalse(result.long_output_visible)
        self.assertTrue(result.long_output_searchable)
        self.assertTrue(result.long_output_recovered)
        self.assertFalse(result.early_pointer_visible)
        self.assertTrue(result.early_evidence_searchable)
        self.assertTrue(result.early_evidence_recovered)
        self.assertEqual(
            result.validation_states,
            ("missing", "passed", "missing", "focused_only", "passed"),
        )


if __name__ == "__main__":
    unittest.main()
