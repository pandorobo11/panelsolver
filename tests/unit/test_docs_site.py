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
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(str(values["id"]))
        if tag == "a" and values.get("href"):
            self.links.append(str(values["href"]))
        if tag in {"img", "script", "source"} and values.get("src"):
            self.resources.append(str(values["src"]))
        if (
            tag == "link"
            and "stylesheet" in str(values.get("rel", ""))
            and values.get("href")
        ):
            self.resources.append(str(values["href"]))


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

    def test_readthedocs_theme_configuration_and_assets_are_complete(self) -> None:
        mkdocs_config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
        self.assertRegex(mkdocs_config, r"theme:\n  name: readthedocs\n  highlightjs: false")
        self.assertRegex(mkdocs_config, r"(?m)^use_directory_urls: false$")
        self.assertRegex(mkdocs_config, r"(?m)^plugins: \[\]$")
        for relative in (
            "css/theme.css",
            "css/theme_extra.css",
            "img/favicon.ico",
            "js/html5shiv.min.js",
            "js/jquery-3.6.0.min.js",
            "js/theme.js",
            "js/theme_extra.js",
            "assets/stylesheets/panelsolver-docs.css",
            "assets/javascripts/panelsolver-docs.js",
            "css/fonts/Roboto-Slab-Bold.woff",
            "css/fonts/Roboto-Slab-Bold.woff2",
            "css/fonts/Roboto-Slab-Regular.woff",
            "css/fonts/Roboto-Slab-Regular.woff2",
            "css/fonts/fontawesome-webfont.eot",
            "css/fonts/fontawesome-webfont.svg",
            "css/fonts/fontawesome-webfont.ttf",
            "css/fonts/fontawesome-webfont.woff",
            "css/fonts/fontawesome-webfont.woff2",
            "css/fonts/lato-bold-italic.woff",
            "css/fonts/lato-bold-italic.woff2",
            "css/fonts/lato-bold.woff",
            "css/fonts/lato-bold.woff2",
            "css/fonts/lato-normal-italic.woff",
            "css/fonts/lato-normal-italic.woff2",
            "css/fonts/lato-normal.woff",
            "css/fonts/lato-normal.woff2",
        ):
            with self.subTest(relative=relative):
                self.assertTrue((self.site / relative).is_file())
        self.assertFalse((self.site / "404.html").exists())
        self.assertFalse((self.site / "search").exists())
        self.assertFalse((self.site / "search.html").exists())
        asset_names = {path.name.casefold() for path in self.site.rglob("*")}
        self.assertFalse(any("highlight" in name for name in asset_names))

    def test_tables_have_rtd_runtime_hooks_and_responsive_local_styles(self) -> None:
        representative_pages = (
            "reference/fmf-input.html",
            "reference/hypersonic-input.html",
            "reference/output-formats.html",
            "user-guide/outputs.html",
        )
        expected_scripts = (
            "js/jquery-3.6.0.min.js",
            "js/theme_extra.js",
            "js/theme.js",
            "assets/javascripts/panelsolver-docs.js",
        )
        for relative in representative_pages:
            html = (self.site / relative).read_text(encoding="utf-8")
            with self.subTest(relative=relative):
                positions = [html.index(f'src="../{script}"') for script in expected_scripts]
                self.assertEqual(sorted(positions), positions)
                self.assertLess(
                    positions[-1],
                    html.index("SphinxRtdTheme.Navigation.enable("),
                )
                self.assertNotIn("search.html", html)
                if relative.endswith("-input.html"):
                    self.assertIn("<table>", html)
        theme_extra_js = (self.site / "js/theme_extra.js").read_text(encoding="utf-8")
        theme_js = (self.site / "js/theme.js").read_text(encoding="utf-8")
        theme_extra_css = (self.site / "css/theme_extra.css").read_text(
            encoding="utf-8"
        )
        project_css = (
            self.site / "assets/stylesheets/panelsolver-docs.css"
        ).read_text(encoding="utf-8")
        project_js = (
            self.site / "assets/javascripts/panelsolver-docs.js"
        ).read_text(encoding="utf-8")
        self.assertIn("$('div.rst-content table').addClass('docutils')", theme_extra_js)
        self.assertIn("<div class='wy-table-responsive'>", theme_js)
        self.assertRegex(
            theme_extra_css,
            r"\.rst-content \.section \.docutils \{[^}]*overflow: auto;[^}]*display: block;",
        )
        self.assertIn("border: 1px solid #e1e4e5 !important", theme_extra_css)
        self.assertRegex(
            project_css,
            r"\.wy-table-responsive \{[^}]*width: 100%;",
        )
        self.assertRegex(
            project_css,
            r"\.wy-table-responsive > table\.docutils \{[^}]*"
            r"min-width: max-content;[^}]*width: 100%;",
        )
        self.assertRegex(
            project_css,
            r'\.rst-content math\[display="block"\] \{[^}]*'
            r"max-width: 100%;[^}]*overflow-x: auto;",
        )
        for expected in (
            "window.SphinxRtdTheme",
            "window.SphinxRtdTheme.Navigation",
            "nav.hashChange = function ()",
            "var self = this",
            "self.linkScroll = true",
            'self.win.one("hashchange"',
            "self.linkScroll = false",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, project_js)
        self.assertNotRegex(project_js, r"(?:https?:)?//")

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

    def test_generated_html_has_no_external_script_font_or_stylesheet_dependency(self) -> None:
        forbidden = re.compile(
            r"(?:\bsrc|<link\b[^>]*\bhref)=[\"'](?:https?:)?//",
            flags=re.IGNORECASE,
        )
        for html in self.site.rglob("*.html"):
            text = html.read_text(encoding="utf-8")
            for match in forbidden.finditer(text):
                with self.subTest(page=html.relative_to(self.site), value=match.group()):
                    self.fail(f"external executable or style resource: {match.group()}")
            self.assertNotIn("cdnjs.cloudflare.com", text)
            self.assertNotIn("highlight.js", text.casefold())
            self.assertNotIn("mathjax", text.casefold())
            self.assertNotIn("katex", text.casefold())

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
