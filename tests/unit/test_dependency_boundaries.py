import ast
import unittest
from pathlib import Path

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


def internal_dependency_graph(imports: dict[str, set[str]]) -> dict[str, set[str]]:
    graph = {name: set() for name in imports}
    for current, targets in imports.items():
        for imported in targets:
            parts = imported.split(".")
            candidates = (".".join(parts[:end]) for end in range(len(parts), 0, -1))
            target = next((item for item in candidates if item in imports), None)
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


def environment_dependencies(tree: ast.AST) -> set[str]:
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name if alias.asname else alias.name.split(".")[0]
                aliases[alias.asname or name] = name
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"os.{alias.name}"

    def qualified_name(node):
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return f"{qualified_name(node.value)}.{node.attr}"
        return ""

    # Inspect executable names, including import aliases, rather than matching
    # comments/docstrings that explain why core must not read the environment.
    return {
        name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Name, ast.Attribute))
        if _matches(
            name := qualified_name(node),
            ("os.environ", "os.environb", "os.getenv", "os.getenvb"),
        )
    }


class DependencyBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.imports = {
            name: imported_names(path, name)
            for name, path in production_modules().items()
        }
        cls.graph = internal_dependency_graph(cls.imports)

    def assert_edges_avoid(
        self,
        sources: tuple[str, ...],
        forbidden: tuple[str, ...],
    ) -> None:
        violations = [
            f"{source} -> {target}"
            for source, targets in self.imports.items()
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
        graph = self.graph
        self.assertEqual(
            [],
            sorted(node for node, edges in graph.items() if node in edges),
        )
        cycle = find_cycle(graph)
        self.assertIsNone(
            cycle, "Internal dependency cycle: " + " -> ".join(cycle or ())
        )

    def test_core_does_not_read_process_environment(self) -> None:
        violations = [
            f"{path.relative_to(SRC_ROOT)}: {token}"
            for path in sorted((SRC_ROOT / "panelsolver" / "core").rglob("*.py"))
            for token in sorted(
                environment_dependencies(ast.parse(path.read_text(encoding="utf-8")))
            )
        ]
        self.assertEqual([], violations)

    def test_every_shared_layer_obeys_documented_inward_direction(self) -> None:
        self.assert_edges_avoid(
            ("panelsolver.core",),
            (
                "panelsolver.models",
                "panelsolver.app",
                "panelsolver.domains",
                "panelsolver.gui",
                "PySide6",
                "pyvistaqt",
            ),
        )
        self.assert_edges_avoid(
            ("panelsolver.models",),
            (
                "panelsolver.app",
                "panelsolver.domains",
                "panelsolver.gui",
                "PySide6",
                "pyvistaqt",
            ),
        )

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
