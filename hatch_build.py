"""Hatch hook that bundles the generated offline documentation in wheels."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """Build documentation and bundle GUI-accessible example resources."""

    def initialize(self, version: str, build_data: dict) -> None:
        del version
        if self.target_name != "wheel":
            return
        root = Path(self.root)
        site_dir = root / ".hatch-build" / "panelsolver-docs-site"
        builder = _load_module(root / "src" / "panelsolver" / "docs_site.py")
        builder.build_documentation_site(root, site_dir)
        force_include = build_data.setdefault("force_include", {})
        force_include[str(site_dir)] = "panelsolver/_docs_site"
        examples_dir = root / "examples"
        for source in sorted(examples_dir.rglob("*")):
            relative = source.relative_to(examples_dir)
            if (
                not source.is_file()
                or "outputs" in relative.parts
                or "__pycache__" in relative.parts
                or source.suffix.lower() in {".npz", ".xls"}
            ):
                continue
            force_include[str(source)] = f"panelsolver/_examples/{relative.as_posix()}"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(
        "panelsolver_build_docs_site",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load documentation builder: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
