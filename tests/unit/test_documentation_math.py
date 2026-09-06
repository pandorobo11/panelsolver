from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOLVER_DOCS = (
    ROOT / "docs" / "methods" / "fmf.md",
    ROOT / "docs" / "methods" / "hypersonic.md",
)
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
WHOLE_EMPHASIS_RE = re.compile(r"\*(?!\*)[\s\S]*\*")


def _is_closing_fence(line: str, marker: str, minimum_length: int) -> bool:
    indentation = len(line) - len(line.lstrip(" "))
    candidate = line.strip()
    return (
        indentation <= 3
        and len(candidate) >= minimum_length
        and set(candidate) == {marker}
    )


def _scan_markdown(markdown: str) -> tuple[int, list[int], tuple[int, str] | None]:
    math_block_count = 0
    legacy_display_markers: list[int] = []
    active_fence: tuple[str, int, int, str] | None = None

    for line_number, line in enumerate(markdown.splitlines(), 1):
        if active_fence is not None:
            marker, minimum_length, _start_line, _info = active_fence
            if _is_closing_fence(line, marker, minimum_length):
                active_fence = None
            continue

        fence_match = FENCE_RE.match(line)
        if fence_match is not None:
            fence, info = fence_match.groups()
            info = info.strip()
            active_fence = (fence[0], len(fence), line_number, info)
            if info == "math":
                math_block_count += 1
            continue

        if line.strip() == "$$":
            legacy_display_markers.append(line_number)

    if active_fence is None:
        unclosed_fence = None
    else:
        marker, minimum_length, start_line, info = active_fence
        unclosed_fence = (start_line, marker * minimum_length + info)

    return math_block_count, legacy_display_markers, unclosed_fence


def _figure_captions(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    captions: list[str] = []

    for line_number, line in enumerate(lines):
        if not line.startswith("![") or line_number + 2 >= len(lines):
            continue
        if lines[line_number + 1] != "":
            continue

        caption_lines: list[str] = []
        for caption_line in lines[line_number + 2 :]:
            if caption_line == "":
                break
            caption_lines.append(caption_line)
        captions.append("\n".join(caption_lines))

    return captions


class DocumentationMathTest(unittest.TestCase):
    def test_solver_docs_use_balanced_fenced_math_blocks(self) -> None:
        for path in SOLVER_DOCS:
            with self.subTest(path=path.relative_to(ROOT)):
                markdown = path.read_text(encoding="utf-8")
                math_block_count, _legacy_markers, unclosed_fence = _scan_markdown(
                    markdown
                )
                self.assertGreater(math_block_count, 0)
                self.assertIsNone(unclosed_fence)

    def test_solver_docs_do_not_use_legacy_multiline_display_math(self) -> None:
        for path in SOLVER_DOCS:
            with self.subTest(path=path.relative_to(ROOT)):
                markdown = path.read_text(encoding="utf-8")
                _math_block_count, legacy_markers, _unclosed_fence = _scan_markdown(
                    markdown
                )
                self.assertEqual(legacy_markers, [])

    def test_solver_docs_do_not_use_unsupported_operatorname_macro(self) -> None:
        for path in SOLVER_DOCS:
            with self.subTest(path=path.relative_to(ROOT)):
                markdown = path.read_text(encoding="utf-8")
                self.assertNotIn(r"\operatorname", markdown)

    def test_math_figure_captions_do_not_wrap_the_whole_paragraph_in_emphasis(
        self,
    ) -> None:
        for path in SOLVER_DOCS:
            with self.subTest(path=path.relative_to(ROOT)):
                markdown = path.read_text(encoding="utf-8")
                for caption in _figure_captions(markdown):
                    if "$" not in caption:
                        continue
                    self.assertIsNone(WHOLE_EMPHASIS_RE.fullmatch(caption))

    def test_scanner_ignores_math_examples_inside_code_fences(self) -> None:
        markdown = r"""````markdown
$$
sample only
$$
```math
sample only
```
````

Inline $C_p$ remains allowed.

```math
C_p=2\sin^2\delta
```
"""

        math_block_count, legacy_markers, unclosed_fence = _scan_markdown(markdown)

        self.assertEqual(math_block_count, 1)
        self.assertEqual(legacy_markers, [])
        self.assertIsNone(unclosed_fence)


if __name__ == "__main__":
    unittest.main()
