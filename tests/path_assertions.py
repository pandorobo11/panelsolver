from __future__ import annotations

import os
import unittest
from pathlib import Path


def paths_equivalent(
    first: str | os.PathLike[str],
    second: str | os.PathLike[str],
) -> bool:
    first_path = Path(first)
    second_path = Path(second)
    try:
        return os.path.samefile(first_path, second_path)
    except OSError:
        return first_path.resolve(strict=False) == second_path.resolve(strict=False)


def assert_paths_equivalent(
    test_case: unittest.TestCase,
    expected: str | os.PathLike[str],
    actual: str | os.PathLike[str],
) -> None:
    expected_path = Path(expected)
    actual_path = Path(actual)
    test_case.assertTrue(
        paths_equivalent(expected_path, actual_path),
        f"Paths are not filesystem-equivalent: {expected_path!r} != {actual_path!r}",
    )
