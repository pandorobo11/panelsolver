from __future__ import annotations

import os
import re
import shutil
import tempfile
import tomllib
import unittest
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

from panelsolver.docs_site import (
    _AUDITED_DOCUMENTATION_BUILD_DEPENDENCIES,
    DocumentationSite,
    build_documentation_site,
    validate_documentation_page,
)

ROOT = Path(__file__).resolve().parents[2]


def _source_math_counts(markdown: str) -> Counter[str]:
    """Count authored formulas independently of the rendering extension."""
    counts: Counter[str] = Counter()

    def remove_fence(match: re.Match[str]) -> str:
        if match[2].strip() == "math":
            counts["block"] += 1
        return ""

    prose = re.sub(
        r"^\s*(`{3,}|~{3,})([^\n]*)\n.*?^\s*\1\s*$",
        remove_fence,
        markdown,
        flags=re.MULTILINE | re.DOTALL,
    )
    prose = re.sub(r"(`+).*?\1", "", prose, flags=re.DOTALL)
    delimiters = len(re.findall(r"(?<!\\)\$", prose))
    assert delimiters % 2 == 0, "Unpaired inline math delimiter"
    counts["inline"] = delimiters // 2
    return counts


_NAVIGATION_ENVIRONMENT = """
var timers = [];
var handlers = {};
var window = {
  location: {hash: '#current'},
  setTimeout: function (callback) { timers.push(callback); },
  SphinxRtdTheme: {Navigation: {
    linkScroll: false,
    win: {
      off: function (name) { delete handlers[name]; return this; },
      one: function (name, callback) { handlers[name] = callback; return this; }
    }
  }}
};
function fireHashChange() {
  Object.keys(handlers).forEach(function (name) {
    if (name.split('.')[0] === 'hashchange') {
      var callback = handlers[name];
      delete handlers[name];
      callback();
    }
  });
}
function flushTimers() {
  timers.splice(0).forEach(function (callback) { callback(); });
}
"""


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

    def test_navigation_registers_every_document_once(self) -> None:
        from mkdocs.config import load_config

        def pages(node):
            if isinstance(node, str):
                yield node
            else:
                for child in node.values() if isinstance(node, dict) else node:
                    yield from pages(child)

        nav = load_config(config_file=str(ROOT / "mkdocs.yml"))["nav"]
        registered = list(pages(nav))
        self.assertEqual(len(registered), len(set(registered)))
        home = _ResourceParser()
        home.feed((self.site / "index.html").read_text(encoding="utf-8"))
        for path in set(registered) - {"index.md"}:
            self.assertIn(Path(path).with_suffix(".html").as_posix(), home.links)
        sources = {
            path.relative_to(ROOT / "docs").as_posix()
            for path in (ROOT / "docs").rglob("*.md")
        }
        self.assertEqual(set(registered), sources)

    def test_site_preserves_legal_files(self) -> None:
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

    def test_audited_build_dependency_versions_are_exact_and_current(self) -> None:
        with (ROOT / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream)
        for name, _label, version in _AUDITED_DOCUMENTATION_BUILD_DEPENDENCIES:
            requirement = f"{name}=={version}"
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, project["dependency-groups"]["docs"])
                self.assertIn(requirement, project["build-system"]["requires"])

    def test_unaudited_dependency_versions_fail_before_documentation_build(
        self,
    ) -> None:
        audited = {
            name: version
            for name, _label, version in _AUDITED_DOCUMENTATION_BUILD_DEPENDENCIES
        }
        for changed, expected in audited.items():
            versions = {**audited, changed: f"{expected}+unaudited"}
            with (
                self.subTest(dependency=changed),
                tempfile.TemporaryDirectory() as temporary,
                patch(
                    "panelsolver.docs_site.distribution_version",
                    side_effect=versions.__getitem__,
                ),
                self.assertRaisesRegex(RuntimeError, "requires audited"),
            ):
                build_documentation_site(ROOT, Path(temporary) / "site")

    def test_html_and_css_require_no_network_resources(self) -> None:
        for html in self.site.rglob("*.html"):
            parser = _ResourceParser()
            parser.feed(html.read_text(encoding="utf-8"))
            referenced = set()
            for value in parser.resources:
                with self.subTest(page=html.relative_to(self.site), resource=value):
                    split = urlsplit(value)
                    self.assertEqual("", split.scheme)
                    self.assertEqual("", split.netloc)
                    target = html.parent / unquote(split.path)
                    self.assertTrue(target.is_file(), target)
                    referenced.add(target.resolve())
            for required in (
                "assets/stylesheets/panelsolver-docs.css",
                "assets/javascripts/panelsolver-docs.js",
            ):
                self.assertIn((self.site / required).resolve(), referenced, str(html))
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

    def assert_navigation_unlocks_at_the_right_time(self, javascript: str) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6 import QtQml, QtWidgets

        # Keep a QApplication, rather than QCoreApplication, so GUI tests can reuse it.
        self.__class__.app = (
            QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        )
        for changed_hash in (True, False):
            with self.subTest(changed_hash=changed_hash):
                engine = QtQml.QJSEngine()

                def evaluate(source, current_engine=engine):
                    value = current_engine.evaluate(source)
                    self.assertFalse(value.isError(), value.toString())
                    return value.toVariant()

                evaluate(_NAVIGATION_ENVIRONMENT)
                evaluate(javascript)
                evaluate("window.SphinxRtdTheme.Navigation.hashChange()")
                self.assertTrue(evaluate("window.SphinxRtdTheme.Navigation.linkScroll"))
                if changed_hash:
                    evaluate("window.location.hash = '#next'")
                evaluate("flushTimers()")
                self.assertEqual(
                    changed_hash,
                    evaluate("window.SphinxRtdTheme.Navigation.linkScroll"),
                )
                if changed_hash:
                    evaluate("fireHashChange()")
                    self.assertFalse(
                        evaluate("window.SphinxRtdTheme.Navigation.linkScroll")
                    )
                self.assertEqual(0, evaluate("Object.keys(handlers).length"))

    def test_project_javascript_releases_link_scroll_on_hash_change(self) -> None:
        javascript = (self.site / "assets/javascripts/panelsolver-docs.js").read_text(
            encoding="utf-8"
        )
        self.assert_navigation_unlocks_at_the_right_time(javascript)

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

    def assert_rendered_math(self, source: str, html: str) -> None:
        formulas = re.findall(r"<math\b.*?</math>", html, flags=re.DOTALL)
        displays: Counter[str] = Counter()
        for formula in formulas:
            element = ElementTree.fromstring(formula)
            displays[element.attrib["display"]] += 1
            self.assertFalse(
                any(node.tag.rsplit("}", 1)[-1] == "merror" for node in element.iter()),
                formula,
            )
            text = "".join(element.itertext()).strip()
            self.assertTrue(text, formula)
            self.assertNotRegex(text, r"\\[A-Za-z]+", formula)
            self.assertNotRegex(
                text, r"(?i)(undefined control sequence|parse\s*error)", formula
            )
        self.assertEqual(_source_math_counts(source), displays)
        self.assertNotIn("<{http://www.w3.org/1998/Math/MathML}", html)

    def test_math_is_prerendered_as_self_contained_mathml(self) -> None:
        for source in (ROOT / "docs").rglob("*.md"):
            relative = source.relative_to(ROOT / "docs").with_suffix(".html")
            html = (self.site / relative).read_text(encoding="utf-8")
            with self.subTest(page=relative):
                self.assert_rendered_math(source.read_text(encoding="utf-8"), html)
                self.assertNotIn("mathjax", html.casefold())

    def test_page_validation_accepts_only_normalized_relative_html(self) -> None:
        self.assertEqual(
            "methods/fmf.html",
            validate_documentation_page(" methods/fmf.html "),
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
            "methods/fmf.md",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_documentation_page(value)

    def test_editable_fallback_keeps_temporary_site_alive_until_close(self) -> None:
        site = DocumentationSite()
        # The class fixture already exercises the real strict build. Reuse its
        # files here so this case isolates editable-site lifetime and cleanup.
        with patch(
            "panelsolver.docs_site.build_documentation_site",
            side_effect=lambda _project, target: shutil.copytree(self.site, target),
        ):
            index = site.resolve()
        root = index.parent
        self.assertTrue(index.is_file())
        self.assertEqual(root, site.resolve().parent)
        self.assertTrue(site.resolve("methods/hypersonic.html").is_file())
        self.assertTrue(site.resolve("inputs/fmf-input.html").is_file())
        site.close()
        self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
