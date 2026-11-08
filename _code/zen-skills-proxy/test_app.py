import tempfile
import unittest
from pathlib import Path

from app import Skills, Facts


class SkillsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.skills = Skills(Path(self.tmp.name) / "knowledge.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_learn_and_load(self) -> None:
        stored = self.skills.add("greet", "Greet the user", "Say hello.")
        self.assertEqual(stored["name"], "greet")
        loaded = self.skills.get("greet")
        self.assertEqual(loaded["content"], "Say hello.")

    def test_list_front_matter(self) -> None:
        self.skills.add("a", "desc a", "body a")
        self.skills.add("b", "desc b", "body b")
        items = self.skills.list()
        self.assertEqual([(s["name"], s["description"]) for s in items], [("a", "desc a"), ("b", "desc b")])

    def test_execute_learn(self) -> None:
        result = self.skills.execute(
            "skill_learn", '{"name": "tea", "description": "Tea rule", "content": "Prefer tea."}'
        )
        self.assertIn("tea", result)
        self.assertIn("Prefer tea.", self.skills.get("tea")["content"])

    def test_execute_learn_from_markdown(self) -> None:
        md = "---\nname: md-skill\ndescription: from markdown\n---\nBody here."
        result = self.skills.execute("skill_learn", {"markdown": md})
        self.assertIn("md-skill", result)
        self.assertEqual(self.skills.get("md-skill")["content"], "Body here.")

    def test_execute_load(self) -> None:
        self.skills.add("x", "dx", "cx")
        result = self.skills.execute("skill_load", '{"name": "x"}')
        self.assertIn("cx", result)

    def test_execute_forget(self) -> None:
        self.skills.add("tmp", "d", "c")
        self.assertTrue(self.skills.delete("tmp"))
        self.assertFalse(self.skills.delete("tmp"))

    def test_execute_unknown_skill_call(self) -> None:
        self.assertIn("unknown tool", self.skills.execute("nope", "{}"))

    def test_parse_markdown(self) -> None:
        name, desc, body = Skills.parse_markdown("---\nname: n\ndescription: d\n---\nbody")
        self.assertEqual((name, desc, body), ("n", "d", "body"))


class FactsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.facts = Facts(Path(self.tmp.name) / "knowledge.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_set_and_get(self) -> None:
        self.facts.set("user_name", "Martin")
        self.assertEqual(self.facts.get("user_name")["value"], "Martin")

    def test_list(self) -> None:
        self.facts.set("a", "1")
        self.facts.set("b", "2")
        self.assertEqual([(f["key"], f["value"]) for f in self.facts.list()], [("a", "1"), ("b", "2")])

    def test_execute_set(self) -> None:
        result = self.facts.execute("fact_set", '{"key": "model", "value": "qwen"}')
        self.assertIn("model", result)

    def test_execute_forget(self) -> None:
        self.facts.set("tmp", "v")
        self.assertTrue(self.facts.delete("tmp"))
        self.assertFalse(self.facts.delete("tmp"))

    def test_execute_unknown(self) -> None:
        self.assertIn("unknown tool", self.facts.execute("nope", "{}"))


if __name__ == "__main__":
    unittest.main()
