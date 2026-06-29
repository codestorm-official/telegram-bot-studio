import unittest
from pathlib import Path

from jinja2 import Environment


class TemplateSyntaxTests(unittest.TestCase):
    def test_all_panel_templates_parse(self):
        environment = Environment()
        templates = Path("bot/panel/templates").glob("*.html")
        for template in templates:
            with self.subTest(template=template.name):
                environment.parse(template.read_text())

    def test_keyboard_refresh_guidance_exists(self):
        base = Path("bot/panel/templates/base.html").read_text()
        self.assertIn("run <code>/start</code> again", base)


if __name__ == "__main__":
    unittest.main()
