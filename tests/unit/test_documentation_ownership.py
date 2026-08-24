from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
DEVDOCS = ROOT / "devdocs"

MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\((?P<target><[^>]+>|[^\s)]+)")


def markdown_without_fenced_code(text: str) -> str:
    retained: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        stripped = line.lstrip()
        marker = stripped[:3]
        if fence is None and marker in {"```", "~~~"}:
            fence = marker
            continue
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            continue
        retained.append(line)
    return "\n".join(retained)


def local_markdown_targets(path: Path) -> list[str]:
    text = markdown_without_fenced_code(path.read_text(encoding="utf-8"))
    return [match.group("target").strip("<>") for match in MARKDOWN_LINK.finditer(text)]


class DocumentationOwnershipTests(unittest.TestCase):
    def test_user_markdown_does_not_link_to_developer_material(self) -> None:
        forbidden_text = (
            "devdocs/",
            "../devdocs/",
            "docs/development/",
            "docs/adr/",
            "docs/history/",
        )
        for page in sorted(DOCS.rglob("*.md")):
            for target in local_markdown_targets(page):
                split = urlsplit(target)
                if split.scheme or split.netloc or not split.path:
                    continue
                decoded = unquote(split.path)
                resolved = (page.parent / decoded).resolve()
                with self.subTest(page=page.relative_to(ROOT), target=target):
                    self.assertFalse(any(value in decoded for value in forbidden_text))
                    self.assertFalse(resolved.is_relative_to(DEVDOCS.resolve()))

    def test_all_local_devdocs_markdown_file_targets_exist(self) -> None:
        for page in sorted(DEVDOCS.rglob("*.md")):
            for target in local_markdown_targets(page):
                split = urlsplit(target)
                if split.scheme or split.netloc or not split.path:
                    continue
                resolved = (page.parent / unquote(split.path)).resolve()
                with self.subTest(page=page.relative_to(ROOT), target=target):
                    self.assertTrue(resolved.is_file(), resolved)


if __name__ == "__main__":
    unittest.main()
