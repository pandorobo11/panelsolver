"""Build current case tables from read-only Phase 1 input evidence."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from panelsolver.app.csv_writer import CSV_ENCODING


def read_current_cases(
    reader: Callable[[str | Path], pd.DataFrame],
    historical_path: str | Path,
) -> pd.DataFrame:
    """Read a Phase 1 CSV after removing only the retired input fields."""
    source = Path(historical_path)
    frame = pd.read_csv(source, encoding=CSV_ENCODING)
    frame = frame.drop(columns=["save_npz_on", "out_dir"])
    frame["stl_path"] = frame["stl_path"].map(
        lambda value: ";".join(
            str((source.parent / token.strip()).resolve())
            for token in str(value).split(";")
        )
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        current_path = Path(temp_dir) / source.name
        frame.to_csv(current_path, index=False, encoding=CSV_ENCODING)
        return reader(current_path)
