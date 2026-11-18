import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills/bogusz/scripts/report_html.py"
sys.path.insert(0, str(SCRIPT.parent))

from report_html import page  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class ExampleReportTest(unittest.TestCase):
    def setUp(self):
        self.out = page((ROOT / "docs/example-report.md").read_text(), ROOT / "docs")

    def test_every_result_row_and_status(self):
        for n in range(1, 14):
            self.assertIn("<td>T%d</td>" % n, self.out)
        self.assertEqual(self.out.count('<tr data-s="passed">'), 11)
        self.assertEqual(self.out.count('<tr data-s="not run">'), 2)
        self.assertIn('<section id="verdict" class="verdict passed">', self.out)
        self.assertIn('aria-label="11 passed, 0 failed, 2 not run"', self.out)

    def test_loads_nothing_from_the_network(self):
        self.assertIn("default-src 'none'", self.out)
        self.assertIsNone(re.search(r"<(?:link|iframe|object)|\ssrc=\"(?!data:)", self.out))


class SafetyTest(unittest.TestCase):
    def test_markup_in_cells_is_escaped(self):
        out = page("| ID | Case | Status |\n|---|---|---|\n| T1 | <script>alert(1)</script> | failed |\n", Path("."))
        self.assertNotIn("<script>alert", out)
        self.assertIn("&lt;script&gt;alert(1)", out)

    def test_only_safe_links_become_anchors(self):
        out = page("[a](javascript:alert(1)) [b](https://example.com/x)\n", Path("."))
        self.assertNotIn('href="javascript', out)
        self.assertIn('<a href="https://example.com/x">b</a>', out)


class ScreenshotTest(unittest.TestCase):
    def test_images_are_embedded_and_fakes_are_not(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "step1.png").write_bytes(PNG)
            (Path(d) / "fake.png").write_text("not an image")
            md = "| # | Screenshot |\n|---|---|\n| 1 | `step1.png` |\n| 2 | fake.png |\n| 3 | missing.png |\n"
            out = page(md, Path(d))
        self.assertEqual(out.count('src="data:image/png;base64,'), 1)
        self.assertIn("fake.png", out)
        self.assertIn("missing.png", out)


class CliTest(unittest.TestCase):
    def test_writes_html_next_to_the_report(self):
        with tempfile.TemporaryDirectory() as d:
            md = Path(d) / "r.md"
            md.write_text("# Test report: x  (2026-01-01, r@main abc)\n\n## Verdict\nFailed. 1 of 1 failed.\n")
            res = subprocess.run([sys.executable, "-I", str(SCRIPT), str(md)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stderr)
            html = (Path(d) / "r.html").read_text()
        self.assertIn('class="verdict failed"', html)
        self.assertIn('<div class="meta">2026-01-01, r@main abc</div>', html)


if __name__ == "__main__":
    unittest.main()
