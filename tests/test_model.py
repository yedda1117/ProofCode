import json
import unittest

from proofcode.errors import ProtocolError
from proofcode.model import OpenAICompatibleModel


class ModelParsingTests(unittest.TestCase):
    def test_parses_native_tool_call(self) -> None:
        body = {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": json.dumps({"path": "a.py"}),
                                },
                            }
                        ],
                    },
                }
            ]
        }

        response = OpenAICompatibleModel._parse(body)

        self.assertEqual(response.tool_calls[0].name, "read_file")
        self.assertEqual(response.tool_calls[0].arguments, {"path": "a.py"})

    def test_rejects_non_object_arguments(self) -> None:
        body = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "function": {"name": "read_file", "arguments": "[]"},
                            }
                        ]
                    }
                }
            ]
        }

        with self.assertRaises(ProtocolError):
            OpenAICompatibleModel._parse(body)


if __name__ == "__main__":
    unittest.main()
