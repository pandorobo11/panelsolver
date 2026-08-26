from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fmfsolver.app.cli_app import _CLI_POLICY as FMF_CLI_POLICY
from fmfsolver.app.cli_app import main as fmf_main
from newtsolver.app.cli_app import _CLI_POLICY as NEWT_CLI_POLICY
from newtsolver.app.cli_app import main as newt_main
from panelsolver.app.cli import build_parser as build_product_parser
from panelsolver.app.cli import parse_case_ids
from panelsolver.app.csv_writer import CSV_ENCODING
from panelsolver.app.runtime import DEFAULT_CHECKPOINT_CASES
from panelsolver.cli import build_parser as build_canonical_parser
from panelsolver.cli import main as canonical_main
from panelsolver.domains.fmf import read_cases as read_fmf_cases
from panelsolver.domains.hypersonic import read_cases as read_newt_cases
from tests.current_case_fixtures import read_current_cases

INPUTS = Path(__file__).parents[1] / "fixtures" / "phase1" / "inputs"


def build_fmf_parser():
    return build_product_parser(FMF_CLI_POLICY)


def build_newt_parser():
    return build_product_parser(NEWT_CLI_POLICY)


class CliCompatibilityTests(unittest.TestCase):
    def test_canonical_help_names_flow_domains_and_delegated_program(self) -> None:
        with patch.dict(os.environ, {"COLUMNS": "80"}):
            help_text = build_canonical_parser().format_help()
            self.assertIn("usage: panelsolver", help_text.casefold())
            self.assertIn("fmf", help_text)
            self.assertIn("hypersonic", help_text)
            for domain, description in (
                ("fmf", "Sentman free-molecular-flow model"),
                ("hypersonic", "hypersonic panel models"),
            ):
                with self.subTest(domain=domain):
                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        with self.assertRaises(SystemExit) as caught:
                            canonical_main([domain, "--help"])
                    self.assertEqual(0, caught.exception.code)
                    delegated = stdout.getvalue()
                    self.assertIn(f"usage: panelsolver {domain}", delegated.casefold())
                    self.assertIn(description, delegated)
                    self.assertIn("Input cases file (.csv/.xlsx/.xlsm)", delegated)
                    self.assertNotIn(".xls)", delegated)

    def test_help_and_explicit_empty_cases_use_common_cardinality(self) -> None:
        with patch.dict(os.environ, {"COLUMNS": "80"}):
            for program, description, builder in (
                (
                    "fmfsolver-cli",
                    "Run FMF solver from CSV/XLSX/XLSM input without GUI.",
                    build_fmf_parser,
                ),
                (
                    "newtsolver-cli",
                    "Run newtsolver from CSV/XLSX/XLSM input without GUI.",
                    build_newt_parser,
                ),
            ):
                with self.subTest(program=program):
                    help_text = builder().format_help()
                    self.assertIn(f"usage: {program}", help_text.casefold())
                    self.assertIn(description, help_text)
                    self.assertIn("Input cases file (.csv/.xlsx/.xlsm)", help_text)
                    self.assertNotIn(".xls)", help_text)
                    self.assertIn("--cases CASES [CASES ...]", help_text)
                    self.assertIn("--checkpoint-every-cases", help_text)
                    self.assertIn("--verbose", help_text)
                    self.assertIn("--plain", help_text)
                    self.assertIn("--debug", help_text)
                    self.assertNotIn("--flush-every-cases", help_text)
                    parsed = builder().parse_args(["--input", "cases.csv"])
                    self.assertEqual(
                        DEFAULT_CHECKPOINT_CASES,
                        parsed.checkpoint_every_cases,
                    )
                    with contextlib.redirect_stderr(io.StringIO()):
                        with self.assertRaises(SystemExit) as caught:
                            builder().parse_args(["--input", "cases.csv", "--cases"])
                    self.assertEqual(2, caught.exception.code)

    def test_case_selector_keeps_comma_space_and_empty_contract(self) -> None:
        self.assertEqual({"a", "b", "c"}, parse_case_ids(["a,b", " c "]))
        self.assertIsNone(parse_case_ids(None))
        self.assertIsNone(parse_case_ids([]))
        self.assertIsNone(parse_case_ids([" , "]))

    def test_argument_errors_and_unknown_cases_keep_exit_boundaries(self) -> None:
        for policy in (FMF_CLI_POLICY, NEWT_CLI_POLICY):
            with self.subTest(product=policy.runtime_policy.product_id):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as workers_exit:
                        parser = (
                            build_fmf_parser()
                            if policy is FMF_CLI_POLICY
                            else build_newt_parser()
                        )
                        args = parser.parse_args(["--input", "x", "--workers", "0"])
                        if args.workers < 1:
                            parser.error("--workers must be >= 1")
                self.assertEqual(2, workers_exit.exception.code)

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "cases.csv"
            frame = (
                read_current_cases(read_fmf_cases, INPUTS / "fmfsolver_cases.csv")
                .iloc[[0]]
                .copy()
            )
            frame.to_csv(input_path, index=False)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(
                    1,
                    fmf_main(
                        [
                            "--input",
                            str(input_path),
                            "--output",
                            str(input_path),
                            "--checkpoint-every-cases",
                            "0",
                        ]
                    ),
                )
            self.assertIn("Error:", stderr.getvalue())
            self.assertIn("protected path", stderr.getvalue())
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(
                    1,
                    fmf_main(
                        [
                            "--input",
                            str(input_path),
                            "--cases",
                            "missing",
                            "--checkpoint-every-cases",
                            "0",
                        ]
                    ),
                )
            self.assertIn("Unknown case_id", stderr.getvalue())

            with self.assertRaisesRegex(ValueError, "Unknown case_id"):
                fmf_main(
                    [
                        "--input",
                        str(input_path),
                        "--cases",
                        "missing",
                        "--debug",
                    ]
                )

    def test_selected_cases_retain_input_order_not_option_order(self) -> None:
        products = (
            (
                fmf_main,
                read_fmf_cases,
                "fmfsolver_cases.csv",
                ("fmf_zero_plate", "fmf_mode_b_offset"),
            ),
            (
                newt_main,
                read_newt_cases,
                "newtsolver_cases.csv",
                ("newt_zero_newtonian", "newt_modified_offset"),
            ),
        )
        for main, reader, filename, case_ids in products:
            frame = read_current_cases(reader, INPUTS / filename).iloc[[0, 1]].copy()
            with (
                self.subTest(filename=filename),
                tempfile.TemporaryDirectory() as temp_dir,
            ):
                root = Path(temp_dir)
                frame["out_dir"] = str(root / "artifacts")
                frame["save_vtp_on"] = 0
                input_path = root / "cases.csv"
                output = root / "results.csv"
                frame.to_csv(input_path, index=False)
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        0,
                        main(
                            [
                                "--input",
                                str(input_path),
                                "--output",
                                str(output),
                                "--cases",
                                f"{case_ids[1]},{case_ids[0]}",
                                "--checkpoint-every-cases",
                                "0",
                            ]
                        ),
                    )
                import pandas as pd

                summary = pd.read_csv(output, encoding=CSV_ENCODING)
                self.assertEqual(
                    list(case_ids),
                    summary.loc[summary["scope"] == "total", "case_id"].tolist(),
                )

    def test_checkpoint_option_reaches_runtime_and_old_name_is_rejected(self) -> None:
        parser = build_fmf_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                parser.parse_args(["--input", "cases.csv", "--flush-every-cases", "1"])
        self.assertEqual(2, caught.exception.code)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "cases.csv"
            output_path = root / "results.csv"
            frame = (
                read_current_cases(read_fmf_cases, INPUTS / "fmfsolver_cases.csv")
                .iloc[[0]]
                .copy()
            )
            frame["out_dir"] = str(root / "artifacts")
            frame["save_vtp_on"] = 0
            frame.to_csv(input_path, index=False)
            for value in (0, 37):
                with (
                    self.subTest(value=value),
                    patch("panelsolver.app.cli.run_and_write_product_cases") as run,
                ):
                    self.assertEqual(
                        0,
                        fmf_main(
                            [
                                "--input",
                                str(input_path),
                                "--output",
                                str(output_path),
                                "--checkpoint-every-cases",
                                str(value),
                            ]
                        ),
                    )
                    self.assertEqual(
                        value,
                        run.call_args.kwargs["checkpoint_every_cases"],
                    )
                    self.assertEqual(value > 0, run.call_args.kwargs["log_snapshots"])


if __name__ == "__main__":
    unittest.main()
