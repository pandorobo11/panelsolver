from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
DEVDOCS = ROOT / "devdocs"

HISTORICAL_BANNER = (
    "Historical record — non-normative for the current product contract. This "
    "page records the repository state at the migration phase or audit named "
    "below. Statements such as “current”, supported commands, package names, "
    "file formats, and future work apply to that recorded point in time. Pinned "
    "source identities, golden evidence, tolerance profiles, and audit results "
    "may still be referenced by current developer workflows where devdocs/ or "
    "tests explicitly do so. Use docs/, devdocs/architecture/, and accepted or "
    "superseding ADRs for the present product contract."
)

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
    def test_target_tree_has_current_entry_points_and_no_old_user_directories(self) -> None:
        for relative in (
            "docs/index.md",
            "docs/solvers/fmf.md",
            "docs/solvers/hypersonic.md",
            "devdocs/README.md",
            "devdocs/architecture/overview.md",
            "devdocs/development/setup-and-testing.md",
            "devdocs/development/release-and-rollback.md",
            "devdocs/data/us1976-generation-and-audit.md",
            "devdocs/adr/README.md",
            "devdocs/history/README.md",
        ):
            with self.subTest(relative=relative):
                self.assertTrue((ROOT / relative).is_file())
        for relative in (
            "docs/development",
            "docs/adr",
            "docs/history",
            "docs/solvers/fmf-overview.md",
            "docs/solvers/hypersonic-overview.md",
        ):
            with self.subTest(relative=relative):
                self.assertFalse((ROOT / relative).exists())

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

    def test_historical_record_pages_have_standard_banner(self) -> None:
        record_pages = sorted((DEVDOCS / "history" / "migration").rglob("*.md"))
        record_pages.extend(sorted((DEVDOCS / "history" / "audits").glob("*.md")))
        self.assertTrue(record_pages)
        for page in record_pages:
            lines = page.read_text(encoding="utf-8").splitlines()
            with self.subTest(page=page.relative_to(ROOT)):
                self.assertTrue(lines[0].startswith("# "))
                self.assertEqual(HISTORICAL_BANNER, lines[2])
        self.assertNotIn(
            HISTORICAL_BANNER,
            (DEVDOCS / "history" / "README.md").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
