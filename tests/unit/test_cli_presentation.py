from __future__ import annotations

import io
import os
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from panelsolver.app.cli import _run_parsed_cli, build_parser
from panelsolver.app.cli_presentation import CliPresentation, use_rich_ui
from panelsolver.app.output_status import (
    OutputFailuresError,
    OutputIssue,
    OutputKind,
    OutputPhase,
)
from panelsolver.domains.fmf import CLI_POLICY


class _Stream(io.StringIO):
    def __init__(self, *, tty: bool) -> None:
        super().__init__()
        self.tty = tty

    def isatty(self) -> bool:
        return self.tty


class CliPresentationTests(unittest.TestCase):
    def test_mode_selection_requires_tty_and_honors_plain_and_ci(self) -> None:
        self.assertFalse(use_rich_ui(plain=False, stream=_Stream(tty=False)))
        self.assertFalse(use_rich_ui(plain=True, stream=_Stream(tty=True)))
        with patch.dict(os.environ, {"CI": "true"}):
            self.assertFalse(use_rich_ui(plain=False, stream=_Stream(tty=True)))
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(use_rich_ui(plain=False, stream=_Stream(tty=True)))

    def test_plain_output_preserves_machine_readable_runtime_messages(self) -> None:
        stream = _Stream(tty=False)
        display = CliPresentation(rich_ui=False, verbose=False, stream=stream)
        display.start(
            domain="fmf",
            input_path=Path("cases.csv"),
            output_path=Path("result.csv"),
            cases=2,
            workers=1,
        )
        display.log("[RUN] (1/2) case_id=one")
        display.log("[INFO] Ray backend: rtree")
        display.update(1, 2)
        display.finish(Path("result.csv"))
        output = stream.getvalue()
        self.assertIn("[RUN] cases=2 workers=1 input=cases.csv", output)
        self.assertIn("[RUN] (1/2) case_id=one", output)
        self.assertIn("[INFO] Ray backend: rtree", output)
        self.assertIn("[OK] Wrote results: result.csv", output)

    def test_rich_output_suppresses_case_logs_unless_verbose(self) -> None:
        for verbose, expected in ((False, False), (True, True)):
            with self.subTest(verbose=verbose):
                stream = _Stream(tty=True)
                display = CliPresentation(rich_ui=True, verbose=verbose, stream=stream)
                display.log("[RUN] (1/1) case_id=one")
                display.log("[WARN] mesh warning")
                output = stream.getvalue()
                self.assertEqual(expected, "case_id=one" in output)
                self.assertIn("WARN", output)
                self.assertIn("mesh warning", output)

    def test_rich_output_treats_external_values_as_literal_text(self) -> None:
        stream = _Stream(tty=True)
        display = CliPresentation(rich_ui=True, verbose=True, stream=stream)
        input_path = Path("cases[1].csv")
        output_path = Path("[/]/results[2].csv")
        display.start(
            domain="[red]fmf[/]",
            input_path=input_path,
            output_path=output_path,
            cases=1,
            workers=1,
        )
        display.log("[WARN] literal [red]log[/]")
        display.finish(output_path)

        output = stream.getvalue()
        self.assertIn("[red]fmf[/]", output)
        self.assertIn(str(input_path), output)
        self.assertGreaterEqual(output.count(str(output_path)), 2)
        self.assertIn("literal [red]log[/]", output)

    def test_cli_passes_runtime_arguments_and_progress_callback_unchanged(self) -> None:
        policy = replace(
            CLI_POLICY,
            read_cases=lambda _path: pd.DataFrame([{"case_id": "one"}]),
            validate_output_path=lambda *_args: Path("result.csv"),
        )
        parser = build_parser(policy)
        args = parser.parse_args(["--input", "cases.csv", "--workers", "3", "--plain"])
        with patch(
            "panelsolver.app.cli.run_and_write_product_cases",
            return_value=SimpleNamespace(
                output_issues=(),
                summary_csv_saved=True,
            ),
        ) as run:
            self.assertEqual(0, _run_parsed_cli(policy, args))
        self.assertEqual(3, run.call_args.kwargs["workers"])
        self.assertTrue(callable(run.call_args.kwargs["progress_cb"]))
        self.assertTrue(callable(run.call_args.kwargs["logfn"]))

    def test_cli_keeps_nonzero_semantics_for_structured_output_failures(self) -> None:
        policy = replace(
            CLI_POLICY,
            read_cases=lambda _path: pd.DataFrame([{"case_id": "one"}]),
            validate_output_path=lambda *_args: Path("result.csv"),
        )
        args = build_parser(policy).parse_args(["--input", "cases.csv", "--plain"])
        issue = OutputIssue(
            OutputKind.VTP,
            OutputPhase.WRITE,
            "one.vtp",
            "permission denied",
            "one",
        )
        with (
            patch(
                "panelsolver.app.cli.run_and_write_product_cases",
                return_value=SimpleNamespace(output_issues=(issue,)),
            ),
            self.assertRaises(OutputFailuresError) as caught,
        ):
            _run_parsed_cli(policy, args)
        self.assertEqual((issue,), caught.exception.issues)


if __name__ == "__main__":
    unittest.main()
