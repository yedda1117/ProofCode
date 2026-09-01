import unittest

from proofcode.context import Conversation


class ConversationTests(unittest.TestCase):
    def test_context_trims_whole_exchanges(self) -> None:
        conversation = Conversation("system", "task")
        conversation.add_exchange(
            {"role": "assistant", "content": None, "tool_calls": [{"id": "1"}]},
            [{"role": "tool", "tool_call_id": "1", "content": "a" * 100}],
        )
        conversation.add_exchange(
            {"role": "assistant", "content": None, "tool_calls": [{"id": "2"}]},
            [{"role": "tool", "tool_call_id": "2", "content": "recent"}],
        )

        messages = conversation.messages(180)

        serialized = str(messages)
        self.assertNotIn("'tool_call_id': '1'", serialized)
        self.assertIn("'tool_call_id': '2'", serialized)
        self.assertIn("earlier tool exchange", serialized)

    def test_places_workspace_context_before_tool_history(self) -> None:
        conversation = Conversation("system", "task")
        conversation.add_exchange(
            {"role": "assistant", "content": None, "tool_calls": [{"id": "1"}]},
            [{"role": "tool", "tool_call_id": "1", "content": "result"}],
        )

        messages = conversation.messages(1_000, "L1 CONTEXT INDEX")

        self.assertEqual(messages[2], {"role": "system", "content": "L1 CONTEXT INDEX"})
        self.assertEqual(messages[3]["role"], "assistant")


if __name__ == "__main__":
    unittest.main()
