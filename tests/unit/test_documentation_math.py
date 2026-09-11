from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class DocumentationMathTest(unittest.TestCase):
    def test_user_docs_do_not_use_unsupported_operatorname_macro(self) -> None:
        for path in sorted((ROOT / "docs").rglob("*.md")):
            with self.subTest(path=path.relative_to(ROOT)):
                markdown = path.read_text(encoding="utf-8")
                self.assertNotIn(r"\operatorname", markdown)


if __name__ == "__main__":
    unittest.main()
