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
            "reference/output-formats.html",
            "user-guide/outputs.html",
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
        ):
            with self.subTest(relative=relative):
                self.assertTrue((self.site / relative).is_file())
        self.assertEqual((ROOT / "LICENSE").read_bytes(), (self.site / "LICENSE").read_bytes())
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
        for requirement in ("mkdocs==1.6.1", "latex2mathml==3.81.0"):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, project["dependency-groups"]["docs"])
                self.assertIn(requirement, project["build-system"]["requires"])
        self.assertEqual("1.6.1", distribution_version("mkdocs"))
        self.assertEqual("3.81.0", distribution_version("latex2mathml"))

    def test_wrong_mkdocs_version_fails_before_documentation_build(self) -> None:
        versions = {"mkdocs": "1.7.0", "latex2mathml": "3.81.0"}
        with tempfile.TemporaryDirectory() as temporary, patch(
            "panelsolver.docs_site.distribution_version",
            side_effect=versions.__getitem__,
        ), self.assertRaisesRegex(
            RuntimeError,
            r"Offline documentation requires audited MkDocs 1\.6\.1; found 1\.7\.0\.",
        ):
            build_documentation_site(ROOT, Path(temporary) / "site")

    def test_wrong_latex2mathml_version_fails_before_documentation_build(self) -> None:
        versions = {"mkdocs": "1.6.1", "latex2mathml": "3.82.0"}
        with tempfile.TemporaryDirectory() as temporary, patch(
            "panelsolver.docs_site.distribution_version",
            side_effect=versions.__getitem__,
        ), self.assertRaisesRegex(
            RuntimeError,
            r"Offline documentation requires audited latex2mathml 3\.81\.0; "
            r"found 3\.82\.0\.",
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
                with self.subTest(stylesheet=css.relative_to(self.site), resource=value):
                    split = urlsplit(value)
                    self.assertEqual("", split.scheme)
                    self.assertEqual("", split.netloc)
                    self.assertTrue((css.parent / unquote(split.path)).is_file())

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
