import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class SetupPromptTest(unittest.TestCase):
    def test_prompt_lists_every_template_section(self):
        template = (ROOT / "skills/bogusz/references/profile-template.md").read_text()
        readme = (ROOT / "README.md").read_text()
        prompt = re.search(r"### The setup prompt\n+```text\n(.*?)\n```", readme, re.S).group(1)
        sections = re.findall(r"^## .+$", template, re.M)
        self.assertTrue(sections)
        self.assertEqual(re.findall(r"^## .+$", prompt, re.M), sections)


if __name__ == "__main__":
    unittest.main()
