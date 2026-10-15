"""Sibling temporary files for atomic output replacement."""

from __future__ import annotations

import os
import secrets
import tempfile
from pathlib import Path

_POSIX_FLAGS = (
    os.O_RDWR
    | os.O_CREAT
    | os.O_EXCL
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_MAX_ATTEMPTS = 10_000


def create_replacement_temp(
    directory: Path,
    *,
    prefix: str,
    suffix: str,
) -> tuple[int, Path]:
    """Exclusively create a temporary file to be renamed over an output.

    ``tempfile.mkstemp`` always uses mode 0600, which ``os.replace`` would carry
    to the final output. On POSIX the file is instead created with mode 0666 so
    the kernel applies the process umask, matching a newly created
    ``open(path, "w")`` file without changing the process-wide umask. Windows
    keeps ``tempfile.mkstemp`` unchanged.
    """
    if os.name != "posix":
        descriptor, name = tempfile.mkstemp(dir=directory, prefix=prefix, suffix=suffix)
        return descriptor, Path(name)
    for _ in range(_MAX_ATTEMPTS):
        candidate = directory / f"{prefix}{secrets.token_hex(8)}{suffix}"
        try:
            descriptor = os.open(candidate, _POSIX_FLAGS, 0o666)
        except FileExistsError:
            continue
        return descriptor, candidate
    raise FileExistsError(
        f"No usable temporary name found in {directory} for prefix {prefix!r}"
    )


__all__ = ("create_replacement_temp",)
