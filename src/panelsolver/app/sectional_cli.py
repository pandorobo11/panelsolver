"""Command boundary for shared sectional definition and batch services."""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from pathlib import Path

from rich_argparse import RichHelpFormatter

from .cli import ProductCliPolicy, parse_case_ids
from .cli_presentation import CliPresentation, use_rich_ui
from .csv_writer import validate_csv_output_path
from .sectional_batch import (
    run_sectional_cases,
    sectional_protected_paths,
    write_sectional_csv,
)
from .sectional_definitions import (
    read_sectional_definitions,
    select_sectional_definitions,
)


def build_sectional_parser(policy: ProductCliPolicy) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=f"{policy.program} sectional-loads",
        description=(
            "Integrate sectional loads for cases × definitions from a separate CSV. "
            "Axes are in STL coordinates; origins and signed bounds are metres (m). "
            "Blank start/stop selects each case's geometry range. Component IDs "
            "are the original zero-based positions in that case's STL list."
        ),
        formatter_class=RichHelpFormatter,
    )
    parser.add_argument(
        "-i", "--input", required=True, help="Case table (.csv/.xlsx/.xlsm)"
    )
    parser.add_argument(
        "-d", "--definitions", required=True, help="Sectional definition CSV"
    )
    parser.add_argument(
        "-o", "--output", required=True, help="Dedicated sectional result CSV"
    )
    parser.add_argument(
        "-j", "--workers", type=int, default=1, help="Case workers (default: 1)"
    )
    parser.add_argument(
        "--cases", nargs="+", help="Case IDs, space/comma separated (default: all)"
    )
    parser.add_argument(
        "--sections",
        nargs="+",
        help="Exact section IDs, space separated; quote labels with spaces (default: all)",
    )
    parser.add_argument(
        "--plain", action="store_true", help="Disable interactive Rich output"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Show case-level messages"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Show Python tracebacks on errors"
    )
    return parser


def run_sectional_cli(policy: ProductCliPolicy, argv: list[str] | None = None) -> int:
    parser = build_sectional_parser(policy)
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers must be >= 1")
    try:
        return _run(policy, args)
    except KeyboardInterrupt:
        print("Cancelled before batch execution.", file=sys.stderr)
        return 130
    except Exception as exc:
        if args.debug:
            raise
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _run(policy: ProductCliPolicy, args: argparse.Namespace) -> int:
    input_path = Path(args.input).expanduser().absolute()
    definition_path = Path(args.definitions).expanduser().absolute()
    # Validate the complete definition file before filtering or running physics.
    definitions = select_sectional_definitions(
        read_sectional_definitions(definition_path), args.sections
    )
    frame = policy.read_cases(input_path)
    if frame.empty:
        raise ValueError("Input file has no cases.")
    all_rows = tuple(frame.to_dict(orient="records"))
    protected = sectional_protected_paths(input_path, definition_path, all_rows)
    selected_ids = parse_case_ids(args.cases)
    if args.cases is not None and selected_ids is None:
        raise ValueError("No cases selected.")
    if selected_ids is not None:
        missing = selected_ids - set(frame["case_id"].astype(str))
        if missing:
            raise ValueError(f"Unknown case_id values: {sorted(missing)}")
        frame = frame[frame["case_id"].astype(str).isin(selected_ids)]
    rows = tuple(frame.to_dict(orient="records"))
    output = validate_csv_output_path(Path(args.output).expanduser(), protected)
    cancelled = threading.Event()
    previous_handler = signal.getsignal(signal.SIGINT)
    presentation = CliPresentation(
        rich_ui=use_rich_ui(plain=args.plain), verbose=args.verbose
    )
    # SIGINT requests normal scheduler cancellation so active cases can finish
    # and compact partial results remain available for export.
    signal.signal(signal.SIGINT, lambda _signum, _frame: cancelled.set())
    try:
        with presentation:
            presentation.start(
                domain=policy.runtime_policy.product_id,
                input_path=input_path,
                output_path=output,
                cases=len(rows),
                workers=args.workers,
            )
            result = run_sectional_cases(
                rows,
                policy.runtime_policy,
                definitions,
                workers=args.workers,
                logfn=presentation.log,
                progress_cb=presentation.update,
                cancel_cb=cancelled.is_set,
            )
            if result.status != "completed":
                print(
                    f"{result.status.capitalize()}: {result.completed_pairs}/"
                    f"{result.requested_pairs} case × section pairs completed.",
                    file=sys.stderr,
                )
                for error in result.errors:
                    print(
                        f"case_id={error.case_id!r} section_id={error.section_id!r}: "
                        f"{error.message}",
                        file=sys.stderr,
                    )
            if result.csv is not None:
                try:
                    write_sectional_csv(output, result, protected)
                except Exception as exc:
                    raise OSError(f"Sectional CSV save failed: {exc}") from exc
                if result.status == "completed":
                    presentation.finish(output)
                else:
                    print(f"Wrote partial sectional results: {output}", file=sys.stderr)
            elif result.status != "completed":
                print(
                    "No completed results to save; output was not changed.",
                    file=sys.stderr,
                )
    finally:
        signal.signal(signal.SIGINT, previous_handler)
    return {"completed": 0, "cancelled": 130, "failed": 1}[result.status]
