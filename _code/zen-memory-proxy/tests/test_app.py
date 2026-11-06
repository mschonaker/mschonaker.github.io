import json
import tempfile
import unittest
from pathlib import Path

import app as proxy


class RunToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.previous = proxy.DB
        proxy.DB = Path(self.tmp.name) / "memory.db"

    def tearDown(self) -> None:
        proxy.DB = self.previous
        self.tmp.cleanup()

    def test_remember_and_recall(self) -> None:
        stored = json.loads(proxy.run_tool("remember", '{"fact": "The user prefers tea."}'))
        found = json.loads(proxy.run_tool("recall", '{"query": "tea"}'))
        self.assertEqual(found["facts"][0]["id"], stored["id"])
        self.assertEqual(found["facts"][0]["text"], "The user prefers tea.")

    def test_recall_falls_back_to_recent(self) -> None:
        proxy.run_tool("remember", '{"fact": "First fact."}')
        proxy.run_tool("remember", '{"fact": "Second fact."}')
        found = json.loads(proxy.run_tool("recall", '{"query": "zzz"}'))
        self.assertEqual([fact["text"] for fact in found["facts"]], ["Second fact.", "First fact."])

    def test_sse_is_valid(self) -> None:
        data = {
            "id": "chatcmpl-test",
            "created": 1,
            "model": "test",
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        }
        stream = proxy.sse(data)
        self.assertTrue(stream.startswith("data: "))
        self.assertTrue(stream.endswith("data: [DONE]\n\n"))


if __name__ == "__main__":
    unittest.main()
