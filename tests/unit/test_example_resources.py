from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from panelsolver.app import ExampleLibrary
from panelsolver.app.examples import ExampleDefinition
from panelsolver.app.sectional_definitions import read_sectional_definitions
from panelsolver.domains import fmf, hypersonic


class ExampleResourceTests(unittest.TestCase):
    def test_every_menu_example_copies_with_loadable_relative_geometry(self) -> None:
        library = ExampleLibrary()
        domains = (
            (fmf, "fmf"),
            (hypersonic, "hypersonic"),
        )
        with tempfile.TemporaryDirectory(prefix="gui_examples_") as directory:
            base = Path(directory)
            for module, domain in domains:
                for example in module.gui_spec().examples:
                    with self.subTest(domain=domain, example=example.label):
                        destination = base / domain / Path(example.input_resource).stem
                        input_path = library.copy_example(example, destination)
                        self.assertTrue(input_path.is_file())
                        if example.sectional_definition_resource is not None:
                            definitions = read_sectional_definitions(
                                destination / example.sectional_definition_resource
                            )
                            self.assertEqual(3, len(definitions))
                        frame = module.read_cases(input_path)
                        self.assertGreater(len(frame), 0)
                        resolved_destination = destination.resolve(strict=False)
                        for raw in frame["stl_path"]:
                            for stl_path in str(raw).split(";"):
                                self.assertTrue(Path(stl_path).is_file())
                                self.assertTrue(
                                    Path(stl_path)
                                    .resolve(strict=False)
                                    .is_relative_to(resolved_destination)
                                )

    def test_copy_never_overwrites_a_modified_workspace_file(self) -> None:
        example = fmf.gui_spec().examples[0]
        with tempfile.TemporaryDirectory(prefix="gui_example_collision_") as directory:
            destination = Path(directory)
            library = ExampleLibrary()
            input_path = library.copy_example(example, destination)
            input_path.write_text("user edit\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "overwrite"):
                library.copy_example(example, destination)

    def test_sectional_resource_validation_and_unique_input_combinations(self):
        for resource in ("../sections.csv", "/sections.csv", "sections.txt"):
            with self.subTest(resource=resource), self.assertRaises(ValueError):
                ExampleDefinition(
                    "Sections", "fmf/basic.csv", sectional_definition_resource=resource
                )
        with self.assertRaises(ValueError):
            ExampleDefinition(
                "Sections", "fmf/basic.csv", ("sections.csv",), "sections.csv"
            )
        spec = fmf.gui_spec()
        with self.assertRaises(ValueError):
            replace(
                spec,
                examples=(*spec.examples, replace(spec.examples[0], label="Duplicate")),
            )


if __name__ == "__main__":
    unittest.main()
