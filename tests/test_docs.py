import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class SetupPromptTest(unittest.TestCase):
    def test_prompt_lists_every_template_section(self):
        template = (ROOT / "skills/bogusz/references/profile-template.md").read_text()
        readme = (ROOT / "README.md").read_text()
        m = re.search(r"### The setup prompt\n+```text\n(.*?)\n```", readme, re.S)
        self.assertIsNotNone(m, "no ```text block under '### The setup prompt' in README.md")
        prompt = m.group(1)
        sections = re.findall(r"^## .+$", template, re.M)
        self.assertTrue(sections)
        self.assertEqual(re.findall(r"^## .+$", prompt, re.M), sections)


class SkillReferencesTest(unittest.TestCase):
    def test_every_referenced_file_exists(self):
        skill_dir = ROOT / "skills/bogusz"
        refs = set(re.findall(r"\$\{CLAUDE_SKILL_DIR\}/(\S+?\.md)", (skill_dir / "SKILL.md").read_text()))
        self.assertTrue(refs)
        for ref in sorted(refs):
            self.assertTrue((skill_dir / ref).is_file(), ref)


class NamedSectionsTest(unittest.TestCase):
    def test_sections_the_skill_names_exist_in_the_templates(self):
        refs = ROOT / "skills/bogusz/references"
        templates = (refs / "reporting.md").read_text() + (refs / "profile-template.md").read_text()
        named = set(re.findall(r"`(## [^`]+)`", (ROOT / "skills/bogusz/SKILL.md").read_text()))
        self.assertTrue(named)
        for section in sorted(named):
            self.assertTrue(f"\n{section}\n" in templates, f"{section} is in neither template")


class DigestDocsTest(unittest.TestCase):
    def test_analyst_explains_every_test_status(self):
        source = (ROOT / "skills/bogusz/scripts/sessions.py").read_text()
        statuses = set(re.findall(r'"status"\]? ?[:=] "(\w+)"', source))
        self.assertIn("passed", statuses)
        analyst = (ROOT / "agents/blazej-analyst.md").read_text()
        for status in sorted(statuses):
            self.assertIn(f"- `{status}`:", analyst)


if __name__ == "__main__":
    unittest.main()
