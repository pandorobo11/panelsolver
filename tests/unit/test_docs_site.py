from __future__ import annotations

import re
import tempfile
import tomllib
import unittest
from html.parser import HTMLParser
from importlib.metadata import version as distribution_version
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

from panelsolver.docs_site import (
    DocumentationSite,
    build_documentation_site,
    validate_documentation_page,
)

ROOT = Path(__file__).resolve().parents[2]


def _css_declarations(stylesheet: str, selector: str) -> dict[str, str]:
    stylesheet = re.sub(r"/\*.*?\*/", "", stylesheet, flags=re.DOTALL)
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", stylesheet):
        if selector not in (value.strip() for value in selectors.split(",")):
            continue
        return {
            name.strip(): value.strip()
            for declaration in body.split(";")
            if ":" in declaration
            for name, value in (declaration.split(":", 1),)
        }
    raise AssertionError(f"CSS selector {selector!r} is missing")


class _ResourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.resources: list[str] = []
        self.links: list[str] = []
        self.anchors: list[tuple[str, str, str]] = []
        self.ids: set[str] = set()
        self._anchor: tuple[str, str, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(str(values["id"]))
        if tag == "a" and values.get("href"):
            href = str(values["href"])
            self.links.append(href)
            self._anchor = (href, str(values.get("class", "")), [])
        if tag in {"img", "script", "source"} and values.get("src"):
            self.resources.append(str(values["src"]))
        if (
            tag == "link"
            and "stylesheet" in str(values.get("rel", ""))
            and values.get("href")
        ):
            self.resources.append(str(values["href"]))

    def handle_data(self, data: str) -> None:
        if self._anchor is not None:
            self._anchor[2].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor is not None:
            href, class_name, text = self._anchor
            self.anchors.append((href, "".join(text).strip(), class_name))
            self._anchor = None


class DocumentationSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="panelsolver docs ünicode ")
        cls.site = Path(cls.temporary.name) / "offline site"
        build_documentation_site(ROOT, cls.site)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_strict_site_has_current_pages_and_legal_files(self) -> None:
        for relative in (
            "index.html",
            "solvers/fmf.html",
            "solvers/hypersonic.html",
            "reference/fmf-input.html",
            "reference/hypersonic-input.html",
            "reference/coordinate-and-attitude-conventions.html",
            "reference/load-and-coefficient-conventions.html",
            "reference/output-formats.html",
            "user-guide/batch-execution-and-recovery.html",
            "assets/screenshots/gui-overview.png",
            "assets/screenshots/gui-result.png",
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
        ):
            with self.subTest(relative=relative):
                self.assertTrue((self.site / relative).is_file())
        self.assertFalse((self.site / "reference/numerical-conventions.html").exists())
        self.assertEqual(
            (ROOT / "LICENSE").read_bytes(), (self.site / "LICENSE").read_bytes()
        )
        self.assertEqual(
            (ROOT / "THIRD_PARTY_NOTICES.md").read_bytes(),
            (self.site / "THIRD_PARTY_NOTICES.md").read_bytes(),
        )
        for license_file in (ROOT / "THIRD_PARTY_LICENSES").iterdir():
            with self.subTest(license_file=license_file.name):
                packaged = self.site / "THIRD_PARTY_LICENSES" / license_file.name
                self.assertTrue(packaged.is_file())
                self.assertEqual(license_file.read_bytes(), packaged.read_bytes())

    def test_site_excludes_developer_history(self) -> None:
        self.assertFalse((self.site / "devdocs").exists())
        self.assertFalse((self.site / "history").exists())

    def test_normal_user_documentation_does_not_expose_repository_owner(self) -> None:
        sources = [
            ROOT / "README.md",
            ROOT / "THIRD_PARTY_NOTICES.md",
            *sorted((ROOT / "docs").rglob("*.md")),
        ]
        built_pages = [
            self.site / "THIRD_PARTY_NOTICES.md",
            *sorted(self.site.rglob("*.html")),
        ]
        for path in (*sources, *built_pages):
            with self.subTest(path=path):
                self.assertNotIn(
                    "pandorobo11",
                    path.read_text(encoding="utf-8").casefold(),
                )

    def test_audited_build_dependency_versions_are_exact_and_current(self) -> None:
        with (ROOT / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream)
        for requirement in ("mkdocs==1.6.1", "latex2mathml==3.81.0"):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, project["dependency-groups"]["docs"])
                self.assertIn(requirement, project["build-system"]["requires"])
        self.assertEqual("1.6.1", distribution_version("mkdocs"))
        self.assertEqual("3.81.0", distribution_version("latex2mathml"))

    def test_wrong_mkdocs_version_fails_before_documentation_build(self) -> None:
        versions = {"mkdocs": "1.7.0", "latex2mathml": "3.81.0"}
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch(
                "panelsolver.docs_site.distribution_version",
                side_effect=versions.__getitem__,
            ),
            self.assertRaisesRegex(
                RuntimeError,
                r"Offline documentation requires audited MkDocs 1\.6\.1; found 1\.7\.0\.",
            ),
        ):
            build_documentation_site(ROOT, Path(temporary) / "site")

    def test_wrong_latex2mathml_version_fails_before_documentation_build(self) -> None:
        versions = {"mkdocs": "1.6.1", "latex2mathml": "3.82.0"}
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch(
                "panelsolver.docs_site.distribution_version",
                side_effect=versions.__getitem__,
            ),
            self.assertRaisesRegex(
                RuntimeError,
                r"Offline documentation requires audited latex2mathml 3\.81\.0; "
                r"found 3\.82\.0\.",
            ),
        ):
            build_documentation_site(ROOT, Path(temporary) / "site")

    def test_html_and_css_require_no_network_resources(self) -> None:
        for html in self.site.rglob("*.html"):
            parser = _ResourceParser()
            parser.feed(html.read_text(encoding="utf-8"))
            for value in parser.resources:
                with self.subTest(page=html.relative_to(self.site), resource=value):
                    split = urlsplit(value)
                    self.assertEqual("", split.scheme)
                    self.assertEqual("", split.netloc)
                    target = html.parent / unquote(split.path)
                    self.assertTrue(target.is_file(), target)
        for css in self.site.rglob("*.css"):
            for value in re.findall(r"url\(([^)]+)\)", css.read_text(encoding="utf-8")):
                value = value.strip(" \t\"'")
                if not value or value.startswith(("data:", "#")):
                    continue
                with self.subTest(
                    stylesheet=css.relative_to(self.site), resource=value
                ):
                    split = urlsplit(value)
                    self.assertEqual("", split.scheme)
                    self.assertEqual("", split.netloc)
                    self.assertTrue((css.parent / unquote(split.path)).is_file())

    def test_generated_html_loads_project_owned_offline_assets(self) -> None:
        parser = _ResourceParser()
        parser.feed((self.site / "index.html").read_text(encoding="utf-8"))
        paths = {urlsplit(resource).path for resource in parser.resources}
        self.assertIn("assets/stylesheets/panelsolver-docs.css", paths)
        self.assertIn("assets/javascripts/panelsolver-docs.js", paths)

    def test_project_css_keeps_tables_and_block_math_responsive(self) -> None:
        stylesheet = (self.site / "assets/stylesheets/panelsolver-docs.css").read_text(
            encoding="utf-8"
        )
        wrapper = _css_declarations(stylesheet, ".wy-table-responsive")
        table = _css_declarations(
            stylesheet,
            ".wy-table-responsive > table.docutils",
        )
        block_math = _css_declarations(
            stylesheet,
            '.rst-content math[display="block"]',
        )
        self.assertEqual("100%", wrapper.get("width"))
        self.assertEqual("100%", table.get("width"))
        self.assertEqual("max-content", table.get("min-width"))
        self.assertEqual("100%", block_math.get("max-width"))
        self.assertEqual("auto", block_math.get("overflow-x"))

    def test_project_javascript_releases_link_scroll_on_hash_change(self) -> None:
        javascript = (self.site / "assets/javascripts/panelsolver-docs.js").read_text(
            encoding="utf-8"
        )
        self.assertRegex(javascript, r"SphinxRtdTheme\s*&&")
        self.assertIn("SphinxRtdTheme.Navigation", javascript)
        self.assertRegex(javascript, r"\.hashChange\s*=\s*function\s*\(")
        self.assertRegex(javascript, r"\.linkScroll\s*=\s*true")
        self.assertRegex(
            javascript,
            r'\.one\(["\']hashchange(?:\.[^"\']+)?["\']\s*,\s*function\s*\([^)]*\)'
            r"\s*\{[^{}]*\.linkScroll\s*=\s*false",
        )
        timeout_call = re.search(r"\b(?:window\.)?setTimeout\s*\(", javascript)
        self.assertIsNotNone(timeout_call)
        timeout_start = timeout_call.start()
        before_timeout = javascript[:timeout_start]
        timeout_fallback = javascript[timeout_start:]
        initial_hash = re.search(
            r"\b(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*"
            r"window\.location\.hash",
            before_timeout,
        )
        registered_handler = re.search(
            r'\.one\(\s*["\'](?P<event>hashchange(?:\.[^"\']+)?)["\']',
            before_timeout,
        )
        self.assertIsNotNone(initial_hash)
        self.assertIsNotNone(registered_handler)
        unchanged_hash = re.search(
            rf"if\s*\(\s*(?:window\.location\.hash\s*={{2,3}}\s*"
            rf"{re.escape(initial_hash.group('name'))}|"
            rf"{re.escape(initial_hash.group('name'))}\s*={{2,3}}\s*"
            r"window\.location\.hash)\s*\)\s*\{(?P<body>.*?)\}",
            timeout_fallback,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(unchanged_hash)
        fallback_body = unchanged_hash.group("body")
        self.assertRegex(fallback_body, r"\.linkScroll\s*=\s*false")
        self.assertRegex(
            fallback_body,
            rf'\.off\(\s*["\']{re.escape(registered_handler.group("event"))}'
            r'["\']\s*\)',
        )

    def test_internal_links_resolve_from_file_urls(self) -> None:
        parsed: dict[Path, _ResourceParser] = {}
        for html in self.site.rglob("*.html"):
            parser = _ResourceParser()
            parser.feed(html.read_text(encoding="utf-8"))
            parsed[html.resolve()] = parser
        for html, parser in parsed.items():
            for value in parser.links:
                split = urlsplit(value)
                if split.scheme or split.netloc:
                    continue
                target = (
                    html
                    if not split.path
                    else (html.parent / unquote(split.path)).resolve()
                )
                with self.subTest(
                    page=html.relative_to(self.site.resolve()),
                    link=value,
                ):
                    self.assertTrue(target.is_file(), target)
                    if split.fragment and target.suffix == ".html":
                        self.assertIn(unquote(split.fragment), parsed[target].ids)

    def test_math_is_prerendered_as_self_contained_mathml(self) -> None:
        for relative in ("solvers/fmf.html", "solvers/hypersonic.html"):
            html = (self.site / relative).read_text(encoding="utf-8")
            with self.subTest(relative=relative):
                self.assertIn("<math", html)
                self.assertIn('display="block"', html)
                self.assertIn('display="inline"', html)
                self.assertNotIn("```math", html)
                self.assertNotIn("mathjax", html.casefold())
                self.assertNotIn("<{http://www.w3.org/1998/Math/MathML}", html)

    def test_page_validation_accepts_only_normalized_relative_html(self) -> None:
        self.assertEqual(
            "solvers/fmf.html",
            validate_documentation_page(" solvers/fmf.html "),
        )
        for value in (
            None,
            "",
            "/index.html",
            "C:\\index.html",
            "../index.html",
            "solvers/../index.html",
            "solvers\\index.html",
            "solvers//fmf.html",
            "solvers/fmf.md",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_documentation_page(value)

    def test_editable_fallback_keeps_temporary_site_alive_until_close(self) -> None:
        site = DocumentationSite()
        index = site.resolve()
        root = index.parent
        self.assertTrue(index.is_file())
        self.assertEqual(root, site.resolve().parent)
        self.assertTrue(site.resolve("solvers/hypersonic.html").is_file())
        self.assertTrue(site.resolve("reference/fmf-input.html").is_file())
        self.assertTrue(site.resolve("reference/output-formats.html").is_file())
        site.close()
        self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
