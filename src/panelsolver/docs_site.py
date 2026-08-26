"""Build and resolve the offline documentation bundled with Panel Solver."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from contextlib import ExitStack
from importlib import resources
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Self

_AUDITED_DOCUMENTATION_BUILD_DEPENDENCIES = (
    ("mkdocs", "MkDocs", "1.6.1"),
    ("latex2mathml", "latex2mathml", "3.81.0"),
)


class DocumentationSiteError(RuntimeError):
    """The packaged or editable-checkout documentation cannot be resolved."""


def validate_documentation_page(value: object) -> str:
    """Return one safe wheel-relative HTML page path."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("documentation page must be a non-empty string")
    text = value.strip()
    if "\\" in text:
        raise ValueError("documentation page must use forward slashes")
    page = PurePosixPath(text)
    if (
        page.is_absolute()
        or PureWindowsPath(text).is_absolute()
        or any(part in {".", ".."} for part in page.parts)
    ):
        raise ValueError("documentation page must be a safe relative path")
    if str(page) != text or page.suffix != ".html":
        raise ValueError("documentation page must be a normalized .html path")
    return text


def build_documentation_site(project_root: Path, site_dir: Path) -> None:
    """Build the strict offline site without leaving a partial destination."""
    _verify_audited_build_dependencies()
    try:
        from mkdocs.commands.build import build
        from mkdocs.config import load_config
    except ImportError as exc:
        raise RuntimeError(
            "Building Panel Solver documentation requires the docs dependency group. "
            "Run: uv sync --locked --group docs"
        ) from exc

    project_root = Path(project_root).resolve()
    site_dir = Path(site_dir).resolve()
    site_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="panelsolver-mkdocs-",
        dir=site_dir.parent,
    ) as temporary:
        staged_site = Path(temporary) / "site"
        build_module_root = str(project_root / "src")
        sys.path.insert(0, build_module_root)
        try:
            config = load_config(config_file=str(project_root / "mkdocs.yml"))
            config["docs_dir"] = str(project_root / "docs")
            config["site_dir"] = str(staged_site)
            config["strict"] = True
            previous_epoch = os.environ.get("SOURCE_DATE_EPOCH")
            os.environ["SOURCE_DATE_EPOCH"] = "0"
            try:
                build(config)
            finally:
                if previous_epoch is None:
                    os.environ.pop("SOURCE_DATE_EPOCH", None)
                else:
                    os.environ["SOURCE_DATE_EPOCH"] = previous_epoch
        finally:
            sys.path.remove(build_module_root)
        if not (staged_site / "index.html").is_file():
            raise RuntimeError("MkDocs did not generate index.html")
        # MkDocs' generic 404 page uses root-relative assets that are meaningful
        # only when served over HTTP, not when opened from a file:// archive.
        (staged_site / "404.html").unlink(missing_ok=True)
        for legal_name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            shutil.copyfile(project_root / legal_name, staged_site / legal_name)
        shutil.copytree(
            project_root / "THIRD_PARTY_LICENSES",
            staged_site / "THIRD_PARTY_LICENSES",
        )
        if site_dir.exists():
            shutil.rmtree(site_dir)
        shutil.copytree(staged_site, site_dir)


def _verify_audited_build_dependencies() -> None:
    for (
        distribution,
        display_name,
        expected,
    ) in _AUDITED_DOCUMENTATION_BUILD_DEPENDENCIES:
        try:
            actual = distribution_version(distribution)
        except PackageNotFoundError:
            actual = "not installed"
        if actual != expected:
            raise RuntimeError(
                f"Offline documentation requires audited {display_name} "
                f"{expected}; found {actual}."
            )


def _editable_project_root() -> Path | None:
    package_dir = Path(__file__).resolve().parent
    if package_dir.name != "panelsolver" or package_dir.parent.name != "src":
        return None
    project_root = package_dir.parent.parent
    if (
        (project_root / "pyproject.toml").is_file()
        and (project_root / "mkdocs.yml").is_file()
        and (project_root / "docs").is_dir()
    ):
        return project_root
    return None


class DocumentationSite:
    """Keep packaged or temporary documentation resources alive for a GUI."""

    def __init__(self) -> None:
        self._resources = ExitStack()
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self._root: Path | None = None

    def resolve(self, page: str = "index.html") -> Path:
        page = validate_documentation_page(page)
        target = self._resolve_root().joinpath(*PurePosixPath(page).parts)
        if not target.is_file():
            raise DocumentationSiteError(
                f"Bundled documentation page was not found: {page}"
            )
        return target

    def _resolve_root(self) -> Path:
        if self._root is not None:
            return self._root
        packaged = resources.files("panelsolver").joinpath("_docs_site")
        try:
            candidate: Path | None = Path(
                self._resources.enter_context(resources.as_file(packaged))
            )
        except (FileNotFoundError, ModuleNotFoundError, NotADirectoryError):
            candidate = None
        if (
            candidate is not None
            and candidate.is_dir()
            and (candidate / "index.html").is_file()
        ):
            self._root = candidate
            return candidate

        project_root = _editable_project_root()
        if project_root is None:
            self.close()
            raise DocumentationSiteError(
                "Bundled Panel Solver documentation was not found. "
                "Reinstall the panelsolver wheel."
            )
        self._temporary = tempfile.TemporaryDirectory(prefix="panelsolver-docs-")
        candidate = Path(self._temporary.name) / "site"
        try:
            build_documentation_site(project_root, candidate)
        except Exception as exc:
            self.close()
            raise DocumentationSiteError(
                f"Could not build documentation from the editable checkout: {exc}"
            ) from exc
        self._root = candidate
        return candidate

    def close(self) -> None:
        self._root = None
        self._resources.close()
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


__all__ = (
    "DocumentationSite",
    "DocumentationSiteError",
    "build_documentation_site",
    "validate_documentation_page",
)
