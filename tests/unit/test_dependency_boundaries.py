import ast
import subprocess
import sys
import unittest
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).parents[2] / "src"


def module_name(path: Path) -> str:
    relative = path.relative_to(SRC_ROOT).with_suffix("")
    parts = relative.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def production_modules() -> dict[str, Path]:
    return {module_name(path): path for path in sorted(SRC_ROOT.rglob("*.py"))}


def _resolved_from_base(current: str, node: ast.ImportFrom) -> str:
    if not node.level:
        return node.module or ""
    package_path = SRC_ROOT / current.replace(".", "/") / "__init__.py"
    package = current if package_path.is_file() else current.rpartition(".")[0]
    parts = package.split(".") if package else []
    keep = max(len(parts) - (node.level - 1), 0)
    return ".".join((*parts[:keep], *((node.module or "").split("."))))


def imported_names(path: Path, current: str) -> set[str]:
    imports: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _resolved_from_base(current, node).rstrip(".")
            if base:
                imports.add(base)
            imports.update(
                f"{base}.{alias.name}" if base else alias.name
                for alias in node.names
                if alias.name != "*"
            )
    return imports


def internal_dependency_graph() -> dict[str, set[str]]:
    modules = production_modules()
    graph = {name: set() for name in modules}
    for current, path in modules.items():
        for imported in imported_names(path, current):
            parts = imported.split(".")
            candidates = (".".join(parts[:end]) for end in range(len(parts), 0, -1))
            target = next((item for item in candidates if item in modules), None)
            if target is not None:
                graph[current].add(target)
    return graph


def find_cycle(graph: dict[str, set[str]]) -> tuple[str, ...] | None:
    active: list[str] = []
    active_index: dict[str, int] = {}
    visited: set[str] = set()

    def visit(node: str) -> tuple[str, ...] | None:
        if node in active_index:
            start = active_index[node]
            return (*active[start:], node)
        if node in visited:
            return None
        active_index[node] = len(active)
        active.append(node)
        for target in sorted(graph[node]):
            if cycle := visit(target):
                return cycle
        active.pop()
        active_index.pop(node)
        visited.add(node)
        return None

    for node in sorted(graph):
        if cycle := visit(node):
            return cycle
    return None


def _matches(name: str, prefixes: tuple[str, ...]) -> bool:
    return any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes)


class DependencyBoundaryTests(unittest.TestCase):
    def assert_edges_avoid(
        self,
        sources: tuple[str, ...],
        forbidden: tuple[str, ...],
    ) -> None:
        violations = [
            f"{source} -> {target}"
            for source, targets in internal_dependency_graph().items()
            if _matches(source, sources)
            for target in sorted(targets)
            if _matches(target, forbidden)
        ]
        self.assertEqual(
            [],
            violations,
            "Forbidden dependencies:\n" + "\n".join(violations),
        )

    def test_complete_internal_graph_has_no_cycles_or_self_loops(self) -> None:
        graph = internal_dependency_graph()
        self.assertEqual(
            [],
            sorted(node for node, edges in graph.items() if node in edges),
        )
        cycle = find_cycle(graph)
        self.assertIsNone(
            cycle, "Internal dependency cycle: " + " -> ".join(cycle or ())
        )

    def test_core_has_no_product_environment_identity_or_environment_reads(
        self,
    ) -> None:
        prohibited = (
            "FMFSOLVER_",
            "NEWTSOLVER_",
            "PANELSOLVER_",
            "legacy_env_prefix",
            "os.environ",
            "os.getenv",
        )
        violations = [
            f"{path.relative_to(SRC_ROOT)}: {token}"
            for path in sorted((SRC_ROOT / "panelsolver" / "core").rglob("*.py"))
            for token in prohibited
            if token in path.read_text(encoding="utf-8")
        ]
        self.assertEqual([], violations)

    def test_every_shared_layer_obeys_documented_inward_direction(self) -> None:
        self.assert_edges_avoid(
            ("panelsolver.core",),
            ("panelsolver.models", "panelsolver.app"),
        )
        self.assert_edges_avoid(
            ("panelsolver.models",),
            ("panelsolver.app",),
        )

    @pytest.mark.slow
    def test_canonical_cli_import_has_no_removed_product_packages(self) -> None:
        code = (
            "import importlib.util; import panelsolver.cli; "
            "assert importlib.util.find_spec('fmfsolver') is None; "
            "assert importlib.util.find_spec('newtsolver') is None; "
            "assert importlib.util.find_spec('panelsolver._compat') is None"
        )
        subprocess.run([sys.executable, "-c", code], check=True)

    @pytest.mark.slow
    def test_canonical_domain_composition_uses_only_current_identities(self) -> None:
        code = (
            "from panelsolver.domains.fmf import CANONICAL_CLI_POLICY as f_cli, "
            "gui_spec as f_gui; "
            "from panelsolver.domains.hypersonic import "
            "CANONICAL_CLI_POLICY as h_cli, gui_spec as h_gui; "
            "assert f_cli.program == 'panelsolver fmf'; "
            "assert h_cli.program == 'panelsolver hypersonic'; "
            "assert f_gui().window_title == 'Panel Solver — FMF'; "
            "assert h_gui().window_title == 'Panel Solver — Hypersonic'"
        )
        subprocess.run([sys.executable, "-c", code], check=True)

    def test_models_do_not_own_filesystem_or_execution_infrastructure(self) -> None:
        prohibited = (
            "os",
            "pathlib",
            "shutil",
            "tempfile",
            "panelsolver.app",
        )
        violations: list[str] = []
        for current, path in production_modules().items():
            if not _matches(current, ("panelsolver.models",)):
                continue
            for imported in sorted(imported_names(path, current)):
                if _matches(imported, prohibited):
                    violations.append(f"{current} -> {imported}")
        self.assertEqual(
            [],
            violations,
            "Model infrastructure imports:\n" + "\n".join(violations),
        )

    def test_gui_implementation_does_not_import_physical_models(self) -> None:
        gui_modules = (
            "panelsolver.app.cases_panel",
            "panelsolver.app.gui_bootstrap",
            "panelsolver.app.main_window",
            "panelsolver.app.run_lifecycle",
            "panelsolver.app.solver_spec",
            "panelsolver.app.viewer",
            "panelsolver.app.viewer_data",
        )
        self.assert_edges_avoid(
            gui_modules,
            ("panelsolver.models",),
        )


if __name__ == "__main__":
    unittest.main()
